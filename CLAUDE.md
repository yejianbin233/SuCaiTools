# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 工作原则

- 修改前先阅读相关代码，不确定时先问，不猜测
- 遵循项目现有模式（面板注册、BaseWorker异步、tr()翻译键约定）
- 只改必要代码，不顺手重构无关部分
- 所有注释使用中文
- 遇到问题明确告知，不隐藏

# CLAUDE.md — 12条规则模板

以下规则适用于本项目中的每个任务，除非显式覆盖。

原则：非平凡任务上谨慎优先于速度。平凡任务自行判断。

## 规则1 — 编码前先思考

明确陈述假设。不确定时询问而非猜测。

存在歧义时呈现多种解读。

有更简单的方案时提出异议。

困惑时停止。指明哪里不清楚。

## 规则2 — 简洁优先

用最少代码解决问题。不写推测性代码。

不添加超出需求的功能。不为单次使用的代码创建抽象。

测试标准：资深工程师会说这过于复杂吗？如果是，简化。

## 规则3 — 精准修改

只触碰必须改的。只清理自己造成的混乱。

不要"改进"相邻代码、注释或格式。

不要重构没坏的东西。匹配现有风格。

## 规则4 — 目标驱动执行

定义成功标准。循环直到验证通过。

不按步骤执行。定义成功并迭代。

强有力的成功标准让你能独立循环。

## 规则5 — 仅在判断性任务上使用模型

使用场景：分类、起草、摘要、提取。

不使用场景：路由、重试、确定性转换。

如果代码能回答，就用代码回答。

## 规则6 — Token预算不可忽视

每任务：4,000 tokens。每会话：30,000 tokens。

接近预算时，总结并重新开始。

暴露超支情况。不要默默超限。

## 规则7 — 暴露冲突，不要取平均

如果两种模式矛盾，选择一种（更新/更久经测试的）。

解释原因。标记另一种待清理。

不要混合冲突的模式。

## 规则8 — 写之前先读

添加代码前，阅读导出、直接调用方、共享工具。

"看起来正交"是危险的。如果不确定代码为何这样组织，询问。

## 规则9 — 测试验证意图，而非仅验证行为

测试必须编码行为为何重要，而非仅编码做了什么。

一个在业务逻辑变更时无法失败的测试是错误的。

## 规则10 — 每个重要步骤后做检查点

总结已完成、已验证、待完成的内容。

不要从一个你无法描述回来的状态继续。

如果失去追踪，停下并重新陈述。

## 规则11 — 匹配代码库的约定，即使你不同意

在代码库内部，一致性 > 个人品味。

如果你真的认为某个约定有害，提出来。不要默默分叉。

## 规则12 — 大声失败

如果任何东西被默默跳过，"已完成"就是错的。

如果任何测试被跳过，"测试通过"就是错的。

默认暴露不确定性，而非隐藏。

# 虚拟环境配置
- 所有 Python 相关操作请使用项目内的虚拟环境：`F:\Python_WorkSpace\sucaitools\sucaitools_env\Scripts\activate`

## 常用命令

```bash
# 激活虚拟环境
F:\Python_WorkSpace\sucaitools\sucaitools_env\Scripts\activate

# 运行应用
python main.py

# 安装依赖
pip install -r requirements.txt

# 翻译功能额外依赖（caption模块）
pip install tencentcloud-sdk-python

# 打包
pyinstaller --onefile --windowed --add-data "languages;languages" --add-data "resources;resources" --name SucaiTools main.py
```

## 架构总览

项目基于 **PySide6** 构建，使用 `QTabWidget` 组织 10 个工具面板。旧版 customtkinter 代码（`main_app.py` + `*_gui.py`）仍保留在根目录但不再使用。

> **虚拟环境**: 所有 Python 操作必须使用 `F:\Python_WorkSpace\sucaitools\sucaitools_env\`

```
main.py                      # QApplication入口，高DPI+字体设置
main_window.py               # QMainWindow + QTabWidget，PANEL_REGISTRY面板注册
├── core/                    # 纯逻辑层（零GUI依赖）
│   ├── base_panel.py        #   BaseToolPanel — changeEvent语言切换、日志、通用对话框
│   ├── base_worker.py       #   BaseWorker(QRunnable) + WorkerSignals — 信号/槽异步任务
│   ├── language_manager.py  #   语言管理器（封装QTranslator）
│   ├── json_translator.py   #   JsonTranslator — 从languages/*.json加载翻译
│   └── utils.py             #   DragDropLineEdit — Qt原生拖放
├── ui/                      # 视图层（10个工具面板，每个一个文件）
│   ├── gif_splitter_panel.py    # GIF拆分
│   ├── rename_panel.py          # 批量重命名
│   ├── resize_panel.py          # 图片缩放（4种模式）
│   ├── jpg_to_png_panel.py      # JPG→PNG
│   ├── rotate_panel.py          # 图片旋转
│   ├── image_processor_panel.py # 翻转/旋转
│   ├── stitch_panel.py          # 图片拼接
│   ├── video2png_panel.py       # 视频→PNG序列
│   ├── mp4_to_gif_panel.py      # MP4→GIF（限制300帧/480px防内存溢出）
│   └── particle_panel.py        # 粒子提取器
├── caption/                 # Caption编辑器（customtkinter，待迁移）
├── resources/style.qss      # 全局样式表（浅色主题）
├── languages/               # JSON翻译文件（7语言）
└── particle_extractor.py    # 粒子提取纯逻辑（新旧共用）
```

### 核心模式

**添加新面板**：在 `main_window.py` 的 `PANEL_REGISTRY` 追加 `(PanelClass, "tab_key", "默认名")` → 框架自动处理tab创建和语言切换。

**面板结构**：每个面板继承 `BaseToolPanel`，在 `__init__` 中调用 `_setup_ui()` 创建布局，然后 `retranslate_ui()` 设置文本。耗时操作使用 `BaseWorker(QRunnable)` + `WorkerSignals` 信号/槽模式。

**语言切换**：`JsonTranslator` 加载 `languages/{lang}.json` → `installTranslator()` → Qt广播 `QEvent.LanguageChange` → 每个面板 `changeEvent()` → `retranslate_ui()`。**不销毁任何widget**。

**翻译键**：代码中使用 `self.tr("语义键")`，全小写snake_case。通用键（`browse`、`error_title`、`stop`、`processing`）可直接复用。

**异步任务**：继承 `BaseWorker(QRunnable)`，通过 `WorkerSignals`（finished/progress/log/error）与主线程通信。禁止在 `run()` 中直接操作UI。

**拖放**：`DragDropLineEdit` / `DragDropFolderLineEdit` 使用 Qt 原生 `dragEnterEvent`/`dropEvent`，接受文件/文件夹拖放，可选扩展名白名单。

### 已知问题

- Caption编辑器尚未从customtkinter迁移到PySide6
- 粒子提取器面板的Canvas遮罩绘制交互需要完善
- 缺少单元测试

### 翻译服务（caption模块）

`caption/translator_manager.py`：`BaseTranslator` → `BaiduTranslator`/`TencentSDKTranslator`/`GoogleTranslator`/`AITranslator`。工厂方法 `TranslatorManager.get_translator()`。

### particle_extractor.py

纯逻辑模块（新旧GUI通用）：`MaskDef` + `ParticleExtractor`（遮罩管理、批量裁剪、JSON序列化、异步处理）。

### CI/CD

`.github/workflows/release.yml`：`v*` 标签触发三平台 PyInstaller 构建。
