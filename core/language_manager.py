"""
语言管理器 — PySide6 QTranslator 适配层

替代原来的 language_manager.py（基于JSON的手动翻译系统）。
使用Qt的 QTranslator + .qm 翻译文件实现运行时语言切换。

核心优势:
- 切换语言无需销毁/重建任何widget
- QEvent.LanguageChange 事件自动通知所有widget更新
- 支持 Qt Designer 生成的 .ui 文件自动翻译
"""

import json
import locale
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTranslator, QLocale


class LanguageManager:
    """语言管理器 — 封装QTranslator的加载和切换逻辑"""

    # 支持的语言及显示名称
    SUPPORTED_LANGUAGES = {
        'zh_CN': '中文',
        'en': 'English',
        'ru': 'Русский',
        'ja': '日本語',
        'de': 'Deutsch',
        'pt': 'Português',
        'fr': 'Français',
    }

    def __init__(self, translations_dir: str = "i18n", config_path: str = "config.json"):
        """
        参数:
            translations_dir: .qm 翻译文件所在目录
            config_path: 配置文件路径（保存语言偏好）
        """
        self.translations_dir = Path(translations_dir)
        self.config_path = Path(config_path)
        self.translator = QTranslator()
        self.current_language: str = 'en'

        # 加载保存的语言偏好或检测系统语言
        saved_lang = self._load_config()
        if saved_lang and self.load_language(saved_lang):
            pass
        else:
            self._detect_system_language()

    # ---------- 语言加载 ----------

    def load_language(self, lang_code: str) -> bool:
        """设置当前语言并保存配置

        实际的翻译文件加载由 JsonTranslator 负责，
        此方法仅更新语言状态和持久化配置。

        参数:
            lang_code: 语言代码，如 'zh_CN', 'en'

        返回:
            设置成功返回True
        """
        if lang_code not in self.SUPPORTED_LANGUAGES:
            lang_code = 'en'

        # 检查翻译文件是否存在（JSON格式）
        json_path = self.translations_dir / f"{lang_code}.json"
        if not json_path.exists():
            if lang_code != 'en':
                return self.load_language('en')
            return False

        self.current_language = lang_code
        self._save_config(lang_code)
        return True

    def get_translator(self) -> QTranslator:
        """获取当前的QTranslator实例"""
        return self.translator

    # ---------- 语言查询 ----------

    def get_current_language(self) -> str:
        """获取当前语言代码"""
        return self.current_language

    def get_current_language_name(self) -> str:
        """获取当前语言的显示名称"""
        return self.SUPPORTED_LANGUAGES.get(self.current_language, 'English')

    def get_supported_languages(self) -> dict[str, str]:
        """获取所有支持的语言及其显示名称"""
        return dict(self.SUPPORTED_LANGUAGES)

    # ---------- 系统语言检测 ----------

    def _detect_system_language(self):
        """检测系统语言并加载对应的翻译"""
        try:
            system_lang = QLocale.system().name()  # 如 'zh_CN', 'en_US'
            # 尝试完整匹配
            if system_lang in self.SUPPORTED_LANGUAGES:
                self.load_language(system_lang)
                return
            # 尝试仅匹配主语言代码
            main_lang = system_lang.split('_')[0]
            for code in self.SUPPORTED_LANGUAGES:
                if code.startswith(main_lang):
                    self.load_language(code)
                    return
        except Exception:
            pass
        # 降级到英文
        self.load_language('en')

    # ---------- 配置文件读写 ----------

    def _save_config(self, lang_code: str):
        """保存语言偏好到配置文件"""
        try:
            config = {'language': lang_code}
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception:
            pass  # 配置文件写入失败不应影响应用运行

    def _load_config(self) -> Optional[str]:
        """从配置文件加载语言偏好"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('language')
        except Exception:
            pass
        return None
