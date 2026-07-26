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
from douyin_monitor import is_douyin_running, wait_for_douyin

pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# 停止标志（由外部 UI 设置，任务循环在每个好友前检查）
_stop_flag = None


def set_stop_flag(flag: threading.Event):
    """设置停止标志，run_bot_task 会在每个好友处理前检查。"""
    global _stop_flag
    _stop_flag = flag


def _is_stop_requested() -> bool:
    return _stop_flag is not None and _stop_flag.is_set()


def _get_ui_regions():
    """根据抖音窗口实际位置和尺寸计算 UI 区域坐标。

    如果抖音窗口未找到，回退到基于全屏百分比的默认值。
    所有区域坐标都是屏幕绝对坐标 (x, y, w, h)，可直接传给 pyautogui.screenshot(region=)。
    """
    default_regions = {
        "top_bar": {"x_pct": 0.65, "y_pct": 0.0, "w_pct": 0.25, "h_pct": 0.10},
        "friend_list": {"x_pct": 0.75, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.85},
        "chat_bottom": {"x_pct": 0.30, "y_pct": 0.85, "w_pct": 0.65, "h_pct": 0.10},
        "chat_top": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.10},
    }
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
        # 只有未找到抖音窗口时，才使用用户自定义的 UI 区域百分比
        try:
            user_regions = config_store.get_ui_regions()
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


def find_friend_with_scrolling(engine, friend_target, max_scrolls=20):
    logging.info(f"🔍 开始在列表查找好友: {friend_target}")

    for i in range(max_scrolls):
        logging.debug(f"第 {i + 1} 次查找，目标={friend_target}")
        if engine.click_element(friend_target, confidence=0.75, timeout=3, region=REGION_FRIEND_LIST):
            logging.debug(f"找到并点击好友: {friend_target}")
            return True

        logging.info(f"📄 第 {i + 1} 页未找到，正在滚动...")
        scroll_friend_list(engine)
        time.sleep(2)

    logging.error(f"❌ 已滚动 {max_scrolls} 次，仍未找到好友: {friend_target}")
    return False


def _control_image_path(file_name):
    return project_path('control_images', file_name)


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


def _ensure_douyin_ready():
    if is_douyin_running():
        return True
    logging.info("⏳ 等待抖音启动... (请打开抖音 PC 客户端)")
    if not wait_for_douyin(timeout=120):
        logging.error("❌ 等待抖音启动超时（120秒），任务取消")
        return False
    return True


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
        sixin_text = recognizer.get_ocr_text("ocr_text_sixin") or "消息"
        if recognizer.hover_or_click(sixin_text, region=REGION_TOP_BAR, timeout=5, mode=mode):
            time.sleep(2)
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

    if avatar_text:
        if not find_friend_with_scrolling(recognizer, avatar_text):
            logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}（OCR文字匹配失败）。")
            return False
        time.sleep(2)
        return True

    if avatar_path:
        # 支持相对路径（如 friend_avatars/xxx.png）
        if os.path.isabs(avatar_path):
            avatar_absolute_path = avatar_path
        else:
            avatar_absolute_path = project_path(*avatar_path.replace('\\', '/').split('/'))
        logging.debug(f"好友 {nickname} 头像绝对路径: {avatar_absolute_path}")
        if not os.path.exists(avatar_absolute_path):
            logging.warning(f"⚠️ 跳过：好友 {nickname} 的头像文件不存在: {avatar_path}")
            return False
        if not find_friend_with_scrolling(recognizer, avatar_absolute_path):
            logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}（图像匹配失败）。")
            return False
        time.sleep(2)
        return True

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
        logging.warning('⚠️ 未能点击"退出会话"按钮，尝试手动退出')
        pyautogui.hotkey('alt', 'f4')
        time.sleep(1)


def _process_friend(recognizer, friend, api_host, api_key, msg_manager, active_preset):
    nickname = friend['nickname']
    logging.debug(f"好友详情: {friend}")

    try:
        if not _enter_friend_list(recognizer):
            return False

        if not _locate_friend(recognizer, friend):
            return True

        message = _build_message(msg_manager, active_preset, friend, api_host, api_key)
        logging.debug(f"生成消息: {message[:80]}..." if message and len(message) > 80 else f"生成消息: {message}")
        if message:
            _send_and_finalize(recognizer, nickname, message)

        time.sleep(3)
        return True

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
        return True


def run_bot_task():
    logging.info("🚀 --- 开始执行自动化任务 ---")

    if not _ensure_douyin_ready():
        return

    # 抖音窗口就绪后，基于其实际位置重新计算 UI 区域
    _refresh_ui_regions()
    logging.info(f"UI 区域: top_bar={REGION_TOP_BAR}, friend_list={REGION_FRIEND_LIST}, "
                 f"chat_bottom={REGION_CHAT_WINDOW_BOTTOM}, chat_top={REGION_CHAT_WINDOW_TOP}")

    runtime = _prepare_runtime()
    if runtime is None:
        return
    config, recognizer, msg_manager, active_preset = runtime

    api_host = config['api_host']
    api_key = config['api_key']
    friends_list = config['friends']

    logging.info(f"识别模式: {'OCR+图像混合' if recognizer.ocr_client else '图像识别'}")
    logging.info(f"私信入口模式: {config_store.get_enter_private_msg_mode()}")
    logging.info(f"发送按钮模式: {config_store.get_send_button_mode()}")
    logging.info(f"退出会话模式: {config_store.get_exit_session_mode()}")
    logging.info(f"滚动步长: {config_store.get_scroll_amount()}")
    logging.info(f"消息预设: {active_preset.get('name', '未知') if active_preset else '无'}")
    logging.info(f"待发送好友: {len(friends_list)} 人")

    logging.info("=" * 50)
    logging.info("⏳ 请在 10 秒内切换到抖音 PC 客户端窗口...")
    time.sleep(10)

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

    for friend in friends_list:
        if _is_stop_requested():
            logging.info("⏹ 检测到停止请求，终止好友循环")
            break

        logging.info(f"👉 ---=> 正在处理: {friend.get('nickname', '?')} <=---")
        result = _process_friend(recognizer, friend, api_host, api_key, msg_manager, active_preset)
        if result is False:
            logging.error("❌ 核心操作失败，终止任务")
            break
        elif result is None:
            skip_count += 1
        elif result is True:
            success_count += 1

    if _is_stop_requested():
        logging.info("⏹ 任务已被用户停止")
    else:
        logging.info("=" * 50)
        logging.info(f"🎉 任务执行完毕。成功: {success_count}, 失败: {fail_count}, 跳过: {skip_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--now', action='store_true', help='立即执行')
    parser.add_argument('--friend', type=str, help='指定单个好友昵称执行')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if args.now or args.friend:
        run_bot_task()
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
