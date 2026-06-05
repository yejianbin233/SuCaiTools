"""
JSON翻译器 — 兼容现有 languages/*.json 翻译文件

将项目原有的扁平JSON翻译文件适配到PySide6的QTranslator接口。
翻译采用语义键模式：代码中使用 self.tr("main_title")，
翻译器从JSON中查找 "main_title" → 对应语言的文本。

优势：无需编译.ts→.qm，直接使用已有JSON翻译文件。
"""

import json
from pathlib import Path

from PySide6.QtCore import QTranslator


class JsonTranslator(QTranslator):
    """从JSON文件加载翻译的QTranslator子类

    翻译流程:
    1. 代码中调用 self.tr("语义键")  # 如 self.tr("main_title")
    2. Qt调用 translate(context, "main_title", ...)
    3. 本类在JSON中查找 "main_title" → 返回对应语言文本
    4. 如果JSON中没有该键，返回空（Qt使用原文即语义键本身）

    注意：语义键在代码中不可读（显示为"main_title"而非"素材工具箱"）。
    但如果当前语言文件的翻译加载成功，用户看到的将是翻译后的文本。
    如果加载失败，会显示语义键本身，这是降级行为。
    """

    def __init__(self, translations_dir: str = "languages", parent=None):
        """
        参数:
            translations_dir: JSON翻译文件所在目录
            parent: Qt父对象
        """
        super().__init__(parent)
        self.translations_dir = Path(translations_dir)
        self.translations: dict[str, str] = {}
        self.current_language: str = ""

    def load_language(self, lang_code: str) -> bool:
        """加载指定语言的JSON翻译文件

        参数:
            lang_code: 语言代码，如 'zh_CN', 'en'

        返回:
            加载成功返回True
        """
        json_path = self.translations_dir / f"{lang_code}.json"
        if not json_path.exists():
            return False

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            self.current_language = lang_code
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def translate(self, context: str, source_text: str,
                  disambiguation: str | None = None, n: int = -1) -> str:
        """重写 QTranslator.translate()

        在已加载的JSON翻译中查找source_text（语义键）对应的翻译文本。
        找不到时返回空字符串，Qt将使用source_text本身作为显示文本。

        参数:
            context: Qt上下文（通常是类名，此实现忽略）
            source_text: 语义键，如 "main_title", "browse"
            disambiguation: 消歧义字符串（忽略）
            n: 复数形式（忽略）
        """
        result = self.translations.get(source_text)
        if result is not None:
            return result
        return ""
