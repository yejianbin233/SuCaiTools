"""
工具面板基类

提供所有工具面板的通用功能：语言切换、处理状态管理、日志输出。
每个工具面板继承此类，实现自己的 setup_ui() 和 retranslate_ui() 方法。
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QProgressBar,
    QComboBox, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QEvent, Signal


class BaseToolPanel(QWidget):
    """所有工具面板的基类

    提供:
    - changeEvent(QEvent.LanguageChange) → retranslate_ui()
    - 处理状态管理 (is_processing)
    - 日志区域和日志输出方法
    - 通用的文件/文件夹选择对话框
    - 通用的文件拖放输入框创建
    """

    # 信号: 当面板状态变化时发射
    status_changed = Signal(str)  # 状态文本

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_processing: bool = False
        self._log_widget: Optional[QTextEdit] = None
        self._progress_bar: Optional[QProgressBar] = None
        self._status_label: Optional[QLabel] = None

    # ---------- 语言切换 ----------

    def changeEvent(self, event: QEvent):
        """Qt事件处理 — 语言切换时自动调用"""
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        """子类重写此方法，更新所有UI文本

        示例:
            self.browse_btn.setText(self.tr("浏览..."))
            self.log_label.setText(self.tr("日志:"))
        """
        pass

    # ---------- 处理状态管理 ----------

    def set_processing(self, processing: bool):
        """设置处理状态，子类可重写以禁用/启用按钮"""
        self.is_processing = processing

    # ---------- 日志输出 ----------

    def setup_log_area(self, parent_layout, row: int = 0, column: int = 0,
                       row_span: int = 1, col_span: int = 1):
        """创建日志文本区域并添加到布局

        返回创建的 QTextEdit 实例，调用方可保存引用。
        """
        self._log_widget = QTextEdit()
        self._log_widget.setReadOnly(True)
        self._log_widget.setMaximumHeight(150)
        self._log_widget.setPlaceholderText(self.tr("日志输出..."))
        parent_layout.addWidget(self._log_widget, row, column, row_span, col_span)
        return self._log_widget

    def log(self, message: str):
        """向日志区域追加消息（线程安全）"""
        if self._log_widget:
            self._log_widget.append(message)

    def clear_log(self):
        """清空日志区域"""
        if self._log_widget:
            self._log_widget.clear()

    # ---------- 通用对话框 ----------

    @staticmethod
    def browse_folder(title: str = "选择文件夹") -> str:
        """打开文件夹选择对话框，返回所选路径"""
        return QFileDialog.getExistingDirectory(None, title)

    @staticmethod
    def browse_file(title: str = "选择文件", file_filter: str = "所有文件 (*.*)") -> str:
        """打开文件选择对话框，返回所选文件路径"""
        path, _ = QFileDialog.getOpenFileName(None, title, "", file_filter)
        return path

    @staticmethod
    def browse_save_file(title: str = "保存文件", file_filter: str = "所有文件 (*.*)") -> str:
        """打开文件保存对话框，返回所选路径"""
        path, _ = QFileDialog.getSaveFileName(None, title, "", file_filter)
        return path

    @staticmethod
    def show_error(title: str, message: str):
        """显示错误对话框"""
        QMessageBox.critical(None, title, message)

    @staticmethod
    def show_info(title: str, message: str):
        """显示信息对话框"""
        QMessageBox.information(None, title, message)

    @staticmethod
    def show_warning(title: str, message: str):
        """显示警告对话框"""
        QMessageBox.warning(None, title, message)

    @staticmethod
    def ask_yes_no(title: str, message: str) -> bool:
        """显示确认对话框，返回用户选择"""
        return QMessageBox.question(None, title, message) == QMessageBox.StandardButton.Yes

    # ---------- 便捷组件创建 ----------

    @staticmethod
    def make_button(text: str, callback, enabled: bool = True) -> QPushButton:
        """创建标准按钮"""
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        btn.setEnabled(enabled)
        return btn

    @staticmethod
    def make_label(text: str, bold: bool = False) -> QLabel:
        """创建标准标签"""
        label = QLabel(text)
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        return label

    @staticmethod
    def make_combo(items: list[str], current_index: int = 0) -> QComboBox:
        """创建标准下拉框"""
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(current_index)
        return combo
