---
intent: 让抖音 Bot 适配新版抖音 UI（悬停私信、图标发送/退出、简化滚动），同时增强日志和 Mini 悬浮状态窗。
success_criteria:
  - 私信入口支持 hover/click/auto 三种模式并可配置
  - 好友列表滚动不再强依赖滚动条控件
  - 发送按钮默认图像识别，支持 image/ocr/both 三种策略
  - 退出会话支持 auto/image/ocr/text 兼容新旧版本
  - 日志级别可配置为 DEBUG/INFO/WARNING，DEBUG 下输出详细坐标/识别结果
  - Mini 模式显示独立悬浮窗，展示运行状态/今日发送/当前好友/倒计时
risk_level: medium
auto_approve: true
branch: feature/ocr-enhancement
worktree: false
---

## Steps

- [ ] **Step 1: 扩展配置默认值和 getter**
action: 在 config_store.py 的 DEFAULT_CONFIG 中增加 enter_private_msg_mode、scroll_amount、send_button_mode、exit_session_mode、log_level；增加对应 getter 方法。
loop: false
verify: python -c "from config_store import config_store; print(config_store.get_enter_private_msg_mode(), config_store.get_scroll_amount(), config_store.get_send_button_mode(), config_store.get_exit_session_mode(), config_store.get_log_level())"

- [ ] **Step 2: 增强 hybrid_recognizer 支持悬停和按模式识别**
action: 在 hybrid_recognizer.py 中新增 hover_or_click(target, region, timeout) 方法；修改 find_element/click_element 支持 mode 参数（image/ocr/both）。
loop: false
verify: python -m pytest tests/test_hybrid_recognizer.py -v

- [ ] **Step 3: 改造 douyin_bot 适应新版抖音**
action: 修改 scroll_friend_list 使用配置 scroll_amount 在列表区域中心滚动；_enter_friend_list 使用 hover_or_click；_send_message_with_retry 使用 send_button_mode；_send_and_finalize 使用 exit_session_mode；全链路增加 DEBUG 日志。
loop: false
verify: python -m pytest tests/test_douyin_bot.py -v

- [ ] **Step 4: 创建 Mini 悬浮状态窗**
action: 新增 ui/mini_window.py，使用 tkinter 创建 always-on-top 无边框半透明小窗；提供 update_status(status, today_count, current_friend, countdown) 接口。
loop: false
verify:
  type: artifact
  path: ui/mini_window.py
  assert:
    kind: exists

- [ ] **Step 5: 在 main.py 和 DPGApp 中集成 Mini 窗与日志级别**
action: main.py 启动时读取 log_level 并应用；实例化 MiniWindow。DPGApp 增加 mini 模式切换按钮，任务运行中向 MiniWindow 发送状态更新；监控页增加日志级别下拉框。
loop: false
verify: python -m py_compile main.py ui/dpg_app.py ui/mini_window.py

- [ ] **Step 6: 在 UI 配置页增加新模式配置项**
action: 在 ui/dpg_app.py 的「抖音界面」或「API 配置」页增加 combo：enter_private_msg_mode、send_button_mode、exit_session_mode、scroll_amount、log_level，保存到 config.json。
loop: false
verify: python -m py_compile ui/dpg_app.py

- [ ] **Step 7: 更新测试覆盖新逻辑**
action: 补充 tests/test_hybrid_recognizer.py 和 tests/test_douyin_bot.py 对 hover、mode 策略的测试。
loop: false
verify: python -m pytest tests/ -v

- [ ] **Step 8: 最终验证**
action: 运行 python main.py，确认窗口正常启动、Mini 窗可切换、日志级别设置生效，无新增 traceback。
loop: false
verify: python -c "from main import main; print('导入成功')"
