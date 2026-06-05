"""
JPG转PNG工具面板

批量将JPG/JPEG图片转换为PNG格式。
支持递归处理子文件夹、跳过已存在文件。
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QCheckBox,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit
from core.base_worker import BaseWorker


class ConvertWorker(BaseWorker):
    """JPG→PNG转换工作线程"""

    def __init__(self, folder_path: str, recursive: bool = True):
        super().__init__()
        self.folder_path = folder_path
        self.recursive = recursive

    def run(self):
        """执行批量转换"""
        from PIL import Image

        try:
            # 收集所有JPG文件
            jpg_files = []
            if self.recursive:
                for root, _, files in os.walk(self.folder_path):
                    for f in files:
                        if f.lower().endswith(('.jpg', '.jpeg')):
                            jpg_files.append(os.path.join(root, f))
            else:
                for f in os.listdir(self.folder_path):
                    if f.lower().endswith(('.jpg', '.jpeg')):
                        jpg_files.append(os.path.join(self.folder_path, f))

            total = len(jpg_files)
            if total == 0:
                self.signals.log.emit("未找到JPG/JPEG文件")
                self.signals.finished.emit(
                    {'success': True, 'converted': 0, 'skipped': 0})
                return

            self.signals.log.emit(f"找到 {total} 个JPG文件")

            converted = 0
            skipped = 0
            for i, jpg_path in enumerate(jpg_files):
                if self._stop_flag:
                    self.signals.log.emit("转换已停止")
                    break

                png_path = os.path.splitext(jpg_path)[0] + '.png'
                if os.path.exists(png_path):
                    skipped += 1
                    self.signals.log.emit(
                        f"跳过(已存在): {os.path.basename(jpg_path)}")
                else:
                    try:
                        with Image.open(jpg_path) as img:
                            if img.mode in ('RGBA', 'P', 'LA'):
                                img = img.convert('RGBA')
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            img.save(png_path, 'PNG')
                        converted += 1
                    except Exception as e:
                        self.signals.log.emit(
                            f"转换失败 {os.path.basename(jpg_path)}: {e}")

                self.signals.progress.emit(i + 1, total)

            self.signals.log.emit(
                f"转换完成! 成功 {converted}, 跳过 {skipped}")
            self.signals.finished.emit({
                'success': True, 'converted': converted, 'skipped': skipped
            })

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


class JpgToPngPanel(BaseToolPanel):
    """JPG转PNG工具面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.worker: ConvertWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        """创建界面布局"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 文件夹选择
        folder_group = QGroupBox()
        folder_layout = QGridLayout(folder_group)

        self.folder_label = QLabel()
        folder_layout.addWidget(self.folder_label, 0, 0)

        self.folder_entry = DragDropFolderLineEdit()
        self.folder_entry.setPlaceholderText("选择包含JPG图片的文件夹或拖放到此处")
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        folder_layout.addWidget(self.folder_entry, 0, 1)

        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.browse_btn, 0, 2)

        self.recursive_check = QCheckBox()
        self.recursive_check.setChecked(True)
        folder_layout.addWidget(self.recursive_check, 1, 1)

        layout.addWidget(folder_group)

        # 操作按钮
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }"
        )
        self.start_btn.clicked.connect(self._start)
        action_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        action_layout.addWidget(self.stop_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        action_layout.addWidget(self.status_label)

        layout.addLayout(action_layout)

        # 日志
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label

        self.retranslate_ui()

    def retranslate_ui(self):
        """更新UI文本"""
        self.folder_label.setText(self.tr("select_folder"))
        self.browse_btn.setText(self.tr("browse"))
        self.recursive_check.setText(self.tr("recursive"))
        self.start_btn.setText(self.tr("start_convert"))
        self.stop_btn.setText(self.tr("stop"))
        if not self.folder_path:
            self.status_label.setText(self.tr("status_idle"))

    def _select_folder(self):
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.folder_entry.setText(folder)

    def _start(self):
        if not self.folder_path:
            self.show_error(self.tr("error_title"),
                            self.tr("error_select_input"))
            return
        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = ConvertWorker(
            self.folder_path, self.recursive_check.isChecked())
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self.worker)

    def _stop(self):
        if self.worker:
            self.worker.stop()

    def _on_progress(self, cur, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(cur)

    def _on_log(self, msg):
        self.log(msg)

    def _on_error(self, err):
        self.log(f"[错误] {err}")

    def _on_finished(self, result):
        self.set_processing(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            self.status_label.setText(
                f"完成! 转换 {result.get('converted', 0)}, "
                f"跳过 {result.get('skipped', 0)}")
            self.progress_bar.setValue(self.progress_bar.maximum())
