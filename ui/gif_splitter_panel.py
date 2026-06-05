"""
GIF拆分工具面板

将GIF动图拆分为逐帧图片序列，支持选择输出格式和自定义输出目录。
基于PySide6重写，使用信号/槽确保线程安全。
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QComboBox, QCheckBox, QProgressBar, QGroupBox,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropLineEdit
from core.base_worker import BaseWorker


# ---------- 后台工作线程 ----------

class SplitGifWorker(BaseWorker):
    """GIF拆分工作线程 — 所有耗时操作在后台线程执行"""

    def __init__(self, gif_path: str, output_dir: str, output_format: str = 'png'):
        super().__init__()
        self.gif_path = gif_path
        self.output_dir = output_dir
        self.output_format = output_format

    def run(self):
        """执行GIF拆分"""
        from PIL import Image

        try:
            if not os.path.exists(self.gif_path):
                self.signals.error.emit(f"GIF文件不存在: {self.gif_path}")
                return

            # 创建输出目录
            if not self.output_dir:
                gif_dir = os.path.dirname(self.gif_path)
                gif_name = os.path.splitext(os.path.basename(self.gif_path))[0]
                self.output_dir = os.path.join(gif_dir, f"{gif_name}_frames")
            os.makedirs(self.output_dir, exist_ok=True)

            self.signals.log.emit(f"开始拆分GIF: {os.path.basename(self.gif_path)}")

            with Image.open(self.gif_path) as img:
                n_frames = getattr(img, 'n_frames', 1)
                is_animated = getattr(img, 'is_animated', False)

                self.signals.log.emit(
                    f"GIF信息: 尺寸={img.size}, "
                    f"模式={img.mode}, 动画={is_animated}, 帧数={n_frames}"
                )

                if is_animated:
                    for i in range(n_frames):
                        if self._stop_flag:
                            self.signals.log.emit("拆分已被用户停止")
                            break

                        img.seek(i)
                        frame_path = os.path.join(
                            self.output_dir,
                            f"frame_{i:04d}.{self.output_format}"
                        )
                        # 保存当前帧
                        frame = img.copy()
                        frame.save(frame_path, format=self.output_format.upper())

                        self.signals.progress.emit(i + 1, n_frames)
                else:
                    # 静态GIF，保存单帧
                    frame = img.copy()
                    frame_path = os.path.join(
                        self.output_dir,
                        f"frame_0000.{self.output_format}"
                    )
                    frame.save(frame_path, format=self.output_format.upper())
                    self.signals.progress.emit(1, 1)
                    n_frames = 1

            self.signals.log.emit(
                f"GIF拆分完成! 共 {n_frames} 帧\n"
                f"输出目录: {self.output_dir}"
            )
            self.signals.finished.emit({
                'success': True,
                'frame_count': n_frames,
                'output_dir': self.output_dir
            })

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


# ---------- GUI面板 ----------

class GifSplitterPanel(BaseToolPanel):
    """GIF拆分工具面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gif_path: str = ""
        self.output_dir: str = ""
        self.worker: SplitGifWorker | None = None

        self._setup_ui()
        self.retranslate_ui()

    # ---------- UI构建 ----------

    def _setup_ui(self):
        """创建界面布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ---- 1. GIF文件选择 ----
        file_group = QGroupBox()
        file_layout = QGridLayout(file_group)

        file_layout.addWidget(QLabel(), 0, 0)  # 占位，retranslate_ui中填充
        self.gif_label = QLabel()
        file_layout.addWidget(self.gif_label, 0, 0)

        self.gif_entry = DragDropLineEdit(
            allowed_extensions=('.gif',))
        self.gif_entry.setPlaceholderText("选择GIF文件或拖放到此处")
        self.gif_entry.textChanged.connect(self._on_gif_path_changed)
        file_layout.addWidget(self.gif_entry, 0, 1)

        self.browse_gif_btn = QPushButton()
        self.browse_gif_btn.clicked.connect(self._select_gif)
        file_layout.addWidget(self.browse_gif_btn, 0, 2)

        # GIF信息显示
        self.gif_info_label = QLabel()
        self.gif_info_label.setStyleSheet("color: gray;")
        file_layout.addWidget(self.gif_info_label, 1, 1)

        main_layout.addWidget(file_group)

        # ---- 2. 输出设置 ----
        output_group = QGroupBox()
        output_layout = QGridLayout(output_group)

        # 输出格式
        format_label = QLabel()
        output_layout.addWidget(format_label, 0, 0)
        self.format_label = format_label

        self.format_combo = QComboBox()
        self.format_combo.addItems(['png', 'jpg', 'bmp'])
        output_layout.addWidget(self.format_combo, 0, 1)

        # 自定义输出目录
        self.custom_dir_check = QCheckBox()
        output_layout.addWidget(self.custom_dir_check, 0, 2)

        self.output_entry = DragDropLineEdit()
        self.output_entry.setPlaceholderText("留空则在GIF同目录创建")
        self.output_entry.setEnabled(False)
        output_layout.addWidget(self.output_entry, 1, 1)

        self.output_browse_btn = QPushButton()
        self.output_browse_btn.clicked.connect(self._select_output_dir)
        self.output_browse_btn.setEnabled(False)
        output_layout.addWidget(self.output_browse_btn, 1, 2)

        self.custom_dir_check.toggled.connect(self.output_entry.setEnabled)
        self.custom_dir_check.toggled.connect(self.output_browse_btn.setEnabled)

        main_layout.addWidget(output_group)

        # ---- 3. 操作按钮和进度 ----
        action_layout = QHBoxLayout()

        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }"
        )
        self.start_btn.clicked.connect(self._start_splitting)
        action_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_splitting)
        action_layout.addWidget(self.stop_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        action_layout.addWidget(self.status_label)

        main_layout.addLayout(action_layout)

        # ---- 4. 日志区域 ----
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        self.log_area.setPlaceholderText(self.tr("log"))
        main_layout.addWidget(self.log_area)

        # 注册为基类的日志组件
        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label

    def retranslate_ui(self):
        """更新所有UI文本（语言切换时自动调用）"""
        self.gif_label.setText(self.tr("select_gif_file"))
        self.browse_gif_btn.setText(self.tr("browse"))
        self.gif_info_label.setText(
            self.tr("no_gif_selected") if not self.gif_path else
            self.tr("gif_selected").format(filename=os.path.basename(self.gif_path))
        )
        self.format_label.setText(self.tr("output_format"))
        self.custom_dir_check.setText(self.tr("custom_output_folder"))
        self.output_browse_btn.setText(self.tr("browse"))
        self.start_btn.setText(self.tr("start_split"))
        self.stop_btn.setText(self.tr("stop"))
        self.status_label.setText(
            self.tr("status_idle") if not self.gif_path else
            self.tr("status_ready")
        )
        # 更新group标题
        for group in self.findChildren(QGroupBox):
            if group.parent() == self:
                if self.findChildren(QLabel)[0] == self.gif_label:
                    # 这是文件选择group
                    pass  # QGroupBox标题通过setTitle设置

    # ---------- 文件选择 ----------

    def _select_gif(self):
        """选择GIF文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("select_gif_file_dialog_title"), "",
            self.tr("gif_files") + " (*.gif);;" + self.tr("all_files") + " (*.*)"
        )
        if path:
            self.gif_entry.setText(path)

    def _on_gif_path_changed(self, text: str):
        """GIF路径变更"""
        path = text.strip()
        if os.path.isfile(path) and path.lower().endswith('.gif'):
            self.gif_path = path
            self.gif_info_label.setText(
                self.tr("gif_selected").format(filename=os.path.basename(path)))
            self.gif_info_label.setStyleSheet("color: #78e46f;")
            self.status_label.setText(self.tr("status_ready"))
        else:
            self.gif_path = ""
            self.gif_info_label.setText(self.tr("no_gif_selected"))
            self.gif_info_label.setStyleSheet("color: gray;")

    def _select_output_dir(self):
        """选择输出目录"""
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("select_folder_dialog_title"))
        if folder:
            self.output_entry.setText(folder)

    # ---------- 拆分操作 ----------

    def _start_splitting(self):
        """开始拆分GIF"""
        if not self.gif_path:
            QMessageBox.warning(self, self.tr("error_title"), self.tr("error_select_gif"))
            return

        output_format = self.format_combo.currentText()
        output_dir = self.output_entry.text().strip() if self.custom_dir_check.isChecked() else ""

        # 确认对话框
        reply = QMessageBox.question(
            self, self.tr("confirm_split"),
            self.tr("confirm_split") + "\n{0}".format(os.path.basename(self.gif_path)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 进入处理状态
        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("processing"))
        self.log_area.clear()

        # 创建并启动工作线程
        self.worker = SplitGifWorker(self.gif_path, output_dir, output_format)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)

        QThreadPool.globalInstance().start(self.worker)

    def _stop_splitting(self):
        """停止拆分"""
        if self.worker:
            self.worker.stop()
            self.log(self.tr("stopping"))
            self.stop_btn.setEnabled(False)

    # ---------- 信号回调 ----------

    def _on_progress(self, current: int, total: int):
        """进度更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(
            self.tr("processing_frames") + f" {current}/{total}")

    def _on_log(self, message: str):
        """日志消息"""
        self.log(message)

    def _on_error(self, error: str):
        """错误消息"""
        self.log(f"[错误] {error}")

    def _on_finished(self, result: dict):
        """处理完成"""
        self.set_processing(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if result.get('success'):
            frame_count = result.get('frame_count', 0)
            output_dir = result.get('output_dir', '')
            self.status_label.setText(
                self.tr("splitting_complete").format(count=frame_count))
            self.progress_bar.setValue(self.progress_bar.maximum())
            QMessageBox.information(
                self, self.tr("info_title"),
                self.tr("splitting_complete").format(count=frame_count) + "\n" +
                self.tr("output_location").format(path=output_dir)
            )
        else:
            error = result.get('error', self.tr('splitting_error'))
            self.status_label.setText(self.tr("splitting_error"))
            self.progress_bar.setVisible(False)
