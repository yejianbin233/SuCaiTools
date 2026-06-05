"""
sucaitools 应用入口

基于 PySide6 重写的素材处理工具集主程序。
解决原 customtkinter 版本的弹窗置顶、Canvas性能、语言切换重建等问题。
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTranslator
from PySide6.QtGui import QFont

from main_window import MainWindow


def main():
    """应用主入口"""
    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("SucaiTools")
    app.setOrganizationName("SucaiTools")

    # 设置默认字体（支持中文）
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
