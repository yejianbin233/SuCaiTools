"""
sucaitools 应用入口 — main.py
==============================

## 文件概述
本文件是 sucaitools 素材处理工具集的 Qt 应用启动入口，负责：
1. 全局 Qt 配置初始化（高 DPI、图片内存限制、默认字体）
2. 创建 QApplication 实例并设置应用元信息
3. 实例化主窗口 MainWindow 并进入事件循环

## 文件结构
- 模块级导入：Python 标准库 + PySide6 + 项目内 MainWindow
- main() 函数：应用启动的完整流程，按配置→实例→运行的顺序编排
- __main__ 守卫：脚本直接运行时调用 main()

## 架构定位
在项目分层中，main.py 属于 **入口层**，仅依赖 main_window.py（框架层）。
不直接引用任何面板或业务逻辑模块，保持入口的轻量性。

## 背景
基于 PySide6 重写的素材处理工具集主程序。
解决原 customtkinter 版本的弹窗置顶、Canvas 性能、语言切换重建等问题。
"""

# sys：标准库，提供应用退出和命令行参数传递功能
import sys

# pathlib.Path：用于路径操作（导入后未使用）
from pathlib import Path

# PySide6.QtWidgets.QApplication：Qt 应用核心类，管理事件循环、对象树和多窗口
from PySide6.QtWidgets import QApplication

# PySide6.QtCore.Qt：枚举类型和标志位（如 HighDpiScaleFactorRoundingPolicy）
from PySide6.QtCore import Qt

# PySide6.QtGui.QFont：字体类，用于设置应用全局字体
from PySide6.QtGui import QFont, QImageReader

# 主窗口：承载 QTabWidget + PANEL_REGISTRY 面板注册机制
from main_window import MainWindow


def main():
    """
    应用主入口

    执行顺序：
    1. Qt 全局设置（必须在 QApplication 实例化之前完成）
    2. 创建 QApplication 并配置应用元信息
    3. 设置全局默认字体（Microsoft YaHei 9pt，支持中文）
    4. 创建并显示主窗口，进入事件循环
    """
    # ---- Qt 全局设置（必须在 QApplication 创建前执行） ----

    # 高 DPI 支持：允许 Qt 按设备实际像素比缩放，避免在高分屏上模糊
    # PassThrough 策略让 Qt 使用操作系统报告的精确缩放因子，而非强制四舍五入
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 解除图片加载的 256MB 限制
    # QImageReader 默认限制 256MB 防止恶意文件耗尽内存。
    # 本工具处理大尺寸素材（视频帧序列、高分辨率图片），需要更大上限。
    # setAllocationLimit 参数单位是 MB，默认 256MB，此处改为 2GB
    QImageReader.setAllocationLimit(2048)

    # ---- QApplication 实例化 ----
    # QApplication(sys.argv)：创建应用实例，sys.argv 传递命令行参数（如文件路径）
    app = QApplication(sys.argv)
    # setApplicationName()：设置应用显示名称（用于窗口标题、任务栏等）
    app.setApplicationName("SucaiTools")
    # setOrganizationName()：组织元数据标识，多应用共享同一配置时常用
    app.setOrganizationName("SucaiTools")

    # ---- 全局默认字体 ----
    # 使用 Microsoft YaHei（微软雅黑）9pt，确保中文文本正常渲染
    # 该字体会被所有子 widget 继承，除非局部覆盖
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    # ---- 主窗口 ----
    # MainWindow()：创建主窗口实例（内部通过 PANEL_REGISTRY 注册并构建 10 个工具面板 Tab）
    window = MainWindow()
    # show()：显示窗口到屏幕，触发事件循环启动前的最后准备工作
    window.show()

    # ---- 进入事件循环 ----
    # app.exec()：Qt 事件循环入口，阻塞当前线程直到用户关闭所有窗口
    # sys.exit() 将 Qt 返回的退出码（通常 0）传递给操作系统
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
