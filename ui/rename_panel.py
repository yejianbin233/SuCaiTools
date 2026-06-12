"""
图片批量重命名工具面板

按文件夹名称+序号的方式递归重命名目录下的图片文件。
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QCheckBox,
    QProgressBar, QGroupBox, QMessageBox
)
from PySide6.QtCore import QThreadPool

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit, natural_sort_key
from core.base_worker import BaseWorker


class RenameWorker(BaseWorker):
    """重命名工作线程"""

    def __init__(self, folder_path: str, recursive: bool = True):
        super().__init__()
        self.folder_path = folder_path
        self.recursive = recursive

    def run(self):
        """执行批量重命名"""
        supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
        # 收集所有图片文件
        all_files = []
        if self.recursive:
            for root, _, files in os.walk(self.folder_path):
                for f in sorted(files):
                    if f.lower().endswith(supported):
                        all_files.append(os.path.join(root, f))
        else:
            for f in sorted(os.listdir(self.folder_path), key=natural_sort_key):
                if f.lower().endswith(supported):
                    all_files.append(os.path.join(self.folder_path, f))

        total = len(all_files)
        if total == 0:
            self.signals.log.emit("未找到图片文件")
            self.signals.finished.emit(
                {'success': True, 'renamed': 0, 'skipped': 0})
            return

        self.signals.log.emit(f"找到 {total} 张图片")

        # 按目录分组
        by_dir: dict[str, list[str]] = {}
        for f in all_files:
            d = os.path.dirname(f)
            by_dir.setdefault(d, []).append(f)

        renamed = 0
        skipped = 0
        processed = 0

        for dir_path, files in by_dir.items():
            folder_name = os.path.basename(dir_path)
            count = 1
            for old_path in files:
                if self._stop_flag:
                    self.signals.log.emit("重命名已停止")
                    break

                ext = os.path.splitext(old_path)[1].lower()
                new_name = f"{folder_name}_{count:04d}{ext}"
                new_path = os.path.join(dir_path, new_name)

                if old_path == new_path:
                    count += 1
                    continue

                if os.path.exists(new_path):
                    skipped += 1
                    self.signals.log.emit(
                        f"跳过(目标已存在): {os.path.basename(old_path)}")
                else:
                    try:
                        os.rename(old_path, new_path)
                        renamed += 1
                    except OSError as e:
                        self.signals.log.emit(
                            f"重命名失败 {os.path.basename(old_path)}: {e}")

                count += 1
                processed += 1
                self.signals.progress.emit(processed, total)

        self.signals.log.emit(
            f"重命名完成! 成功 {renamed}, 跳过 {skipped}")
        self.signals.finished.emit(
            {'success': True, 'renamed': renamed, 'skipped': skipped})


class RenamePanel(BaseToolPanel):
    """图片批量重命名面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.worker: RenameWorker | None = None
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
        self.folder_entry.setPlaceholderText("选择包含图片的文件夹或拖放到此处")
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
        self.recursive_check.setText(self.tr("recursive"))
        self.start_btn.setText(self.tr("start_rename"))
        self.stop_btn.setText(self.tr("stop"))

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

        self.worker = RenameWorker(
            self.folder_path, self.recursive_check.isChecked())
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
                f"完成! 重命名 {result.get('renamed', 0)}, "
                f"跳过 {result.get('skipped', 0)}")
