import requests
import base64
import logging
import time
from typing import Dict, List, Optional, Tuple
from PIL import Image
import io
import numpy as np

logger = logging.getLogger(__name__)


def normalize_for_match(text: str) -> str:
    """OCR 文本匹配前的归一化：去空白、全角转半角、转小写。

    RapidOCR 常在中文之间插入空格（如 '王 佳 豪'），或把冒号识别成全角 '：'，
    直接 substring 匹配会漏。两边都归一化后再比较。
    """
    if not text:
        return ""
    text = str(text)
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:  # 全角空格
            continue
        if 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII 区
            ch = chr(code - 0xFEE0)
        out.append(ch)
    return "".join(out).replace(" ", "").replace("\t", "").replace("\n", "").lower()


class RapidLocalOCR:
    """本地OCR引擎，基于PaddleOCR的RapidOCR，支持文字检测和边界提取，无需网络"""

    def __init__(self):
        self.ocr = None
        self._init_ocr()

    def _init_ocr(self):
        try:
            from rapidocr_onnxruntime import RapidOCR

            self.ocr = RapidOCR()
            logger.info("RapidOCR本地引擎初始化成功")
        except ImportError:
            logger.warning("RapidOCR未安装，请运行: pip install rapidocr_onnxruntime")
            raise
        except Exception as e:
            logger.warning(f"RapidOCR初始化失败: {e}")
            raise

    def _run_ocr(self, image_input, region=None):
        if self.ocr is None:
            return []

        if isinstance(image_input, Image.Image):
            if region:
                x, y, w, h = region
                image_input = image_input.crop((x, y, x + w, y + h))
            img_array = np.array(image_input.convert("RGB"))
        elif isinstance(image_input, str):
            img_array = image_input
        else:
            return []

        try:
            result, _ = self.ocr(img_array)
            if result:
                return result
        except Exception as e:
            logger.debug(f"RapidOCR识别异常: {e}")

        return []

    def recognize_text(self, image_input, region=None) -> List[str]:
        results = self._run_ocr(image_input, region)
        return [item[1] for item in results if item[1]]

    def recognize_text_with_bbox(self, image_input, region=None) -> List[Dict]:
        results = self._run_ocr(image_input, region)
        output = []
        for item in results:
            bbox_points = item[0]
            text = item[1]
            confidence = item[2]

            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            left = int(min(xs))
            top = int(min(ys))
            width = int(max(xs) - left)
            height = int(max(ys) - top)

            offset_x = region[0] if region else 0
            offset_y = region[1] if region else 0

            output.append({
                "words": text,
                "confidence": confidence,
                "bbox": bbox_points,
                "location": {
                    "left": left + offset_x,
                    "top": top + offset_y,
                    "width": width,
                    "height": height,
                },
                "center": (
                    left + width // 2 + offset_x,
                    top + height // 2 + offset_y,
                ),
            })
        return output

    def find_text_on_screen(
        self,
        screenshot: Image.Image,
        target_text: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        confidence_threshold: float = 0.6,
    ) -> Optional[Tuple[int, int]]:
        results = self.recognize_text_with_bbox(screenshot, region)

        norm_target = normalize_for_match(target_text)
        for item in results:
            if (norm_target in normalize_for_match(item["words"])
                    and item["confidence"] >= confidence_threshold):
                return item["center"]

        return None

    def find_all_text_on_screen(
        self,
        screenshot: Image.Image,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[Dict]:
        return self.recognize_text_with_bbox(screenshot, region)


class BaiduOCR:
    """百度OCR服务封装，支持通用文字识别（高精度版）"""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0
        self._base_url = "https://aip.baidubce.com/rest/2.0/ocr/v1"

    def _get_access_token(self) -> str:
        if self.access_token and time.time() < self.token_expires_at - 60:
            return self.access_token

        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        resp = requests.post(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if "access_token" not in data:
            raise RuntimeError(f"获取access_token失败: {data}")

        self.access_token = data["access_token"]
        self.token_expires_at = time.time() + data.get("expires_in", 2592000)
        logger.info("百度OCR access_token获取成功")
        return self.access_token

    @staticmethod
    def _image_to_base64(image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def recognize_text(self, image_path: str, language: str = "CHN_ENG") -> List[str]:
        token = self._get_access_token()
        url = f"{self._base_url}/accurate_basic?access_token={token}"
        image_b64 = self._image_to_base64(image_path)

        resp = requests.post(
            url,
            data={"image": image_b64, "language_type": language},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if "words_result" not in data:
            logger.warning(f"OCR识别无结果: {data.get('error_msg', 'unknown')}")
            return []

        return [item["words"] for item in data["words_result"]]

    def find_text_on_screen(
        self,
        screenshot: Image.Image,
        target_text: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        confidence_threshold: float = 0.8,
    ) -> Optional[Tuple[int, int]]:
        if region:
            x, y, w, h = region
            screenshot = screenshot.crop((x, y, x + w, y + h))

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        token = self._get_access_token()
        url = f"{self._base_url}/accurate_basic?access_token={token}"

        resp = requests.post(
            url,
            data={"image": image_b64, "language_type": "CHN_ENG"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if "words_result" not in data:
            return None

        for item in data["words_result"]:
            words = item["words"]
            prob = item.get("probability", {})
            avg_prob = prob.get("average", 0) if isinstance(prob, dict) else 0

            if target_text in words and avg_prob >= confidence_threshold:
                location = item.get("location", {})
                if location:
                    left = location.get("left", 0) + (region[0] if region else 0)
                    top = location.get("top", 0) + (region[1] if region else 0)
                    width = location.get("width", 0)
                    height = location.get("height", 0)
                    center_x = left + width // 2
                    center_y = top + height // 2
                    return (center_x, center_y)

        return None


def create_ocr_engine(
    ocr_provider: str = "local",
    baidu_api_key: str = "",
    baidu_secret_key: str = "",
):
    """工厂函数，创建OCR引擎实例

    Args:
        ocr_provider: OCR提供商，"local" 或 "baidu"
        baidu_api_key: 百度OCR API Key
        baidu_secret_key: 百度OCR Secret Key

    Returns:
        OCR引擎实例
    """
    if ocr_provider == "local":
        try:
            return RapidLocalOCR()
        except Exception as e:
            logger.warning(f"本地OCR初始化失败: {e}，尝试百度OCR...")
            if baidu_api_key and baidu_secret_key:
                return BaiduOCR(baidu_api_key, baidu_secret_key)
            raise
    elif ocr_provider == "baidu":
        if not (baidu_api_key and baidu_secret_key):
            raise ValueError("百度OCR需要提供api_key和secret_key")
        return BaiduOCR(baidu_api_key, baidu_secret_key)
    else:
        raise ValueError(f"不支持的OCR提供商: {ocr_provider}")
