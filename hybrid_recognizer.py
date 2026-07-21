import os
import time
import logging
import pyautogui

from config_utils import project_path, load_config

logger = logging.getLogger(__name__)


class HybridRecognizer:
    def __init__(self):
        self.ocr_client = None
        self.use_ocr = True
        self.use_image = True
        self._init_ocr()
        self._load_config()

    def _init_ocr(self):
        try:
            from ocr_service import RapidLocalOCR
            self.ocr_client = RapidLocalOCR()
            logger.info("本地OCR引擎初始化成功")
        except Exception as e:
            logger.warning(f"OCR初始化失败: {e}")

    def _load_config(self):
        try:
            cfg = load_config()
            self.use_ocr = cfg.get('use_local_ocr', True) and self.ocr_client is not None
            self.ocr_texts = cfg.get('ocr_texts', {
                "ocr_text_sixin": "消息",
                "ocr_text_send": "发送",
                "ocr_text_exit": "退出会话",
            })
        except Exception:
            self.ocr_texts = {
                "ocr_text_sixin": "消息",
                "ocr_text_send": "发送",
                "ocr_text_exit": "退出会话",
            }

    def find_element(self, target_text, region=None, timeout=5, confidence=0.6):
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.use_ocr and self.ocr_client:
                result = self._ocr_find(target_text, region, confidence)
                if result:
                    return result

            if self.use_image:
                result = self._image_find(target_text, region, confidence)
                if result:
                    return result

            time.sleep(0.5)

        return None

    def _ocr_find(self, text, region, confidence):
        try:
            screenshot = pyautogui.screenshot()
            result = self.ocr_client.find_text_on_screen(
                screenshot, text, region=region, confidence_threshold=confidence
            )
            if result:
                logger.info(f"OCR找到文字 '{text}' 在 {result}")
                return result
        except Exception as e:
            logger.debug(f"OCR识别异常: {e}")
        return None

    def _image_find(self, text, region, confidence):
        image_map = {
            "消息": "douyin_sixin_icon.png",
            "私信": "douyin_sixin_icon.png",
            "发送": "douyin_send_button.png",
            "退出会话": "douyin_exit_chat_button.png",
        }

        filename = image_map.get(text)
        if not filename:
            return None

        image_path = project_path('control_images', filename)
        if not os.path.exists(image_path):
            return None

        try:
            location = pyautogui.locateCenterOnScreen(
                image_path, confidence=confidence, region=region
            )
            if location:
                logger.info(f"图像匹配找到 '{filename}' 在 {location}")
                return location
        except pyautogui.PyAutoGUIException:
            pass
        return None

    def click_element(self, target_text, region=None, timeout=5):
        result = self.find_element(target_text, region, timeout)
        if result:
            pyautogui.click(result)
            return True
        return False

    def get_ocr_text(self, key):
        return self.ocr_texts.get(key, "")
