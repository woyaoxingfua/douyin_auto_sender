import pytest
import pyautogui
from unittest.mock import patch, MagicMock


class TestHybridRecognizer:
    @pytest.fixture
    def recognizer(self):
        with patch('rapidocr_onnxruntime.RapidOCR'):
            from hybrid_recognizer import HybridRecognizer
            return HybridRecognizer()

    def test_init(self, recognizer):
        assert recognizer.use_ocr is True
        assert recognizer.use_image is True
        assert recognizer._last_found is None
        assert recognizer._last_method is None

    def test_find_element_timeout(self, recognizer):
        with patch.object(recognizer, '_ocr_find', return_value=None):
            with patch.object(recognizer, '_image_find', return_value=None):
                result = recognizer.find_element("test", timeout=1)
                assert result is None
                assert recognizer._last_found is None

    def test_click_element_success(self, recognizer):
        mock_pos = (100, 200)
        with patch.object(recognizer, 'find_element', return_value=mock_pos):
            with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                result = recognizer.click_element("test")
                assert result is True
                mock_click.assert_called_once_with(mock_pos)

    def test_click_element_failure(self, recognizer):
        with patch.object(recognizer, 'find_element', return_value=None):
            with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                result = recognizer.click_element("test")
                assert result is False
                mock_click.assert_not_called()

    def test_get_ocr_text(self, recognizer):
        recognizer.ocr_texts = {"ocr_text_send": "发送"}
        assert recognizer.get_ocr_text("ocr_text_send") == "发送"
        assert recognizer.get_ocr_text("nonexistent") == ""

    def test_get_last_found(self, recognizer):
        recognizer._last_found = (50, 100)
        assert recognizer.get_last_found() == (50, 100)

    def test_get_last_method(self, recognizer):
        recognizer._last_method = "ocr"
        assert recognizer.get_last_method() == "ocr"

    def test_set_recognition_mode(self, recognizer):
        recognizer.set_recognition_mode(use_ocr=False, use_image=True)
        assert recognizer.use_ocr is False
        assert recognizer.use_image is True

    def test_ocr_disabled_when_client_none(self):
        with patch('rapidocr_onnxruntime.RapidOCR', side_effect=ImportError):
            from hybrid_recognizer import HybridRecognizer
            recognizer = HybridRecognizer()
            assert recognizer._ocr_enabled is False
            assert recognizer.ocr_client is None

    def test_hover_or_click_auto(self, recognizer):
        with patch.object(recognizer, 'find_element', return_value=(100, 200)):
            with patch('hybrid_recognizer.pyautogui.moveTo') as mock_move:
                with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                    with patch('hybrid_recognizer.time.sleep'):
                        result = recognizer.hover_or_click("test", mode="auto")
                        assert result is True
                        mock_move.assert_called_once_with((100, 200))
                        mock_click.assert_called_once_with((100, 200))

    def test_hover_or_click_hover_only(self, recognizer):
        with patch.object(recognizer, 'find_element', return_value=(100, 200)):
            with patch('hybrid_recognizer.pyautogui.moveTo') as mock_move:
                with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                    with patch('hybrid_recognizer.time.sleep'):
                        result = recognizer.hover_or_click("test", mode="hover")
                        assert result is True
                        mock_move.assert_called_once_with((100, 200))
                        mock_click.assert_not_called()

    def test_hover_or_click_not_found(self, recognizer):
        with patch.object(recognizer, 'find_element', return_value=None):
            result = recognizer.hover_or_click("test", mode="auto")
            assert result is False

    def test_find_element_with_mode(self, recognizer):
        with patch.object(recognizer, '_ocr_find', return_value=(50, 60)) as mock_ocr:
            with patch.object(recognizer, '_image_find', return_value=None) as mock_image:
                result = recognizer.find_element("test", timeout=1, mode="ocr")
                assert result == (50, 60)
                mock_ocr.assert_called()
                mock_image.assert_not_called()

    def test_scroll_at_with_region(self, recognizer):
        with patch('hybrid_recognizer.pyautogui.moveTo') as mock_move:
            with patch('hybrid_recognizer.pyautogui.scroll') as mock_scroll:
                result = recognizer.scroll_at(region=(0, 0, 100, 200), amount=-3)
                assert result is True
                mock_move.assert_called_once_with(50, 100)
                mock_scroll.assert_called_once_with(-3)

    def test_scroll_at_without_region(self, recognizer):
        with patch('hybrid_recognizer.pyautogui.moveTo') as mock_move:
            with patch('hybrid_recognizer.pyautogui.scroll') as mock_scroll:
                result = recognizer.scroll_at(amount=-5)
                assert result is True
                mock_move.assert_not_called()
                mock_scroll.assert_called_once_with(-5)

    def test_hover_or_click_click_only(self, recognizer):
        with patch.object(recognizer, 'find_element', return_value=(100, 200)):
            with patch('hybrid_recognizer.pyautogui.moveTo') as mock_move:
                with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                    with patch('hybrid_recognizer.time.sleep'):
                        result = recognizer.hover_or_click("test", mode="click")
                        assert result is True
                        mock_move.assert_not_called()
                        mock_click.assert_called_once_with((100, 200))

    def test_click_element_with_mode(self, recognizer):
        mock_pos = (150, 250)
        with patch.object(recognizer, 'find_element', return_value=mock_pos) as mock_find:
            with patch('hybrid_recognizer.pyautogui.click') as mock_click:
                result = recognizer.click_element("test", mode="ocr")
                assert result is True
                mock_find.assert_called_once_with("test", region=None, timeout=5,
                                                   confidence=0.6, mode="ocr")
                mock_click.assert_called_once_with(mock_pos)

    def test_find_element_image_mode(self, recognizer):
        with patch.object(recognizer, '_ocr_find', return_value=(50, 60)) as mock_ocr:
            with patch.object(recognizer, '_image_find', return_value=(70, 80)) as mock_image:
                result = recognizer.find_element("test", timeout=1, mode="image")
                assert result == (70, 80)
                mock_ocr.assert_not_called()
                mock_image.assert_called()


class TestOcrRegionOffset:
    """OCR 坐标系回归：子图内相对坐标必须加回区域偏移。

    2026-11 排查发现：d3a82ca 修复"重复裁剪"时把 region=None 传进 OCR，
    但忘了把返回的子图内坐标加回 (region_x, region_y) 偏移 —— 图像匹配路径
    （pyautogui.locateCenterOnScreen）返回的是屏幕绝对坐标，两条路径不一致
    会导致 OCR 找到目标后点错位置。
    """

    def _make_recognizer_with_fake_ocr(self):
        with patch('rapidocr_onnxruntime.RapidOCR'):
            from hybrid_recognizer import HybridRecognizer
            recognizer = HybridRecognizer()
        recognizer.ocr_client.find_text_on_screen = lambda *a, **k: (50, 60)
        recognizer.ocr_client.recognize_text_with_bbox = lambda *a, **k: []
        return recognizer

    def test_ocr_find_adds_region_offset(self):
        from PIL import Image
        recognizer = self._make_recognizer_with_fake_ocr()
        fake_img = Image.new('RGB', (100, 100))
        with patch('hybrid_recognizer.pyautogui.screenshot', return_value=fake_img):
            result = recognizer.find_element(
                "目标", region=(200, 100, 300, 200), timeout=1, mode="ocr")
        assert result == (250, 160)  # (200+50, 100+60)

    def test_ocr_find_without_region_uses_raw_coords(self):
        from PIL import Image
        recognizer = self._make_recognizer_with_fake_ocr()
        fake_img = Image.new('RGB', (100, 100))
        with patch('hybrid_recognizer.pyautogui.screenshot', return_value=fake_img):
            result = recognizer.find_element("目标", timeout=1, mode="ocr")
        assert result == (50, 60)


class TestOcrEngineSelection:
    """ocr_engine 配置应真正决定加载哪个引擎。"""

    def test_engine_none_disables_ocr(self, monkeypatch):
        import config_store as cs
        monkeypatch.setattr(
            cs.config_store, "get",
            lambda key=None, default=None: 'none' if key == 'ocr_engine' else default)
        with patch('rapidocr_onnxruntime.RapidOCR') as mock_rapid:
            from hybrid_recognizer import HybridRecognizer
            recognizer = HybridRecognizer()
        assert recognizer.ocr_client is None
        assert recognizer._ocr_enabled is False
        mock_rapid.assert_not_called()

    def test_engine_baidu_uses_baidu_client(self, monkeypatch):
        import config_store as cs
        monkeypatch.setattr(
            cs.config_store, "get",
            lambda key=None, default=None: 'baidu' if key == 'ocr_engine' else default)
        monkeypatch.setattr(cs.config_store, "get_ocr_api_key", lambda: "ak")
        monkeypatch.setattr(cs.config_store, "get_ocr_secret_key", lambda: "sk")
        with patch('ocr_service.BaiduOCR') as mock_baidu:
            from hybrid_recognizer import HybridRecognizer
            recognizer = HybridRecognizer()
        mock_baidu.assert_called_once_with("ak", "sk")
        assert recognizer.ocr_client is mock_baidu.return_value

    def test_engine_baidu_without_keys_falls_back_to_rapid(self, monkeypatch):
        import config_store as cs
        monkeypatch.setattr(
            cs.config_store, "get",
            lambda key=None, default=None: 'baidu' if key == 'ocr_engine' else default)
        monkeypatch.setattr(cs.config_store, "get_ocr_api_key", lambda: "")
        monkeypatch.setattr(cs.config_store, "get_ocr_secret_key", lambda: "")
        with patch('rapidocr_onnxruntime.RapidOCR'):
            with patch('ocr_service.BaiduOCR') as mock_baidu:
                from hybrid_recognizer import HybridRecognizer
                recognizer = HybridRecognizer()
        mock_baidu.assert_not_called()
        assert recognizer.ocr_client is not None
