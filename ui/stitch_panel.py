"""
图片拼接工具面板

将多张图片水平或垂直拼接为一张大图。
修复原版将所有图片加载到内存的问题——使用流式处理。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QCheckBox,
    QProgressBar, QGroupBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit
from core.base_worker import BaseWorker


class StitchWorker(BaseWorker):
    """图片拼接工作线程"""

    def __init__(self, folder_path: str, direction: str = 'horizontal',
                 uniform_size: bool = True):
        super().__init__()
        self.folder_path = folder_path
        self.direction = direction
        self.uniform_size = uniform_size

    def run(self):
        """执行拼接操作

        改进：使用两次遍历——第一次获取尺寸信息，第二次逐张拼接，
        避免将所有图片同时加载到内存。
        """
        from PIL import Image

        supported = ('.png', '.jpg', '.jpeg', '.bmp')
        image_files = sorted([
            os.path.join(self.folder_path, f)
            for f in os.listdir(self.folder_path)
            if f.lower().endswith(supported)
        ])

        total = len(image_files)
        if total < 2:
            self.signals.log.emit("至少需要2张图片才能拼接")
            self.signals.finished.emit({'success': False, 'error': '图片不足'})
            return

        self.signals.log.emit(f"找到 {total} 张图片")

        try:
            # 第一次遍历：获取尺寸并计算总画布大小
            sizes = []
            max_w, max_h = 0, 0
            for path in image_files:
                with Image.open(path) as img:
                    w, h = img.size
                    sizes.append((w, h))
                    max_w = max(max_w, w)
                    max_h = max(max_h, h)

            # 计算画布尺寸
            if self.uniform_size:
                if self.direction == 'horizontal':
                    canvas_size = (max_w * total, max_h)
                else:
                    canvas_size = (max_w, max_h * total)
            else:
                if self.direction == 'horizontal':
                    canvas_size = (sum(s[0] for s in sizes), max_h)
                else:
                    canvas_size = (max_w, sum(s[1] for s in sizes))

            # 创建画布
            canvas = Image.new('RGB', canvas_size, (255, 255, 255))

            # 第二次遍历：逐张粘贴
            offset = 0
            for idx, path in enumerate(image_files):
                if self._stop_flag:
                    break
                with Image.open(path) as img:
                    w, h = img.size
                    if self.uniform_size:
                        paste_img = img.resize(
                            (max_w, max_h), Image.Resampling.LANCZOS)
                    else:
                        paste_img = img.copy().convert('RGB')

                    if self.direction == 'horizontal':
                        canvas.paste(paste_img, (offset, 0))
                        offset += max_w if self.uniform_size else w
                    else:
                        canvas.paste(paste_img, (0, offset))
                        offset += max_h if self.uniform_size else h

                self.signals.progress.emit(idx + 1, total)

            # 保存
            out_path = os.path.join(self.folder_path, "stitched.png")
            canvas.save(out_path, 'PNG')
            self.signals.log.emit(f"拼接完成! 输出: {out_path}")
            self.signals.log.emit(
                f"画布尺寸: {canvas_size[0]}x{canvas_size[1]}")
            self.signals.finished.emit(
                {'success': True, 'output': out_path, 'processed': total})

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


class StitchPanel(BaseToolPanel):
    """图片拼接面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.worker: StitchWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        folder_group = QGroupBox()
        folder_layout = QGridLayout(folder_group)
        self.folder_label = QLabel()
        folder_layout.addWidget(self.folder_label, 0, 0)
        self.folder_entry = DragDropFolderLineEdit()
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        folder_layout.addWidget(self.folder_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.browse_btn, 0, 2)
        layout.addWidget(folder_group)

        # 拼接设置
        settings_layout = QHBoxLayout()
        self.dir_label = QLabel()
        settings_layout.addWidget(self.dir_label)
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(['horizontal', 'vertical'])
        settings_layout.addWidget(self.dir_combo)
        self.uniform_check = QCheckBox()
        self.uniform_check.setChecked(True)
        settings_layout.addWidget(self.uniform_check)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        action_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.start_btn.clicked.connect(self._start)
        action_layout.addWidget(self.start_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        action_layout.addWidget(self.status_label)
        layout.addLayout(action_layout)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    def retranslate_ui(self):
        self.folder_label.setText(self.tr("select_folder"))
        self.browse_btn.setText(self.tr("browse"))
        self.dir_label.setText(self.tr("stitch_direction"))
        self.uniform_check.setText(self.tr("uniform_size"))
        self.start_btn.setText(self.tr("start_stitch"))

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
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = StitchWorker(
            self.folder_path,
            self.dir_combo.currentText(),
            self.uniform_check.isChecked())
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self.worker)

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
        if result.get('success'):
            self.status_label.setText(
                f"完成! {result.get('processed', 0)} 张")
            QMessageBox.information(
                self, self.tr("info_title"),
                f"拼接完成!\n{result.get('output', '')}")
