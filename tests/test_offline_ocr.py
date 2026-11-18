"""离线 OCR 回归测试。

核心背景：2026-07-28 的真实运行中，hybrid_recognizer 把已裁剪的截图再次
按 region 裁剪，导致 OCR 永远识别出 0 个文本块（run.log 可查）。
commit d3a82ca 修复后一直没验证过 —— 这里用当时保存的调试截图离线复现
_ocr_find 的调用路径（screenshot 已裁剪 + region=None），确保：
  1. OCR 能识别出大量文本块（不再是 0）
  2. 能定位当时找不到的好友"王佳豪"
  3. 归一化匹配能容忍 OCR 插入的空格/全角字符

不依赖抖音运行，随时可跑。
"""
import os
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
from PIL import Image

from core.ocr import RapidLocalOCR, normalize_for_match

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRIEND_LIST_PNG = os.path.join(PROJECT_ROOT, 'last_friend_list.png')
TOP_BAR_PNG = os.path.join(PROJECT_ROOT, 'last_top_bar.png')


# ---------------- 归一化（纯函数） ----------------

def test_normalize_removes_spaces():
    assert normalize_for_match("王 佳 豪") == "王佳豪"
    assert normalize_for_match("  消息\n(99+) ") == "消息(99+)"


def test_normalize_fullwidth_to_halfwidth():
    assert normalize_for_match("Ａｂｃ") == "abc"
    assert normalize_for_match("消息：99＋") == "消息:99+"
    # 全角空格 U+3000
    assert normalize_for_match("a\u3000b") == "ab"


def test_normalize_empty():
    assert normalize_for_match("") == ""
    assert normalize_for_match(None) == ""


def test_find_text_matches_spaced_ocr_output():
    """OCR 把 '王佳豪' 识别成 '王 佳 豪' 时也应匹配成功。"""
    mock_ocr = MagicMock()
    mock_ocr.return_value = ([[[[0, 0], [100, 0], [100, 50], [0, 50]], "王 佳 豪", 0.95]], None)
    with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
        ocr = RapidLocalOCR()
        mock_img = MagicMock(spec=Image.Image)
        mock_img.convert.return_value = mock_img
        with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype='uint8')):
            assert ocr.find_text_on_screen(mock_img, "王佳豪") == (50, 25)


# ---------------- 真实截图回归（RapidOCR 真跑） ----------------

@pytest.mark.skipif(not os.path.exists(FRIEND_LIST_PNG),
                    reason="缺少上次运行保存的 last_friend_list.png 调试截图")
class TestOfflineRecognition:
    """用 2026-07-28 失败那次运行留下的截图做回归。

    如果换了截图，第一个用例仍然有效（验证 OCR 管线非空），
    第二个用例的期望名字可能需要同步修改。
    """

    def test_ocr_pipeline_produces_text_blocks(self):
        """修复前这里识别出 0 块（重复裁剪 bug），必须 >= 10 块。"""
        ocr = RapidLocalOCR()
        img = Image.open(FRIEND_LIST_PNG)
        results = ocr.recognize_text_with_bbox(img, region=None)
        assert len(results) >= 10, f"OCR 只识别出 {len(results)} 块，疑似回归了重复裁剪 bug"

    def test_ocr_finds_friend_from_failed_run(self):
        ocr = RapidLocalOCR()
        img = Image.open(FRIEND_LIST_PNG)
        hit = ocr.find_text_on_screen(img, "王佳豪", region=None, confidence_threshold=0.6)
        assert hit is not None, "当时运行找不到的好友现在应能定位（d3a82ca 修复验证）"

    @pytest.mark.skipif(not os.path.exists(TOP_BAR_PNG),
                        reason="缺少 last_top_bar.png 调试截图")
    def test_ocr_finds_sixin_entry_in_top_bar(self):
        ocr = RapidLocalOCR()
        img = Image.open(TOP_BAR_PNG)
        hit = ocr.find_text_on_screen(img, "消息", region=None, confidence_threshold=0.6)
        assert hit is not None
