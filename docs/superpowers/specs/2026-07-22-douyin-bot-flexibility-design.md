# 抖音 Bot 灵活性增强设计

## 背景
新版抖音 PC 客户端 UI 发生以下变化，导致现有自动化逻辑僵化：
1. 私信入口支持悬停打开，不仅限于点击
2. 好友列表滚动不再依赖滚动条控件，只要焦点在列表区域即可滚轮滚动
3. 发送按钮变为纯图标，OCR 文字识别失效
4. 退出会话从文字变为图标，但老版本仍可能是文字
5. 日志输出不足，难以调试
6. Mini 模式需要真正的悬浮状态窗，而非简单调整主窗口尺寸

## 目标
让 bot 适配新版抖音 UI，同时保持对旧版的兼容，并提供更好的可观测性。

## 设计

### 1. 私信入口双模式
- **配置项**：`enter_private_msg_mode`，取值 `auto`（默认） / `hover` / `click`
- **行为**：
  - `auto`：先悬停到私信入口 1 秒，若未打开再点击
  - `hover`：仅悬停
  - `click`：仅点击（老版本行为）
- **实现**：`hybrid_recognizer.py` 增加 `hover_or_click(target, region, timeout)`

### 2. 好友列表滚动简化
- **移除**对 `douyin_scrollbar.png` 的强依赖
- **配置项**：`scroll_amount`，默认 `-3`（滚轮单位）
- **行为**：直接在好友列表区域中心模拟滚轮，每次滚动 `scroll_amount`
- **实现**：`douyin_bot.py` 的 `scroll_friend_list` 改用 `pyautogui.scroll(scroll_amount)`

### 3. 发送按钮识别策略
- **配置项**：`send_button_mode`，取值 `image`（默认） / `ocr` / `both`
- **行为**：
  - `image`：仅图像匹配 `control_images/douyin_send_button.png`
  - `ocr`：仅 OCR 识别"发送"文字
  - `both`：先图像，失败再 OCR
- **实现**：`hybrid_recognizer.py` 的 `click_element` 支持按模式选择识别方法

### 4. 退出会话兼容
- **配置项**：`exit_session_mode`，取值 `auto`（默认） / `image` / `ocr` / `text`
- **行为**：
  - `auto`：先尝试图像匹配退出按钮，失败则 OCR "退出会话"
  - `image` / `ocr` / `text`：单一策略
- **实现**：`douyin_bot.py` 的 `_send_and_finalize` 根据配置调用不同策略

### 5. 日志级别配置
- **配置项**：`log_level`，取值 `DEBUG` / `INFO` / `WARNING`，默认 `INFO`
- **行为**：启动时根据配置设置 logging level；UI 监控页提供下拉框实时调整
- **实现**：`config_store.py` 读取并应用；`douyin_bot.py` 增加 DEBUG 级详细日志

### 6. Mini 悬浮状态窗
- **方案**：使用 tkinter 独立 TopLevel 窗口
- **特性**：
  - always-on-top
  - 无边框、半透明
  - 显示：运行状态、今日发送数、当前好友、倒计时
  - 位置：屏幕右下角
  - 主窗口切换到 mini 模式时隐藏主窗口，仅显示悬浮窗
- **实现**：新增 `ui/mini_window.py`，`main.py` 在启动时初始化，状态由 `DPGApp` 通过回调更新

## 兼容性
- 所有新增配置项均有默认值，老 `config.json` 无需修改
- 保存时同时保留新旧字段，切回 master 分支仍可读取

## 测试
- 更新 `tests/test_douyin_bot.py` 覆盖新的识别策略
- 更新 `tests/test_hybrid_recognizer.py` 覆盖悬停/点击逻辑
