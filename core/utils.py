"""
公共工具函数和基础类

提供项目中各模块共用的工具，包括拖放输入框、日志辅助函数等。
"""

from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from pathlib import Path


class DragDropLineEdit(QLineEdit):
    """支持拖放文件/文件夹的输入框

    替代原来的 tkinterdnd2 + drag_drop_handler.py，
    使用Qt原生拖放机制，跨平台稳定可靠。
    """

    def __init__(self, parent=None, allowed_extensions: tuple[str, ...] | None = None):
        """
        参数:
            parent: 父组件
            allowed_extensions: 允许的文件扩展名元组，如 ('.mp4', '.avi')。
                               None 表示接受所有文件和文件夹。
        """
        super().__init__(parent)
        self.allowed_extensions = allowed_extensions
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖入事件 — 检查是否为文件/文件夹"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """放下事件 — 提取第一个有效路径"""
        urls = event.mimeData().urls()
        if not urls:
            return

        path = urls[0].toLocalFile()
        path_obj = Path(path)

        # 如果设置了扩展名限制，验证文件类型
        if self.allowed_extensions is not None:
            if path_obj.is_file() and path_obj.suffix.lower() in self.allowed_extensions:
                self.setText(path)
            elif path_obj.is_dir():
                self.setText(path)
        else:
            # 接受任何文件或文件夹
            self.setText(path)


class DragDropFolderLineEdit(DragDropLineEdit):
    """只接受文件夹拖放的输入框"""

    def dropEvent(self, event: QDropEvent):
        """放下事件 — 只接受文件夹"""
        urls = event.mimeData().urls()
        if not urls:
            return

        path = urls[0].toLocalFile()
        if Path(path).is_dir():
            self.setText(path)


def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为可读的文件大小"""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_supported_image_files(directory: str) -> list[str]:
    """扫描目录下的所有支持的图片文件，按文件名排序

    参数:
        directory: 目标目录路径

    返回:
        排序后的图片文件路径列表
    """
    supported = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp')
    files = []
    dir_path = Path(directory)

    for ext in supported:
        files.extend(str(p) for p in dir_path.glob(f"*{ext}"))
        files.extend(str(p) for p in dir_path.glob(f"*{ext.upper()}"))

    return sorted(set(files))


import re as _re

def natural_sort_key(name: str):
    """自然排序键：将文件名中的数字按数值排序，而非字符串排序。

    示例: "r0c1" < "r0c8" < "r0c11" (而非 "r0c1" < "r0c11" < "r0c8")
    """
    return [int(t) if t.isdigit() else t.lower()
            for t in _re.split(r'(\d+)', name)]
