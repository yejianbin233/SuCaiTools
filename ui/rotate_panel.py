"""
图片批量旋转工具面板

对文件夹下的图片按指定角度间隔批量旋转，生成多个旋转版本。
"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QGroupBox, QSpinBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit, natural_sort_key
from core.base_worker import BaseWorker


class RotateWorker(BaseWorker):
    """图片旋转工作线程"""

    def __init__(self, folder_path: str, angle_interval: int):
        super().__init__()
        self.folder_path = folder_path
        self.angle_interval = angle_interval

    def run(self):
        """执行批量旋转"""
        from PIL import Image

        try:
            supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
            image_files = []
            for f in sorted(os.listdir(self.folder_path), key=natural_sort_key):
                if f.lower().endswith(supported):
                    image_files.append(os.path.join(self.folder_path, f))

            total = len(image_files)
            if total == 0:
                self.signals.log.emit("未找到图片文件")
                self.signals.finished.emit(
                    {'success': True, 'processed': 0})
                return

            self.signals.log.emit(
                f"找到 {total} 张图片，角度间隔: {self.angle_interval}°")

            num_rotations = 360 // self.angle_interval
            for idx, img_path in enumerate(image_files):
                if self._stop_flag:
                    break

                try:
                    with Image.open(img_path) as img:
                        name = os.path.splitext(os.path.basename(img_path))[0]
                        ext = os.path.splitext(img_path)[1]
                        for r in range(num_rotations):
                            angle = (r + 1) * self.angle_interval
                            rotated = img.rotate(
                                -angle, expand=True,
                                fillcolor=(0, 0, 0, 0) if img.mode == 'RGBA'
                                else (255, 255, 255))
                            out_path = os.path.join(
                                self.folder_path,
                                f"{name}_rot{angle}{ext}")
                            rotated.save(out_path)
                    self.signals.log.emit(
                        f"已处理: {os.path.basename(img_path)}")
                except Exception as e:
                    self.signals.log.emit(
                        f"处理失败 {os.path.basename(img_path)}: {e}")

                self.signals.progress.emit(idx + 1, total)

            self.signals.log.emit(f"旋转完成! 共处理 {total} 张图片")
            self.signals.finished.emit({'success': True, 'processed': total})

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit({'success': False, 'error': str(e)})


class RotatePanel(BaseToolPanel):
    """图片批量旋转面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.worker: RotateWorker | None = None
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
        self.folder_entry.setPlaceholderText("选择包含图片的文件夹或拖放到此处")
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        folder_layout.addWidget(self.folder_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.browse_btn, 0, 2)
        layout.addWidget(folder_group)

        # 角度设置
        angle_group = QGroupBox()
        angle_layout = QHBoxLayout(angle_group)
        self.angle_label = QLabel()
        angle_layout.addWidget(self.angle_label)
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(1, 180)
        self.angle_spin.setValue(90)
        self.angle_spin.setSuffix("°")
        angle_layout.addWidget(self.angle_spin)
        self.angle_hint = QLabel()
        self.angle_hint.setStyleSheet("color: gray;")
        angle_layout.addWidget(self.angle_hint)
        angle_layout.addStretch()
        layout.addWidget(angle_group)

        # 操作按钮
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton()
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
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
        self.angle_label.setText(self.tr("rotation_angle_interval"))
        self.start_btn.setText(self.tr("start_rotation"))
        self.stop_btn.setText(self.tr("stop"))
        angle = self.angle_spin.value()
        count = 360 // angle if angle > 0 else 0
        self.angle_hint.setText(
            self.tr("will_generate_count").format(count=count))

    def _select_folder(self):
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.folder_entry.setText(folder)

    def _start(self):
        if not self.folder_path:
            self.show_error(self.tr("error_title"),
                            self.tr("error_no_folder"))
            return
        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        self.worker = RotateWorker(self.folder_path, self.angle_spin.value())
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
                self.tr("completed_count").format(
                    count=result.get('processed', 0)))
