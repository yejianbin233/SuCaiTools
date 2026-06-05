"""
Caption编辑器面板

加载图片文件夹，自动匹配中英文标注文件（name.txt / name_en.txt），
支持图片缩略图浏览、编辑、保存和翻译。
"""

import os
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QScrollArea, QMessageBox, QFileDialog, QSplitter,
    QListWidget, QListWidgetItem, QCheckBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThreadPool, Signal, QTimer, QSize, QObject
from PySide6.QtGui import QPixmap, QIcon

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit
from core.base_worker import BaseWorker


class CaptionPanel(BaseToolPanel):
    """Caption编辑器面板 — 图片标注编辑+中英翻译"""

    # 翻译线程 → 主线程 安全信号
    _translate_result = Signal(str)
    _translate_error = Signal(str)
    _translate_progress = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_path: str = ""
        # caption_pairs: [(图片路径, 中文txt路径, 英文txt路径)]
        self.caption_pairs: list[tuple[str, str, str]] = []
        self.current_index: int = -1
        self.translator_config: dict = {
            'current_service': 'google',
            'secret_id': '',
            'secret_key': '',
            'ai_service': None,
            'ai_api_key': ''
        }
        self._pending_target: QTextEdit | None = None
        self._batch_mode: bool = False
        self._load_translator_config()
        self._setup_ui()

        # 持久信号连接（不反复断开/重连）
        self._translate_result.connect(self._on_translate_result)
        self._translate_error.connect(self._on_translate_error)
        self._translate_progress.connect(self._on_translate_progress)

    # ---------- 翻译器配置 ----------

    def _load_translator_config(self):
        """加载腾讯云API密钥配置"""
        try:
            import json
            key_path = Path(__file__).parent.parent / "caption" / "tentcent_secretkey.json"
            if key_path.exists():
                with open(key_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.translator_config['secret_id'] = data.get('SecretId', '')
                self.translator_config['secret_key'] = data.get('SecretKey', '')
        except Exception:
            pass

    # ---------- UI构建 ----------

    def _setup_ui(self):
        """创建界面布局"""
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # ---- 顶部：文件夹选择 + 加载 ----
        top_layout = QGridLayout()
        self.folder_label = QLabel()
        top_layout.addWidget(self.folder_label, 0, 0)
        self.folder_entry = DragDropFolderLineEdit()
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        top_layout.addWidget(self.folder_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        top_layout.addWidget(self.browse_btn, 0, 2)
        self.load_btn = QPushButton()
        self.load_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        self.load_btn.clicked.connect(self._load_images)
        top_layout.addWidget(self.load_btn, 0, 3)
        layout.addLayout(top_layout)

        # ---- 中部：缩略图列表 + 图片预览 + 文本编辑 ----
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：缩略图列表
        thumb_panel = QWidget()
        thumb_layout = QVBoxLayout(thumb_panel)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)

        self.thumb_label = QLabel()
        self.thumb_label.setStyleSheet("font-weight: bold;")
        thumb_layout.addWidget(self.thumb_label)

        self.thumb_list = QListWidget()
        self.thumb_list.setIconSize(QSize(80, 60))
        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        # 支持多选 + 复选框勾选
        self.thumb_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.thumb_list.setMovement(QListWidget.Movement.Static)
        self.thumb_list.setSpacing(4)
        self.thumb_list.setMinimumWidth(260)
        self.thumb_list.setMaximumWidth(300)
        self.thumb_list.itemClicked.connect(self._on_thumb_clicked)
        thumb_layout.addWidget(self.thumb_list)

        # 缩略图操作按钮
        thumb_btns = QHBoxLayout()
        self.thumb_select_all_btn = QPushButton()
        self.thumb_select_all_btn.clicked.connect(self._thumb_select_all)
        thumb_btns.addWidget(self.thumb_select_all_btn)
        self.thumb_deselect_btn = QPushButton()
        self.thumb_deselect_btn.clicked.connect(self._thumb_deselect_all)
        thumb_btns.addWidget(self.thumb_deselect_btn)
        self.thumb_delete_btn = QPushButton()
        self.thumb_delete_btn.clicked.connect(self._thumb_delete_selected)
        self.thumb_delete_btn.setStyleSheet("color: #c42b1c;")
        thumb_btns.addWidget(self.thumb_delete_btn)
        thumb_layout.addLayout(thumb_btns)

        main_splitter.addWidget(thumb_panel)

        # 中间：图片预览 + 导航
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # 导航栏
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton()
        self.prev_btn.clicked.connect(self._prev_image)
        nav_layout.addWidget(self.prev_btn)
        self.index_label = QLabel("0/0")
        self.index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.index_label.setMinimumWidth(60)
        nav_layout.addWidget(self.index_label)
        self.next_btn = QPushButton()
        self.next_btn.clicked.connect(self._next_image)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addStretch()
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self._save_changes)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 4px 12px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }")
        nav_layout.addWidget(self.save_btn)
        center_layout.addLayout(nav_layout)

        # 图片显示
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(350, 280)
        self.image_label.setStyleSheet(
            "background-color: #e8e8e8; border: 1px solid #ccc;")
        center_layout.addWidget(self.image_label, stretch=1)

        main_splitter.addWidget(center_panel)

        # 右侧：文本编辑
        text_panel = QWidget()
        text_layout = QVBoxLayout(text_panel)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        # 中文标注
        cn_group = QGroupBox()
        cn_layout = QVBoxLayout(cn_group)
        cn_header = QHBoxLayout()
        self.cn_label = QLabel()
        cn_header.addWidget(self.cn_label)
        cn_header.addStretch()
        self.cn_translate_btn = QPushButton()
        self.cn_translate_btn.clicked.connect(self._translate_cn_to_en)
        cn_header.addWidget(self.cn_translate_btn)
        cn_layout.addLayout(cn_header)
        self.cn_text = QTextEdit()
        self.cn_text.setPlaceholderText("中文标注 (name.txt)")
        self.cn_text.setMinimumWidth(250)
        cn_layout.addWidget(self.cn_text)
        text_layout.addWidget(cn_group)

        # 英文标注
        en_group = QGroupBox()
        en_layout = QVBoxLayout(en_group)
        en_header = QHBoxLayout()
        self.en_label = QLabel()
        en_header.addWidget(self.en_label)
        en_header.addStretch()
        self.en_translate_btn = QPushButton()
        self.en_translate_btn.clicked.connect(self._translate_en_to_cn)
        en_header.addWidget(self.en_translate_btn)
        en_layout.addLayout(en_header)
        self.en_text = QTextEdit()
        self.en_text.setPlaceholderText("English caption (name_en.txt)")
        self.en_text.setMinimumWidth(250)
        en_layout.addWidget(self.en_text)
        text_layout.addWidget(en_group)

        main_splitter.addWidget(text_panel)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setStretchFactor(2, 2)
        layout.addWidget(main_splitter, stretch=1)

        # ---- 底部：状态 + 批量操作 ----
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        self.batch_translate_btn = QPushButton()
        self.batch_translate_btn.clicked.connect(self._batch_translate)
        bottom_layout.addWidget(self.batch_translate_btn)
        self.config_btn = QPushButton()
        self.config_btn.clicked.connect(self._open_config)
        bottom_layout.addWidget(self.config_btn)
        layout.addLayout(bottom_layout)

        self._status_label = self.status_label
        self.retranslate_ui()

    def retranslate_ui(self):
        """更新UI文本"""
        self.folder_label.setText(self.tr("select_folder"))
        self.browse_btn.setText(self.tr("browse"))
        self.load_btn.setText(self.tr("load_images"))
        self.thumb_label.setText(self.tr("thumbnails"))
        self.thumb_select_all_btn.setText(self.tr("select_all"))
        self.thumb_deselect_btn.setText(self.tr("deselect_all"))
        self.thumb_delete_btn.setText(self.tr("delete"))
        self.prev_btn.setText("◀ " + self.tr("prev"))
        self.next_btn.setText(self.tr("next") + " ▶")
        self.save_btn.setText(self.tr("save"))
        self.cn_label.setText(self.tr("chinese_caption") + " (name.txt)")
        self.cn_translate_btn.setText(self.tr("translate_cn_to_en"))
        self.en_label.setText(self.tr("english_caption") + " (name_en.txt)")
        self.en_translate_btn.setText(self.tr("translate_en_to_cn"))
        self.batch_translate_btn.setText(self.tr("batch_translate"))
        self.config_btn.setText(self.tr("translator_config"))

    # ---------- 图片加载 ----------

    def _select_folder(self):
        """选择图片文件夹"""
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.folder_entry.setText(folder)

    def _load_images(self):
        """加载文件夹中的图片和对应标注文件

        文件匹配规则（与原版一致）：
        - 图片: *.png, *.jpg, *.jpeg, *.bmp, *.gif, *.webp
        - 中文标注: 图片名.txt  (如 image.png → image.txt)
        - 英文标注: 图片名_en.txt (如 image.png → image_en.txt)
        """
        folder = self.folder_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            self.show_error(self.tr("error_title"),
                            self.tr("pe_error_no_frames"))
            return

        # 扫描图片文件
        supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff')
        image_files = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(supported):
                image_files.append(os.path.join(folder, f))

        if not image_files:
            self.show_error(self.tr("error_title"),
                            self.tr("pe_error_no_frames"))
            return

        # 匹配标注文件
        self.caption_pairs = []
        for img_path in image_files:
            base = os.path.splitext(img_path)[0]
            # 中文: name.txt（与原版一致）
            cn_txt = base + '.txt'
            # 英文: name_en.txt（与原版一致）
            en_txt = base + '_en.txt'
            self.caption_pairs.append((img_path, cn_txt, en_txt))

        self.folder_path = folder
        self.current_index = 0

        # 填充缩略图列表
        self._build_thumbnail_list()

        self.status_label.setText(
            f"已加载 {len(self.caption_pairs)} 组图片/标注")
        self._display_current()

    def _build_thumbnail_list(self):
        """构建缩略图列表（每项带复选框）"""
        self.thumb_list.clear()
        for img_path, cn_txt, en_txt in self.caption_pairs:
            name = os.path.basename(img_path)
            has_cn = os.path.exists(cn_txt) if cn_txt else False
            has_en = os.path.exists(en_txt) if en_txt else False

            # 缩略图
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                icon = QIcon(pixmap.scaled(
                    80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                icon = QIcon()

            # 显示名称+标注状态
            status = ""
            if has_cn:
                status += "中"
            if has_en:
                status += "英" if not status else "/英"
            display = name if not status else f"{name} [{status}]"

            item = QListWidgetItem(icon, display)
            item.setData(Qt.ItemDataRole.UserRole, img_path)
            item.setToolTip(
                f"{name}\n中文: {'✓' if has_cn else '✗'}\n英文: {'✓' if has_en else '✗'}")
            # 添加复选框，默认未勾选
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.thumb_list.addItem(item)

    def _on_thumb_clicked(self, item: QListWidgetItem):
        """缩略图被点击→跳转到对应图片（仅当点击非复选框区域时）"""
        img_path = item.data(Qt.ItemDataRole.UserRole)
        for i, pair in enumerate(self.caption_pairs):
            if pair[0] == img_path:
                self.current_index = i
                self._display_current()
                break

    # ---------- 缩略图批量操作 ----------

    def _thumb_select_all(self):
        """全选复选框"""
        for i in range(self.thumb_list.count()):
            self.thumb_list.item(i).setCheckState(Qt.CheckState.Checked)

    def _thumb_deselect_all(self):
        """取消全选复选框"""
        for i in range(self.thumb_list.count()):
            self.thumb_list.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _thumb_delete_selected(self):
        """删除已勾选的图片（同时删除对应的中英文txt文件）"""
        # 收集所有被勾选的项
        checked_items = []
        for i in range(self.thumb_list.count()):
            item = self.thumb_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_items.append(item)

        if not checked_items:
            QMessageBox.information(self, "提示", "请先勾选要删除的图片")
            return

        count = len(checked_items)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {count} 张图片及其标注文件吗？\n\n"
            "（将同时删除: 图片文件、.txt 中文标注、_en.txt 英文标注）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        for item in checked_items:
            img_path = item.data(Qt.ItemDataRole.UserRole)
            # 找到对应的caption_pair并删除所有关联文件
            for pair in list(self.caption_pairs):
                if pair[0] == img_path:
                    img_file, cn_txt, en_txt = pair
                    files_to_delete = [img_file]
                    if cn_txt and os.path.exists(cn_txt):
                        files_to_delete.append(cn_txt)
                    if en_txt and os.path.exists(en_txt):
                        files_to_delete.append(en_txt)
                    for path in files_to_delete:
                        try:
                            os.remove(path)
                        except OSError as e:
                            self.status_label.setText(f"删除失败: {e}")
                    self.caption_pairs.remove(pair)
                    deleted += 1
                    break

        # 重建缩略图列表
        self._build_thumbnail_list()
        if self.current_index >= len(self.caption_pairs):
            self.current_index = max(0, len(self.caption_pairs) - 1)
        self._display_current()
        self.status_label.setText(f"已删除 {deleted} 张图片及标注文件")

    # ---------- 当前图片显示 ----------

    def _display_current(self):
        """显示当前索引的图片和标注"""
        if not self.caption_pairs:
            self.image_label.setText("无图片")
            self.cn_text.clear()
            self.en_text.clear()
            return

        total = len(self.caption_pairs)
        if self.current_index < 0:
            self.current_index = 0
        elif self.current_index >= total:
            self.current_index = total - 1

        img_path, cn_txt, en_txt = self.caption_pairs[self.current_index]

        # 显示图片
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                max(1, self.image_label.width() - 8),
                max(1, self.image_label.height() - 8),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        else:
            self.image_label.setText("无法加载图片")

        # 加载中文标注 (name.txt)
        self.cn_text.clear()
        if cn_txt and os.path.exists(cn_txt):
            try:
                with open(cn_txt, 'r', encoding='utf-8') as f:
                    self.cn_text.setPlainText(f.read())
            except Exception:
                pass

        # 加载英文标注 (name_en.txt)
        self.en_text.clear()
        if en_txt and os.path.exists(en_txt):
            try:
                with open(en_txt, 'r', encoding='utf-8') as f:
                    self.en_text.setPlainText(f.read())
            except Exception:
                pass

        # 更新UI状态
        self.index_label.setText(f"{self.current_index + 1}/{total}")
        self.status_label.setText(
            f"[{self.current_index + 1}/{total}] {os.path.basename(img_path)}")

        # 同步缩略图列表选中
        self.thumb_list.blockSignals(True)
        self.thumb_list.setCurrentRow(self.current_index)
        self.thumb_list.blockSignals(False)

        # 启用/禁用导航按钮
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < total - 1)

    # ---------- 导航 ----------

    def _prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._display_current()

    def _next_image(self):
        if self.current_index < len(self.caption_pairs) - 1:
            self.current_index += 1
            self._display_current()

    # ---------- 保存 ----------

    def _save_changes(self):
        """保存中文和英文标注到文件"""
        if not self.caption_pairs or self.current_index < 0:
            return

        img_path, _, _ = self.caption_pairs[self.current_index]
        base = os.path.splitext(img_path)[0]

        # 保存中文标注到 name.txt
        cn_path = base + '.txt'
        cn_text = self.cn_text.toPlainText().strip()
        if cn_text:
            with open(cn_path, 'w', encoding='utf-8') as f:
                f.write(cn_text)

        # 保存英文标注到 name_en.txt
        en_path = base + '_en.txt'
        en_text = self.en_text.toPlainText().strip()
        if en_text:
            with open(en_path, 'w', encoding='utf-8') as f:
                f.write(en_text)

        # 更新pair记录
        self.caption_pairs[self.current_index] = (img_path, cn_path, en_path)

        name = os.path.basename(img_path)
        self.status_label.setText(f"已保存: {name}")
        self._build_thumbnail_list()

    # ---------- 翻译回调（主线程） ----------

    def _on_translate_result(self, text: str):
        """翻译结果回调 — 在主线程执行"""
        if self._batch_mode:
            # 批量模式：仅更新进度文字
            self.status_label.setText(text)
        else:
            # 单条模式：写入目标文本框
            if self._pending_target:
                self._pending_target.setPlainText(text)
            self.status_label.setText(self.tr("completed"))

    def _on_translate_error(self, err_msg: str):
        """翻译错误回调 — 在主线程执行"""
        self.status_label.setText(f"翻译失败: {err_msg}")

    def _on_translate_progress(self, msg: str):
        """翻译进度回调 — 在主线程执行"""
        self.status_label.setText(msg)

    # ---------- 单条翻译 ----------

    def _translate_cn_to_en(self):
        text = self.cn_text.toPlainText().strip()
        if not text:
            return
        self._do_translate(text, 'cn_to_en', self.en_text)

    def _translate_en_to_cn(self):
        text = self.en_text.toPlainText().strip()
        if not text:
            return
        self._do_translate(text, 'en_to_cn', self.cn_text)

    def _do_translate(self, text: str, direction: str, target_edit: QTextEdit):
        """执行单条翻译"""
        self._batch_mode = False
        self._pending_target = target_edit
        self.status_label.setText(self.tr("processing"))

        def run_translate():
            try:
                from caption.translator_manager import TranslatorManager
                service = self._get_service()
                config = dict(self.translator_config)
                translator = TranslatorManager.get_translator(service, config)
                result = (translator.translate_to_english(text) if direction == 'cn_to_en'
                          else translator.translate_to_chinese(text))
                self._translate_result.emit(result)
            except Exception as e:
                self._translate_error.emit(str(e))

        threading.Thread(target=run_translate, daemon=True).start()

    # ---------- 批量翻译 ----------

    def _get_service(self) -> str:
        """获取可用的翻译服务"""
        service = self.translator_config.get('current_service', 'google')
        if service == 'tencent':
            sid = self.translator_config.get('secret_id', '')
            skey = self.translator_config.get('secret_key', '')
            if not sid or not skey:
                return 'google'
        return service

    def _batch_translate(self):
        """批量翻译：将所有中文标注翻译为英文"""
        if not self.caption_pairs:
            return

        # 先保存当前编辑
        self._save_changes()

        # 统计需要翻译的数量
        pending = sum(1 for _, cn, en in self.caption_pairs
                     if os.path.exists(cn) and not os.path.exists(en))
        if pending == 0:
            self.status_label.setText("所有英文标注已存在，无需翻译")
            return

        reply = QMessageBox.question(
            self, self.tr("pe_confirm_extract_title"),
            f"批量翻译 {pending}/{len(self.caption_pairs)} 组中文→英文标注?\n\n"
            f"(仅处理还没有 _en.txt 的图片)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._batch_mode = True
        self._pending_target = None
        self._translate_progress.emit(f"批量翻译中... 0/{pending}")

        def run_batch():
            from caption.translator_manager import TranslatorManager
            service = self._get_service()
            translator = TranslatorManager.get_translator(service, dict(self.translator_config))
            done = 0
            errors = 0

            for i, (img_path, cn_txt, en_txt) in enumerate(self.caption_pairs):
                # 如果英文文件已存在，跳过
                if os.path.exists(en_txt) or not os.path.exists(cn_txt):
                    continue
                try:
                    with open(cn_txt, 'r', encoding='utf-8') as f:
                        text = f.read().strip()
                    if not text:
                        continue
                    result = translator.translate_to_english(text)
                    with open(en_txt, 'w', encoding='utf-8') as f:
                        f.write(result)
                    # 更新内存中的pair
                    self.caption_pairs[i] = (img_path, cn_txt, en_txt)
                    done += 1
                    # 实时进度
                    self._translate_progress.emit(
                        f"批量翻译中... {done}/{pending}  [{os.path.basename(img_path)}]")
                except Exception as e:
                    errors += 1
                    self._translate_progress.emit(
                        f"批量翻译中... {done}/{pending}  "
                        f"跳过: {os.path.basename(img_path)}")

            # 完成
            self._batch_mode = False
            err_info = f", {errors}个失败" if errors > 0 else ""
            self._translate_progress.emit(
                f"批量翻译完成! {done}/{pending} 成功{err_info}")
            # 刷新界面
            QTimer.singleShot(0, lambda: (
                self._build_thumbnail_list(),
                self._display_current()))

        threading.Thread(target=run_batch, daemon=True).start()

    # ---------- 配置 ----------

    def _open_config(self):
        QMessageBox.information(
            self, self.tr("translator_config"),
            "翻译服务配置: caption/tentcent_secretkey.json\n"
            "支持的服务: tencent(腾讯云), baidu(百度), google, openai, deepseek\n\n"
            "密钥格式:\n"
            '{"SecretId":"...", "SecretKey":"..."}')
