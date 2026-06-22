"""
AnythingLLM 批量文件上传工具面板

核心流程:
1. 选择本地文件夹 → 自动加载 .gitignore 规则过滤
2. 扫描所有文件 (递归) → 应用 gitignore + 自动排除规则 → 生成追踪记录
3. 拖拽/按钮二次筛选 → 左侧树：来源文件 | 右侧树：待上传列表
4. 点击「同步」→ 删除本地已删文件的旧版本 + 修改文件的旧版本 (不上传)
5. 点击「开始上传」→ 逐个上传 → 增量同步 (仅更新变化的文件) → 添加到工作区
6. 工作区名称 = 所选文件夹的名称 (如：/data/project → "project")

文件状态说明:
- 📄 [新增] = 从未上传过的文件
- 📄 [更新] = 本地已修改的文件 (大小或修改时间变化)
- 绿色   = 新文件 / 未上传过但追踪中存在
- 黄色   = 已修改 (需删除旧版本后重新上传)
- 青色   = 待上传 (追踪中有记录但未上传过)
- 灰色   = 已上传且无变化 (自动跳过)

跨列表拖拽:
- 支持在同一面板的两个树之间拖拽文件
- 选中文件夹时会自动包含其所有子文件
- 同一树内的拖放会被忽略 (避免误操作)
"""

import os
import json
import requests
from pathlib import Path

import pathspec

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QGroupBox, QMessageBox, QFileDialog,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QSplitter, QHeaderView
)
from PySide6.QtCore import Qt, QThreadPool, QMimeData, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDrag

from core.base_panel import BaseToolPanel
from core.base_worker import BaseWorker, WorkerSignals
from core.utils import DragDropFolderLineEdit, format_file_size


# ============================================================
# 跨列表拖拽 QTreeWidget
# ============================================================

class _DraggableTreeWidget(QTreeWidget):
    """支持跨控件拖拽的树形文件列表

    两个树均可拖出（Drag）和放入（Drop），选中文件夹拖拽时连带所有子文件。
    同一控件内的拖放被忽略。
    """

    def __init__(self, parent=None, drag_enabled: bool = True,
                 drop_enabled: bool = True):
        super().__init__(parent)
        self._drag_enabled = drag_enabled
        self._drop_enabled = drop_enabled

        if drag_enabled:
            self.setDragEnabled(True)
        if drop_enabled:
            self.setAcceptDrops(True)
        if drag_enabled and drop_enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        elif drop_enabled:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        self._panel: 'AnythingLLMUploadPanel' | None = None

    # ---- 拖拽开始 ----

    def startDrag(self, supportedActions):
        """开始拖拽 — 收集选中项的所有文件路径（含文件夹下的子文件）"""
        if not self._drag_enabled:
            return

        items = self.selectedItems()
        if not items:
            return

        paths = self._collect_paths_from_items(items)
        if not paths:
            return

        mime = QMimeData()
        mime.setData("application/x-filelist",
                     "\n".join(paths).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.DropAction.MoveAction)

    def _collect_paths_from_items(self, items: list[QTreeWidgetItem]) -> list[str]:
        """从选中项中递归收集所有文件路径"""
        paths: list[str] = []
        seen = set()

        def _walk(item: QTreeWidgetItem):
            abs_path = item.data(0, Qt.ItemDataRole.UserRole)
            if abs_path:
                # 是文件节点
                if abs_path not in seen:
                    paths.append(abs_path)
                    seen.add(abs_path)
            # 无论是否为文件夹，都遍历子节点（文件夹下的文件）
            for i in range(item.childCount()):
                _walk(item.child(i))

        for item in items:
            _walk(item)
        return paths

    # ---- 拖拽进入 / 移动 ----

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._drop_enabled and event.mimeData().hasFormat(
                "application/x-filelist"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._drop_enabled and event.mimeData().hasFormat(
                "application/x-filelist"):
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---- 放置 ----

    def dropEvent(self, event: QDropEvent):
        """接收拖放 — 将文件从来源树移动到本树"""
        if not self._drop_enabled or not self._panel:
            event.ignore()
            return

        data = event.mimeData().data("application/x-filelist")
        if not data:
            event.ignore()
            return

        paths = data.data().decode("utf-8").split("\n")
        paths = [p.strip() for p in paths if p.strip()]
        if not paths:
            event.ignore()
            return

        source = event.source()
        if source is self:
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
            return

        if self is self._panel.right_tree:
            self._panel._move_files_to_right(paths)
        elif self is self._panel.left_tree:
            self._panel._move_files_to_left(paths)

        event.acceptProposedAction()

    # ---- 辅助：文件计数（只算文件节点，不算文件夹） ----

    def file_count(self) -> int:
        """递归统计树中的文件节点数"""
        def _count(item: QTreeWidgetItem) -> int:
            n = 1 if item.data(0, Qt.ItemDataRole.UserRole) else 0
            for i in range(item.childCount()):
                n += _count(item.child(i))
            return n
        total = 0
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            total += _count(root.child(i))
        return total


# ============================================================
# 扫描 Worker
# ============================================================

class ScanSignals(WorkerSignals):
    """扫描专用信号 —— 扩展基础信号，新增批量文件通知"""
    file_found = Signal(list)  # list[dict]


# 自动排除的目录名（构建产物、依赖、IDE 配置等）
_AUTO_EXCLUDE_DIRS = frozenset({
    '.git', '__pycache__', 'node_modules',
    '.venv', 'venv', '.env',
    '.idea', '.vscode', '.vs',
    'dist', 'build', '.egg-info',
})

# 自动排除的文件后缀（AnythingLLM 明确拒绝的二进制/非文本类型）
_AUTO_EXCLUDE_SUFFIXES = frozenset({
    '.pyc', '.pyo',
})

_SCAN_BATCH_SIZE = 80
_LIST_FLUSH_BATCHES = 5
_TRACKING_FILE = ".allm_track.json"


def _load_tracking(folder: str) -> dict:
    """加载追踪文件，key 为 rel_path，value 为 {name, size, mtime}"""
    path = os.path.join(folder, _TRACKING_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_tracking(folder: str, data: dict):
    """保存追踪文件"""
    path = os.path.join(folder, _TRACKING_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _delete_documents(base_url: str, api_key: str,
                      names: list[str]) -> tuple[int, int]:
    """调用 DELETE /api/system/remove-documents 删除文档

    返回 (deleted, failed) 计数。
    """
    if not names:
        return 0, 0
    base = base_url.rstrip('/')
    try:
        resp = requests.delete(
            f"{base}/api/system/remove-documents",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"names": names},
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get("success"):
                return len(names), 0
        return 0, len(names)
    except Exception:
        return 0, len(names)


def _normalize_location(raw: str) -> str:
    """将 AnythingLLM 返回的 location 归一化为相对路径

    桌面版可能返回绝对路径如 C:/Users/.../custom-documents/file.json，
    工作区 API 要求相对路径 custom-documents/file.json。
    """
    loc = raw.replace('\\', '/')
    marker = 'custom-documents'
    idx = loc.find(marker)
    if idx >= 0:
        loc = loc[idx:]
    return loc


class ScanFolderWorker(BaseWorker):
    """后台扫描文件夹，应用 gitignore 过滤

    每 _SCAN_BATCH_SIZE 个文件发射一次 file_found，
    界面端日志实时输出，树控件仅在多批次后批量刷新。
    """

    def __init__(self, folder_path: str, gitignore_spec,
                 ignore_enabled: bool):
        super().__init__()
        self.signals = ScanSignals()
        self.folder_path = folder_path
        self.gitignore_spec = gitignore_spec
        self.ignore_enabled = ignore_enabled

    def run(self):
        base = Path(self.folder_path)
        count = 0
        filtered = 0
        batch: list[dict] = []

        def _flush_batch():
            if batch:
                self.signals.file_found.emit(batch)
                batch.clear()

        for file_path in base.rglob("*"):
            if self._stop_flag:
                break
            if not file_path.is_file():
                continue

            # 排除追踪文件自身
            if file_path.name == _TRACKING_FILE:
                filtered += 1
                continue

            # 自动排除：目录名匹配
            if _AUTO_EXCLUDE_DIRS.intersection(file_path.parts):
                filtered += 1
                continue

            # 自动排除：文件后缀匹配
            if file_path.suffix.lower() in _AUTO_EXCLUDE_SUFFIXES:
                filtered += 1
                continue

            if self._should_filter(file_path, base):
                filtered += 1
                continue

            try:
                st = file_path.stat()
                size = st.st_size
                mtime = st.st_mtime
            except OSError:
                size = 0
                mtime = 0

            count += 1
            batch.append({
                'abs_path': str(file_path),
                'rel_path': str(file_path.relative_to(base)),
                'size': size,
                'mtime': mtime,
            })

            if len(batch) >= _SCAN_BATCH_SIZE:
                _flush_batch()

        _flush_batch()

        self.signals.finished.emit({
            'success': True,
            'count': count,
            'filtered': filtered,
            'folder': self.folder_path,
        })

    def _should_filter(self, file_path: Path, base_dir: Path) -> bool:
        if not self.ignore_enabled or self.gitignore_spec is None:
            return False
        try:
            rel_path = file_path.relative_to(base_dir)
            return self.gitignore_spec.match_file(str(rel_path))
        except ValueError:
            return False


# ============================================================
# 上传 Worker
# ============================================================

class AnythingLLMUploadWorker(BaseWorker):
    """逐个上传文件到 AnythingLLM 并添加到工作区

    对已修改的文件先删除旧版本再上传新版本，实现增量同步。
    """

    def __init__(self, files: list[dict], base_url: str, api_key: str,
                 workspace: str, old_docs: dict[str, str] | None = None):
        """
        参数:
            files: [{'abs_path': ..., 'rel_dir': ..., 'rel_path': ...}, ...]
            old_docs: {rel_path: old_doc_name}  需要先删除的旧文档
        """
        super().__init__()
        self.files = files
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.workspace = workspace
        self.old_docs = old_docs or {}

    def run(self):
        total = len(self.files)
        uploaded = 0
        failed = 0
        doc_locations: list[str] = []
        new_tracking: dict[str, dict] = {}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        # 批量删除旧文档（修改过的文件）
        old_names = list(self.old_docs.values())
        if old_names:
            self.signals.log.emit(
                f"\n清理 {len(old_names)} 个旧版本文档...")
            deleted, del_failed = _delete_documents(
                self.base_url, self.api_key, old_names)
            if deleted > 0:
                self.signals.log.emit(f"  ✓ 已删除 {deleted} 个旧版本")
            if del_failed > 0:
                self.signals.log.emit(
                    f"  ⚠ {del_failed} 个旧版本删除失败（将尝试覆盖上传）")

        for idx, finfo in enumerate(self.files):
            if self._stop_flag:
                break

            file_path = finfo['abs_path']
            rel_dir = finfo.get('rel_dir', '')
            rel_path = finfo.get('rel_path', '')
            filename = os.path.basename(file_path)
            status = finfo.get('status', '')

            # 标签
            tag = ""
            if status == "modified":
                tag = " [更新]"
            elif status == "new":
                tag = " [新增]"

            try:
                if rel_dir:
                    upload_url = f"{self.base_url}/api/v1/document/upload"
                    self.signals.log.emit(
                        f"[{idx + 1}/{total}] 上传{tag}: {filename} → {rel_dir}")
                    with open(file_path, 'rb') as f:
                        resp = requests.post(
                            upload_url,
                            headers=headers,
                            files={"file": (filename, f)},
                            data={"folder": rel_dir},
                            timeout=120
                        )
                else:
                    upload_url = f"{self.base_url}/api/v1/document/upload"
                    self.signals.log.emit(
                        f"[{idx + 1}/{total}] 上传{tag}: {filename}")
                    with open(file_path, 'rb') as f:
                        resp = requests.post(
                            upload_url,
                            headers=headers,
                            files={"file": (filename, f)},
                            timeout=120
                        )

                # 解析响应
                result = None
                try:
                    result = resp.json()
                except Exception:
                    pass

                # 代码此处省略原来的 500 回退逻辑，直接检查状态码
                if resp.status_code != 200:
                    err_body = ""
                    try:
                        err_body = f" — {resp.text[:200]}"
                    except Exception:
                        pass
                    self.signals.log.emit(
                        f"  ✗ {filename} 上传失败: HTTP "
                        f"{resp.status_code}{err_body}")
                    failed += 1
                    self.signals.progress.emit(idx + 1, total)
                    continue

                # result 已在上方解析
                if not result or not result.get("success"):
                    self.signals.log.emit(
                        f"  ✗ {filename} 上传失败: "
                        f"{result.get('error', '未知错误')}")
                    failed += 1
                    self.signals.progress.emit(idx + 1, total)
                    continue

                documents = result.get("documents", [])
                if not documents:
                    self.signals.log.emit(
                        f"  ✗ {filename} 上传失败: 响应中无文档信息")
                    failed += 1
                    self.signals.progress.emit(idx + 1, total)
                    continue

                location = documents[0].get("location", "")
                if location:
                    location = _normalize_location(location)
                    doc_locations.append(location)

                # 构建追踪条目
                if rel_path:
                    try:
                        mtime = os.path.getmtime(file_path)
                    except OSError:
                        mtime = 0
                    try:
                        size = os.path.getsize(file_path)
                    except OSError:
                        size = 0
                    new_tracking[rel_path] = {
                        "name": location,
                        "size": size,
                        "mtime": mtime,
                    }

                uploaded += 1
                self.signals.log.emit(
                    f"  ✓ {filename} 上传成功 ({location})")

            except requests.exceptions.ConnectionError:
                self.signals.log.emit(
                    f"  ✗ {filename} 连接失败: 无法连接到 {self.base_url}")
                failed += 1
            except requests.exceptions.Timeout:
                self.signals.log.emit(f"  ✗ {filename} 上传超时")
                failed += 1
            except Exception as e:
                self.signals.log.emit(f"  ✗ {filename} 异常: {str(e)}")
                failed += 1

            self.signals.progress.emit(idx + 1, total)

        # 添加到工作区
        if doc_locations and self.workspace:
            self.signals.log.emit(
                f"\n正在将 {len(doc_locations)} 个文档添加到工作区 "
                f"'{self.workspace}'...")
            try:
                resp = requests.post(
                    f"{self.base_url}/api/v1/workspace/"
                    f"{self.workspace}/update-embeddings",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"adds": doc_locations},
                    timeout=60
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("success"):
                        self.signals.log.emit(
                            f"  ✓ 已添加到工作区 '{self.workspace}'")
                    else:
                        self.signals.log.emit(
                            f"  ⚠ 工作区添加失败: "
                            f"{result.get('error', '未知错误')}")
                else:
                    err_body = ""
                    try:
                        err_body = f" — {resp.text[:200]}"
                    except Exception:
                        pass
                    self.signals.log.emit(
                        f"  ⚠ 工作区添加失败: HTTP {resp.status_code}"
                        f"{err_body}")
            except Exception as e:
                self.signals.log.emit(f"  ⚠ 工作区添加异常: {str(e)}")

        self.signals.finished.emit({
            'success': uploaded > 0,
            'uploaded': uploaded,
            'failed': failed,
            'locations': doc_locations,
            'tracking': new_tracking,
        })


# ============================================================
# 面板主类
# ============================================================

class AnythingLLMUploadPanel(BaseToolPanel):
    """AnythingLLM 批量文件上传面板"""

    def __init__(self, parent=None):
        self.folder_path: str = ""
        self.gitignore_spec: pathspec.PathSpec | None = None
        self.current_gitignore_path: Path | None = None
        self.ignore_enabled: bool = True

        self._source_files: set[str] = set()
        self._pending_files: set[str] = set()

        self.root_name: str = ""
        self.worker: AnythingLLMUploadWorker | None = None
        self.scan_worker: ScanFolderWorker | None = None

        self._scan_buffer: list[dict] = []
        self._batches_since_flush: int = 0

        # 增量同步：{rel_path: {name, size, mtime}}
        self._tracking: dict = {}
        # 当前扫描文件的元数据缓存：{rel_path: {size, mtime}}
        self._track_data: dict[str, dict] = {}
        # 本地已删除的文件：{rel_path: doc_name}（上传时从 AnythingLLM 中删除）
        self._deleted_docs: dict[str, str] = {}

        super().__init__(parent)
        self._setup_ui()

    # ---------- UI 构建 ----------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ---- 文件夹选择 ----
        folder_group = QGroupBox()
        folder_layout = QGridLayout(folder_group)
        self.folder_label = QLabel()
        folder_layout.addWidget(self.folder_label, 0, 0)
        self.folder_entry = DragDropFolderLineEdit()
        self.folder_entry.setPlaceholderText("拖放文件夹到此处或点击浏览...")
        self.folder_entry.textChanged.connect(
            lambda t: setattr(self, 'folder_path', t.strip()))
        folder_layout.addWidget(self.folder_entry, 0, 1)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.browse_btn, 0, 2)
        self.scan_btn = QPushButton()
        self.scan_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; color: white; "
            "padding: 6px 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #1084e0; }")
        self.scan_btn.clicked.connect(self._scan_folder)
        folder_layout.addWidget(self.scan_btn, 0, 3)
        layout.addWidget(folder_group)

        # ---- 服务配置 ----
        config_group = QGroupBox()
        config_layout = QGridLayout(config_group)
        self.url_label = QLabel()
        config_layout.addWidget(self.url_label, 0, 0)
        self.url_entry = QLineEdit()
        self.url_entry.setText("http://localhost:3001")
        self.url_entry.setPlaceholderText("http://localhost:3001")
        config_layout.addWidget(self.url_entry, 0, 1)
        self.apikey_label = QLabel()
        config_layout.addWidget(self.apikey_label, 1, 0)
        self.apikey_entry = QLineEdit()
        self.apikey_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.apikey_entry.setPlaceholderText("输入 AnythingLLM API Key...")
        self.apikey_entry.textChanged.connect(
            lambda: (self._update_upload_btn(), self._update_sync_btn()))
        config_layout.addWidget(self.apikey_entry, 1, 1)
        self.workspace_label = QLabel()
        config_layout.addWidget(self.workspace_label, 2, 0)
        self.workspace_display = QLabel()
        self.workspace_display.setStyleSheet(
            "color: #0078d4; font-weight: bold;")
        config_layout.addWidget(self.workspace_display, 2, 1)
        layout.addWidget(config_group)

        # ---- .gitignore 控制栏 ----
        gitignore_layout = QHBoxLayout()
        self.ignore_check = QCheckBox()
        self.ignore_check.setChecked(True)
        self.ignore_check.stateChanged.connect(self._on_ignore_toggle)
        gitignore_layout.addWidget(self.ignore_check)
        self.load_gitignore_btn = QPushButton()
        self.load_gitignore_btn.clicked.connect(self._load_gitignore_dialog)
        gitignore_layout.addWidget(self.load_gitignore_btn)
        self.gitignore_status = QLabel()
        self.gitignore_status.setStyleSheet("color: gray;")
        gitignore_layout.addWidget(self.gitignore_status)
        gitignore_layout.addStretch()
        layout.addLayout(gitignore_layout)

        # ---- 中部：双树 + 移动按钮 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：来源文件
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        self.source_label = QLabel()
        self.source_label.setStyleSheet("font-weight: bold;")
        left_layout.addWidget(self.source_label)

        self.left_tree = _DraggableTreeWidget(drag_enabled=True, drop_enabled=True)
        self.left_tree._panel = self
        self.left_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.left_tree.setHeaderHidden(True)
        self.left_tree.setColumnCount(1)
        self.left_tree.setIndentation(20)
        self.left_tree.setAnimated(True)
        left_layout.addWidget(self.left_tree)

        left_btns = QHBoxLayout()
        self.expand_all_btn = QPushButton()
        self.expand_all_btn.clicked.connect(self.left_tree.expandAll)
        left_btns.addWidget(self.expand_all_btn)
        self.collapse_all_btn = QPushButton()
        self.collapse_all_btn.clicked.connect(self.left_tree.collapseAll)
        left_btns.addWidget(self.collapse_all_btn)
        left_btns.addStretch()
        left_layout.addLayout(left_btns)

        splitter.addWidget(left_panel)

        # 中间：移动按钮
        move_panel = QWidget()
        move_layout = QVBoxLayout(move_panel)
        move_layout.setContentsMargins(4, 0, 4, 0)
        move_layout.addStretch()
        self.move_right_btn = QPushButton(">>")
        self.move_right_btn.setToolTip("将选中的文件/文件夹移到待上传列表")
        self.move_right_btn.clicked.connect(self._move_selected_to_right)
        move_layout.addWidget(self.move_right_btn)
        self.move_left_btn = QPushButton("<<")
        self.move_left_btn.setToolTip("将选中的文件/文件夹移回来源列表")
        self.move_left_btn.clicked.connect(self._move_selected_to_left)
        move_layout.addWidget(self.move_left_btn)
        self.move_all_right_btn = QPushButton(">")
        self.move_all_right_btn.setToolTip("将所有文件移到待上传列表")
        self.move_all_right_btn.clicked.connect(self._move_all_to_right)
        move_layout.addWidget(self.move_all_right_btn)
        self.move_all_left_btn = QPushButton("<")
        self.move_all_left_btn.setToolTip("将所有文件移回来源列表")
        self.move_all_left_btn.clicked.connect(self._move_all_to_left)
        move_layout.addWidget(self.move_all_left_btn)
        move_layout.addStretch()
        splitter.addWidget(move_panel)

        # 右侧：待上传文件
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        self.pending_label = QLabel()
        self.pending_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.pending_label)

        self.right_tree = _DraggableTreeWidget(drag_enabled=True, drop_enabled=True)
        self.right_tree._panel = self
        self.right_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.right_tree.setHeaderHidden(True)
        self.right_tree.setColumnCount(1)
        self.right_tree.setIndentation(20)
        self.right_tree.setAnimated(True)
        right_layout.addWidget(self.right_tree)

        right_btns = QHBoxLayout()
        self.select_all_right_btn = QPushButton()
        self.select_all_right_btn.clicked.connect(
            lambda: self.right_tree.selectAll())
        right_btns.addWidget(self.select_all_right_btn)
        self.remove_btn = QPushButton()
        self.remove_btn.clicked.connect(self._remove_selected_from_right)
        right_btns.addWidget(self.remove_btn)
        right_btns.addStretch()
        right_layout.addLayout(right_btns)

        splitter.addWidget(right_panel)

        splitter.setSizes([350, 60, 350])
        layout.addWidget(splitter)

        # ---- 操作栏 ----
        action_layout = QHBoxLayout()
        self.sync_btn = QPushButton()
        self.sync_btn.setStyleSheet(
            "QPushButton { background-color: #d83b01; color: white; "
            "padding: 6px 16px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #ea4a12; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.sync_btn.clicked.connect(self._start_sync)
        self.sync_btn.setEnabled(False)
        self.sync_btn.setToolTip("只清理 AnythingLLM 中的无效文档，不上传文件")
        action_layout.addWidget(self.sync_btn)
        self.upload_btn = QPushButton()
        self.upload_btn.setStyleSheet(
            "QPushButton { background-color: #107c10; color: white; "
            "padding: 6px 20px; font-weight: bold; border: none; }"
            "QPushButton:hover { background-color: #138a13; }"
            "QPushButton:disabled { background-color: #d0d0d0; color: #888; }")
        self.upload_btn.clicked.connect(self._start_upload)
        self.upload_btn.setEnabled(False)
        action_layout.addWidget(self.upload_btn)
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
        self.log_area.setMinimumHeight(150)
        layout.addWidget(self.log_area)

        self._log_widget = self.log_area
        self._progress_bar = self.progress_bar
        self._status_label = self.status_label

        self.retranslate_ui()

    # ---------- 语言切换 ----------

    def retranslate_ui(self):
        self.folder_label.setText(self.tr("allm_folder"))
        self.browse_btn.setText(self.tr("browse"))
        self.scan_btn.setText(self.tr("allm_scan"))
        self.url_label.setText(self.tr("allm_url"))
        self.apikey_label.setText(self.tr("allm_api_key"))
        self.workspace_label.setText(self.tr("allm_workspace"))
        self.ignore_check.setText(self.tr("allm_enable_gitignore"))
        self.load_gitignore_btn.setText(self.tr("allm_load_gitignore"))
        self.source_label.setText(self.tr("allm_source_files"))
        self.pending_label.setText(self.tr("allm_pending_files"))
        self.expand_all_btn.setText(self.tr("allm_expand_all"))
        self.collapse_all_btn.setText(self.tr("allm_collapse_all"))
        self.select_all_right_btn.setText(self.tr("allm_select_all"))
        self.remove_btn.setText(self.tr("allm_remove_selected"))
        self.sync_btn.setText(self.tr("allm_sync"))
        self.upload_btn.setText(self.tr("allm_start_upload"))
        self.status_label.setText(self.tr("status_idle"))
        self._update_list_labels()

    # ---------- 文件夹选择 ----------

    def _select_folder(self):
        folder = self.browse_folder(self.tr("allm_folder"))
        if folder:
            self.folder_entry.setText(folder)

    # ---------- 扫描 ----------

    def _scan_folder(self):
        folder = self.folder_entry.text().strip()
        if not folder or not os.path.isdir(folder):
            self.show_error(self.tr("error_title"), "请先选择有效的文件夹")
            return

        self.folder_path = folder
        self.log_area.clear()
        self.log(f"📂 扫描文件夹: {folder}")

        # 工作区名 = 所选文件夹本身的名称
        self.root_name = os.path.basename(folder)
        self.workspace_display.setText(self.root_name)
        self.log(f"工作区: {self.root_name}")

        self._auto_load_gitignore(Path(folder))

        # 加载追踪文件，用于自动跳过未变化文件
        self._tracking = _load_tracking(folder)
        self._auto_skipped = 0
        self._new_count = 0
        self._modified_count = 0
        self._not_uploaded_count = 0

        # 清空树、缓冲区和元数据缓存
        self.left_tree.clear()
        self.right_tree.clear()
        self._source_files.clear()
        self._pending_files.clear()
        self._scan_buffer.clear()
        self._track_data.clear()
        self._batches_since_flush = 0

        self.set_processing(True)
        self.scan_btn.setEnabled(False)
        self.status_label.setText("扫描中...")

        self.scan_worker = ScanFolderWorker(
            folder, self.gitignore_spec, self.ignore_enabled)
        self.scan_worker.signals.file_found.connect(self._on_file_found)
        self.scan_worker.signals.finished.connect(self._on_scan_finished)
        QThreadPool.globalInstance().start(self.scan_worker)

    def _on_file_found(self, batch: list):
        """每批次回调 — 智能跳过：已上传 + 未变化 → 跳过；未上传 → 显示"""
        filtered_batch = []
        for f_info in batch:
            rel = f_info['rel_path'].replace('\\', '/')
            size = f_info['size']
            mtime = f_info.get('mtime', 0)

            self._track_data[rel] = {'size': size, 'mtime': mtime}

            old = self._tracking.get(rel) if self._tracking else None

            if old is not None:
                # 已在追踪中，检查是否变化
                if (old.get('size') == size and
                        old.get('mtime') == mtime):
                    # 未变化，但只有已上传的才自动跳过
                    if old.get('name'):
                        self._auto_skipped += 1
                        continue
                    # 未上传过 → 仍显示在来源树（状态：待上传）
                    self._source_files.add(f_info['abs_path'])
                    self._not_uploaded_count += 1
                    filtered_batch.append(f_info)
                    continue
                # 已变化 → 修改
                self._source_files.add(f_info['abs_path'])
                self._modified_count += 1
                filtered_batch.append(f_info)
                continue

            # 全新文件
            self._source_files.add(f_info['abs_path'])
            self._new_count += 1
            filtered_batch.append(f_info)

        if not filtered_batch:
            return

        self._scan_buffer.extend(filtered_batch)

        self._batches_since_flush += 1
        total = len(self._scan_buffer)

        if batch:
            sample = batch[-1]
            self.log(f"  已扫描 {total} 个文件 | 最近: {sample['rel_path']}")

        if self._batches_since_flush >= _LIST_FLUSH_BATCHES:
            self._flush_scan_buffer()

        self.status_label.setText(f"扫描中... 已发现 {total} 个文件")
        self._update_list_labels()

    def _flush_scan_buffer(self):
        """将缓冲区文件批量刷入左侧树（文件夹层级结构）"""
        if not self._scan_buffer:
            return

        self.left_tree.setUpdatesEnabled(False)
        try:
            self._insert_files_into_tree(self.left_tree, self._scan_buffer)
        finally:
            self.left_tree.setUpdatesEnabled(True)

        self._scan_buffer.clear()
        self._batches_since_flush = 0

    def _on_scan_finished(self, result: dict):
        self._flush_scan_buffer()

        self.set_processing(False)
        self.scan_btn.setEnabled(True)

        if not result.get('success'):
            self.log("扫描失败")
            return

        count = result.get('count', 0)
        filtered = result.get('filtered', 0)

        # 检测本地已删除的文件（追踪中有但本次扫描没出现）
        self._deleted_docs = {}
        deleted_no_name = 0
        if self._tracking:
            for rel_path, info in self._tracking.items():
                if rel_path not in self._track_data:
                    name = info.get('name', '')
                    if name:
                        self._deleted_docs[rel_path] = name
                    else:
                        deleted_no_name += 1
            # 诊断日志：追踪 vs 扫描的条目数
            self.log(f"  [诊断] 追踪条目: {len(self._tracking)}, "
                     f"本次扫描条目: {len(self._track_data)}, "
                     f"差异: {len(self._tracking) - len(self._track_data)}")

        # 保存全量追踪：所有扫描到的文件 + 保留已有 name
        self._save_full_tracking()

        # 给树节点染色
        self._color_tree_by_status(self.left_tree)

        # 日志摘要
        parts = [f"扫描完成: {count} 个文件"]
        if self._auto_skipped:
            parts.append(f"跳过 {self._auto_skipped} 个(已上传且未变)")
        if self._not_uploaded_count:
            parts.append(f"待上传 {self._not_uploaded_count} 个(追踪中但未上传)")
        if self._new_count:
            parts.append(f"新增 {self._new_count}")
        if self._modified_count:
            parts.append(f"已修改 {self._modified_count}")
        if self._deleted_docs:
            parts.append(f"将删除 {len(self._deleted_docs)} 个(本地已删)")
        if deleted_no_name:
            parts.append(f"追踪移除 {deleted_no_name} 个(本地已删,未上传)")
        if filtered:
            parts.insert(0, f"已过滤 {filtered} 个")
        self.log("，".join(parts))
        self.status_label.setText(
            self.tr("allm_scan_done").format(count=count))
        self._update_list_labels()
        self._update_upload_btn()

    def _save_full_tracking(self):
        """更新追踪文件：已存在的文件更新 size/mtime，新增文件追加，
        已删除文件的条目保留不动（由同步/上传时清理）。
        """
        if not self.folder_path:
            return
        # 基于现有追踪 + 本次扫描数据合并
        merged = dict(self._tracking)  # 保留所有旧条目（含已删除的）
        for rel_path, td in self._track_data.items():
            old = self._tracking.get(rel_path, {}) if self._tracking else {}
            entry = {'size': td['size'], 'mtime': td['mtime']}
            name = old.get('name', '')
            if name:
                entry['name'] = name
            merged[rel_path] = entry  # 更新或新增
        self._tracking = merged
        _save_tracking(self.folder_path, self._tracking)

    def _color_tree_by_status(self, tree: QTreeWidget):
        """根据追踪文件对比结果给树节点染色"""
        def _walk(item: QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                rel = None
                try:
                    rel = os.path.relpath(path, self.folder_path)
                except ValueError:
                    pass
                if rel:
                    rel = rel.replace('\\', '/')
                    old = self._tracking.get(rel) if self._tracking else None
                    td = self._track_data.get(rel, {})
                    if old is None:
                        status = "new"
                        item.setForeground(0, Qt.GlobalColor.darkGreen)
                    elif not old.get('name'):
                        # 追踪中有记录但未上传过 → 待上传
                        status = "not_uploaded"
                        item.setForeground(0, Qt.GlobalColor.darkCyan)
                    elif (old.get('size') != td.get('size', -1) or
                          old.get('mtime') != td.get('mtime', -1)):
                        status = "modified"
                        item.setForeground(0, Qt.GlobalColor.darkYellow)
                    else:
                        status = "unchanged"
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, status)
            for i in range(item.childCount()):
                _walk(item.child(i))

        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            _walk(root.child(i))

    # ---------- 树操作：构建文件夹层级 ----------

    @staticmethod
    def _insert_files_into_tree(tree: QTreeWidget, files_info: list[dict]):
        """将文件列表按相对路径插入树中，自动创建文件夹层级。

        使用文件夹缓存避免重复的子节点遍历。
        """
        files_info = sorted(files_info, key=lambda f: f['rel_path'])

        # 文件夹查找缓存：{parent_id: {child_name: child_item}}
        folder_cache: dict[int, dict[str, QTreeWidgetItem]] = {}

        def _get_folder_child(parent: QTreeWidgetItem,
                              name: str) -> QTreeWidgetItem | None:
            pid = id(parent)
            if pid not in folder_cache:
                cache: dict[str, QTreeWidgetItem] = {}
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    text = child.text(0)
                    # 去掉 📁 前缀拿到纯名称
                    for pfx in ('📁 ', '📄 '):
                        if text.startswith(pfx):
                            cache[text[len(pfx):]] = child
                            break
                folder_cache[pid] = cache
            return folder_cache[pid].get(name)

        def _create_folder(parent: QTreeWidgetItem, name: str) -> QTreeWidgetItem:
            folder = QTreeWidgetItem(parent)
            folder.setText(0, f"📁 {name}")
            folder.setData(0, Qt.ItemDataRole.UserRole, None)
            folder.setFlags(
                folder.flags() | Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable |
                Qt.ItemFlag.ItemIsDragEnabled)
            # 更新缓存
            pid = id(parent)
            if pid in folder_cache:
                folder_cache[pid][name] = folder
            return folder

        for f_info in files_info:
            parts = f_info['rel_path'].replace('\\', '/').split('/')
            parent = tree.invisibleRootItem()

            for part in parts[:-1]:
                folder = _get_folder_child(parent, part)
                if folder is None:
                    folder = _create_folder(parent, part)
                parent = folder

            filename = parts[-1]
            size_str = format_file_size(f_info['size'])
            file_item = QTreeWidgetItem(parent)
            file_item.setText(0, f"📄 {filename}  ({size_str})")
            file_item.setData(0, Qt.ItemDataRole.UserRole,
                              f_info['abs_path'])

    @staticmethod
    def _remove_files_from_tree(tree: QTreeWidget, paths: set[str]):
        """单次树遍历，批量移除指定路径的所有文件节点"""

        def _walk(parent: QTreeWidgetItem):
            i = 0
            while i < parent.childCount():
                child = parent.child(i)
                child_path = child.data(0, Qt.ItemDataRole.UserRole)
                if child_path and child_path in paths:
                    parent.removeChild(child)
                    # 不递增 i，移除后索引自动前移
                    continue
                # 递归处理子节点（无论是否为文件夹）
                _walk(child)
                i += 1

        root = tree.invisibleRootItem()
        _walk(root)
        _cleanup_empty_folders(root)

    @staticmethod
    def _collect_all_file_infos(tree: QTreeWidget,
                                 root_folder: str) -> list[dict]:
        """收集树中所有文件节点的信息：绝对路径 + 相对目录

        返回: [{'abs_path': ..., 'rel_dir': ...}, ...]
           rel_dir = 根文件夹名/子目录路径（正斜杠）。
           例如 root_folder='/data/project', 文件 '/data/project/src/a.py'
           → rel_dir = 'project/src'
        """
        infos: list[dict] = []
        root_name = os.path.basename(root_folder)

        def _walk(item: QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                try:
                    rel = os.path.relpath(os.path.dirname(path), root_folder)
                except ValueError:
                    rel = ''
                if rel == '.':
                    rel = ''
                rel = rel.replace('\\', '/')
                # 前缀根文件夹名
                if rel:
                    rel = root_name + '/' + rel
                else:
                    rel = root_name
                infos.append({'abs_path': path, 'rel_dir': rel})
            for i in range(item.childCount()):
                _walk(item.child(i))

        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            _walk(root.child(i))
        return infos

    # ---------- .gitignore ----------

    def _on_ignore_toggle(self):
        self.ignore_enabled = self.ignore_check.isChecked()
        if self.folder_path:
            self.log(f"{'启用' if self.ignore_enabled else '禁用'}"
                     f" .gitignore 过滤，重新扫描...")
            self._scan_folder()

    def _load_gitignore_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr("allm_load_gitignore"), "",
            "Git忽略文件 (.gitignore);;所有文件 (*.*)"
        )
        if file_path and self._load_gitignore(Path(file_path)):
            if self.folder_path:
                self._scan_folder()

    def _load_gitignore(self, gitignore_path: Path) -> bool:
        if not gitignore_path.exists():
            self.log(f"⚠ 文件不存在: {gitignore_path}")
            return False
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
            self.gitignore_spec = spec
            self.current_gitignore_path = gitignore_path
            rule_count = len(spec.patterns) if spec.patterns else 0
            self.gitignore_status.setText(
                self.tr("allm_gitignore_loaded")
                .format(count=rule_count, name=gitignore_path.name))
            self.gitignore_status.setStyleSheet(
                "color: green; font-weight: bold;")
            self.log(f"✓ 已加载 .gitignore: {gitignore_path} "
                     f"({rule_count} 条规则)")
            return True
        except Exception as e:
            self.log(f"✗ 加载 .gitignore 失败: {e}")
            self.gitignore_status.setText(
                self.tr("allm_gitignore_load_failed"))
            self.gitignore_status.setStyleSheet("color: red;")
            return False

    def _auto_load_gitignore(self, folder_path: Path):
        gitignore_path = folder_path / ".gitignore"
        if gitignore_path.exists():
            self._load_gitignore(gitignore_path)
        else:
            self.gitignore_spec = None
            self.current_gitignore_path = None
            self.gitignore_status.setText(self.tr("allm_no_gitignore"))
            self.gitignore_status.setStyleSheet("color: gray;")

    # ---------- 列表间移动 ----------

    def _move_files_to_right(self, paths: list[str]):
        """将指定文件从左侧批量移到右侧

        暂停两个树的重绘 + 动画 → 一次遍历批量移除 → 一次遍历批量插入
        """
        # 过滤并构建待移动列表
        moved: list[dict] = []
        valid_paths: set[str] = set()
        for file_path in paths:
            if file_path not in self._source_files:
                continue
            valid_paths.add(file_path)
            self._source_files.discard(file_path)
            self._pending_files.add(file_path)
            try:
                rel = os.path.relpath(file_path, self.folder_path)
            except ValueError:
                rel = os.path.basename(file_path)
            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
            moved.append({'abs_path': file_path, 'rel_path': rel,
                          'size': size})

        if not moved:
            return

        # 暂停重绘和动画
        self.left_tree.setUpdatesEnabled(False)
        self.right_tree.setUpdatesEnabled(False)
        self.left_tree.setAnimated(False)
        self.right_tree.setAnimated(False)
        try:
            # 单次遍历批量移除
            self._remove_files_from_tree(self.left_tree, valid_paths)
            self._insert_files_into_tree(self.right_tree, moved)
            self._color_tree_by_status(self.right_tree)
        finally:
            self.left_tree.setAnimated(True)
            self.right_tree.setAnimated(True)
            self.left_tree.setUpdatesEnabled(True)
            self.right_tree.setUpdatesEnabled(True)

        self._update_list_labels()
        self._update_upload_btn()

    def _move_files_to_left(self, paths: list[str]):
        """将指定文件从右侧批量移回左侧"""
        moved: list[dict] = []
        valid_paths: set[str] = set()
        for file_path in paths:
            if file_path not in self._pending_files:
                continue
            valid_paths.add(file_path)
            self._pending_files.discard(file_path)
            self._source_files.add(file_path)
            try:
                rel = os.path.relpath(file_path, self.folder_path)
            except ValueError:
                rel = os.path.basename(file_path)
            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
            moved.append({'abs_path': file_path, 'rel_path': rel,
                          'size': size})

        if not moved:
            return

        self.left_tree.setUpdatesEnabled(False)
        self.right_tree.setUpdatesEnabled(False)
        self.left_tree.setAnimated(False)
        self.right_tree.setAnimated(False)
        try:
            self._remove_files_from_tree(self.right_tree, valid_paths)
            self._insert_files_into_tree(self.left_tree, moved)
            self._color_tree_by_status(self.left_tree)
        finally:
            self.left_tree.setAnimated(True)
            self.right_tree.setAnimated(True)
            self.left_tree.setUpdatesEnabled(True)
            self.right_tree.setUpdatesEnabled(True)

        self._update_list_labels()
        self._update_upload_btn()

    def _move_selected_to_right(self):
        items = self.left_tree.selectedItems()
        paths = self.left_tree._collect_paths_from_items(items)
        self._move_files_to_right(paths)

    def _move_selected_to_left(self):
        items = self.right_tree.selectedItems()
        paths = self.right_tree._collect_paths_from_items(items)
        self._move_files_to_left(paths)

    def _move_all_to_right(self):
        paths = list(self._source_files)
        self._move_files_to_right(paths)

    def _move_all_to_left(self):
        paths = list(self._pending_files)
        self._move_files_to_left(paths)

    def _remove_selected_from_right(self):
        """从右侧移除选中项（直接丢弃，不移回左侧）"""
        items = self.right_tree.selectedItems()
        for item in items:
            self._remove_tree_item_recursive(item, self._pending_files)
        self._update_list_labels()
        self._update_upload_btn()

    def _remove_tree_item_recursive(self, item: QTreeWidgetItem,
                                     file_set: set[str]):
        """递归移除树节点及其子节点，同步清理文件集合"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            file_set.discard(path)
        for i in range(item.childCount()):
            self._remove_tree_item_recursive(item.child(i), file_set)
        parent = item.parent() or item.treeWidget().invisibleRootItem()
        parent.removeChild(item)

    def _update_list_labels(self):
        self.source_label.setText(
            f"{self.tr('allm_source_files')} "
            f"({self.left_tree.file_count()})")
        self.pending_label.setText(
            f"{self.tr('allm_pending_files')} "
            f"({self.right_tree.file_count()})")

    def _update_sync_btn(self):
        """同步按钮：有本地删除 或 右侧有已修改文件时才启用"""
        has_api_key = bool(self.apikey_entry.text().strip())
        can_sync = (bool(self._deleted_docs) or
                    self._has_modified_in_right_tree())
        self.sync_btn.setEnabled(
            can_sync and has_api_key and not self.is_processing)

    def _has_modified_in_right_tree(self) -> bool:
        """检查右侧树中是否有已修改的文件（有待删除的旧版本）"""
        def _walk(item: QTreeWidgetItem) -> bool:
            status = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if status == 'modified':
                return True
            for i in range(item.childCount()):
                if _walk(item.child(i)):
                    return True
            return False
        root = self.right_tree.invisibleRootItem()
        for i in range(root.childCount()):
            if _walk(root.child(i)):
                return True
        return False

    def _update_upload_btn(self):
        has_pending = self.right_tree.file_count() > 0
        has_api_key = bool(self.apikey_entry.text().strip())
        self.upload_btn.setEnabled(
            has_pending and has_api_key and not self.is_processing)
        self._update_sync_btn()

    # ---------- 同步（仅清理，不上传） ----------

    def _start_sync(self):
        """只删除 AnythingLLM 中的无效文档，不上传文件"""
        api_key = self.apikey_entry.text().strip()
        base_url = self.url_entry.text().strip()

        if not api_key:
            self.show_error(self.tr("error_title"), "请输入 API Key")
            return
        if not base_url:
            self.show_error(self.tr("error_title"),
                            "请输入 AnythingLLM 服务地址")
            return

        # 收集需要删除的文档：本地已删除 + 右侧已修改文件的旧版本
        docs_to_delete: dict[str, str] = dict(self._deleted_docs)

        # 加上右侧树中已修改文件的旧版本
        def _collect_modified(item: QTreeWidgetItem):
            status = item.data(0, Qt.ItemDataRole.UserRole + 1)
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if status == 'modified' and path:
                try:
                    rel = os.path.relpath(path, self.folder_path)
                except ValueError:
                    rel = os.path.basename(path)
                rel = rel.replace('\\', '/')
                old = (self._tracking.get(rel, {})
                       if self._tracking else {})
                old_name = old.get('name', '')
                if old_name and rel not in docs_to_delete:
                    docs_to_delete[rel] = old_name
            for i in range(item.childCount()):
                _collect_modified(item.child(i))

        root = self.right_tree.invisibleRootItem()
        for i in range(root.childCount()):
            _collect_modified(root.child(i))

        if not docs_to_delete:
            QMessageBox.information(
                self, self.tr("info_title"),
                "没有需要清理的文档。")
            return

        self.set_processing(True)
        self.sync_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.log_area.clear()

        self.log(f"开始同步: 清理 {len(docs_to_delete)} 个无效文档")
        self.log(f"  - 本地已删除: {len(self._deleted_docs)} 个")
        self.log(f"  - 旧版本: {len(docs_to_delete) - len(self._deleted_docs)} 个")

        deleted, failed = _delete_documents(
            base_url, api_key, list(docs_to_delete.values()))

        if deleted > 0:
            self.log(f"✓ 已清理 {deleted} 个文档")
        if failed > 0:
            self.log(f"✗ {failed} 个清理失败")

        # 更新追踪文件
        if self.folder_path:
            for rel_path in docs_to_delete:
                self._tracking.pop(rel_path, None)
            _save_tracking(self.folder_path, self._tracking)

        self._deleted_docs.clear()
        self.set_processing(False)
        self._update_upload_btn()

        self.log("同步完成")
        QMessageBox.information(
            self, self.tr("info_title"),
            f"同步完成!\n清理: {deleted}\n失败: {failed}")

    def _start_upload(self):
        api_key = self.apikey_entry.text().strip()
        base_url = self.url_entry.text().strip()
        workspace = self.workspace_display.text().strip()

        if not api_key:
            self.show_error(self.tr("error_title"), "请输入 API Key")
            return
        if not base_url:
            self.show_error(self.tr("error_title"),
                            "请输入 AnythingLLM 服务地址")
            return

        files_to_upload = self._collect_all_file_infos(
            self.right_tree, self.folder_path)

        # 附加 rel_path 和状态信息
        old_docs: dict[str, str] = {}
        for finfo in files_to_upload:
            abs_path = finfo['abs_path']
            try:
                rel_path = os.path.relpath(abs_path, self.folder_path)
            except ValueError:
                rel_path = os.path.basename(abs_path)
            rel_path = rel_path.replace('\\', '/')
            finfo['rel_path'] = rel_path

            # 查找旧文档
            old = self._tracking.get(rel_path) if self._tracking else None
            td = self._track_data.get(rel_path, {})
            if old is None:
                finfo['status'] = 'new'
            elif not old.get('name'):
                # 追踪中有记录但未上传 → 按新增处理
                finfo['status'] = 'new'
            elif (old.get('size') != td.get('size', -1) or
                  old.get('mtime') != td.get('mtime', -1)):
                finfo['status'] = 'modified'
                old_docs[rel_path] = old['name']
            else:
                finfo['status'] = 'unchanged'

        # 跳过未变化的文件
        skipped = sum(1 for f in files_to_upload
                      if f.get('status') == 'unchanged')
        files_to_upload = [f for f in files_to_upload
                           if f.get('status') != 'unchanged']

        # 合并本地已删除的文件到删除列表
        if self._deleted_docs:
            old_docs.update(self._deleted_docs)

        if not files_to_upload and not old_docs:
            self.log("所有文件均为最新，无需上传")
            QMessageBox.information(
                self, self.tr("info_title"),
                f"所有文件均为最新，无需上传。\n跳过了 {skipped} 个未变化文件。")
            return

        self.set_processing(True)
        self.upload_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(max(len(files_to_upload), 1))
        self.progress_bar.setValue(0)
        self.log_area.clear()

        parts = []
        if files_to_upload:
            parts.append(f"上传 {len(files_to_upload)} 个文件")
        if self._deleted_docs:
            parts.append(f"清理 {len(self._deleted_docs)} 个已删除")
        self.log(f"开始同步: {' + '.join(parts)}")
        self.log(f"服务地址: {base_url}")
        self.log(f"工作区: {workspace}")

        self.worker = AnythingLLMUploadWorker(
            files_to_upload, base_url, api_key, workspace, old_docs)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.log.connect(self._on_log)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self.worker)

    def _on_progress(self, cur: int, total: int):
        self.progress_bar.setValue(cur)
        self.status_label.setText(
            f"{self.tr('allm_uploading')} {cur}/{total}")

    def _on_log(self, msg: str):
        self.log(msg)

    def _on_error(self, err: str):
        self.log(f"[错误] {err}")

    def _on_finished(self, result: dict):
        self.set_processing(False)
        self.progress_bar.setVisible(False)
        uploaded = result.get('uploaded', 0)
        failed = result.get('failed', 0)

        # 补充已上传文件的 name 到追踪
        deleted_cleaned = len(self._deleted_docs)
        if self.folder_path:
            # 移除已删除的条目
            for rel_path in self._deleted_docs:
                self._tracking.pop(rel_path, None)
            # 补充新上传文件的 name
            new_tracking = result.get('tracking', {})
            for rel_path, entry in new_tracking.items():
                if rel_path in self._tracking:
                    self._tracking[rel_path]['name'] = entry['name']
            _save_tracking(self.folder_path, self._tracking)
            if new_tracking:
                self.log(f"追踪文件已更新: {len(new_tracking)} 个文档名")

        self._deleted_docs.clear()

        # 状态
        if uploaded == 0 and failed == 0 and deleted_cleaned > 0:
            self.log(f"同步完成: 清理了 {deleted_cleaned} 个已删除文档")
            self.status_label.setText(
                f"已清理 {deleted_cleaned} 个文档")
        else:
            msg_parts = [self.tr("allm_upload_done")]
            if uploaded > 0:
                msg_parts.append(f"✓ {uploaded}")
            if failed > 0:
                msg_parts.append(f"✗ {failed}")
            self.status_label.setText("  ".join(msg_parts))
            self.log(f"\n上传完成: 成功 {uploaded}, 失败 {failed}")

        self._update_upload_btn()

        QMessageBox.information(
            self, self.tr("info_title"),
            f"同步完成!\n成功: {uploaded}\n失败: {failed}")


# ============================================================
# 辅助：清理空文件夹
# ============================================================

def _cleanup_empty_folders(parent: QTreeWidgetItem):
    """递归删除空的文件夹节点"""
    i = 0
    while i < parent.childCount():
        child = parent.child(i)
        _cleanup_empty_folders(child)
        # 如果清理后子节点变为空文件夹（无 UserRole 数据 = 文件夹，且无子节点）
        if (child.childCount() == 0 and
                not child.data(0, Qt.ItemDataRole.UserRole)):
            parent.removeChild(child)
            # 不递增 i，因为删除后索引前移
            continue
        i += 1
