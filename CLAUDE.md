# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 运行应用
python main_app.py

# 安装依赖
pip install -r requirements.txt

# 额外依赖（翻译功能需要）
pip install tencentcloud-sdk-python dashscope openai

# 打包为可执行文件
pyinstaller --onefile --windowed --add-data "languages;languages" --name SucaiTools main_app.py
```

本项目没有测试套件和 lint 配置。

## 架构总览

### 主入口与Tab管理

`main_app.py` 是应用入口，使用 `customtkinter.CTkTabview` 组织10个工具。每个工具是一个独立的 `CTkFrame` 子类，被嵌入到对应的 tab 中。

`MainApplication` 继承 `CTk`（不是 `TkinterDnD.Tk`），通过 `tkinterdnd2.TkinterDnD._require(self)` 手动启用拖放支持。

### 语言切换机制

`LanguageManager`（`language_manager.py`）从 `languages/` 目录加载 JSON 翻译文件，支持 en/zh_CN/ru/ja/de/pt/fr 七种语言。当前语言持久化到 `config.json`。

**关键模式**：切换语言时，`MainApplication.update_ui_texts()` 会**销毁所有工具 Frame 并重新实例化**，然后调用每个 Frame 的 `update_ui_texts()` 方法。这意味着新增工具需要在 `update_ui_texts()` 中添加对应的销毁/重建逻辑，否则会导致状态不一致。

每个工具 Frame 的构造函数接受 `(master, lang_manager)` 两个参数，并使用 `lang_manager.get_text(key)` 获取翻译文本。

### 翻译服务架构（caption模块）

`caption/translator_manager.py` 定义了基于策略模式的翻译架构：

- `BaseTranslator` — 抽象基类，定义 `translate_to_chinese()` 和 `translate_to_english()` 接口
- `BaiduTranslator` / `YoudaoTranslator` / `TencentSDKTranslator` / `GoogleTranslator` / `AITranslator` — 具体实现
- `TranslatorManager.get_translator(service, config)` — 工厂方法，根据服务名返回对应实例

腾讯云 API 密钥存储在 `caption/tentcent_secretkey.json`（该文件不在版本控制中）。

### Caption 编辑器（最复杂模块）

`caption/caption_editor_frame_gui.py` 是功能最丰富的模块，用于 AI 训练数据的 caption（提示词）编辑。核心流程：

1. 加载图片文件夹，自动匹配中英文 txt 文件组成的 caption pair
2. 支持手动编辑、批量翻译、AI 标准化 caption
3. 子窗口：`ThumbnailWindow`（缩略图浏览+删除）、`GifWindow`（GIF预览）、`RestoreWindow`（恢复已删除文件）
4. `ConfigDialog` 管理翻译服务配置

### GIF 拆分

`gif_splitter.py` 是纯逻辑类，无 GUI 依赖，使用 Pillow 逐帧读取 GIF。`GifSplitterFrame`（`gif_splitter_gui.py`）提供 GUI 界面，支持拖放 GIF 文件、选择输出格式、异步处理。

### 拖放处理

`drag_drop_handler.py` 提供两个函数：`handle_file_drop()` 和 `handle_folder_drop()`，在多个模块中复用。使用 `tkinterdnd2` 的 `DND_FILES` 注册目标组件。

### 各工具模块的通用模式

每个工具模块（`*_gui.py`）遵循统一结构：

- 继承 `ctk.CTkFrame`
- 构造函数接受 `(master, lang_manager)`
- 实现 `update_ui_texts()` 方法用于语言切换
- 使用 `self.grid_columnconfigure(1, weight=1)` 让输入区域自适应宽度
- 耗时操作放在 `threading.Thread` 中异步执行，通过回调更新 UI
- 日志通过 `CTkTextbox` 输出，状态设为 `disabled` 后通过 `configure(state='normal')` 写入

### CI/CD

`.github/workflows/release.yml` 在推送版本标签（`v*`）时触发，在 ubuntu/macos/windows 三平台用 PyInstaller 构建单文件可执行文件，上传到 GitHub Releases。
