import time
import os
import logging
from PySide6.QtCore import QThread, Signal

from config_utils import load_config, normalize_config, validate_runtime_config, project_path
from weather_service import get_weather_data
from ocr_service import RapidLocalOCR, BaiduOCR

try:
    import pyautogui
    import pyperclip
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class BotWorker(QThread):
    log = Signal(str, str)
    progress = Signal(int, int)
    status = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self.engine = None

    def _emit_log(self, level, msg):
        self.log.emit(level, msg)

    def run(self):
        if not PYAUTOGUI_AVAILABLE:
            self.failed.emit("pyautogui 未安装，无法执行自动化任务")
            return

        self._running = True
        self.status.emit("正在加载配置...")

        try:
            raw_config = load_config()
        except ValueError as e:
            self.failed.emit(f"配置文件错误: {e}")
            return

        config, warnings = normalize_config(raw_config)
        config['api_key'] = os.environ.get('DOUYIN_WEATHER_API_KEY', config.get('api_key', '')).strip()
        if not config.get('ocr_api_key'):
            config['ocr_api_key'] = os.environ.get('BAIDU_OCR_API_KEY', '').strip()
        if not config.get('ocr_secret_key'):
            config['ocr_secret_key'] = os.environ.get('BAIDU_OCR_SECRET_KEY', '').strip()

        for w in warnings:
            self._emit_log("WARNING", f"配置兼容处理: {w}")

        errors = validate_runtime_config(config)
        if errors:
            self.failed.emit("配置错误: " + "；".join(errors))
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

        self.status.emit("正在初始化识别引擎...")
        engine = self._init_engine(ocr_config)
        self.engine = engine

        if not engine:
            self._emit_log("WARNING", "OCR未配置，将使用传统图像识别模式")
            for img in ('douyin_sixin_icon.png', 'douyin_send_button.png', 'douyin_exit_chat_button.png'):
                if not os.path.exists(project_path('control_images', img)):
                    self.failed.emit(f"缺少控制图像文件: {img}")
                    return

        total = len(friends_list)
        self.progress.emit(0, total)

        self._emit_log("INFO", "🚀 --- 开始执行自动化任务 ---")
        self.status.emit("请在 10 秒内切换到抖音 PC 客户端窗口...")
        for i in range(10, 0, -1):
            if not self._running:
                self._emit_log("INFO", "任务已取消")
                return
            self.status.emit(f"等待切换窗口... ({i}s)")
            time.sleep(1)

        for idx, friend in enumerate(friends_list, 1):
            if not self._running:
                self._emit_log("INFO", "任务已取消")
                return

            nickname = friend['nickname']
            city_name = friend['city_name']
            location_id = friend['location_id']
            avatar_path = friend.get('avatar_image', '')
            avatar_text = friend.get('avatar_text', '')

            self._emit_log("INFO", f"👉 ---=> 正在处理: {nickname} <=---")
            self.status.emit(f"正在处理 {idx}/{total}: {nickname}")

            try:
                self._process_friend(engine, friend, api_key, api_host, message_template)
            except Exception as e:
                self._emit_log("ERROR", f"处理好友 {nickname} 时出错: {e}")

            self.progress.emit(idx, total)

        self._emit_log("INFO", "🎉 所有任务执行完毕。")
        self.status.emit("任务完成")
        self.finished_ok.emit()

    def _init_engine(self, ocr_config):
        engine = {"mode": "image", "ocr": None}

        if ocr_config.get("use_local_ocr", True):
            try:
                ocr = RapidLocalOCR()
                engine = {"mode": "local", "ocr": ocr}
                self._emit_log("INFO", "✅ 本地OCR引擎初始化成功 (RapidOCR)")
                return engine
            except Exception as e:
                self._emit_log("WARNING", f"⚠️ 本地OCR初始化失败: {e}")

        baidu_key = ocr_config.get("baidu_api_key", "")
        baidu_secret = ocr_config.get("baidu_secret_key", "")
        if baidu_key and baidu_secret:
            try:
                ocr = BaiduOCR(api_key=baidu_key, secret_key=baidu_secret)
                engine = {"mode": "baidu", "ocr": ocr}
                self._emit_log("INFO", "✅ 百度OCR引擎初始化成功")
                return engine
            except Exception as e:
                self._emit_log("WARNING", f"⚠️ 百度OCR初始化失败: {e}")

        return None

    def _find_text(self, engine, text, region=None, timeout=5):
        if not engine or not engine["ocr"]:
            return False
        mode_name = "本地OCR" if engine["mode"] == "local" else "百度OCR"
        region_str = f"区域 {region}" if region else "全屏"
        self._emit_log("INFO", f"🔍 {mode_name}模式：在 {region_str} 寻找文字 '{text}'...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                screenshot = pyautogui.screenshot()
                result = engine["ocr"].find_text_on_screen(
                    screenshot, text, region=region, confidence_threshold=0.6
                )
                if result:
                    self._emit_log("INFO", f"✅ OCR找到文字 '{text}' 在 {result}")
                    pyautogui.click(result)
                    return True
            except Exception as e:
                self._emit_log("DEBUG", f"OCR识别异常: {e}")
            time.sleep(1)
        self._emit_log("WARNING", f"❌ OCR超时！在 {timeout} 秒内未找到文字: '{text}'")
        return False

    def _find_image(self, image_path, region=None, timeout=5, confidence=0.8):
        region_str = f"区域 {region}" if region else "全屏"
        self._emit_log("INFO", f"🖼️ 图像模式：在 {region_str} 寻找图像 '{image_path}'...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                location = pyautogui.locateCenterOnScreen(image_path, confidence=confidence, region=region)
                if location:
                    self._emit_log("INFO", f"✅ 找到图像 '{image_path}' 在 {location}")
                    pyautogui.click(location)
                    return True
            except pyautogui.PyAutoGUIException:
                pass
            time.sleep(0.5)
        self._emit_log("WARNING", f"❌ 图像超时！在 {timeout} 秒内未找到图像: '{image_path}'")
        return False

    def _scroll_friend_list(self, amount=-200):
        screen_w, screen_h = pyautogui.size()
        x = int(screen_w * 0.75)
        y = int(screen_h * 0.10)
        w = int(screen_w * 0.25)
        h = int(screen_h * 0.85)
        center_x = x + w // 2
        center_y = y + h // 2
        pyautogui.moveTo(center_x, center_y)
        time.sleep(0.8)
        pyautogui.scroll(amount)
        self._emit_log("INFO", f"⬇️ 在列表中心悬停并滚动了 {amount} 单位。")

    def _find_friend(self, engine, friend_target, region):
        for i in range(20):
            if engine and engine["ocr"] and not friend_target.endswith(('.png', '.jpg')):
                if self._find_text(engine, friend_target, region=region, timeout=3):
                    return True
            elif friend_target.endswith(('.png', '.jpg')):
                if self._find_image(friend_target, region=region, timeout=3):
                    return True
                if engine and engine["ocr"]:
                    base = os.path.splitext(os.path.basename(friend_target))[0]
                    base = base.replace('douyin_', '').replace('_', ' ')
                    self._emit_log("INFO", f"图像识别失败，尝试OCR识别文字: '{base}'")
                    if self._find_text(engine, base, region=region, timeout=3):
                        return True
            self._emit_log("INFO", f"📄 第 {i + 1} 页未找到，正在滚动...")
            self._scroll_friend_list(amount=-200)
            time.sleep(2)
        self._emit_log("ERROR", f"❌ 已滚动 20 次，仍未找到好友: {friend_target}")
        return False

    def _process_friend(self, engine, friend, api_key, api_host, message_template):
        screen_w, screen_h = pyautogui.size()
        region_top = (int(screen_w * 0.70), 0, int(screen_w * 0.15), int(screen_h * 0.12))
        region_list = (int(screen_w * 0.75), int(screen_h * 0.10), int(screen_w * 0.25), int(screen_h * 0.85))
        region_bottom = (int(screen_w * 0.30), int(screen_h * 0.85), int(screen_w * 0.65), int(screen_h * 0.10))
        region_chat_top = (int(screen_w * 0.70), int(screen_h * 0.10), int(screen_w * 0.25), int(screen_h * 0.10))

        nickname = friend['nickname']
        city_name = friend['city_name']
        location_id = friend['location_id']
        avatar_path = friend.get('avatar_image', '')
        avatar_text = friend.get('avatar_text', '')

        if engine and engine["ocr"]:
            if not self._find_text(engine, "私信", region=region_top, timeout=5):
                self._emit_log("CRITICAL", '无法找到"私信"文字，任务停止。')
                return
        else:
            icon = project_path('control_images', 'douyin_sixin_icon.png')
            if not self._find_image(icon, region=region_top, timeout=5):
                self._emit_log("CRITICAL", '无法找到"私信"图标，任务停止。')
                return
        time.sleep(2)

        if avatar_text:
            if not self._find_friend(engine, avatar_text, region_list):
                self._emit_log("WARNING", f"⚠️ 跳过：无法在列表中找到好友 {nickname}。")
                return
        elif avatar_path:
            abs_path = project_path(*avatar_path.split('/'))
            if not os.path.exists(abs_path):
                self._emit_log("WARNING", f"⚠️ 跳过：好友 {nickname} 的头像文件不存在: {avatar_path}")
                return
            if not self._find_friend(engine, abs_path, region_list):
                self._emit_log("WARNING", f"⚠️ 跳过：无法在列表中找到好友 {nickname}。")
                return
        else:
            self._emit_log("WARNING", f"⚠️ 跳过：好友 {nickname} 未配置头像路径或文字。")
            return

        time.sleep(2)

        try:
            weather_message = get_weather_data(city_name, nickname, api_key, api_host, location_id, message_template)
        except Exception as e:
            self._emit_log("ERROR", f"天气接口请求失败: {e}")
            weather_message = None

        if weather_message:
            self._emit_log("INFO", "正在粘贴并发送消息...")
            pyperclip.copy(weather_message)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.5)

            if engine and engine["ocr"]:
                send_ok = self._find_text(engine, "发送", region=region_bottom)
            else:
                send_btn = project_path('control_images', 'douyin_send_button.png')
                send_ok = self._find_image(send_btn, region=region_bottom)

            if send_ok:
                self._emit_log("INFO", f"✅ 发送成功 -> {nickname}")
                time.sleep(1)

                if engine and engine["ocr"]:
                    exit_ok = self._find_text(engine, "退出会话", region=region_chat_top)
                else:
                    exit_btn = project_path('control_images', 'douyin_exit_chat_button.png')
                    exit_ok = self._find_image(exit_btn, region=region_chat_top)

                if not exit_ok:
                    self._emit_log("ERROR", '⚠️ 警告：未能点击"退出会话"按钮，可能影响下一位好友。')
            else:
                self._emit_log("WARNING", '❌ 发送失败：找不到"发送"按钮。')

        time.sleep(3)

    def stop(self):
        self._running = False
