import pyautogui
import time
import os
import pyperclip
import logging
import schedule
import argparse
from logging.handlers import RotatingFileHandler
from requests.exceptions import RequestException
from PIL import Image

from weather_service import get_weather_data
from config_utils import load_config, normalize_config, validate_runtime_config, project_path

pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()


def _get_ui_regions():
    """从配置文件读取UI区域，如无则使用默认值"""
    default_regions = {
        "top_bar": {"x_pct": 0.65, "y_pct": 0.0, "w_pct": 0.25, "h_pct": 0.10},
        "friend_list": {"x_pct": 0.75, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.85},
        "chat_bottom": {"x_pct": 0.30, "y_pct": 0.85, "w_pct": 0.65, "h_pct": 0.10},
        "chat_top": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.10},
    }
    try:
        import json
        cfg_path = project_path('config.json')
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            user_regions = cfg.get('ui_regions', {})
            for key in default_regions:
                if key in user_regions:
                    default_regions[key].update(user_regions[key])
    except Exception:
        pass

    regions = {}
    for key, r in default_regions.items():
        regions[key] = (
            int(r["x_pct"] * SCREEN_WIDTH),
            int(r["y_pct"] * SCREEN_HEIGHT),
            int(r["w_pct"] * SCREEN_WIDTH),
            int(r["h_pct"] * SCREEN_HEIGHT),
        )
    return regions


def _get_ocr_texts():
    """从配置文件读取OCR识别文字"""
    default_texts = {
        "sixin": "消息",
        "send": "发送",
        "exit": "退出会话",
    }
    try:
        import json
        cfg_path = project_path('config.json')
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            user_texts = cfg.get('ocr_texts', {})
            default_texts["sixin"] = user_texts.get("ocr_text_sixin", default_texts["sixin"])
            default_texts["send"] = user_texts.get("ocr_text_send", default_texts["send"])
            default_texts["exit"] = user_texts.get("ocr_text_exit", default_texts["exit"])
    except Exception:
        pass
    return default_texts


_regions = _get_ui_regions()
_ocr_texts = _get_ocr_texts()
REGION_TOP_BAR = _regions["top_bar"]
REGION_FRIEND_LIST = _regions["friend_list"]
REGION_CHAT_WINDOW_BOTTOM = _regions["chat_bottom"]
REGION_CHAT_WINDOW_TOP = _regions["chat_top"]


class RecognitionEngine:
    """识别引擎，支持本地OCR、百度OCR和图像识别三种模式"""

    def __init__(self, ocr_config=None):
        self.ocr_config = ocr_config or {}
        self.ocr_client = None
        self.ocr_mode = "image"

        if self.ocr_config.get("use_local_ocr", True):
            try:
                from ocr_service import RapidLocalOCR
                self.ocr_client = RapidLocalOCR()
                self.ocr_mode = "local"
                logging.info("✅ 本地OCR引擎初始化成功 (RapidOCR)")
                return
            except Exception as e:
                logging.warning(f"⚠️ 本地OCR初始化失败: {e}")

        baidu_key = self.ocr_config.get("baidu_api_key", "")
        baidu_secret = self.ocr_config.get("baidu_secret_key", "")
        if baidu_key and baidu_secret:
            try:
                from ocr_service import BaiduOCR
                self.ocr_client = BaiduOCR(api_key=baidu_key, secret_key=baidu_secret)
                self.ocr_mode = "baidu"
                logging.info("✅ 百度OCR引擎初始化成功")
                return
            except Exception as e:
                logging.warning(f"⚠️ 百度OCR初始化失败: {e}")

        logging.info("📌 OCR未配置，将使用传统图像识别模式")

    def find_and_click_text(self, text: str, region=None, timeout=5) -> bool:
        if not self.ocr_client:
            return False

        start_time = time.time()
        mode_name = "本地OCR" if self.ocr_mode == "local" else "百度OCR"
        logging.info(f"🔍 {mode_name}模式：在 {('区域 ' + str(region)) if region else '全屏'} 寻找文字 '{text}'...")

        while time.time() - start_time < timeout:
            try:
                screenshot = pyautogui.screenshot()
                result = self.ocr_client.find_text_on_screen(
                    screenshot, text, region=region, confidence_threshold=0.6
                )
                if result:
                    logging.info(f"✅ OCR找到文字 '{text}' 在 {result}，准备点击。")
                    pyautogui.click(result)
                    return True
            except Exception as e:
                logging.debug(f"OCR识别异常: {e}")
            time.sleep(1)

        logging.warning(f"❌ OCR超时！在 {timeout} 秒内未找到文字: '{text}'")
        return False

    def find_and_click_image(self, image_path: str, confidence=0.8, region=None, timeout=5) -> bool:
        start_time = time.time()
        logging.info(f"🖼️ 图像模式：在 {('区域 ' + str(region)) if region else '全屏'} 寻找图像 '{image_path}'...")

        while time.time() - start_time < timeout:
            try:
                location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence, region=region)
                if location:
                    logging.info(f"✅ 找到图像 '{image_path}' 在 {location}，准备点击。")
                    pyautogui.click(location)
                    return True
            except pyautogui.PyAutoGUIException:
                pass
            time.sleep(0.5)

        logging.warning(f"❌ 图像超时！在 {timeout} 秒内未找到图像: '{image_path}'")
        return False

    def find_and_click(self, target, confidence=0.8, region=None, timeout=5) -> bool:
        if isinstance(target, str):
            if target.endswith('.png') or target.endswith('.jpg'):
                if self.ocr_client:
                    result = self.find_and_click_image(target, confidence, region, timeout)
                    if result:
                        return True
                    text_from_filename = os.path.splitext(os.path.basename(target))[0]
                    text_from_filename = text_from_filename.replace('douyin_', '').replace('_', ' ')
                    logging.info(f"图像识别失败，尝试OCR识别文字: '{text_from_filename}'")
                    return self.find_and_click_text(text_from_filename, region, timeout)
                else:
                    return self.find_and_click_image(target, confidence, region, timeout)
            else:
                if self.ocr_client:
                    return self.find_and_click_text(target, region, timeout)
                else:
                    logging.warning(f"未配置OCR，无法识别文字: '{target}'")
                    return False
        return False


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()
    file_handler = RotatingFileHandler(project_path('run.log'), maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def scroll_friend_list(amount=-200):
    x, y, width, height = REGION_FRIEND_LIST
    center_x = x + width // 2
    center_y = y + height // 2
    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.8)
    pyautogui.scroll(amount)
    logging.info(f"⬇️ 在列表中心悬停并滚动了 {amount} 单位。")


def find_friend_with_scrolling(engine: RecognitionEngine, friend_target, max_scrolls=20):
    logging.info(f"🔍 开始在列表查找好友: {friend_target}")

    for i in range(max_scrolls):
        if engine.find_and_click(friend_target, confidence=0.75, timeout=3, region=REGION_FRIEND_LIST):
            return True

        logging.info(f"📄 第 {i + 1} 页未找到，正在滚动...")
        scroll_friend_list(amount=-200)
        time.sleep(2)

    logging.error(f"❌ 已滚动 {max_scrolls} 次，仍未找到好友: {friend_target}")
    return False


def _control_image_path(file_name):
    return project_path('control_images', file_name)


def _load_runtime_config():
    try:
        raw_config = load_config()
    except ValueError as e:
        logging.critical(f"配置文件错误: {e}")
        return None

    config, warnings = normalize_config(raw_config)
    config['api_key'] = os.environ.get('DOUYIN_WEATHER_API_KEY', config.get('api_key', '')).strip()

    if not config.get('ocr_api_key'):
        config['ocr_api_key'] = os.environ.get('BAIDU_OCR_API_KEY', '').strip()
    if not config.get('ocr_secret_key'):
        config['ocr_secret_key'] = os.environ.get('BAIDU_OCR_SECRET_KEY', '').strip()

    for warning in warnings:
        logging.warning(f"配置兼容处理: {warning}")

    errors = validate_runtime_config(config)
    if errors:
        logging.critical("配置错误: " + "；".join(errors))
        return None

    return config


def run_bot_task():
    logging.info("🚀 --- 开始执行自动化任务 ---")
    config = _load_runtime_config()
    if not config:
        return

    api_host = config['api_host']
    api_key = config['api_key']
    message_template = config.get('message_template')
    friends_list = config['friends']

    ocr_config = {
        'use_local_ocr': config.get('use_local_ocr', True),
        'baidu_api_key': config.get('ocr_api_key', ''),
        'baidu_secret_key': config.get('ocr_secret_key', ''),
    }
    engine = RecognitionEngine(ocr_config)

    if engine.ocr_mode == "local":
        logging.info("识别模式: 本地OCR (RapidOCR，离线)")
    elif engine.ocr_mode == "baidu":
        logging.info("📌 识别模式: 百度OCR (在线)")
    else:
        logging.info("📌 识别模式: 传统图像识别")
        sixin_icon = _control_image_path('douyin_sixin_icon.png')
        send_button = _control_image_path('douyin_send_button.png')
        exit_button = _control_image_path('douyin_exit_chat_button.png')
        for required_image in (sixin_icon, send_button, exit_button):
            if not os.path.exists(required_image):
                logging.critical(f"缺少控制图像文件: {required_image}")
                return

    logging.info("=" * 50)
    logging.info("⏳ 请在 10 秒内切换到抖音 PC 客户端窗口...")
    time.sleep(10)

    for friend in friends_list:
        nickname = friend['nickname']
        city_name = friend['city_name']
        location_id = friend['location_id']
        avatar_path = friend.get('avatar_image', '')
        avatar_text = friend.get('avatar_text', '')

        logging.info(f"👉 ---=> 正在处理: {nickname} <=---")

        if engine.ocr_client:
            if not engine.find_and_click_text(_ocr_texts["sixin"], timeout=5, region=REGION_TOP_BAR):
                logging.critical(f'无法找到"{_ocr_texts["sixin"]}"文字，无法进入好友列表，任务停止。')
                break
        else:
            sixin_icon = _control_image_path('douyin_sixin_icon.png')
            if not engine.find_and_click_image(sixin_icon, timeout=5, region=REGION_TOP_BAR):
                logging.critical('无法找到"私信"图标，无法进入好友列表，任务停止。')
                break
        time.sleep(2)

        if avatar_text:
            if not find_friend_with_scrolling(engine, avatar_text):
                logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}。")
                continue
        elif avatar_path:
            avatar_absolute_path = project_path(*avatar_path.split('/'))
            if not os.path.exists(avatar_absolute_path):
                logging.warning(f"⚠️ 跳过：好友 {nickname} 的头像文件不存在: {avatar_path}")
                continue
            if not find_friend_with_scrolling(engine, avatar_absolute_path):
                logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}。")
                continue
        else:
            logging.warning(f"⚠️ 跳过：好友 {nickname} 未配置头像路径或文字。")
            continue

        time.sleep(2)

        try:
            weather_message = get_weather_data(city_name, nickname, api_key, api_host, location_id, message_template)
        except RequestException as e:
            logging.error(f"天气接口请求失败（重试后仍失败）: {e}")
            weather_message = None

        if weather_message:
            logging.info("正在粘贴并发送消息...")
            pyperclip.copy(weather_message)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.5)

            if engine.ocr_client:
                send_success = engine.find_and_click_text(_ocr_texts["send"], region=REGION_CHAT_WINDOW_BOTTOM)
            else:
                send_button = _control_image_path('douyin_send_button.png')
                send_success = engine.find_and_click_image(send_button, region=REGION_CHAT_WINDOW_BOTTOM)

            if send_success:
                logging.info(f"✅ 发送成功 -> {nickname}")
                time.sleep(1)

                if engine.ocr_client:
                    exit_success = engine.find_and_click_text(_ocr_texts["exit"], region=REGION_CHAT_WINDOW_TOP)
                else:
                    exit_button = _control_image_path('douyin_exit_chat_button.png')
                    exit_success = engine.find_and_click_image(exit_button, region=REGION_CHAT_WINDOW_TOP)

                if not exit_success:
                    logging.error('⚠️ 警告：未能点击"退出会话"按钮，可能会影响下一位好友的查找。')
            else:
                logging.warning('❌ 发送失败：找不到"发送"按钮。')

        time.sleep(3)

    logging.info("🎉 所有任务执行完毕。")


def main():
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument('--now', action='store_true', help='立即执行')
    args = parser.parse_args()

    if args.now:
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
