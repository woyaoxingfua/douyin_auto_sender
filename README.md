# 抖音PC客户端 - 每日天气助手-自动续火花 (DearPyGui 桌面版 v6.0)

本项目是一个基于 DearPyGui 的完整桌面 GUI 自动化工具，旨在每日定时向指定的抖音好友发送其所在城市的天气预报。通过结合和风天气API、RapidOCR本地文字识别（基于PaddleOCR）、现代化图形用户界面以及 PyAutoGUI 库，实现高度自动化、稳定可靠的每日任务。

v6.0 相较旧版（PySide6 v5.0）完成重构：GUI 框架从 PySide6 迁移至 DearPyGui（即时模式，体积从 100MB+ 降至约 2MB），新增 OCR+图像混合识别、消息预设库、进程监控、发送留痕（SQLite）、屏幕区域可视化框选、抖音窗口监听等能力。旧版 PySide6 文件（`ui/main_window.py`、`ui/styles.py`、`ui/qt_log_handler.py`、`ui/pages/`）已移除，配置入口统一到 DearPyGui 主窗口。

## ✨ 主要功能

*   **完整桌面 GUI 应用**（DearPyGui 即时模式）：
    *   **仪表盘**：概览今日发送数、抖音窗口状态、调度时间，一键立即执行任务。
    *   **好友管理**：图形化管理好友昵称、城市、识别方式（OCR 文字 / 头像截图），支持城市速查、剪贴板粘贴/文件选择/屏幕截取三种头像采集方式。
    *   **消息预设库**：内置 6 个预设（天气、早安、晚安、提醒、生日、纯文本），支持新建/复制/导入导出，可切换激活预设。
    *   **抖音界面配置**：可视化配置控制图像（私信/发送/退出按钮、滚动条）、OCR 关键字、屏幕区域（拖拽框选 + 百分比自适应）、滚动条匹配。
    *   **API 配置**：和风天气 API、本地/百度 OCR 引擎切换与连通性测试。
    *   **进程监控**：实时显示主进程+子进程内存/CPU/线程数，超阈值报警。
    *   **调度设置**：可视化配置每日自动执行时间，启用/禁用调度，近 7 天发送统计。
    *   **发送记录**：SQLite 持久化发送日志，支持按日统计、CSV 导出、清空。
    *   **窗口模式**：normal / compact / mini 三档尺寸，重启后保留。
    *   **主题切换**：暖黑（默认）/ 亮色双主题，直角优先设计。
*   **三重识别模式**：
    *   **本地OCR识别**（推荐）：使用开源RapidOCR引擎（基于PaddleOCR），完全离线运行，支持文字检测和边界提取，定位更精准。
    *   **百度OCR识别**（备选）：当本地OCR不可用时，可切换到百度OCR在线服务。
    *   **传统图像识别模式**：保留原有PyAutoGUI图像识别方式，适合习惯使用截图的用户。
    *   **混合识别**：`HybridRecognizer` 优先尝试 OCR，失败后回退图像匹配。
*   **双重运行模式**：
    *   **定时调度模式**：默认模式，启动桌面应用 (`main.py`) 后保持运行，即可在设定时间自动执行任务。
    *   **立即执行模式**：通过仪表盘的"立即执行任务"按钮，随时手动触发一次任务。
    *   **命令行模式**（备用）：`python douyin_bot.py --now` 立即执行，或 `python douyin_bot.py` 进入每日 08:00 调度循环。
*   **高度可配置与个性化**：
    *   **图形化配置后台**：集成在桌面应用的"配置管理"页面中，轻松管理API、好友和城市信息。
    *   **自定义消息模板**：自由编辑天气播报文案，支持多种变量，让您的问候与众不同。
*   **健壮性与稳定性增强**：
    *   **专业日志系统**：用 `logging` 模块取代了简单的 `print`，所有操作和潜在错误都会记录到 `run.log` 文件中，便于追溯和调试。
    *   **日志滚动**：`run.log` 自动轮转，避免长期运行导致日志文件无限增大。
    *   **网络重试机制**：为天气API请求增加了 `tenacity` 库支持的重试功能，有效应对瞬时网络波动。
    *   **区域化图像识别**：限定 `pyautogui` 在屏幕的特定区域（如右侧列表、右下角聊天区）寻找图像，大幅提升识别速度和准确性。
*   **更佳的用户体验与安全性**：
    *   **API连通性测试**：在配置界面一键测试和风天气API及百度OCR的有效性。
    *   **敏感数据保护**：支持从环境变量读取API密钥，避免在配置文件中明文存储，更加安全。
    *   **任务前倒计时**：执行前给予 10 秒倒计时，方便切换到抖音 PC 客户端窗口。
    *   **未捕获异常处理**：全局异常钩子，错误时弹窗提示并记录日志。

## 项目结构

```
douyin_auto_sender/
│
├── main.py                     # 主程序入口（DearPyGui），启动 v6.0 GUI
├── douyin_bot.py               # 自动化任务核心：好友遍历、混合识别、发送、留痕
├── config_store.py             # 单例配置管理（统一加载，兼容旧版 config.json）
│
├── ocr_service.py              # OCR 服务封装（RapidLocalOCR + BaiduOCR + 工厂）
├── weather_service.py          # 和风天气 API 封装（含 tenacity 重试）
├── hybrid_recognizer.py        # OCR + 图像混合识别引擎
├── message_manager.py          # 消息预设库管理（messages.json 读写）
├── send_log.py                 # 发送留痕（SQLite，含 JSON→SQLite 迁移）
├── process_monitor.py          # 进程监控（内存/CPU/线程，超阈值报警）
├── douyin_monitor.py           # 抖音进程/窗口监听（Win32 API + psutil）
├── region_selector.py          # 屏幕区域可视化框选器（Tk 透明覆盖层）
├── font_loader.py              # 中文字体检测与 DearPyGui 字体注册
├── config_utils.py             # 配置文件读写、兼容校验、城市速查表
│
├── ui/
│   ├── __init__.py
│   ├── dpg_app.py              # DearPyGui 主窗口（仪表盘/好友/消息/界面/API/监控/调度/记录）
│   └── pages/
│       └── dashboard.py        # 仪表盘页面（God Class 拆分样板）
│
├── config.json                 # 配置文件 (向后兼容，老配置可直接使用)
├── messages.json               # 消息预设库
├── send_log.db                 # 发送记录 SQLite 数据库
├── requirements.txt            # 项目依赖库
├── pyproject.toml              # Poetry 配置 + 代码规范（black/isort/flake8/mypy）
├── Makefile                    # 开发命令（install/test/format/lint/run）
├── .pre-commit-config.yaml     # Git 提交前代码规范检查
├── run.log                     # 运行日志文件（自动轮转）
│
├── control_images/             # 存放 UI 控制按钮截图与头像 (图像识别模式需要)
│   ├── douyin_sixin_icon.png
│   ├── douyin_send_button.png
│   ├── douyin_exit_chat_button.png
│   └── avatars/                # 好友头像子目录
│
└── tests/                      # 单元测试（64 个用例）
    ├── conftest.py
    ├── test_config_utils.py
    ├── test_weather_service.py
    ├── test_send_log.py
    ├── test_message_manager.py
    ├── test_douyin_bot.py
    ├── test_hybrid_recognizer.py
    ├── test_ocr_service.py
    └── test_process_monitor.py
```

## 从旧版升级（v5.x → v6.0）

**老配置完全兼容，无需全部重新配置。**

v6.0 保留了 `config.json` 的完整向后兼容性，升级时只需关注以下几点：

| 项目 | 是否必须操作 | 说明 |
|------|-------------|------|
| `config.json` | **无需改动** | 老配置直接可用。新增字段（`ui_regions`、`ocr_texts`、`process_monitor`）均有默认值，首次保存时自动写入 |
| `city` → `location_id` | **自动兼容** | 读取时自动识别旧字段；保存时同时保留 `city` 和 `location_id`，切回 master 仍可读取 |
| 依赖安装 | **必须** | 新增 `dearpygui`、`rapidocr_onnxruntime`、`psutil`，运行 `pip install -r requirements.txt` 即可 |
| 控制图像 | **建议检查** | 如之前用的是图像识别模式，原有截图仍可继续使用 |
| 旧版 PySide6 GUI | **已移除** | `config_manager_gui.py` 等 Tkinter/PySide6 文件已清理，配置入口统一到 `main.py` |
| 窗口标题 | **DPG 限制** | 操作系统标题栏仅支持英文字体，故显示为 "Douyin Weather Assistant v6.0"，窗口内中文标题不受影响 |

**升级步骤（3步）：**

```bash
# 1. 拉取最新代码（在 feature/ocr-enhancement 分支）
git pull origin feature/ocr-enhancement

# 2. 安装新依赖
pip install -r requirements.txt

# 3. 直接启动，老配置自动加载
python main.py
```

> 如需回退：master 分支保持原样，可随时切回。

## ️ 环境安装与配置

#### 1\. 软件依赖

*   **Python**: 建议使用 3.8 或更高版本。

#### 2\. Python库安装

项目依赖已全部记录在 `requirements.txt` 中。请在项目根目录打开终端，运行以下命令以安装所有必需的Python库：

```bash
pip install -r requirements.txt
```

这会安装 `pyautogui`, `requests`, `pyperclip`, `tenacity`, `schedule`, `pillow`, `rapidocr_onnxruntime`, `dearpygui`, `psutil`, `pytest`, `numpy` 等所有必要的库。

> 注：v6.0 已移除 PySide6 依赖，改用 DearPyGui（约 2MB）。老用户无需卸载旧依赖，直接安装新依赖即可。

#### 3\. 本地OCR配置 (推荐)

RapidOCR是基于PaddleOCR的轻量级封装，完全离线运行，无需API Key。

1.  首次运行时，RapidOCR会自动下载模型文件（约10MB，比PaddleOCR小很多）。
2.  在配置界面的"OCR配置"标签页中，确保"启用本地OCR识别"已勾选（默认已启用）。

#### 4\. 百度OCR配置 (可选)

当本地OCR不可用时，系统会自动切换到百度OCR在线服务。

1.  访问 [百度AI开放平台](https://ai.baidu.com/tech/ocr) 并注册账号。
2.  在控制台创建一个应用，选择"文字识别"服务。
3.  获取 `API Key` 和 `Secret Key`。
4.  在配置界面的"OCR配置"标签页中填入上述信息。
5.  每月有2000次免费调用额度，足够日常使用。

#### 5\. 可选：运行快速自检

```bash
python -m py_compile *.py
pytest -q
```

## 📖 使用指南

#### 第一步：启动桌面应用

运行主程序 `main.py` 启动 DearPyGui 桌面应用：

```bash
python main.py
```

启动后会看到主窗口，顶部为状态栏（抖音探测、内存/CPU/线程、时间），下方为 8 个 tab：仪表盘、好友、消息预设、抖音界面、API 配置、监控、调度、发送记录。

#### 第二步：配置（仅需一次或在需要修改时运行）

1.  **打开「API 配置」tab**：
    *   填入您从 **和风天气开发者平台** 获取的 `API Host` 和 `API Key`。
    *   点击 **"测试和风连接"** 按钮，确保您的API配置无误。
    *   在 OCR 配置区，选择 OCR 引擎（本地RapidOCR / 百度云OCR / 不使用OCR），按需填入百度 OCR Key/Secret，可点击"测试本地 OCR"/"测试百度 OCR"验证。
2.  **打开「消息预设」tab**（可选）：
    *   从左侧预设库选择一个预设（如"天气预报（默认）"），点击"设为当前"激活。
    *   可新建/编辑预设模板，支持 `{nickname}`、`{city_name}`、`{text_day}`、`{text_night}`、`{temp_min}`、`{temp_max}`、`{wind_dir}`、`{wind_scale}`、`{custom_text}` 等变量。
3.  **打开「好友」tab**:
    *   点击"+ 新建"，填写好友昵称、城市名、城市 ID（可用"城市速查"快速查询）。
    *   选择识别方式：填入 OCR 文字（好友在私信列表显示的昵称），或通过"从剪贴板粘贴/从文件选择/从屏幕截取"采集头像截图。
    *   点击"保存修改"或"保存并新建"。
    *   可点"导入示例"快速添加 3 个示例好友。
4.  **打开「抖音界面」tab**（可选，调试识别时用）:
    *   在「控制图像」子页为私信/发送/退出按钮配置截图（截图选定区域 / 从文件 / 从剪贴板）。
    *   在「OCR 文字」子页设置界面关键字（消息、发送、退出会话等）。
    *   在「屏幕区域」子页拖拽框选四个关键区域（顶部Bar、好友列表、聊天底部、聊天顶部），百分比自动换算。
5.  **保存**: 各 tab 的"保存"按钮会即时写入 `config.json`。

#### 第三步：设置调度时间

1.  打开「调度」tab。
2.  勾选或取消"启用调度"以控制是否自动执行。
3.  设置期望的每日执行时间（默认 08:00）。
4.  点击 **"保存"**。下方会显示近 7 天发送统计。

#### 第四步：执行任务（选择一种方式）

**方式一：定时调度 (长期运行)**

1.  保持桌面应用运行。
2.  程序会在每天设定的时间自动执行任务。
3.  可在「监控」tab 查看进程状态与运行日志，在「发送记录」tab 查看历史。

**方式二：立即执行 (用于测试或按需运行)**

1.  在「仪表盘」tab 点击 **"立即执行任务"** 按钮。
2.  确认执行后，程序会给出 10 秒倒计时，请在倒计时结束前切换到抖音 PC 客户端窗口。
3.  可在「监控」tab 的运行日志区实时查看执行进度。

**方式三：命令行 (备用)**

```bash
python douyin_bot.py --now     # 立即执行一次
python douyin_bot.py           # 进入每日 08:00 调度循环
```

## 🔒 安全建议：使用环境变量 (推荐)

为了避免 API Key 泄露，建议您使用环境变量来存储它，而不是保存在 `config.json` 中。

1.  **设置环境变量**:
    *   **Windows**: 
        ```cmd
        set DOUYIN_WEATHER_API_KEY=你的天气APIKey
        set BAIDU_OCR_API_KEY=你的OCR-APIKey
        set BAIDU_OCR_SECRET_KEY=你的OCR-SecretKey
        ```
    *   **macOS/Linux**: 
        ```bash
        export DOUYIN_WEATHER_API_KEY="你的天气APIKey"
        export BAIDU_OCR_API_KEY="你的OCR-APIKey"
        export BAIDU_OCR_SECRET_KEY="你的OCR-SecretKey"
        ```
2.  **程序将自动优先使用**：如果检测到对应的环境变量，程序会优先使用它们，并忽略配置文件中的相应字段。

## ️ 注意事项

*   **本地OCR优势**：使用RapidOCR本地识别，完全离线运行，无需网络，且支持文字边界提取，定位更精准。
*   **截图精度**（图像识别模式）：程序的识别成功率与您的截图精度直接相关。如果某个按钮找不到，请尝试重新截取。
*   **界面更新**：如果抖音PC客户端版本更新导致UI文字发生变化，您可能需要更新好友的OCR文字配置。
*   **紧急停止**：程序内置了 `pyautogui.FAILSAFE` 机制。在自动化任务执行期间，如果您想紧急停止，只需将鼠标指针**猛地移动到屏幕的左上角**即可。
*   **日志查看**：如果程序运行异常，可在「监控」tab 的运行日志区查看实时日志，或打开项目根目录下的 `run.log` 文件查看详细的错误信息。
*   **发送记录**：所有发送结果（成功/失败、耗时、消息预览）持久化到 `send_log.db`（SQLite），可在「发送记录」tab 查看、导出 CSV 或清空。

## 🔧 OCR识别模式详解

### 工作原理

OCR识别模式通过本地RapidOCR引擎识别屏幕上的文字来定位按钮，而不是通过图像匹配。

1.  **截图**：程序会截取当前屏幕的指定区域。
2.  **文字检测**：RapidOCR检测图像中的文字区域，返回边界框（bounding box）。
3.  **文字识别**：对检测到的文字区域进行OCR识别，获取文字内容。
4.  **文字匹配**：在识别结果中查找目标文字（如"私信"、"发送"等）。
5.  **精准定位**：根据边界框计算文字中心点，实现精准点击。

### 优势

*   **完全离线**：无需网络，无需API Key，完全本地运行。
*   **边界提取**：RapidOCR支持返回文字的边界框，可以实现更精准的定位。
*   **适应性强**：即使按钮位置发生变化，只要文字不变就能正常工作。
*   **免费开源**：RapidOCR基于PaddleOCR，是开源项目，无任何费用。
*   **轻量快速**：模型仅约10MB，启动快，识别速度快。

### 本地OCR vs 百度OCR

| 特性 | 本地OCR (RapidOCR) | 百度OCR |
|------|-----------|---------|
| 网络要求 | 无需网络 | 需要网络 |
| 费用 | 免费 | 每月2000次免费 |
| 边界提取 | 支持 | 支持 |
| 识别精度 | 高 | 高 |
| 首次使用 | 需下载模型(10MB) | 无需下载 |

## ❓ 常见问题

### Q: OCR模式和图像识别模式有什么区别？

**A:** 
- **OCR模式**：通过识别界面上的文字来定位按钮，无需截取控制图像，适应性更强。
- **图像识别模式**：通过图像匹配来定位按钮，需要提前截取控制图像，对界面变化更敏感。

### Q: 如何选择识别模式？

**A:** 
推荐使用OCR模式（特别是本地OCR），除非：
- 您的界面有无法通过文字识别的元素（如纯图标按钮）
- 本地OCR安装失败（此时可使用百度OCR或图像识别模式）

### Q: 本地OCR识别失败怎么办？

**A:** 
1. 确认已安装RapidOCR：`pip install rapidocr_onnxruntime`
2. 查看日志文件 `run.log` 获取详细错误信息
3. 如果本地OCR不可用，系统会自动尝试使用百度OCR
4. 如果百度OCR也不可用，会回退到图像识别模式

### Q: 首次运行本地OCR很慢？

**A:** 
首次运行时，RapidOCR会自动下载模型文件（约10MB），之后会缓存到本地，后续运行会很快。

### Q: 如何获取好友在私信列表中的显示文字？

**A:** 
打开抖音PC客户端的私信列表，观察好友在列表中的显示方式。通常是好友的昵称或备注名。

-----

*作者GitHub-https://github.com/woyaoxingfua*
