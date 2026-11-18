# 抖音PC客户端 - 每日天气助手-自动续火花 (v7 窗口绑定版)

向指定的抖音好友每日定时发送其所在城市的天气预报。v7 在 v6 基础上**整包重写**：
借鉴 [MaaNTE](https://github.com/Maa-NTE/MaaNTE)（MaaFramework 流水线）与
[ok-nte](https://github.com/BnanZ0/ok-nte)（窗口句柄后台截图）两类游戏辅助的成熟做法，
核心变化是——**绑定窗口、先断言页面状态、再行动**。

## ✨ 核心特性

*   **窗口句柄绑定截图**（不再全屏截图+屏幕百分比区域）
    *   PrintWindow **后台截图**：抖音被遮挡、放副屏都能正常识别与点击
    *   BitBlt / mss 全屏裁剪自动降级（探针会如实报告抖音支持哪种）
    *   DWM 真实边界 + DPI 感知：多屏/缩放不失真
    *   一键把抖音挪到**副屏**，不占主屏幕
*   **页面状态机流水线**（Maa 风格，先识别后行动）
    *   每一步先 OCR 断言当前页面（首页 / 消息列表 / 聊天中 / 未知）
    *   状态不匹配绝不动手；失败走恢复链（滚回顶部重找 / 退出聊天收尾）
    *   完整执行路径留痕（history），失败可复盘
*   **桌面 GUI**（DearPyGui）：仪表盘 / 好友 / 消息预设 / 设置 / 监控 / 发送记录
    *   Mini 悬浮窗：任务运行时主窗隐藏，副屏小窗看进度、一键停止
*   **消息预设库**：天气模板 / 早安 / 晚安 / 自定义文本，一键激活
*   **发送留痕**：SQLite 记录成功/失败/耗时/消息预览，CSV 导出
*   **调度器**：每日 HH:MM 自动执行（时间归一化，`8:00` 也能正确触发）
*   **天气 API**：和风天气 + tenacity 重试；密钥支持环境变量且不落盘

## 📁 项目结构

```
douyin_auto_sender/
├── main.py                 # GUI 入口（薄壳）
├── core/                   # 核心引擎
│   ├── config.py           #   统一配置（单例 + 纯函数，唯一入口）
│   ├── ocr.py              #   RapidOCR 封装 + 百度OCR + 归一化匹配
│   ├── window_capture.py   #   HWND 绑定 + 三模式截图 + 副屏安置
│   ├── page_state.py       #   页面状态检测（先断言后行动）
│   ├── pipeline.py         #   Maa 风格引擎（识别/动作/next/on_error）
│   ├── actions.py          #   鼠标键盘动作唯一出口（窗口坐标）
│   └── bot.py              #   节点组装 + CLI（python -m core.bot）
├── services/               # 外围服务
│   ├── weather.py          #   和风天气
│   ├── messages.py         #   消息预设库
│   ├── send_log.py         #   SQLite 发送留痕
│   ├── scheduler.py        #   每日调度
│   └── process_stats.py     #   进程统计（按需采样）
├── ui/                     # 界面
│   ├── app.py              #   App 薄壳（组装/任务线程/后台刷新）
│   ├── pages/              #   六个页面各一文件
│   ├── theme.py / widgets.py / fonts.py / mini_window.py
├── tools/
│   └── capture_probe.py    #   零动作探针（验证截图模式+状态识别）
└── tests/                  # 90 个离线测试（含 7-28 真实截图回归）
```

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 零动作探针（不碰鼠标键盘，安全验证截图与识别链路）
python tools/capture_probe.py

# 3. GUI 配置好友/消息/API（或直接编辑 config.json）
python main.py

# 4. 真机单好友测试（推荐先跑这个）
python -m core.bot --friend 王佳豪

# 5. 全量发送 / 每日调度
python -m core.bot --now
```

有副屏的话加 `--to-secondary`，抖音窗口自动挪过去，主屏继续干别的。

## 🔬 推荐验证流程（三步，由安全到真实）

1.  **探针** `python tools/capture_probe.py`：打印三种截图模式哪种有效、
    当前识别到的页面状态与锚点，并保存 `last_probe.png` 供人眼复核
2.  **单好友** `python -m core.bot --friend 王佳豪`：完整流水线，
    每步坐标与状态断言都写入 `run.log`（DEBUG 级别下含 OCR 识别块）
3.  **全量** `python -m core.bot --now` 或 GUI 里点「立即执行任务」

紧急停止：鼠标猛甩到**屏幕左上角**（pyautogui FAILSAFE），或 Mini 窗 / GUI 停止按钮。

## ⚙️ 配置说明（config.json）

```jsonc
{
  "api_host": "xxx.qweatherapi.com",
  "api_key": "和风天气Key",
  "schedule_time": "08:00",        // 每日执行时间
  "scheduler_enabled": true,
  "log_level": "INFO",
  "friends": [
    {
      "nickname": "王佳豪",        // 私信列表里显示的名字（v7 识别即 OCR 该文字）
      "city_name": "项城",
      "location_id": "101181407"   // 和风天气城市ID（GUI 里有速查表）
    }
  ]
}
```

v7 的好友识别 = OCR 匹配列表里的昵称文字，**不再需要截头像、框屏幕区域**。
密钥建议用环境变量：`DOUYIN_WEATHER_API_KEY`（运行时优先，且不会被保存动作写进文件）。

## 🧪 测试

```bash
pytest -q          # 90 个测试：OCR/配置/调度/动作层/流水线/状态识别（真实截图回归）
```

所有测试离线运行（mock 鼠标键盘），含 2026-07-28 真实运行截图的识别回归用例。

## 📜 版本史

| 版本 | 要点 |
|---|---|
| v5.x | Tkinter/PySide6 时代（master 分支保留） |
| v6.0 | DearPyGui 重构 + OCR（`feature/ocr-enhancement` 分支） |
| v7 | **整包重写**：窗口绑定 + 状态机流水线（本分支） |

v6 及更早版本可在对应分支找到；设计文档见 `docs/plans/`。

-----
*作者GitHub - https://github.com/woyaoxingfua*
