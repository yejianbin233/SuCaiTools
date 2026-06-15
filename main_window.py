"""
主窗口 — QMainWindow + QTabWidget

管理所有工具面板的注册、语言切换和全局状态。
使用 JsonTranslator 兼容项目已有的 languages/*.json 翻译文件。

关键改进（相比原 main_app.py）:
- 语言切换不销毁任何widget（仅重新加载翻译 + changeEvent更新）
- 使用 QTabWidget 替代 CTkTabview，原生支持运行时重命名tab
- 每个面板继承 BaseToolPanel，统一生命周期管理
- 信号/槽模式彻底解决线程安全问题
"""

from typing import Type

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QComboBox, QStatusBar, QApplication
)
from PySide6.QtCore import QEvent

from core.language_manager import LanguageManager
from core.json_translator import JsonTranslator
from ui.gif_splitter_panel import GifSplitterPanel
from ui.rename_panel import RenamePanel
from ui.resize_panel import ResizePanel
from ui.video2png_panel import VideoToPngPanel
from ui.mp4_to_gif_panel import Mp4ToGifPanel
from ui.stitch_panel import StitchPanel
from ui.image_processor_panel import ImageProcessorPanel
from ui.jpg_to_png_panel import JpgToPngPanel
from ui.rotate_panel import RotatePanel
from ui.particle_panel import ParticlePanel
from ui.caption_panel import CaptionPanel
from ui.gif_maker_panel import GifMakerPanel
from ui.file_distributor_panel import FileDistributorPanel
from ui.anythingllm_upload_panel import AnythingLLMUploadPanel


class MainWindow(QMainWindow):
    """主窗口"""

    # 面板注册表: [(面板类, 语义键, 默认显示名)]
    # 语义键用于语言切换时查找翻译
    PANEL_REGISTRY: list[tuple[Type[QWidget], str, str]] = [
        (GifSplitterPanel,     "tab_gif_splitter",       "GIF拆分"),
        (RenamePanel,          "tab_rename_images",      "批量重命名"),
        (ResizePanel,          "tab_resize_images",       "图片缩放"),
        (VideoToPngPanel,      "tab_video_to_png",        "视频转PNG"),
        (Mp4ToGifPanel,        "tab_mp4_to_gif",          "MP4转GIF"),
        (StitchPanel,          "tab_image_stitcher",      "图片拼接"),
        (ImageProcessorPanel,  "tab_image_processor",     "图片处理"),
        (JpgToPngPanel,        "tab_jpg_to_png",          "JPG转PNG"),
        (RotatePanel,          "tab_image_rotator",       "图片旋转"),
        (ParticlePanel,        "tab_particle_extractor",  "粒子提取器"),
        (CaptionPanel,         "tab_caption_editor",      "Caption编辑器"),
        (GifMakerPanel,        "tab_gif_maker",           "GIF合成"),
        (FileDistributorPanel, "tab_file_distributor",    "文件分发"),
        (AnythingLLMUploadPanel, "tab_anythingllm_upload", "AnythingLLM上传"),
    ]

    def __init__(self):
        super().__init__()

        # 初始化语言管理器（使用JsonTranslator兼容现有JSON翻译文件）
        self.lang_manager = LanguageManager(
            translations_dir="languages",
            config_path="config.json"
        )

        # 创建JsonTranslator并安装到应用
        self.translator = JsonTranslator(translations_dir="languages")
        self.translator.load_language(self.lang_manager.get_current_language())
        QApplication.instance().installTranslator(self.translator)

        # 窗口基本设置
        self.setWindowTitle(self.tr("main_title"))
        self.resize(900, 680)
        self.setMinimumSize(800, 600)

        # 面板实例存储
        self.panels: dict[str, QWidget] = {}

        # 创建UI
        self._setup_ui()
        self._register_panels()
        self._apply_style()

    # ---------- UI初始化 ----------

    def _setup_ui(self):
        """创建主窗口UI结构"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # ---- 顶部：语言选择器 ----
        lang_layout = QHBoxLayout()

        self.lang_label = QLabel(self.tr("language") + ":")
        lang_layout.addWidget(self.lang_label)

        self.lang_combo = QComboBox()
        languages = self.lang_manager.get_supported_languages()
        for code, name in languages.items():
            self.lang_combo.addItem(name, code)
        current_code = self.lang_manager.get_current_language()
        current_name = languages.get(current_code, 'English')
        self.lang_combo.setCurrentText(current_name)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()

        # GitHub链接
        github_label = QLabel(
            '<a href="https://github.com/dependon/sucaitools" '
            'style="color: #0078d4;">GitHub: dependon/sucaitools</a>')
        github_label.setOpenExternalLinks(True)
        lang_layout.addWidget(github_label)

        layout.addLayout(lang_layout)

        # ---- 中部：标签页 ----
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        layout.addWidget(self.tab_widget)

        # ---- 底部：状态栏 ----
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(self.tr("status_idle"))

    def _register_panels(self):
        """注册所有工具面板到标签页"""
        for panel_cls, tab_key, default_name in self.PANEL_REGISTRY:
            self._add_panel(panel_cls, tab_key, default_name)

    def _add_panel(self, panel_cls: Type[QWidget], tab_key: str,
                   default_name: str = ""):
        """添加一个工具面板到标签页

        参数:
            panel_cls: 面板类
            tab_key: tab名称的翻译语义键
            default_name: 翻译加载失败时的默认显示名
        """
        panel = panel_cls()
        # tr(tab_key) 会通过JsonTranslator查找当前语言的翻译
        display_name = self.tr(tab_key) if tab_key else default_name
        if not display_name or display_name == tab_key:
            display_name = default_name
        self.tab_widget.addTab(panel, display_name)
        self.panels[panel_cls.__name__] = panel

    # ---------- 语言切换 ----------

    def _on_language_changed(self, index: int):
        """语言下拉框变更"""
        lang_code = self.lang_combo.currentData()
        if lang_code and lang_code != self.lang_manager.get_current_language():
            self._switch_language(lang_code)

    def _switch_language(self, lang_code: str):
        """切换界面语言

        创建新的JsonTranslator实例替换旧实例，确保Qt正确发送
        LanguageChange事件到所有widget。不销毁任何widget。
        """
        if not self.lang_manager.load_language(lang_code):
            return

        # 移除旧翻译器
        QApplication.instance().removeTranslator(self.translator)

        # 创建新翻译器实例（必须新建实例，Qt才会触发LanguageChange）
        self.translator = JsonTranslator(translations_dir="languages")
        self.translator.load_language(lang_code)
        QApplication.instance().installTranslator(self.translator)

        # 更新tab名称
        for i, (_, tab_key, default_name) in enumerate(self.PANEL_REGISTRY):
            if i < self.tab_widget.count():
                name = self.tr(tab_key)
                if not name or name == tab_key:
                    name = default_name
                self.tab_widget.setTabText(i, name)

        # 更新语言标签
        self.lang_label.setText(self.tr("language") + ":")

        self.status_bar.showMessage(
            self.tr("status_idle"))

    def changeEvent(self, event: QEvent):
        """语言切换事件 — 更新窗口标题和所有tab名称"""
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self.tr("main_title"))
            self.lang_label.setText(self.tr("language") + ":")
            for i, (_, tab_key, default_name) in enumerate(self.PANEL_REGISTRY):
                if i < self.tab_widget.count():
                    name = self.tr(tab_key)
                    if not name or name == tab_key:
                        name = default_name
                    self.tab_widget.setTabText(i, name)
        super().changeEvent(event)

    # ---------- 样式 ----------

    def _apply_style(self):
        """加载全局QSS样式表"""
        try:
            with open("resources/style.qss", 'r', encoding='utf-8') as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            pass
