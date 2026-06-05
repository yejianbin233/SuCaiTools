"""
图片批量缩放工具面板

支持按比例缩放、固定宽度/高度缩放。
修复原版直接覆盖源文件的危险行为——新增输出目录选择。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit
from core.base_worker import BaseWorker


class ResizeWorker(BaseWorker):
    """图片缩放工作线程"""

    def __init__(self, input_dir: str, output_dir: str, mode: str,
                 scale: float = 0.5, width: int = 800, height: int = 600):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.mode = mode
        self.scale = scale
        self.width = width
        self.height = height

    def run(self):
        """执行批量缩放"""
        from PIL import Image

        supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        image_files = []
        for f in sorted(os.listdir(self.input_dir)):
            if f.lower().endswith(supported):
                image_files.append(os.path.join(self.input_dir, f))

        total = len(image_files)
        if total == 0:
            self.signals.log.emit("未找到图片文件")
            self.signals.finished.emit({'success': True, 'processed': 0})
            return

        self.signals.log.emit(f"找到 {total} 张图片，模式: {self.mode}")
        os.makedirs(self.output_dir, exist_ok=True)

        for idx, img_path in enumerate(image_files):
            if self._stop_flag:
                break
            try:
                with Image.open(img_path) as img:
                    if self.mode == 'scale':
                        new_size = (int(img.width * self.scale),
                                    int(img.height * self.scale))
                    elif self.mode == 'fixed_width':
                        ratio = self.width / img.width
                        new_size = (self.width, int(img.height * ratio))
                    elif self.mode == 'fixed_height':
                        ratio = self.height / img.height
                        new_size = (int(img.width * ratio), self.height)
                    else:
                        new_size = (self.width, self.height)

                    resized = img.resize(new_size, Image.Resampling.LANCZOS)
                    out_path = os.path.join(
                        self.output_dir, os.path.basename(img_path))
                    # 保持原始格式
                    save_format = None
                    ext = os.path.splitext(img_path)[1].lower()
                    if ext in ('.jpg', '.jpeg'):
                        save_format = 'JPEG'
                        if resized.mode == 'RGBA':
                            resized = resized.convert('RGB')
                    elif ext == '.png':
                        save_format = 'PNG'
                    resized.save(out_path, format=save_format)

                self.signals.progress.emit(idx + 1, total)
            except Exception as e:
                self.signals.log.emit(
                    f"缩放失败 {os.path.basename(img_path)}: {e}")

        self.signals.log.emit(f"缩放完成! 共 {total} 张")
        self.signals.finished.emit({'success': True, 'processed': total})


class ResizePanel(BaseToolPanel):
    """图片批量缩放面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_dir: str = ""
        self.output_dir: str = ""
        self.worker: ResizeWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 输入/输出文件夹
        io_group = QGroupBox()
        io_layout = QGridLayout(io_group)
        self.input_label = QLabel()
        io_layout.addWidget(self.input_label, 0, 0)
        self.input_entry = DragDropFolderLineEdit()
        self.input_entry.setPlaceholderText("输入文件夹")
        io_layout.addWidget(self.input_entry, 0, 1)
        self.input_btn = QPushButton()
        self.input_btn.clicked.connect(self._select_input)
        io_layout.addWidget(self.input_btn, 0, 2)
        self.output_label = QLabel()
        io_layout.addWidget(self.output_label, 1, 0)
        self.output_entry = DragDropFolderLineEdit()
        self.output_entry.setPlaceholderText("输出文件夹")
        self.output_entry.textChanged.connect(
            lambda t: setattr(self, 'output_dir', t.strip()))
        io_layout.addWidget(self.output_entry, 1, 1)
        self.output_btn = QPushButton()
        self.output_btn.clicked.connect(self._select_output)
        io_layout.addWidget(self.output_btn, 1, 2)
        layout.addWidget(io_group)

        # 缩放模式
        mode_group = QGroupBox()
        mode_layout = QHBoxLayout(mode_group)
        self.mode_label = QLabel()
        mode_layout.addWidget(self.mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["scale", "fixed_width", "fixed_height"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        self.param_label = QLabel()
        mode_layout.addWidget(self.param_label)
        self.param_entry = QLineEdit("0.5")
        self.param_entry.setMaximumWidth(80)
        mode_layout.addWidget(self.param_entry)
        mode_layout.addStretch()
        layout.addWidget(mode_group)

        # 操作
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

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    def _on_mode_changed(self, mode):
        hints = {'scale': '0.5', 'fixed_width': '800', 'fixed_height': '600'}
        self.param_entry.setText(hints.get(mode, '0.5'))

    def retranslate_ui(self):
        self.input_label.setText(self.tr("select_input"))
        self.output_label.setText(self.tr("output_dir"))
        self.input_btn.setText(self.tr("browse"))
        self.output_btn.setText(self.tr("browse"))
        self.mode_label.setText(self.tr("scale_mode"))
        self.start_btn.setText(self.tr("start_resize"))
        self.stop_btn.setText(self.tr("stop"))

    def _select_input(self):
        folder = self.browse_folder(self.tr("select_input"))
        if folder:
            self.input_dir = folder
            self.input_entry.setText(folder)
            if not self.output_dir:
                default_out = os.path.join(folder, "resized")
                self.output_entry.setText(default_out)
                self.output_dir = default_out

    def _select_output(self):
        folder = self.browse_folder(self.tr("select_output_dir"))
        if folder:
            self.output_dir = folder
            self.output_entry.setText(folder)

    def _start(self):
        if not self.input_dir:
            self.show_error(self.tr("error_title"),
                            self.tr("error_no_input"))
            return
        output = self.output_dir or os.path.join(self.input_dir, "resized")
        mode = self.mode_combo.currentText()
        try:
            param = float(self.param_entry.text())
        except ValueError:
            self.show_error(self.tr("error_title"), "参数无效")
            return

        self.set_processing(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.log_area.clear()

        kwargs = {mode if mode == 'scale' else
                  ('width' if mode == 'fixed_width' else 'height'): param}
        if mode == 'fixed_width':
            kwargs['width'] = int(param)
        elif mode == 'fixed_height':
            kwargs['height'] = int(param)
        else:
            kwargs = {'scale': param}

        self.worker = ResizeWorker(
            self.input_dir, output, mode, **kwargs)
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
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if result.get('success'):
            self.status_label.setText(
                f"完成! {result.get('processed', 0)} 张")
