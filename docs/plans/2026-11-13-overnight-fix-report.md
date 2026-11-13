# 2026-11-13 夜间无人值守修复报告

> 范围：`feature/ocr-enhancement` 分支工作区（含此前未提交的 v6.0 重构改动）。
> 全程未打开抖音客户端、未触碰真实鼠标键盘；所有改动停留在工作区，**未 commit**。
> 最终状态：**pytest 149/149 通过，离线端到端 dry-run 11/11 通过，py_compile 全部通过**。

## 一、结论（TL;DR）

1. **7-28 那次任务失败的根因已确认并修复**：OCR 找到好友后返回的是"子图内相对坐标"，
   没加回区域偏移就去点击，会点到屏幕左上角区域。这是 7-28 提交 `d3a82ca`
   （修复重复裁剪）只修了一半留下的——防住了二次裁剪，却丢了坐标偏移。
2. 用 7-28 保存的调试截图 `last_friend_list.png` 离线验证：RapidOCR 能识别出 64 个文本块，
   "王佳豪" 置信度 1.00 —— OCR 引擎本身没坏，坏的只是坐标换算。
3. 离线 dry-run（虚拟屏幕=当时的全屏截图）复现全链路：点击坐标
   `(1515, 332)` 与 7-28 全屏截图中王佳豪的真实位置完全吻合。

## 二、修复清单

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `hybrid_recognizer.py` | **OCR 坐标缺少区域偏移**，OCR 命中后点击错位 | `_ocr_find` 命中后加回 `(region_x, region_y)` |
| 2 | `ocr_service.py` | RapidOCR 输出常带空格/全角字符，`王 佳 豪` 匹配不上 `王佳豪` | 新增 `normalize_for_match()` 归一化后匹配 |
| 3 | `hybrid_recognizer.py` | UI 选"百度OCR/不使用OCR"实际不生效，永远加载 RapidOCR；BaiduOCR 缺 `recognize_text_with_bbox` 会被静默吞异常 | 按配置 `ocr_engine` 分发引擎；诊断日志加 hasattr 守卫 |
| 4 | `douyin_bot.py` | 退出会话兜底用 `alt+f4` —— **会把整个抖音关掉，后面好友全灭** | 改为按 `Esc` |
| 5 | `douyin_bot.py` | `_process_friend` 返回 True/False 语义模糊，找不到好友被计入"成功" | 返回 `fatal/skipped/sent/failed` 四态，统计口径正确 |
| 6 | `douyin_bot.py` | 多好友连续发送：上个好友查找把列表滚到中/底部，排前面的好友永远找不到 | 每次查找前先滚回列表顶部 |
| 7 | `douyin_bot.py` | 等待抖音启动 120 秒内不响应停止；10 秒倒计时不可中断 | 等待/倒计时循环里检查停止标志 |
| 8 | `douyin_bot.py` | `--friend` 参数从未生效（解析了没用） | `run_bot_task(only_friend=...)` 真正过滤 |
| 9 | `douyin_bot.py` | 无识别方式的好友也会白点一次"消息"入口 | 进列表前提前跳过 |
| 10 | `douyin_bot.py` | 无进度回调，Mini 悬浮窗看不到当前好友 | 新增 `set_progress_callback()`，UI 已接线 |
| 11 | `config_store.py` | 部分保存（如只存主题）会用默认值覆盖 `friends` 等未提供的键 —— **丢数据** | `save()` 以磁盘现有配置为基底合并 |
| 12 | `config_store.py` | 环境变量密钥会被 UI 保存动作明文落盘（README 承诺的安全特性被自己破坏） | 环境变量覆盖的键不回写磁盘；显式修改仍可保存 |
| 13 | `ui/dpg_app.py` | 调度时间输 `8:00` 永远不触发（与 strftime 输出 `08:00` 不匹配，静默失效） | 保存/加载都归一化为 `HH:MM`，非法输入拒绝并提示 |
| 14 | `ui/dpg_app.py` | **区域框选坐标系错位**：框选器存全屏百分比，bot 按"抖音窗口相对"换算，框出的区域整体偏移 | 新增 `screen_rect_to_window_pct()` 统一换算；预览画板同步修正（画出抖音窗口边框） |
| 15 | `ui/dpg_app.py` | 后台循环每 0.2s 全量枚举进程+窗口，CPU 空耗 | 抖音探测降为 2.5s 一次，停止/恢复请求保持 0.2s 响应 |
| 16 | `ui/dpg_app.py` | `_refresh_dashboard` 被任务线程调用时无 DPG 锁（段错误风险）；元素不存在时直接炸 | 统一 `_dpg_locked()` + `does_item_exist` 防御 |
| 17 | `main.py` / `ui/mini_window.py` | tkinter 不可用时主程序无法启动；destroy 后 Tk 根对象泄漏 | Mini 窗初始化失败降级为 None；mainloop 退出后 `_teardown_tk()` |
| 18 | `.gitignore` | 运行时产物（`last_*.png`、`send_log.db`、`preview_*.png` 等）会误入版本库 | 补齐忽略规则；清理残留 `ui/workers/` |

另：修正 `test_hybrid_recognizer.py` 一处错误断言（基线中唯一的失败项）。

## 三、验证方式（全部离线，未开抖音）

1. **单元测试**：149 个全部通过（基线 110 过 1 挂 → 修复 1 + 新增 39）。
2. **真实截图回归**：`tests/test_offline_ocr.py` 用 7-28 失败运行留下的截图，
   断言 OCR 识别块数 ≥ 10（修复前是 0）且能定位王佳豪 —— 防回归哨兵。
3. **离线端到端 dry-run**：`tools/dry_run.py`
   - 虚拟屏幕 = 7-28 的全屏截图；pyautogui 全部 mock，OCR/模板匹配用真引擎；
   - 场景 A：全链路 —— 私信入口点击 `(1474,63)` ✓、好友点击 `(1515,332)` ✓、
     无 `(233,321)` 错位点击 ✓、ctrl+v ✓、留痕 ✓、无识别方式好友跳过 ✓；
   - 场景 B：强制发送成功 → 退出会话兜底按 Esc、无 alt+f4 ✓。
   - 以后随时可跑：`.venv/Scripts/python.exe tools/dry_run.py`（约 1 分钟，退出码 0=全过）。
4. **天气 API 实测**：和风 key 请求 `/v7/weather/now` 与 `/v7/weather/3d` 均返回 200。

## 四、早上接管后建议做的事

1. **commit**（改动都在工作区，未提交；`git status` 过一遍再决定怎么拆提交）。
2. **真机小规模验证**：`python douyin_bot.py --friend 王佳豪`（本次新增的能力，
   只跑单个好友，风险最小）。 dry-run 已把点击坐标验证到像素级，但真实抖音的
   聊天窗/发送按钮在静态截图里没有，发送和退出环节仍需真机确认一次。
3. 若一切正常，切回调度模式常驻。

## 五、已知边界（非 bug，但要知道）

- dry-run 中"发送失败 -> 王佳豪"是预期：静态截图里没有聊天窗和发送按钮，
  场景 A 本来就只验证"找得到、点得准"。
- `config.json` 里的 `top_bar` 自定义区域仍会被安全校验强制回退默认值
  （`h_pct=0.3463` 超过 0.20 的历史遗留配置，属于保护行为）；框选新区域后会被覆盖。
- 搜索框路径未实现：好友定位依赖列表滚动查找（`max_scrolls=20`），对超长列表偏慢。
