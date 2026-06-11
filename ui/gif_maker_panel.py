"""
GIF合成工具面板

加载文件夹中的图片，勾选后按顺序合成为GIF动图。
支持自定义帧率、输出尺寸、循环次数。
"""

import os
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QTextEdit, QSpinBox,
    QProgressBar, QMessageBox, QFileDialog, QListWidget,
    QListWidgetItem, QAbstractItemView, QSplitter
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QIcon, QImage

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit


class GifMakerPanel(BaseToolPanel):
    """GIF合成面板 — 从图片序列合成GIF"""

    # 线程安全信号
    _gif_progress = Signal(str)           # 进度文字
    _gif_bar = Signal(int, int)           # 进度条 (current, total)
    _gif_finished = Signal(str)           # 完成

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        self.image_files: list[str] = []
        self._setup_ui()

        # 持久信号连接
        self._gif_progress.connect(self._on_progress_msg)
        self._gif_bar.connect(self._on_progress_bar)
        self._gif_finished.connect(self._on_gif_done)

    # ---------- UI ----------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ---- 文件夹加载 ----
        top = QGridLayout()
        self.folder_label = QLabel()
        top.addWidget(self.folder_label, 0, 0)
        self.folder_entry = DragDropFolderLineEdit()
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        top.addWidget(self.folder_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        top.addWidget(self.browse_btn, 0, 2)
        self.load_btn = QPushButton()
        self.load_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        self.load_btn.clicked.connect(self._load_images)
        top.addWidget(self.load_btn, 0, 3)
        layout.addLayout(top)

        # ---- 中部：图片列表 + 设置 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：图片列表（带复选框）
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        list_header = QHBoxLayout()
        self.preview_label = QLabel()
        list_header.addWidget(self.preview_label)
        list_header.addStretch()
        self.select_all_btn = QPushButton()
        self.select_all_btn.clicked.connect(self._select_all)
        list_header.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton()
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        list_header.addWidget(self.deselect_all_btn)
        self.reverse_btn = QPushButton()
        self.reverse_btn.clicked.connect(self._reverse_selection)
        list_header.addWidget(self.reverse_btn)

        # 间隔选择
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 100)
        self.interval_spin.setValue(2)
        self.interval_spin.setToolTip("每隔N张勾选一张，2=隔1张选1张")
        self.interval_spin.setMaximumWidth(60)
        list_header.addWidget(self.interval_spin)
        self.interval_btn = QPushButton()
        self.interval_btn.clicked.connect(self._select_interval)
        list_header.addWidget(self.interval_btn)
        list_layout.addLayout(list_header)

        self.image_list = QListWidget()
        self.image_list.setIconSize(QSize(80, 56))
        self.image_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.image_list.setMovement(QListWidget.Movement.Static)
        self.image_list.setSpacing(4)
        self.image_list.setMinimumWidth(300)
        self.image_list.itemChanged.connect(lambda: self._update_count())
        list_layout.addWidget(self.image_list)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: gray;")
        list_layout.addWidget(self.count_label)

        splitter.addWidget(list_panel)

        # 右侧：设置面板
        settings_panel = QWidget()
        settings_panel.setMinimumWidth(200)
        settings_panel.setMaximumWidth(280)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setSpacing(8)

        # GIF参数设置
        gif_group = QGroupBox()
        gif_layout = QGridLayout(gif_group)
        gif_layout.setSpacing(6)

        # 帧率
        self.fps_label = QLabel()
        gif_layout.addWidget(self.fps_label, 0, 0)
        self.fps_spin = QSpinBox()
        self.fps_spin.setKeyboardTracking(False)
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(10)
        self.fps_spin.setSuffix(" fps")
        gif_layout.addWidget(self.fps_spin, 0, 1)

        # 尺寸
        self.size_label = QLabel()
        gif_layout.addWidget(self.size_label, 1, 0)
        size_layout = QHBoxLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(32, 1920)
        self.width_spin.setValue(480)
        size_layout.addWidget(self.width_spin)
        size_label_x = QLabel("×")
        size_label_x.setFixedWidth(15)
        size_layout.addWidget(size_label_x)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(32, 1920)
        self.height_spin.setValue(480)
        size_layout.addWidget(self.height_spin)
        gif_layout.addLayout(size_layout, 1, 1)

        # 循环次数
        self.loop_label = QLabel()
        gif_layout.addWidget(self.loop_label, 2, 0)
        self.loop_spin = QSpinBox()
        self.loop_spin.setRange(0, 9999)
        self.loop_spin.setValue(0)
        self.loop_spin.setSpecialValueText("无限循环")
        gif_layout.addWidget(self.loop_spin, 2, 1)

        # 输出文件名
        self.out_label = QLabel()
        gif_layout.addWidget(self.out_label, 3, 0)
        self.out_entry = QLineEdit()
        self.out_entry.setText("output.gif")
        gif_layout.addWidget(self.out_entry, 4, 1)

        settings_layout.addWidget(gif_group)

        # 操作按钮
        self.generate_btn = QPushButton()
        self.generate_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 8px 16px; font-weight: bold; border: none; font-size: 14px; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.generate_btn.clicked.connect(self._generate_gif)
        settings_layout.addWidget(self.generate_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        settings_layout.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setWordWrap(True)
        settings_layout.addWidget(self.status_label)

        settings_layout.addStretch()
        splitter.addWidget(settings_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, stretch=1)

        self._log_widget = None
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label
        self.retranslate_ui()

    def retranslate_ui(self):
        self.folder_label.setText(self.tr("select_folder"))
        self.browse_btn.setText(self.tr("browse"))
        self.load_btn.setText(self.tr("load_images"))
        self.preview_label.setText(self.tr("thumbnails"))
        self.select_all_btn.setText(self.tr("select_all"))
        self.deselect_all_btn.setText(self.tr("deselect_all"))
        self.reverse_btn.setText(self.tr("reverse_selection"))
        self.fps_label.setText(self.tr("gif_fps"))
        self.size_label.setText(self.tr("gif_size"))
        self.loop_label.setText(self.tr("gif_loop"))
        self.interval_btn.setText(self.tr("gif_interval_select"))
        self.out_label.setText(self.tr("gif_output_name"))
        self.generate_btn.setText(self.tr("gif_generate"))
        self.count_label.setText(self.tr("gif_no_images"))

    # ---------- 图片加载 ----------

    def _select_folder(self):
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.folder_entry.setText(folder)

    def _load_images(self):
        folder = self.folder_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            return

        supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff')
        files = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(supported):
                files.append(os.path.join(folder, f))

        if not files:
            self.status_label.setText(self.tr("gif_no_images"))
            return

        self.image_files = files
        self._build_list()

        # 自动获取第一张图片的分辨率作为GIF输出尺寸
        first = QPixmap(files[0])
        if not first.isNull():
            self.width_spin.setValue(first.width())
            self.height_spin.setValue(first.height())

        self.status_label.setText(f"已加载 {len(files)} 张图片")
        self._update_count()

    def _build_list(self):
        """构建带复选框的缩略图列表"""
        self.image_list.clear()
        for path in self.image_files:
            name = os.path.basename(path)
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                icon = QIcon(pixmap.scaled(
                    80, 56, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                icon = QIcon()

            item = QListWidgetItem(icon, name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.image_list.addItem(item)

    def _update_count(self):
        checked = sum(1 for i in range(self.image_list.count())
                      if self.image_list.item(i).checkState() == Qt.CheckState.Checked)
        self.count_label.setText(
            f"已勾选 {checked}/{self.image_list.count()}")
        self.generate_btn.setEnabled(checked > 0)

    # ---------- 选择操作 ----------

    def _select_all(self):
        for i in range(self.image_list.count()):
            self.image_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._update_count()

    def _deselect_all(self):
        for i in range(self.image_list.count()):
            self.image_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._update_count()

    def _reverse_selection(self):
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            new_state = (Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                         else Qt.CheckState.Checked)
            item.setCheckState(new_state)
        self._update_count()

    def _select_interval(self):
        """间隔勾选：从第1张开始，每隔N张勾选一张，不取消已有勾选"""
        interval = self.interval_spin.value()
        self.image_list.itemChanged.disconnect()
        for i in range(0, self.image_list.count(), interval):
            self.image_list.item(i).setCheckState(Qt.CheckState.Checked)
        self.image_list.itemChanged.connect(lambda: self._update_count())
        self._update_count()

    # ---------- GIF生成 ----------

    def _generate_gif(self):
        """收集勾选的图片，启动后台线程生成GIF"""
        # 按列表顺序收集已勾选的图片路径
        selected = []
        for i in range(self.image_list.count()):
            item = self.image_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))

        if not selected:
            QMessageBox.warning(self, self.tr("warning_title"),
                                self.tr("gif_select_first"))
            return

        # 输出路径
        folder = self.folder_path or os.path.dirname(selected[0])
        filename = self.out_entry.text().strip()
        if not filename.endswith('.gif'):
            filename += '.gif'
        output_path = os.path.join(folder, filename)

        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, self.tr("warning_title"),
                f"文件 {filename} 已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 参数
        fps = self.fps_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()
        loop = self.loop_spin.value()

        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在生成GIF...")

        def run():
            try:
                from PIL import Image
                frames = []
                total = len(selected)

                for idx, path in enumerate(selected):
                    with Image.open(path) as img:
                        if img.mode == 'RGBA':
                            # 转RGB（GIF不支持透明）
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        if img.size != (width, height):
                            img = img.resize((width, height), Image.Resampling.LANCZOS)
                        frames.append(img.copy())

                    self._gif_progress.emit(f"处理中... {idx + 1}/{total}")
                    self._gif_bar.emit(idx + 1, total)

                if not frames:
                    self._gif_finished.emit("FAIL|没有可用的图片帧")
                    return

                duration = int(1000 / fps)
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=duration,
                    loop=loop,
                    optimize=True
                )

                file_size = os.path.getsize(output_path)
                self._gif_finished.emit(
                    f"OK|{output_path}|{len(frames)}|{file_size}")

            except Exception as e:
                self._gif_finished.emit(f"FAIL|{str(e)}")

        threading.Thread(target=run, daemon=True).start()

    def _on_progress_msg(self, msg: str):
        self.status_label.setText(msg)

    def _on_progress_bar(self, current: int, total: int):
        """进度条更新 — 在主线程执行"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_gif_done(self, msg: str):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if msg.startswith("OK|"):
            _, path, frames, size = msg.split("|")
            size_kb = int(size) / 1024
            self.status_label.setText(
                f"GIF生成完成! {frames}帧, {size_kb:.0f}KB\n{path}")
            QMessageBox.information(
                self, self.tr("info_title"),
                f"GIF生成完成!\n{int(frames)} 帧\n{size_kb:.0f} KB\n\n"
                f"保存至: {path}")
        elif msg.startswith("FAIL|"):
            error = msg[5:]
            self.status_label.setText(f"生成失败: {error}")
        else:
            self.status_label.setText(f"生成失败: {msg}")
