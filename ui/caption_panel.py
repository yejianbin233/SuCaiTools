"""
Caption编辑器面板

加载图片文件夹，自动匹配中英文标注文件（name.txt / name_en.txt），
支持图片缩略图浏览、编辑、保存和翻译。
"""

import os
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox,
    QScrollArea, QMessageBox, QFileDialog, QSplitter,
    QListWidget, QListWidgetItem, QCheckBox, QAbstractItemView,
    QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QThreadPool, Signal, QTimer, QSize, QObject
from PySide6.QtGui import QPixmap, QIcon

from core.base_panel import BaseToolPanel
from core.utils import DragDropFolderLineEdit, natural_sort_key
from core.base_worker import BaseWorker


# ---------- 文件夹列表子窗口 ----------

class FolderListDialog(QDialog):
    """文件夹列表子窗口 — 可滚动显示筛选后的Train_*文件夹

    支持直接点击选择要工作的文件夹，双击或点击确定切换到所选文件夹。
    """

    folder_selected = Signal(str)  # 发射选中的文件夹路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件夹列表")
        self.setMinimumSize(450, 500)
        self.resize(500, 600)
        self.setModal(False)  # 非模态，方便持续使用

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 顶部信息标签
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: gray;")
        layout.addWidget(self.info_label)

        # 搜索/筛选
        search_layout = QHBoxLayout()
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("搜索文件夹名...")
        self.search_entry.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self.search_entry)

        self.unprocessed_only_cb = QCheckBox("仅显示未处理")
        self.unprocessed_only_cb.toggled.connect(self._apply_filter)
        search_layout.addWidget(self.unprocessed_only_cb)
        layout.addLayout(search_layout)

        # 文件夹列表
        self.folder_list = QListWidget()
        self.folder_list.setAlternatingRowColors(True)
        self.folder_list.itemDoubleClicked.connect(self._on_item_activated)
        layout.addWidget(self.folder_list, stretch=1)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.goto_btn = QPushButton("跳转到选中文件夹")
        self.goto_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        self.goto_btn.clicked.connect(self._on_goto_clicked)
        btn_layout.addStretch()
        btn_layout.addWidget(self.goto_btn)
        layout.addLayout(btn_layout)

        # 全量数据（由外部设置）
        self._all_tasks: list[dict] = []

    def set_tasks(self, tasks: list[dict]):
        """设置任务列表并刷新显示

        参数:
            tasks: [{"folder": str, "folder_name": str, "processed_time": str|None}, ...]
        """
        self._all_tasks = tasks
        self._apply_filter()

    def _apply_filter(self):
        """根据搜索文本和未处理筛选重建列表"""
        self.folder_list.clear()
        search_text = self.search_entry.text().strip().lower()
        unprocessed_only = self.unprocessed_only_cb.isChecked()

        filtered = []
        for task in self._all_tasks:
            name = task.get('folder_name', '')
            processed = task.get('processed_time')

            # 未处理筛选
            if unprocessed_only and processed:
                continue
            # 搜索文本筛选
            if search_text and search_text not in name.lower():
                continue
            filtered.append(task)

        for task in filtered:
            name = task['folder_name']
            processed = task.get('processed_time')
            if processed:
                display = f"✓ {name}  [{processed}]"
                tip = f"已处理: {processed}"
            else:
                display = f"✗ {name}  (未处理)"
                tip = "未处理"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, task['folder'])
            item.setToolTip(tip)
            # 未处理的用粗体
            if not processed:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.folder_list.addItem(item)

        self.info_label.setText(
            f"共 {len(filtered)} 个文件夹 (总计 {len(self._all_tasks)} 个)")

    def _on_item_activated(self, item: QListWidgetItem):
        """双击项目 → 选中并关闭"""
        folder = item.data(Qt.ItemDataRole.UserRole)
        self.folder_selected.emit(folder)
        self.accept()

    def _on_goto_clicked(self):
        """点击跳转按钮"""
        current = self.folder_list.currentItem()
        if current:
            folder = current.data(Qt.ItemDataRole.UserRole)
            self.folder_selected.emit(folder)
            self.accept()
        else:
            QMessageBox.information(self, "提示", "请先选择一个文件夹")


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

        # 工作区任务状态（基于JSON维护）
        self.workspace_path: str = ""           # 父文件夹路径
        self.tasks: list[dict] = []             # [{"folder": str, "folder_name": str, "processed_time": str|None}, ...]
        self.filtered_tasks: list[dict] = []    # 筛选后的任务列表（与tasks相同对象的子集）
        self.current_task_index: int = -1       # 当前在filtered_tasks中的索引
        self.filter_unprocessed: bool = False   # 是否仅显示未处理
        self._folder_dialog: FolderListDialog | None = None  # 文件夹列表子窗口
        self.translator_config: dict = {
            'current_service': 'google',
            'secret_id': '',
            'secret_key': '',
            'ai_service': None,
            'ai_api_key': ''
        }
        self._pending_target: QTextEdit | None = None
        self._batch_mode: bool = False
        self._batch_stop: bool = False
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

        # ---- 第1行：工作区选择 + 扫描 ----
        ws_layout = QGridLayout()
        self.workspace_label = QLabel()
        ws_layout.addWidget(self.workspace_label, 0, 0)
        self.workspace_entry = DragDropFolderLineEdit()
        self.workspace_entry.textChanged.connect(
            lambda t: setattr(self, 'workspace_path', t.strip()))
        ws_layout.addWidget(self.workspace_entry, 0, 1)
        self.workspace_browse_btn = QPushButton()
        self.workspace_browse_btn.clicked.connect(self._select_workspace)
        ws_layout.addWidget(self.workspace_browse_btn, 0, 2)
        self.scan_btn = QPushButton()
        self.scan_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        self.scan_btn.clicked.connect(self._scan_workspace)
        ws_layout.addWidget(self.scan_btn, 0, 3)
        layout.addLayout(ws_layout)

        # ---- 第2行：文件夹导航（上一文件夹/下一文件夹/筛选/列表） ----
        nav_layout = QHBoxLayout()
        self.prev_folder_btn = QPushButton()
        self.prev_folder_btn.setEnabled(False)
        self.prev_folder_btn.clicked.connect(self._prev_folder)
        nav_layout.addWidget(self.prev_folder_btn)
        self.folder_index_label = QLabel("0/0")
        self.folder_index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.folder_index_label.setMinimumWidth(80)
        nav_layout.addWidget(self.folder_index_label)
        self.next_folder_btn = QPushButton()
        self.next_folder_btn.setEnabled(False)
        self.next_folder_btn.clicked.connect(self._next_folder)
        nav_layout.addWidget(self.next_folder_btn)
        nav_layout.addSpacing(12)
        self.filter_toggle_btn = QPushButton()
        self.filter_toggle_btn.setCheckable(True)
        self.filter_toggle_btn.setChecked(False)
        self.filter_toggle_btn.clicked.connect(self._toggle_filter)
        nav_layout.addWidget(self.filter_toggle_btn)
        self.folder_list_btn = QPushButton()
        self.folder_list_btn.clicked.connect(self._open_folder_list)
        nav_layout.addWidget(self.folder_list_btn)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        # ---- 第3行：当前文件夹选择 + 加载 ----
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
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }")
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
        self.batch_stop_btn = QPushButton()
        self.batch_stop_btn.clicked.connect(self._stop_batch_translate)
        self.batch_stop_btn.setVisible(False)
        self.batch_stop_btn.setStyleSheet("color: #c42b1c;")
        bottom_layout.addWidget(self.batch_stop_btn)
        self.config_btn = QPushButton()
        self.config_btn.clicked.connect(self._open_config)
        bottom_layout.addWidget(self.config_btn)
        layout.addLayout(bottom_layout)

        self._status_label = self.status_label
        self.retranslate_ui()

    def retranslate_ui(self):
        """更新UI文本"""
        # 工作区行
        self.workspace_label.setText(self.tr("workspace"))
        self.workspace_browse_btn.setText(self.tr("browse"))
        self.scan_btn.setText(self.tr("scan"))
        # 导航行
        self.prev_folder_btn.setText("◀◀ " + self.tr("prev_folder"))
        self.next_folder_btn.setText(self.tr("next_folder") + " ▶▶")
        self._update_filter_btn_text()
        self.folder_list_btn.setText("📋 " + self.tr("folder_list_btn"))
        # 当前文件夹行
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
        self.batch_stop_btn.setText(self.tr("stop"))
        self.config_btn.setText(self.tr("translator_config"))

    # ---------- 工作区管理 ----------

    def _select_workspace(self):
        """浏览选择工作区文件夹"""
        folder = self.browse_folder(self.tr("select_folder"))
        if folder:
            self.workspace_entry.setText(folder)
            # 选择后自动扫描
            self._scan_workspace()

    def _scan_workspace(self):
        """递归扫描工作区下所有 Train_ 前缀的子文件夹，构建任务列表并加载JSON状态

        扫描逻辑:
        1. 递归遍历工作区下所有层级，找出 Train_* 文件夹
        2. 加载 .caption_tasks.json（如存在），合并已处理状态
        3. 新的 Train_* 文件夹自动加入任务列表（未处理）
        4. folder_name 使用相对路径以避免同名冲突
        """
        ws = self.workspace_entry.text().strip()
        if not ws or not os.path.isdir(ws):
            self.show_error(self.tr("error_title"),
                            self.tr("pe_error_no_frames"))
            return

        self.workspace_path = ws

        # 加载已有的任务状态JSON
        old_tasks = self._load_task_state()

        # 递归扫描所有 Train_* 文件夹（不检查内容，仅按文件夹名前缀匹配）
        disk_folders: dict[str, str] = {}  # {相对路径名: 绝对路径}
        try:
            for root, dirs, _ in os.walk(ws):
                dirs.sort(key=natural_sort_key)
                for d in dirs:
                    if d.startswith('Train_'):
                        sub_path = os.path.join(root, d)
                        rel_path = os.path.relpath(sub_path, ws)
                        disk_folders[rel_path] = sub_path
        except OSError:
            self.show_error(self.tr("error_title"),
                            "无法读取工作区文件夹")
            return

        # 构建旧任务查找表
        old_task_map: dict[str, dict] = {
            t['folder']: t for t in old_tasks
        }

        # 构建新任务列表（仅包含磁盘上存在的 Train_* 文件夹）
        self.tasks = []
        for name, full_path in disk_folders.items():
            old = old_task_map.get(full_path)
            self.tasks.append({
                'folder': full_path,
                'folder_name': name,
                'processed_time': old.get('processed_time') if old else None,
            })

        # 保存任务状态（同步磁盘变化）
        self._save_task_state()

        # 构建筛选列表
        self._rebuild_filtered_tasks()

        if not self.filtered_tasks:
            self.status_label.setText(self.tr("no_subfolders"))
            self.folder_index_label.setText("0/0")
            self.prev_folder_btn.setEnabled(False)
            self.next_folder_btn.setEnabled(False)
            self.folder_list_btn.setEnabled(False)
            return

        self.status_label.setText(
            self.tr("scan_complete").format(count=len(self.filtered_tasks)))
        self.folder_list_btn.setEnabled(True)

        # 自动加载第一个
        self._navigate_to_task(0)

    # ---------- 任务状态JSON持久化 ----------

    def _get_task_file_path(self) -> str:
        """获取任务状态JSON文件路径"""
        return os.path.join(self.workspace_path, '.caption_tasks.json')

    def _load_task_state(self) -> list[dict]:
        """从JSON文件加载任务状态"""
        task_file = self._get_task_file_path()
        if os.path.exists(task_file):
            try:
                import json
                with open(task_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('tasks', [])
            except Exception:
                return []
        return []

    def _save_task_state(self):
        """持久化任务状态到JSON文件"""
        if not self.workspace_path or not self.tasks:
            return
        try:
            import json
            task_file = self._get_task_file_path()
            data = {
                'workspace': self.workspace_path,
                'tasks': self.tasks,
            }
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.status_label.setText(f"保存任务状态失败: {e}")

    def _mark_folder_processed(self, folder: str):
        """标记某任务文件夹已处理（记录当前时间）

        只有属于tasks列表中的文件夹才会被标记。
        已处理过的保留首次处理时间，不覆盖。
        """
        if not folder or not self.tasks:
            return
        for task in self.tasks:
            if task['folder'] == folder:
                if task.get('processed_time'):
                    return  # 已处理过，保留首次时间
                task['processed_time'] = datetime.now().isoformat(
                    sep='T', timespec='seconds')
                self._save_task_state()
                return

    # ---------- 文件夹筛选与导航 ----------

    def _rebuild_filtered_tasks(self):
        """根据filter_unprocessed重建filtered_tasks"""
        if self.filter_unprocessed:
            self.filtered_tasks = [
                t for t in self.tasks
                if not t.get('processed_time')
            ]
        else:
            self.filtered_tasks = list(self.tasks)

    def _update_folder_nav_ui(self):
        """更新文件夹导航UI状态"""
        total = len(self.filtered_tasks)
        if total == 0:
            self.folder_index_label.setText("0/0")
            self.prev_folder_btn.setEnabled(False)
            self.next_folder_btn.setEnabled(False)
            return
        idx = self.current_task_index
        self.folder_index_label.setText(
            self.tr("folder_index").format(current=idx + 1, total=total))
        self.prev_folder_btn.setEnabled(idx > 0)
        self.next_folder_btn.setEnabled(idx < total - 1)

    def _navigate_to_task(self, index: int):
        """导航到筛选列表中指定索引的任务并加载"""
        if index < 0 or index >= len(self.filtered_tasks):
            return
        self.current_task_index = index
        folder = self.filtered_tasks[index]['folder']
        self.folder_entry.setText(folder)
        self._update_folder_nav_ui()
        self._load_images()

    def _prev_folder(self):
        """导航到上一个文件夹"""
        if self.current_task_index > 0:
            self._navigate_to_task(self.current_task_index - 1)

    def _next_folder(self):
        """导航到下一个文件夹"""
        if self.current_task_index < len(self.filtered_tasks) - 1:
            self._navigate_to_task(self.current_task_index + 1)

    def _toggle_filter(self):
        """切换筛选状态（全部 / 仅显示未处理）"""
        self.filter_unprocessed = self.filter_toggle_btn.isChecked()
        self._update_filter_btn_text()

        # 记住当前文件夹路径，用于筛选后定位
        current_folder = self.folder_path

        self._rebuild_filtered_tasks()

        if not self.filtered_tasks:
            self.folder_index_label.setText("0/0")
            self.prev_folder_btn.setEnabled(False)
            self.next_folder_btn.setEnabled(False)
            self.status_label.setText(self.tr("no_subfolders"))
            return

        # 尝试定位到当前文件夹在筛选列表中的位置
        new_index = 0
        for i, task in enumerate(self.filtered_tasks):
            if task['folder'] == current_folder:
                new_index = i
                break

        self.status_label.setText(
            self.tr("scan_complete").format(count=len(self.filtered_tasks)))
        self._navigate_to_task(new_index)

    def _update_filter_btn_text(self):
        """更新筛选按钮文本"""
        if self.filter_unprocessed:
            self.filter_toggle_btn.setText("📋 " + self.tr("show_all"))
        else:
            self.filter_toggle_btn.setText("📋 " + self.tr("filter_unprocessed"))

    # ---------- 文件夹列表子窗口 ----------

    def _open_folder_list(self):
        """打开文件夹列表子窗口"""
        if not self.tasks:
            QMessageBox.information(self, "提示", "请先扫描工作区")
            return

        # 复用已有对话框，更新数据
        if self._folder_dialog is None:
            self._folder_dialog = FolderListDialog(self.window())
            self._folder_dialog.folder_selected.connect(
                self._on_folder_dialog_selected)
            # 同步筛选状态
            self._folder_dialog.unprocessed_only_cb.setChecked(
                self.filter_unprocessed)

        self._folder_dialog.set_tasks(self.tasks)
        self._folder_dialog.show()
        self._folder_dialog.raise_()
        self._folder_dialog.activateWindow()

    def _on_folder_dialog_selected(self, folder: str):
        """子窗口中选择了文件夹 → 导航到该文件夹"""
        # 在filtered_tasks中查找索引
        for i, task in enumerate(self.filtered_tasks):
            if task['folder'] == folder:
                self._navigate_to_task(i)
                return
        # 如果不在筛选列表中（如筛选未处理但选了已处理的），
        # 临时切换到显示全部，然后导航
        for i, task in enumerate(self.tasks):
            if task['folder'] == folder:
                self.filter_unprocessed = False
                self.filter_toggle_btn.setChecked(False)
                self._update_filter_btn_text()
                self._rebuild_filtered_tasks()
                self._navigate_to_task(i)
                return

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
        for f in sorted(os.listdir(folder), key=natural_sort_key):
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
            # 中文: name_cn.txt (如 laser_0001#0001.gif → laser_0001#0001_cn.txt)
            cn_txt = base + '_cn.txt'
            # 英文: name_en.txt (如 laser_0001#0001.gif → laser_0001#0001_en.txt)
            en_txt = base + '_en.txt'
            self.caption_pairs.append((img_path, cn_txt, en_txt))

        self.folder_path = folder
        self.current_index = 0

        # 记录处理状态（仅tasks中的文件夹）
        self._mark_folder_processed(folder)

        # 如果手动加载的文件夹在筛选任务列表中，同步导航索引
        if self.filtered_tasks:
            for i, task in enumerate(self.filtered_tasks):
                if task['folder'] == folder:
                    self.current_task_index = i
                    self._update_folder_nav_ui()
                    break

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

        # 保存中文标注到 name_cn.txt
        cn_path = base + '_cn.txt'
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

    def _stop_batch_translate(self):
        """停止批量翻译"""
        self._batch_stop = True
        self.batch_stop_btn.setEnabled(False)
        self.status_label.setText("正在停止...")

    def _on_batch_done(self):
        """批量翻译完成/中断后的UI恢复"""
        self.batch_translate_btn.setVisible(True)
        self.batch_stop_btn.setVisible(False)
        self.batch_stop_btn.setEnabled(True)
        if self.caption_pairs:
            self._build_thumbnail_list()
            self._display_current()

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
        """批量翻译TXT：遍历文件夹，将中文.txt翻译为英文_en.txt

        规则:
        1. 只处理 .txt 文件（非 _en.txt）
        2. 必须有对应的图片文件（.png/.jpg等）
        3. 必须不存在对应的 _en.txt 文件
        """
        folder = self.folder_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            # 尝试使用已加载的 caption_pairs
            if not self.caption_pairs:
                self.status_label.setText("请先选择文件夹或加载图片")
                return
            # 没有文件夹但有已加载数据，使用老逻辑
            self._save_changes()
            pairs = self.caption_pairs
        else:
            # 递归扫描文件夹及所有子文件夹 — 从txt出发匹配图片
            self._save_changes()
            img_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
            pairs = []
            for root, _, files in os.walk(folder):
                for f in sorted(files, key=natural_sort_key):
                    if not f.endswith('.txt') or f.endswith('_en.txt'):
                        continue
                    base = os.path.splitext(f)[0]
                    txt_path = os.path.join(root, f)
                    en_path = os.path.join(root, f"{base}_en.txt")
                    # 检查是否有对应图片（同目录下）
                    has_image = any(
                        os.path.exists(os.path.join(root, f"{base}{ext}"))
                        for ext in img_exts)
                    if has_image:
                        pairs.append((os.path.join(root, f"{base}.png"), txt_path, en_path))

        if not pairs:
            self.status_label.setText("没有找到需要翻译的TXT文件")
            return

        # 统计待处理
        pending = sum(1 for _, cn, en in pairs
                     if os.path.exists(cn) and not os.path.exists(en))
        if pending == 0:
            self.status_label.setText("所有英文标注已存在，无需翻译")
            return

        reply = QMessageBox.question(
            self, self.tr("pe_confirm_extract_title"),
            f"批量翻译 {pending} 个中文TXT → 英文_en.txt?\n\n"
            f"(递归扫描: {folder if folder else '已加载'})\n"
            f"条件: 有对应图片 + 无_en.txt",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._batch_mode = True
        self._batch_stop = False
        self._pending_target = None
        self.batch_translate_btn.setVisible(False)
        self.batch_stop_btn.setVisible(True)
        self._translate_progress.emit(f"批量翻译中... 0/{pending}")

        def run_batch():
            from caption.translator_manager import TranslatorManager
            service = self._get_service()
            translator = TranslatorManager.get_translator(service, dict(self.translator_config))
            done = 0
            errors = 0

            for i, (img_path, cn_txt, en_txt) in enumerate(pairs):
                if self._batch_stop:
                    break
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
                    done += 1
                    self._translate_progress.emit(
                        f"批量翻译中... {done}/{pending}  "
                        f"[{cn_txt}]")
                except Exception as e:
                    errors += 1
                    self._translate_progress.emit(
                        f"批量翻译中... {done}/{pending}  "
                        f"跳过: {cn_txt} ({e})")

            self._batch_mode = False
            if self._batch_stop:
                self._translate_progress.emit(
                    f"翻译已中断 ({done}/{pending})")
            else:
                err_info = f", {errors}个失败" if errors > 0 else ""
                self._translate_progress.emit(
                    f"批量翻译完成! {done}/{pending} 成功{err_info}")
            QTimer.singleShot(0, self._on_batch_done)

        threading.Thread(target=run_batch, daemon=True).start()

    # ---------- 配置 ----------

    def _open_config(self):
        QMessageBox.information(
            self, self.tr("translator_config"),
            "翻译服务配置: caption/tentcent_secretkey.json\n"
            "支持的服务: tencent(腾讯云), baidu(百度), google, openai, deepseek\n\n"
            "密钥格式:\n"
            '{"SecretId":"...", "SecretKey":"..."}')
