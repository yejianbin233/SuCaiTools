"""
文件分发工具面板

将一个文件复制到目标文件夹下的所有一级子文件夹中（跳过已存在同名文件的子文件夹）。
"""

import os
import shutil
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog,
    QCheckBox
)
from PySide6.QtCore import Signal

from core.base_panel import BaseToolPanel
from core.utils import DragDropLineEdit, DragDropFolderLineEdit


class FileDistributorPanel(BaseToolPanel):
    """文件分发面板 — 将文件复制到目标文件夹的各子文件夹中"""

    _progress_signal = Signal(int, int, str)  # (done, total, sub_name)
    _done_signal = Signal(int, int)           # (copied, errors)
    _log_signal = Signal(str)                 # log message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_file: str = ""
        self.target_folder: str = ""
        self._setup_ui()
        self._progress_signal.connect(self._on_progress_update)
        self._done_signal.connect(self._on_done)
        self._log_signal.connect(self.log)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 源文件选择 ----
        src_group = QGroupBox()
        src_layout = QGridLayout(src_group)
        self.src_label = QLabel()
        src_layout.addWidget(self.src_label, 0, 0)
        self.src_entry = DragDropLineEdit()
        self.src_entry.setPlaceholderText("拖放文件到此处或点击浏览...")
        self.src_entry.textChanged.connect(
            lambda t: setattr(self, 'source_file', t.strip()))
        src_layout.addWidget(self.src_entry, 0, 1)
        self.src_btn = QPushButton()
        self.src_btn.clicked.connect(self._select_source)
        src_layout.addWidget(self.src_btn, 0, 2)
        layout.addWidget(src_group)

        # ---- 目标文件夹选择 ----
        dst_group = QGroupBox()
        dst_layout = QGridLayout(dst_group)
        self.dst_label = QLabel()
        dst_layout.addWidget(self.dst_label, 0, 0)
        self.dst_entry = DragDropFolderLineEdit()
        self.dst_entry.setPlaceholderText("拖放文件夹到此处或点击浏览...")
        self.dst_entry.textChanged.connect(
            lambda t: setattr(self, 'target_folder', t.strip()))
        dst_layout.addWidget(self.dst_entry, 0, 1)
        self.dst_btn = QPushButton()
        self.dst_btn.clicked.connect(self._select_target)
        dst_layout.addWidget(self.dst_btn, 0, 2)
        layout.addWidget(dst_group)

        # ---- 操作按钮 ----
        action_layout = QHBoxLayout()
        self.scan_btn = QPushButton()
        self.scan_btn.clicked.connect(self._scan)
        self.scan_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        action_layout.addWidget(self.scan_btn)

        self.execute_btn = QPushButton()
        self.execute_btn.clicked.connect(self._execute)
        self.execute_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.execute_btn.setEnabled(False)
        action_layout.addWidget(self.execute_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        action_layout.addWidget(self.status_label)
        layout.addLayout(action_layout)

        # ---- 日志 ----
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(200)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self._pending_dirs: list[str] = []
        self.retranslate_ui()

    def retranslate_ui(self):
        self.src_label.setText(self.tr("source_file"))
        self.src_btn.setText(self.tr("browse"))
        self.dst_label.setText(self.tr("target_folder"))
        self.dst_btn.setText(self.tr("browse"))
        self.scan_btn.setText(self.tr("scan_subdirs"))
        self.execute_btn.setText(self.tr("start_distribute"))
        self.status_label.setText(self.tr("status_idle"))

    # ---------- 文件选择 ----------

    def _select_source(self):
        path = self.browse_file(self.tr("source_file"), "所有文件 (*.*)")
        if path:
            self.src_entry.setText(path)

    def _select_target(self):
        folder = self.browse_folder(self.tr("target_folder"))
        if folder:
            self.dst_entry.setText(folder)

    # ---------- 扫描 ----------

    def _scan(self):
        """扫描目标文件夹下的一级子文件夹"""
        src = self.src_entry.text().strip()
        dst = self.dst_entry.text().strip()

        if not src or not os.path.isfile(src):
            self.show_error(self.tr("error_title"), "请先选择有效的源文件")
            return
        if not dst or not os.path.isdir(dst):
            self.show_error(self.tr("error_title"), "请先选择有效的目标文件夹")
            return

        self.source_file = src
        self.target_folder = dst
        src_name = os.path.basename(src)
        self.log_area.clear()

        # 收集一级子文件夹
        subdirs = []
        try:
            for entry in os.listdir(dst):
                full = os.path.join(dst, entry)
                if os.path.isdir(full):
                    subdirs.append(full)
        except PermissionError:
            self.show_error(self.tr("error_title"), "无法访问目标文件夹")
            return

        if not subdirs:
            self.log("目标文件夹下没有子文件夹")
            return

        subdirs.sort()
        self._pending_dirs = []

        self.log(f"源文件: {src_name}")
        self.log(f"目标文件夹: {dst}")
        self.log(f"共找到 {len(subdirs)} 个子文件夹\n")

        missing = 0
        exists = 0
        for sub in subdirs:
            dest_path = os.path.join(sub, src_name)
            if os.path.exists(dest_path):
                exists += 1
                self.log(f"  ✓ {os.path.basename(sub)}/  (已存在)")
            else:
                missing += 1
                self._pending_dirs.append(sub)
                self.log(f"  → {os.path.basename(sub)}/  (待复制)")

        self.log(f"\n扫描完成: {exists} 个已存在, {missing} 个待复制")
        self.status_label.setText(
            f"{missing} 个子文件夹需要复制文件")
        self.execute_btn.setEnabled(missing > 0)

    # ---------- 执行 ----------

    def _execute(self):
        """执行文件复制到待处理的子文件夹"""
        if not self._pending_dirs or not self.source_file:
            return

        src_name = os.path.basename(self.source_file)
        total = len(self._pending_dirs)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.execute_btn.setEnabled(False)
        self.status_label.setText(f"正在复制... 0/{total}")

        # 复制 pending_dirs 列表（防止在线程中被修改）
        dirs_to_process = list(self._pending_dirs)
        source = self.source_file

        def run():
            copied = 0
            errors = 0
            for i, sub in enumerate(dirs_to_process):
                dest = os.path.join(sub, src_name)
                try:
                    shutil.copy2(source, dest)
                    copied += 1
                    self._log_signal.emit(f"  ✓ {os.path.basename(sub)}/  (已复制)")
                except Exception as ex:
                    errors += 1
                    self._log_signal.emit(f"  ✗ {os.path.basename(sub)}/  (失败: {ex})")
                self._progress_signal.emit(copied + errors, total, os.path.basename(sub))

            self._done_signal.emit(copied, errors)

        threading.Thread(target=run, daemon=True).start()

    def _on_progress_update(self, done: int, total: int, sub_name: str):
        """进度更新（主线程）"""
        self.progress_bar.setValue(done)
        self.status_label.setText(f"复制中... {done}/{total}")

    def _on_done(self, copied: int, errors: int):
        """完成（主线程）"""
        self.execute_btn.setEnabled(False)
        total = copied + errors
        self.log(f"\n分发完成: 成功 {copied}, 失败 {errors}")
        self.status_label.setText(
            f"完成! 复制 {copied} 个文件" +
            (f", {errors} 个失败" if errors > 0 else ""))
        self._pending_dirs.clear()
        QMessageBox.information(
            self, self.tr("info_title"),
            f"分发完成!\n成功: {copied}\n失败: {errors}")
