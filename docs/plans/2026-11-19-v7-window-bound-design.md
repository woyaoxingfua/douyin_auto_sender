# v7 窗口绑定版设计文档（feature/v7-window-bound）

> 立项动机：v6 的根本缺陷是"无状态、无窗口感知"——全屏截图 + 屏幕绝对百分比区域，
> 任务开始后切小窗，它还在小窗尺寸里找全屏坐标的按钮；且从不确认"当前到底是不是
> 消息页"，盲目 hover 私信入口硬试。
>
> 本分支学习 MaaNTE（MaaFramework）与 ok-nte（ok-script/AutoSplit 流派）的做法重构。

## 一、借鉴来源与对应关系

| 借鉴对象 | 学到的做法 | 本项目落点 |
|---|---|---|
| MaaFramework Pipeline 协议 | 节点 = recognition + action + next(顺序探测) + on_error(恢复链)；先识别后行动，识别不到绝不硬点 | `pipeline.py` + `bot_v2.py` |
| ok-nte / Toufool-AutoSplit | 窗口句柄绑定截图（PrintWindow 后台截图），不依赖窗口在前台/主屏 | `window_capture.py` |
| MaaFramework 页面感知 | 每步先断言页面状态，next 列表本质是"可能出现的下一状态集合" | `page_state.py` |

## 二、v6 vs v7 架构对比

```
v6 (douyin_bot.py):
  全屏截图 ──► 屏幕百分比区域(绝对坐标) ──► 找图/OCR ──► 直接点击
  问题：窗口挪了/缩小了区域全错；不知道自己在哪个页面；失败只会原地重试

v7 (bot_v2.py):
  绑定 HWND ──► PrintWindow 窗口截图(后台) ──► PageDetector 断言状态
       │                                              │
       │              状态不符 → 不动手，走恢复链
       ▼                                              ▼
  窗口相对坐标 ◄────────────────── 命中才执行 Click/Paste/Send
```

## 三、模块说明

### window_capture.py — 窗口绑定截图
- `find_douyin_hwnd()`：枚举顶层窗口按标题锁定抖音（复用 v6 判定口径）
- `get_window_rect()`：**DWM 真实边界**（DwmGetWindowAttribute），消除 Win10 阴影
  边框导致的 ~7px 系统性偏移；进程启动即设 DPI aware，多屏缩放不失真
- `WindowCapture.capture()`：三模式自动降级
  1. `print` PrintWindow(PW_RENDERFULLCONTENT)——**后台截图**，窗口可在副屏/被遮挡
  2. `bitblt` GetDC+BitBlt——print 黑图时降级（需前台）
  3. `screen` mss 全屏裁剪——保底
  黑图检测（亮度 extrema）自动触发降级，`_last_mode` 记录实际生效模式
- `move_window_to_secondary_screen()`：把抖音挪到副屏（不占主屏的关键配套）
- 所有点击坐标经 `to_screen(x, y)` 由窗口相对坐标换算——**窗口在哪都能点对**

### page_state.py — 页面状态检测
- 状态：`HOME` / `MESSAGE_LIST` / `CHAT_OPEN` / `UNKNOWN`
- ROI 全部为**窗口相对比例**；ROI 裁剪后 OCR 坐标加回偏移（防 v6 聚原点 bug 回归）
- 判定规则（7-28 真实截图验证校准）：
  - CHAT_OPEN：聊天顶部 ROI 出现"退出会话"
  - MESSAGE_LIST：列表头 ROI 同时有"搜索" + 「消息(99+)」标题特征
    （首页也有搜索框，只看"搜索"会误判——这就是 v6 "无法确认在不在消息页"的解药）
  - HOME：顶部导航有"消息"入口

### pipeline.py — Maa 风格执行引擎
- 节点生命周期：`recognize` 命中 → `action` → post_delay → 顺序探测 `next`
- `next` 轮询直到命中或超时（超时预算归当前节点 timeout，与 Maa 一致）
- 超时/action 失败 → `on_error` 恢复链（短超时探测）
- 保险丝：MAX_STEPS 死循环保护；stop_check 全程响应停止请求
- `ctx.history` 完整记录执行路径（失败诊断直接看走了哪条路）

### bot_v2.py — 全链路节点
```
AssertHome → EnterMessageList → AssertMessageList → OpenFriendChat
                                                    ├─ on_error: ScrollListTop ↺
                                                    ▼
                              AssertChatOpen → PasteMessage → ClickSend
                                                    │              │ (失败均 on_error)
                                                    ▼              ▼
                                                 ExitChat ◄────────┘
```
- `OpenFriendChat`：列表 ROI OCR 找好友名（归一化匹配），带滚回顶部重试
- `PasteMessage`：点输入区 → ctrl+a 清空 → 剪贴板粘贴
- `ClickSend`：OCR 找"发送"按钮，找不到按 Enter 兜底
- `ExitChat`：优先点"退出会话"，已回列表视为成功
- CLI：`--friend x`（单好友）、`--now`（全量）、`--probe`（零动作）、`--to-secondary`（挪副屏）

### tools/capture_probe.py — 零动作探针
只截图+识别+打印，不碰鼠标键盘。验证 hwnd 绑定/三种截图模式/状态识别，
产出 `probe_capture_*.png` 与 `last_probe.png` 供人眼复核。

## 四、测试（164/164 全过）

- v7 套件 15 个：引擎语义（顺序探测/超时/恢复链/停止/死循环保险丝）+
  真实截图回归（7-28 全屏图应判 HOME；消息浮层图应找到王佳豪；锚点不聚原点）+
  端到端 mock 流水线（点击坐标逐像素断言）
- v6 套件 149 个全部保持通过（新旧共存，v6 是回退保障）

## 五、真机验证步骤（交给用户的下一步）

```bash
# 1. 零动作探针：验证截图模式与状态识别（安全，随便跑）
python tools/capture_probe.py

# 2. 有副屏的话：先看探针输出，然后
python bot_v2.py --friend 王佳豪 --to-secondary

# 3. 通过后全量
python bot_v2.py --now
```

## 六、已知边界

- `PrintWindow` 对部分自绘渲染引擎可能截到黑图（黑图检测会自动降级 bitblt/screen，
  探针会如实报告每种模式的有效性——真机跑一次探针即知抖音支持哪种）
- `OpenFriendChat` 超长列表依赖滚动重试，搜索框直达方案留作后续优化
  （搜索框锚点 `search_box` 已在 PageDetector 里产出，接上只是节点层工作）
- v6 (douyin_bot.py) 保持原样可用，作为对照与回退
