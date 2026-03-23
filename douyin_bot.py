import pyautogui
import time
import os
import pyperclip
import logging
import schedule
import argparse
from logging.handlers import RotatingFileHandler
from requests.exceptions import RequestException

from weather_service import get_weather_data
from config_utils import load_config, normalize_config, validate_runtime_config, project_path

# 设置pyautogui的暂停时间和紧急停止功能
pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

# --- 配置区域常量 ---
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# 1. 顶栏区域：用于寻找右上角的“私信”图标
# 建议：保持原状，除非您发现点击不准
REGION_TOP_BAR = (int(SCREEN_WIDTH * 0.70), 0, int(SCREEN_WIDTH * 0.15), int(SCREEN_HEIGHT * 0.12))

# 2. 好友列表区域 (屏幕右侧列表)
# 这是鼠标悬停和查找头像的关键区域
REGION_FRIEND_LIST = (int(SCREEN_WIDTH * 0.75), int(SCREEN_HEIGHT * 0.10), int(SCREEN_WIDTH * 0.25),
                      int(SCREEN_HEIGHT * 0.85))

# 3. 聊天窗口底部区域 (发送按钮)
REGION_CHAT_WINDOW_BOTTOM = (int(SCREEN_WIDTH * 0.30), int(SCREEN_HEIGHT * 0.85), int(SCREEN_WIDTH * 0.65),
                             int(SCREEN_HEIGHT * 0.10))

# 4. 聊天窗口顶部区域 (退出会话按钮)
REGION_CHAT_WINDOW_TOP = (int(SCREEN_WIDTH * 0.70), int(SCREEN_HEIGHT * 0.10), int(SCREEN_WIDTH * 0.25),
                          int(SCREEN_HEIGHT * 0.10))


def setup_logging():
    """配置日志系统"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 移除旧的处理器，防止重复打印
    if logger.hasHandlers():
        logger.handlers.clear()

    # 文件日志（滚动，防止长期运行导致日志无限膨胀）
    file_handler = RotatingFileHandler(project_path('run.log'), maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def find_and_click(image_path, confidence=0.8, timeout=5, region=None):
    """
    在屏幕上查找图像并点击
    """
    start_time = time.time()
    logging.info(f"正在 {(('区域 ' + str(region)) if region else '全屏')} 寻找 '{image_path}'...")
    while time.time() - start_time < timeout:
        try:
            # 查找图片中心点
            location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence, region=region)
            if location:
                logging.info(f"✅ 找到 '{image_path}' 在 {location}，准备点击。")
                pyautogui.click(location)
                return True
        except pyautogui.PyAutoGUIException:
            pass
        time.sleep(0.5)  # 缩短单次循环间隔，提高响应速度
    logging.warning(f"❌ 超时！在 {timeout} 秒内未找到图片: '{image_path}'")
    return False


def scroll_friend_list(amount=-200):
    """
    在好友列表区域执行纯滚动操作 (无点击)
    :param amount: 滚动量，负数表示向下滚动。建议设置小一点(-200)以防跳过。
    """
    # 计算好友列表区域的中心点
    x, y, width, height = REGION_FRIEND_LIST
    center_x = x + width // 2
    center_y = y + height // 2

    # 1. 将鼠标悬停在列表中心
    pyautogui.moveTo(center_x, center_y)

    # 【关键修改】增加悬停等待时间
    # 许多UI需要鼠标停留一小会儿才会把滚动焦点切换过去
    time.sleep(0.8)

    # 2. 执行滚动
    pyautogui.scroll(amount)
    logging.info(f"⬇️ 在列表中心悬停并滚动了 {amount} 单位。")


def find_friend_with_scrolling(friend_avatar_path, max_scrolls=20):
    """
    通过“查找 -> 滚动 -> 查找”的循环来寻找好友
    """
    logging.info(f"🔍 开始在列表查找好友头像: {friend_avatar_path}")

    for i in range(max_scrolls):
        # 1. 尝试在当前视野中查找好友
        # 【关键修改】timeout 增加到 3 秒。
        # 给程序足够的时间“看清”当前屏幕，防止因为识别慢而错过
        if find_and_click(friend_avatar_path, confidence=0.75, timeout=3, region=REGION_FRIEND_LIST):
            return True

        logging.info(f"📄 第 {i + 1} 页未找到，正在滚动...")

        # 2. 如果没找到，就滚动列表
        scroll_friend_list(amount=-200)  # 减小幅度，防止滚过头

        # 3. 给时间让界面动画完成并完全静止
        # 【关键修改】增加到 2 秒，确保列表完全停稳，图像不再模糊
        time.sleep(2)

    logging.error(f"❌ 已滚动 {max_scrolls} 次，仍未找到好友头像: {friend_avatar_path}")
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

    # 遍历处理每个好友
    for friend in friends_list:
        nickname = friend['nickname']
        city_name = friend['city_name']
        location_id = friend['location_id']
        avatar_path = friend.get('avatar_image', '')

        logging.info(f"👉 ---=> 正在处理: {nickname} <=---")

        # 1. 确保私信列表是打开的 (点击右上角私信图标)
        # 增加 region 限制，防止点错
        if not find_and_click(sixin_icon, timeout=5, region=REGION_TOP_BAR):
            logging.critical("无法找到“私信”图标，无法进入好友列表，任务停止。")
            break
        time.sleep(2)

        # 2. 查找好友 (核心查找逻辑)
        if avatar_path:
            avatar_absolute_path = project_path(*avatar_path.split('/'))
            if not os.path.exists(avatar_absolute_path):
                logging.warning(f"⚠️ 跳过：好友 {nickname} 的头像文件不存在: {avatar_path}")
                continue

            if not find_friend_with_scrolling(avatar_absolute_path):
                logging.warning(f"⚠️ 跳过：无法在列表中找到好友 {nickname}。")
                continue
        else:
            logging.warning(f"⚠️ 跳过：好友 {nickname} 未配置头像路径。")
            continue

        # 找到好友并点击后，稍微等待进入聊天界面
        time.sleep(2)

        # 3. 获取天气并发送
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

            if find_and_click(send_button, region=REGION_CHAT_WINDOW_BOTTOM):
                logging.info(f"✅ 发送成功 -> {nickname}")
                time.sleep(1)

                # 4. 退出会话 (关键：返回列表以便处理下一个)
                if not find_and_click(exit_button, region=REGION_CHAT_WINDOW_TOP):
                    logging.error("⚠️ 警告：未能点击“退出会话”按钮，可能会影响下一位好友的查找。")
            else:
                logging.warning("❌ 发送失败：找不到“发送”按钮。")

        time.sleep(3)  # 缓冲时间，准备下一位

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