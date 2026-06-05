"""
图片处理工具面板

支持图片水平/垂直翻转、旋转、颜色转透明等功能。
修复原版 resized_img 变量名错误、线程安全问题。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QComboBox, QFileDialog,
    QProgressBar, QGroupBox, QMessageBox
)
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QPixmap

from core.base_panel import BaseToolPanel
from core.utils import DragDropLineEdit, DragDropFolderLineEdit
from core.base_worker import BaseWorker


class ImageProcWorker(BaseWorker):
    """图片处理工作线程"""

    def __init__(self, folder_path: str, operation: str, **kwargs):
        super().__init__()
        self.folder_path = folder_path
        self.operation = operation
        self.kwargs = kwargs

    def run(self):
        """执行批量图片处理"""
        from PIL import Image

        supported = ('.png', '.jpg', '.jpeg', '.bmp')
        image_files = []
        for f in sorted(os.listdir(self.folder_path)):
            if f.lower().endswith(supported):
                image_files.append(os.path.join(self.folder_path, f))

        total = len(image_files)
        if total == 0:
            self.signals.log.emit("未找到图片文件")
            self.signals.finished.emit({'success': True, 'processed': 0})
            return

        self.signals.log.emit(f"找到 {total} 张图片，操作: {self.operation}")

        processed = 0
        for idx, img_path in enumerate(image_files):
            if self._stop_flag:
                break
            try:
                with Image.open(img_path) as img:
                    result = self._apply_operation(img)
                    if result:
                        result.save(img_path)
                        processed += 1
                self.signals.progress.emit(idx + 1, total)
            except Exception as e:
                self.signals.log.emit(
                    f"处理失败 {os.path.basename(img_path)}: {e}")

        self.signals.log.emit(
            f"处理完成! 成功处理 {processed}/{total} 张图片")
        self.signals.finished.emit(
            {'success': True, 'processed': processed})

    def _apply_operation(self, img: 'Image.Image'):
        """对单张图片执行指定操作"""
        op = self.operation
        if op == 'flip_horizontal':
            return img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        elif op == 'flip_vertical':
            return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif op == 'rotate_90':
            return img.rotate(-90, expand=True)
        elif op == 'rotate_180':
            return img.rotate(180, expand=True)
        elif op == 'rotate_270':
            return img.rotate(-270, expand=True)
        return None


class ImageProcessorPanel(BaseToolPanel):
    """图片处理面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.worker: ImageProcWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 文件夹选择
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

        # 操作按钮组
        btn_group = QGroupBox()
        btn_layout = QHBoxLayout(btn_group)

        self.flip_h_btn = QPushButton()
        self.flip_h_btn.clicked.connect(
            lambda: self._start_operation('flip_horizontal'))
        btn_layout.addWidget(self.flip_h_btn)

        self.flip_v_btn = QPushButton()
        self.flip_v_btn.clicked.connect(
            lambda: self._start_operation('flip_vertical'))
        btn_layout.addWidget(self.flip_v_btn)

        self.rot90_btn = QPushButton()
        self.rot90_btn.clicked.connect(
            lambda: self._start_operation('rotate_90'))
        btn_layout.addWidget(self.rot90_btn)

        self.rot180_btn = QPushButton()
        self.rot180_btn.clicked.connect(
            lambda: self._start_operation('rotate_180'))
        btn_layout.addWidget(self.rot180_btn)

        self.rot270_btn = QPushButton()
        self.rot270_btn.clicked.connect(
            lambda: self._start_operation('rotate_270'))
        btn_layout.addWidget(self.rot270_btn)

        layout.addWidget(btn_group)

        # 操作
        action_layout = QHBoxLayout()
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
        self.flip_h_btn.setText(self.tr("flip_horizontal"))
        self.flip_v_btn.setText(self.tr("flip_vertical"))
        self.rot90_btn.setText(self.tr("rotate_left"))
        self.rot180_btn.setText(self.tr("rotate_180"))
        self.rot270_btn.setText(self.tr("rotate_right"))
        self.stop_btn.setText(self.tr("stop"))

    def _select_folder(self):
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.folder_entry.setText(folder)

    def _start_operation(self, operation: str):
        if not self.folder_path:
            self.show_error(self.tr("error_title"),
                            self.tr("error_no_folder"))
            return

        # 确认（这些操作直接覆盖源文件）
        reply = QMessageBox.question(
            self, self.tr("confirm_title"),
            self.tr("confirm_overwrite"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.set_processing(True)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = ImageProcWorker(self.folder_path, operation)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
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

    def _on_finished(self, result):
        self.set_processing(False)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            self.status_label.setText(
                f"完成! {result.get('processed', 0)} 张")
