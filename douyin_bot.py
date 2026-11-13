import pyautogui
import time
import os
import pyperclip
import logging
import schedule
import argparse
import threading
from requests.exceptions import RequestException
from contextlib import contextmanager

from weather_service import get_weather_data
from config_utils import project_path
from config_store import config_store
from hybrid_recognizer import HybridRecognizer
from message_manager import MessageManager
from send_log import log_send
from douyin_monitor import is_douyin_window_ready

pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# 停止标志（由外部 UI 设置，任务循环在每个好友前检查）
_stop_flag = None

# 进度回调（由外部 UI 设置：Mini 悬浮窗等需要实时知道当前好友/倒计时）
# 回调签名：cb(stage=..., friend=..., index=..., total=..., seconds_left=...)
_progress_callback = None


def set_stop_flag(flag: threading.Event):
    """设置停止标志，run_bot_task 会在每个好友处理前检查。"""
    global _stop_flag
    _stop_flag = flag


def set_progress_callback(callback):
    """设置进度回调（线程安全：回调里自行处理跨线程更新）。"""
    global _progress_callback
    _progress_callback = callback


def _report_progress(**kwargs):
    if _progress_callback is not None:
        try:
            _progress_callback(**kwargs)
        except Exception as e:
            logging.debug(f"进度回调异常: {e}")


def _is_stop_requested() -> bool:
    return _stop_flag is not None and _stop_flag.is_set()


def _get_ui_regions():
    """根据抖音窗口实际位置和尺寸计算 UI 区域坐标。

    如果抖音窗口未找到，回退到基于全屏百分比的默认值。
    所有区域坐标都是屏幕绝对坐标 (x, y, w, h)，可直接传给 pyautogui.screenshot(region=)。
    """
    default_regions = {
        "top_bar": {"x_pct": 0.65, "y_pct": 0.0, "w_pct": 0.25, "h_pct": 0.10},
        "friend_list": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.28, "h_pct": 0.85},
        "chat_bottom": {"x_pct": 0.30, "y_pct": 0.85, "w_pct": 0.65, "h_pct": 0.10},
        "chat_top": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.28, "h_pct": 0.10},
    }

    def _is_region_sane(name, region):
        # 只强制校验 top_bar，避免旧配置把高度撑到 0.34 导致图像匹配异常
        if name == 'top_bar':
            return (
                region.get('h_pct', 0) <= 0.20 and
                region.get('w_pct', 0) <= 0.50 and
                region.get('y_pct', 0) <= 0.30
            )
        return True

    # 加载用户自定义 UI 区域配置
    user_regions = {}
    try:
        user_regions = config_store.get_ui_regions()
    except Exception:
        pass

    # 检测用户自定义区域是否合理
    invalid_regions = [k for k in user_regions if not _is_region_sane(k, user_regions[k])]
    if invalid_regions:
        logging.warning(f"用户自定义区域配置异常 {invalid_regions}, 强制使用默认值")

    # 尝试获取抖音窗口实际位置和尺寸
    from douyin_monitor import get_douyin_screenshot_rect
    douyin_rect = get_douyin_screenshot_rect()

    if douyin_rect:
        dx, dy, dw, dh = douyin_rect
        logging.info(f"基于抖音窗口计算 UI 区域: 位置=({dx},{dy}), 尺寸={dw}x{dh}")
        # clamp 窗口阴影导致的负坐标
        dx = max(0, dx)
        dy = max(0, dy)
        logging.info(f"clamp 后窗口原点: ({dx},{dy}), 尺寸: {dw}x{dh}")
        regions = {}
        for key, r in default_regions.items():
            # 使用用户配置，但异常区域强制用默认
            if key in user_regions and _is_region_sane(key, user_regions[key]):
                r = {**r, **user_regions[key]}
            x = dx + int(r["x_pct"] * dw)
            y = dy + int(r["y_pct"] * dh)
            w = int(r["w_pct"] * dw)
            h = int(r["h_pct"] * dh)
            # 保证区域不超出屏幕
            x = max(0, x)
            y = max(0, y)
            w = min(w, SCREEN_WIDTH - x)
            h = min(h, SCREEN_HEIGHT - y)
            regions[key] = (x, y, w, h)
        return regions
    else:
        # 未找到抖音窗口时，允许用户自定义百分比覆盖（全屏回退模式）
        try:
            for key in default_regions:
                if key in user_regions:
                    default_regions[key].update(user_regions[key])
        except Exception:
            pass
        logging.warning("未找到抖音窗口，UI 区域基于全屏百分比（可能不准确）")
        regions = {}
        for key, r in default_regions.items():
            regions[key] = (
                int(r["x_pct"] * SCREEN_WIDTH),
                int(r["y_pct"] * SCREEN_HEIGHT),
                int(r["w_pct"] * SCREEN_WIDTH),
                int(r["h_pct"] * SCREEN_HEIGHT),
            )
        return regions


# UI 区域占位符，run_bot_task() 启动时动态计算
REGION_TOP_BAR = None
REGION_FRIEND_LIST = None
REGION_CHAT_WINDOW_BOTTOM = None
REGION_CHAT_WINDOW_TOP = None


def _refresh_ui_regions():
    """在任务启动时重新计算 UI 区域（此时抖音窗口应该已经打开）。

    被装饰为 @contextmanager 的 wrapper，在 run_bot_task 开始时调用。
    """
    global REGION_TOP_BAR, REGION_FRIEND_LIST, REGION_CHAT_WINDOW_BOTTOM, REGION_CHAT_WINDOW_TOP
    regions = _get_ui_regions()
    REGION_TOP_BAR = regions["top_bar"]
    REGION_FRIEND_LIST = regions["friend_list"]
    REGION_CHAT_WINDOW_BOTTOM = regions["chat_bottom"]
    REGION_CHAT_WINDOW_TOP = regions["chat_top"]


def scroll_friend_list(recognizer, amount=None):
    """在好友列表区域中心滚动，amount 为 None 时使用配置值。"""
    if amount is None:
        amount = config_store.get_scroll_amount()
    recognizer.scroll_at(region=REGION_FRIEND_LIST, amount=amount)
    logging.info(f"⬇️ 在好友列表中心滚动了 {amount} 单位。")


def scroll_friend_list_to_top(recognizer, rounds=2):
    """把好友列表滚回顶部。

    上一个好友查找会把列表滚到中/底部；不回顶的话，排在列表上方的好友
    永远滚不到（查找只会向下滚），多好友连续发送时会全部失败。
    """
    for _ in range(rounds):
        if _is_stop_requested():
            return
        recognizer.scroll_at(region=REGION_FRIEND_LIST, amount=20)
        time.sleep(0.3)
    logging.debug("已将好友列表滚回顶部")


def find_friend_with_scrolling(engine, friend_target, max_scrolls=20, mode=None):
    logging.info(f"🔍 开始在列表查找好友: {friend_target}, 模式={mode or 'default'}")
    scroll_friend_list_to_top(engine)

    for i in range(max_scrolls):
        if _is_stop_requested():
            logging.info("⏹ 收到停止请求，中断好友查找")
            return False
        # 每次查找前保存区域截图（覆盖），便于确认区域和 OCR 状态
        _save_region_screenshot('friend_list_search', REGION_FRIEND_LIST)
        logging.debug(f"第 {i + 1} 次查找，目标={friend_target}")
        if engine.click_element(friend_target, confidence=0.75, timeout=3, region=REGION_FRIEND_LIST, mode=mode):
            logging.debug(f"找到并点击好友: {friend_target}")
            return True

        logging.info(f"📄 第 {i + 1} 页未找到，正在滚动...")
        scroll_friend_list(engine)
        time.sleep(2)

    logging.error(f"❌ 已滚动 {max_scrolls} 次，仍未找到好友: {friend_target}")
    return False


def _control_image_path(file_name):
    return project_path('control_images', file_name)


def _save_region_screenshot(name, region):
    """保存指定区域的调试截图，便于确认 UI 区域是否覆盖目标元素。"""
    try:
        if not region or len(region) < 4:
            return
        x, y, w, h = region
        screenshot = pyautogui.screenshot(region=(x, y, w, h))
        path = project_path(f'last_{name}.png')
        screenshot.save(path)
        logging.info(f"已保存 {name} 区域截图: {path}, 区域={region}")
    except Exception as e:
        logging.warning(f"保存 {name} 区域截图失败: {e}")


def _load_runtime_config():
    try:
        config_store.load()
        errors = config_store.validate()
        if errors:
            logging.critical("配置错误: " + "；".join(errors))
            return None
        return config_store._normalized
    except Exception as e:
        logging.critical(f"配置加载失败: {e}")
        return None


def _ensure_douyin_ready(timeout=120):
    """等待抖音窗口就绪（进程在跑但窗口没好时区域计算会退化为全屏百分比）。

    等待期间每 2 秒响应一次停止请求，避免用户点了停止还要干等 120 秒。
    """
    if is_douyin_window_ready():
        return True
    logging.info(f"⏳ 等待抖音启动... (请打开抖音 PC 客户端，最多 {timeout} 秒)")
    start = time.time()
    while time.time() - start < timeout:
        if _is_stop_requested():
            logging.info("⏹ 等待抖音启动期间收到停止请求，任务取消")
            return False
        if is_douyin_window_ready():
            logging.info("检测到抖音窗口已就绪")
            return True
        time.sleep(2)
    logging.error(f"❌ 等待抖音启动超时（{timeout}秒），任务取消")
    return False


def _prepare_runtime():
    config = _load_runtime_config()
    if not config:
        return None
    recognizer = HybridRecognizer()
    msg_manager = MessageManager()
    active_preset = msg_manager.get_active_preset()
    return config, recognizer, msg_manager, active_preset


def _enter_friend_list(recognizer, max_retries=2):
    mode = config_store.get_enter_private_msg_mode()
    logging.debug(f"进入好友列表模式: {mode}")
    for attempt in range(max_retries):
        if _is_stop_requested():
            logging.info("⏹ 收到停止请求，中断进入好友列表")
            return False
        sixin_text = recognizer.get_ocr_text("ocr_text_sixin") or "消息"
        if recognizer.hover_or_click(sixin_text, region=REGION_TOP_BAR, timeout=5, mode=mode):
            time.sleep(2)
            # 保存好友列表区域截图，便于诊断区域是否覆盖实际列表
            _save_region_screenshot('friend_list', REGION_FRIEND_LIST)
            return True
        logging.warning(f"⚠️ 第{attempt+1}次尝试进入好友列表失败")
        time.sleep(3)
    logging.critical(f'无法找到"{sixin_text}"，无法进入好友列表，任务停止。')
    return False


def _locate_friend(recognizer, friend):
    nickname = friend['nickname']
    avatar_path = friend.get('avatar_image', '')
    avatar_text = friend.get('avatar_text', '')
    logging.debug(f"定位好友 {nickname}: avatar_text={avatar_text}, avatar_path={avatar_path}")

    # 1) 优先用 OCR 文字匹配（如"王佳豪"），避免图像匹配把文字当文件名
    if avatar_text:
        if find_friend_with_scrolling(recognizer, avatar_text, mode="ocr"):
            time.sleep(2)
            return True
        logging.warning(f"⚠️ OCR文字匹配失败，尝试头像匹配: {nickname}")

    # 2) fallback 到头像图像匹配
    if avatar_path:
        if os.path.isabs(avatar_path):
            avatar_absolute_path = avatar_path
        else:
            avatar_absolute_path = project_path(*avatar_path.replace('\\', '/').split('/'))
        logging.debug(f"好友 {nickname} 头像绝对路径: {avatar_absolute_path}")
        if not os.path.exists(avatar_absolute_path):
            logging.warning(f"⚠️ 跳过：好友 {nickname} 的头像文件不存在: {avatar_path}")
            return False
        if find_friend_with_scrolling(recognizer, avatar_absolute_path, mode="image"):
            time.sleep(2)
            return True
        logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}（图像匹配失败）。")
        return False

    if avatar_text:
        logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}（OCR文字匹配失败）。")
    else:
        logging.warning(f"⚠️ 跳过：好友 {nickname} 未配置头像路径或文字。")
    return False


def _build_message(msg_manager, active_preset, friend, api_host, api_key):
    if not active_preset:
        return None

    nickname = friend['nickname']
    city_name = friend['city_name']
    location_id = friend['location_id']

    if active_preset.get('use_weather_api'):
        try:
            return get_weather_data(city_name, nickname, api_key, api_host, location_id, active_preset.get('template'))
        except RequestException as e:
            logging.error(f"天气接口请求失败: {e}")
            return None

    return msg_manager.format_message(active_preset['id'], {"nickname": nickname})


def _clear_input_box(recognizer):
    try:
        send_text = recognizer.get_ocr_text("ocr_text_send") or "发送"
        result = recognizer.find_element(send_text, region=REGION_CHAT_WINDOW_BOTTOM, timeout=2)
        if result:
            input_x = result[0] - 200
            input_y = result[1]
            logging.debug(f"清空输入框: 点击位置 ({input_x}, {input_y})")
            pyautogui.click(input_x, input_y)
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('backspace')
            time.sleep(0.3)
            return True
        else:
            logging.debug("清空输入框: 未找到发送按钮位置，跳过")
    except Exception as e:
        logging.debug(f"清空输入框异常: {e}")
    return False


def _verify_paste(message):
    try:
        pasted = pyperclip.paste()
        ok = pasted is not None and message[:20] in pasted
        logging.debug(f"粘贴验证: {'成功' if ok else '失败'} (期望前20字={message[:20]!r}, 实际={pasted[:50]!r})")
        return ok
    except Exception as e:
        logging.debug(f"粘贴验证异常: {e}，默认通过")
        return True


def _send_message_with_retry(recognizer, message, max_retries=3):
    send_mode = config_store.get_send_button_mode()
    logging.debug(f"发送按钮模式: {send_mode}")

    for attempt in range(max_retries):
        try:
            _clear_input_box(recognizer)

            pyperclip.copy(message)
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.0)

            if not _verify_paste(message):
                logging.warning(f"第{attempt+1}次发送尝试：粘贴失败，重试中")
                time.sleep(2)
                continue

            clicked = False
            if send_mode == "ocr":
                send_text = recognizer.get_ocr_text("ocr_text_send") or "发送"
                clicked = recognizer.click_element(send_text, region=REGION_CHAT_WINDOW_BOTTOM, timeout=3, mode="ocr")
            elif send_mode == "image":
                clicked = recognizer.click_element("发送", region=REGION_CHAT_WINDOW_BOTTOM, timeout=3, mode="image")
            else:  # both
                send_text = recognizer.get_ocr_text("ocr_text_send") or "发送"
                clicked = recognizer.click_element(send_text, region=REGION_CHAT_WINDOW_BOTTOM, timeout=3, mode="both")

            if clicked:
                logging.debug(f"发送按钮点击成功，模式={send_mode}")
                time.sleep(1.5)
                return True

            logging.warning(f"第{attempt+1}次发送尝试：点击发送按钮失败")
            time.sleep(2)
        except Exception as e:
            logging.error(f"发送异常 (第{attempt+1}次): {e}")
            time.sleep(2)

    return False


def _send_and_finalize(recognizer, nickname, message):
    start_time = time.time()
    success = _send_message_with_retry(recognizer, message)
    duration_ms = int((time.time() - start_time) * 1000)

    log_send(
        friend=nickname,
        success=success,
        method="hybrid",
        message=message,
        duration_ms=duration_ms,
    )

    if success:
        logging.info(f"✅ 发送成功 -> {nickname}")
        time.sleep(1)
        _exit_session(recognizer)
    else:
        logging.warning(f"❌ 发送失败 -> {nickname}")
    return success


def _exit_session(recognizer):
    """根据配置退出当前会话，兼容新版图标和老版文字。"""
    exit_mode = config_store.get_exit_session_mode()
    logging.debug(f"退出会话模式: {exit_mode}")

    success = False
    if exit_mode in ("auto", "image"):
        success = recognizer.click_element("退出会话", region=REGION_CHAT_WINDOW_TOP, timeout=3, mode="image")
        logging.debug(f"图像模式退出会话结果: {success}")

    if not success and exit_mode in ("auto", "ocr", "text"):
        exit_text = recognizer.get_ocr_text("ocr_text_exit") or "退出会话"
        success = recognizer.click_element(exit_text, region=REGION_CHAT_WINDOW_TOP, timeout=3, mode="ocr")
        logging.debug(f"OCR 模式退出会话结果: {success}")

    if not success:
        # 注意：这里不能用 alt+f4 —— 它会把整个抖音客户端关掉，
        # 后面的好友就全没法发了。Esc 通常足以关闭当前聊天会话。
        logging.warning('⚠️ 未能点击"退出会话"按钮，按 Esc 尝试关闭当前会话')
        pyautogui.press('esc')
        time.sleep(0.5)


def _process_friend(recognizer, friend, api_host, api_key, msg_manager, active_preset):
    """处理单个好友。

    返回值：
      'fatal'   —— 无法进入好友列表等致命错误，调用方应终止整个任务
      'skipped' —— 好友未配置识别方式 / 列表中找不到 / 消息生成为空
      'sent'    —— 消息已发送
      'failed'  —— 找到好友但发送失败，或处理过程异常
    """
    nickname = friend['nickname']
    logging.debug(f"好友详情: {friend}")

    # 无识别方式的好友在进好友列表之前就跳过，省一次"消息"入口点击
    if not friend.get('avatar_text') and not friend.get('avatar_image'):
        logging.warning(f"⚠️ 跳过：好友 {nickname} 未配置头像路径或文字。")
        return 'skipped'

    try:
        if not _enter_friend_list(recognizer):
            return 'fatal'

        if not _locate_friend(recognizer, friend):
            return 'skipped'

        message = _build_message(msg_manager, active_preset, friend, api_host, api_key)
        logging.debug(f"生成消息: {message[:80]}..." if message and len(message) > 80 else f"生成消息: {message}")
        if not message:
            logging.warning(f"⚠️ 跳过 {nickname}：消息生成为空（天气接口失败或模板问题）")
            return 'skipped'

        sent = _send_and_finalize(recognizer, nickname, message)
        time.sleep(3)
        return 'sent' if sent else 'failed'

    except Exception as e:
        logging.error(f"处理好友 {nickname} 时发生异常: {e}", exc_info=True)
        log_send(
            friend=nickname,
            success=False,
            method="hybrid",
            message=str(e),
            duration_ms=0,
        )
        time.sleep(3)
        return 'failed'


def run_bot_task(only_friend=None):
    logging.info("🚀 --- 开始执行自动化任务 ---")

    if not _ensure_douyin_ready():
        _report_progress(stage='done')
        return

    # 抖音窗口就绪后，基于其实际位置重新计算 UI 区域
    _refresh_ui_regions()
    logging.info(f"UI 区域: top_bar={REGION_TOP_BAR}, friend_list={REGION_FRIEND_LIST}, "
                 f"chat_bottom={REGION_CHAT_WINDOW_BOTTOM}, chat_top={REGION_CHAT_WINDOW_TOP}")

    runtime = _prepare_runtime()
    if runtime is None:
        _report_progress(stage='done')
        return
    config, recognizer, msg_manager, active_preset = runtime

    api_host = config['api_host']
    api_key = config['api_key']
    friends_list = config['friends']

    # 命令行 --friend：只处理指定昵称的好友
    if only_friend:
        friends_list = [f for f in friends_list if f.get('nickname') == only_friend]
        if not friends_list:
            logging.error(f"❌ 配置中找不到昵称为 {only_friend!r} 的好友")
            _report_progress(stage='done')
            return

    logging.info(f"识别模式: {'OCR+图像混合' if recognizer.ocr_client else '图像识别'}")
    logging.info(f"私信入口模式: {config_store.get_enter_private_msg_mode()}")
    logging.info(f"发送按钮模式: {config_store.get_send_button_mode()}")
    logging.info(f"退出会话模式: {config_store.get_exit_session_mode()}")
    logging.info(f"滚动步长: {config_store.get_scroll_amount()}")
    logging.info(f"消息预设: {active_preset.get('name', '未知') if active_preset else '无'}")
    logging.info(f"待发送好友: {len(friends_list)} 人")

    logging.info("=" * 50)
    logging.info("⏳ 请在 10 秒内切换到抖音 PC 客户端窗口...")
    for i in range(10, 0, -1):
        if _is_stop_requested():
            logging.info("⏹ 倒计时期间收到停止请求，任务取消")
            _report_progress(stage='done')
            return
        _report_progress(stage='countdown', seconds_left=i)
        time.sleep(1)

    # 保存当前屏幕截图，用于调试 UI 区域是否正确
    try:
        debug_screenshot = pyautogui.screenshot()
        debug_path = project_path('last_screen.png')
        debug_screenshot.save(debug_path)
        logging.info(f"已保存调试截图: {debug_path}")
        if REGION_TOP_BAR:
            # 裁剪 top_bar 区域保存，方便确认截图位置
            crop = debug_screenshot.crop((
                REGION_TOP_BAR[0], REGION_TOP_BAR[1],
                REGION_TOP_BAR[0] + REGION_TOP_BAR[2],
                REGION_TOP_BAR[1] + REGION_TOP_BAR[3]
            ))
            crop_path = project_path('last_top_bar.png')
            crop.save(crop_path)
            logging.info(f"已保存 top_bar 区域截图: {crop_path}, 区域={REGION_TOP_BAR}")
    except Exception as e:
        logging.warning(f"保存调试截图失败: {e}")

    success_count = 0
    fail_count = 0
    skip_count = 0

    for index, friend in enumerate(friends_list):
        if _is_stop_requested():
            logging.info("⏹ 检测到停止请求，终止好友循环")
            break

        nickname = friend.get('nickname', '?')
        logging.info(f"👉 ---=> [{index + 1}/{len(friends_list)}] 正在处理: {nickname} <=---")
        _report_progress(stage='friend', friend=nickname, index=index + 1, total=len(friends_list))
        result = _process_friend(recognizer, friend, api_host, api_key, msg_manager, active_preset)
        if result == 'fatal':
            logging.error("❌ 核心操作失败，终止任务")
            fail_count += 1
            break
        elif result == 'sent':
            success_count += 1
        elif result == 'skipped':
            skip_count += 1
        elif result == 'failed':
            fail_count += 1

    if _is_stop_requested():
        logging.info("⏹ 任务已被用户停止")
    else:
        logging.info("=" * 50)
        logging.info(f"🎉 任务执行完毕。成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")
    _report_progress(stage='done', success=success_count, failed=fail_count, skipped=skip_count)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--now', action='store_true', help='立即执行')
    parser.add_argument('--friend', type=str, help='指定单个好友昵称执行')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.now or args.friend:
        run_bot_task(only_friend=args.friend)
    else:
        logging.info("⏰ 程序已启动，等待每日 08:00 调度执行...")
        schedule.every().day.at("08:00").do(run_bot_task)
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("收到 Ctrl+C，程序退出。")


if __name__ == "__main__":
    main()
