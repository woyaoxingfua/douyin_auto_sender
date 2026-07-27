import os
import time
import logging
import pyautogui

from config_utils import project_path
from config_store import config_store

logger = logging.getLogger(__name__)


class HybridRecognizer:
    def __init__(self):
        self.ocr_client = None
        self.use_ocr = True
        self.use_image = True
        self._ocr_enabled = True
        self._image_enabled = True
        self._last_found = None
        self._last_method = None
        self._init_ocr()
        self._load_config()

    def _init_ocr(self):
        try:
            from ocr_service import RapidLocalOCR
            self.ocr_client = RapidLocalOCR()
            logger.info("本地OCR引擎初始化成功")
        except Exception as e:
            logger.warning(f"OCR初始化失败: {e}")
            self._ocr_enabled = False

    def _load_config(self):
        try:
            self.use_ocr = config_store.get_use_local_ocr() and self._ocr_enabled
            self.use_image = True
            self.ocr_texts = config_store.get_ocr_texts()
        except Exception:
            self.ocr_texts = {
                "ocr_text_sixin": "消息",
                "ocr_text_send": "发送",
                "ocr_text_exit": "退出会话",
            }

    def find_element(self, target_text, region=None, timeout=5, confidence=0.6, mode=None):
        """
        查找屏幕元素。
        :param mode: 'image' | 'ocr' | 'both'，None 表示使用实例默认设置
        """
        self._last_found = None
        self._last_method = None
        start_time = time.time()

        use_ocr = self.use_ocr and self.ocr_client
        use_image = self.use_image
        if mode == "image":
            use_ocr = False
            use_image = True
        elif mode == "ocr":
            use_ocr = self.use_ocr and self.ocr_client
            use_image = False
        elif mode == "both":
            use_ocr = self.use_ocr and self.ocr_client
            use_image = True

        methods = []
        if use_ocr:
            methods.append(('ocr', lambda: self._ocr_find(target_text, region, confidence)))
        if use_image:
            methods.append(('image', lambda: self._image_find(target_text, region, confidence)))

        if not methods:
            logger.warning(f"未启用任何识别方法，无法查找: {target_text}")
            return None

        logger.debug(f"开始查找元素 '{target_text}', 模式={mode or 'default'}, 区域={region}, 超时={timeout}s")
        while time.time() - start_time < timeout:
            for method_name, finder in methods:
                try:
                    result = finder()
                    if result:
                        self._last_found = result
                        self._last_method = method_name
                        logger.debug(f"find_element 成功: {target_text}, 方法: {method_name}, 位置: {result}")
                        return result
                except Exception as e:
                    logger.debug(f"find_element {method_name}方法异常: {e}")

            remaining = timeout - (time.time() - start_time)
            if remaining > 0:
                time.sleep(min(0.5, remaining))

        logger.debug(f"find_element 超时({timeout}s): {target_text}")
        return None

    def _ocr_find(self, text, region, confidence):
        try:
            screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
            all_texts = self.ocr_client.recognize_text_with_bbox(screenshot, region=region)
            words = [item["words"] for item in all_texts]
            logger.debug(f"OCR识别到 {len(words)} 个文本块: {words[:20]!r}")

            result = self.ocr_client.find_text_on_screen(
                screenshot, text, region=region, confidence_threshold=confidence
            )
            if result:
                logger.info(f"OCR找到文字 '{text}' 在 {result}")
                return result
            logger.debug(f"OCR未找到文字 '{text}'，区域内全部文本: {words[:30]!r}")
        except Exception as e:
            logger.debug(f"OCR识别异常: {type(e).__name__}: {e!r}")
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
            filename = text

        image_path = project_path('control_images', filename)
        if not os.path.exists(image_path):
            if filename not in image_map:
                logger.debug(f"图像文件不存在: {image_path}")
            else:
                logger.debug(f"控制图像缺失: {image_path}")
            return None

        try:
            logger.debug(f"图像匹配 '{filename}', 置信度={confidence}, 区域={region}")
            location = pyautogui.locateCenterOnScreen(
                image_path, confidence=confidence, region=region
            )
            if location:
                logger.info(f"图像匹配找到 '{filename}' 在 {location}")
                return location
            logger.debug(f"图像匹配未找到 '{filename}'")
        except Exception as e:
            logger.debug(f"图像匹配异常 '{filename}': {type(e).__name__}: {e!r}")
        return None

    def click_element(self, target_text, region=None, timeout=5, confidence=0.6, mode=None):
        result = self.find_element(target_text, region=region, timeout=timeout, confidence=confidence, mode=mode)
        if result:
            pyautogui.click(result)
            logger.info(f"点击元素 '{target_text}' 在 {result}")
            return True
        logger.warning(f"未能找到并点击 '{target_text}'")
        return False

    def hover_or_click(self, target_text, region=None, timeout=5, confidence=0.6, mode="auto"):
        """
        悬停打开或点击打开私信入口等支持 hover 的 UI 元素。
        :param mode: 'auto'（先悬停 1 秒再点击） | 'hover' | 'click'
        """
        result = self.find_element(target_text, region, timeout, confidence, mode="both")
        if not result:
            logger.warning(f"hover_or_click 未找到目标: {target_text}")
            return False

        logger.debug(f"hover_or_click 找到目标 '{target_text}' 在 {result}，模式={mode}")
        if mode == "hover":
            pyautogui.moveTo(result)
            time.sleep(1.0)
            logger.info(f"悬停 '{target_text}' 在 {result}")
            return True

        if mode == "click":
            pyautogui.click(result)
            logger.info(f"点击 '{target_text}' 在 {result}")
            return True

        # auto: 先悬停，再点击，兼容 hover-only 和 click-only 两种客户端
        pyautogui.moveTo(result)
        time.sleep(1.0)
        pyautogui.click(result)
        logger.info(f"悬停+点击 '{target_text}' 在 {result}")
        return True

    def scroll_at(self, region=None, amount=-3):
        """
        在指定区域中心模拟滚轮滚动。
        :param region: (x, y, w, h)；为 None 时在当前鼠标位置滚动
        :param amount: 滚轮单位，负数为向下
        """
        if region and len(region) >= 4:
            cx = region[0] + region[2] // 2
            cy = region[1] + region[3] // 2
            pyautogui.moveTo(cx, cy)
            logger.debug(f"移动鼠标到滚动区域中心 ({cx}, {cy})")
        pyautogui.scroll(amount)
        logger.info(f"滚动 {amount} 单位")
        return True

    def get_ocr_text(self, key):
        return self.ocr_texts.get(key, "")

    def get_last_found(self):
        return self._last_found

    def get_last_method(self):
        return self._last_method

    def set_recognition_mode(self, use_ocr=None, use_image=None):
        if use_ocr is not None:
            self.use_ocr = use_ocr and self._ocr_enabled
        if use_image is not None:
            self.use_image = use_image
        logger.info(f"识别模式更新: OCR={self.use_ocr}, 图像={self.use_image}")
