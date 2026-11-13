import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import numpy as np


class TestRapidLocalOCR:
    def test_init_success(self):
        mock_ocr = MagicMock()
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            assert ocr.ocr is not None

    def test_init_failure(self):
        with patch('rapidocr_onnxruntime.RapidOCR', side_effect=ImportError):
            from ocr_service import RapidLocalOCR
            with pytest.raises(ImportError):
                RapidLocalOCR()

    def test_recognize_text(self):
        mock_ocr = MagicMock()
        mock_ocr.return_value = ([[[[0, 0], [100, 0], [100, 50], [0, 50]], "测试文字", 0.95]], None)
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            mock_img = MagicMock(spec=Image.Image)
            mock_img.convert.return_value = mock_img
            with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
                result = ocr.recognize_text(mock_img)
                assert "测试文字" in result

    def test_find_text_on_screen_success(self):
        mock_ocr = MagicMock()
        mock_ocr.return_value = ([[[[0, 0], [100, 0], [100, 50], [0, 50]], "目标文字", 0.95]], None)
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            mock_img = MagicMock(spec=Image.Image)
            mock_img.convert.return_value = mock_img
            with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
                result = ocr.find_text_on_screen(mock_img, "目标文字")
                assert result == (50, 25)

    def test_find_text_on_screen_not_found(self):
        mock_ocr = MagicMock()
        mock_ocr.return_value = ([[[[0, 0], [100, 0], [100, 50], [0, 50]], "其他文字", 0.95]], None)
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            mock_img = MagicMock(spec=Image.Image)
            mock_img.convert.return_value = mock_img
            with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
                result = ocr.find_text_on_screen(mock_img, "目标文字")
                assert result is None

    def test_find_text_on_screen_below_confidence(self):
        mock_ocr = MagicMock()
        mock_ocr.return_value = ([[[[0, 0], [100, 0], [100, 50], [0, 50]], "目标文字", 0.4]], None)
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            mock_img = MagicMock(spec=Image.Image)
            mock_img.convert.return_value = mock_img
            with patch('numpy.array', return_value=np.zeros((100, 100, 3), dtype=np.uint8)):
                result = ocr.find_text_on_screen(mock_img, "目标文字", confidence_threshold=0.6)
                assert result is None


class TestBaiduOCR:
    def test_get_access_token_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "test_token", "expires_in": 2592000}
        mock_resp.raise_for_status = MagicMock()
        with patch('ocr_service.requests.post', return_value=mock_resp):
            from ocr_service import BaiduOCR
            ocr = BaiduOCR("api_key", "secret_key")
            token = ocr._get_access_token()
            assert token == "test_token"
            assert ocr.access_token == "test_token"

    def test_get_access_token_cached(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "test_token", "expires_in": 2592000}
        mock_resp.raise_for_status = MagicMock()
        with patch('ocr_service.requests.post', return_value=mock_resp) as mock_post:
            from ocr_service import BaiduOCR
            ocr = BaiduOCR("api_key", "secret_key")
            ocr.access_token = "cached_token"
            ocr.token_expires_at = float('inf')
            token = ocr._get_access_token()
            assert token == "cached_token"
            mock_post.assert_not_called()

    def test_find_text_on_screen_success(self):
        mock_resp_token = MagicMock()
        mock_resp_token.json.return_value = {"access_token": "test_token", "expires_in": 2592000}
        mock_resp_token.raise_for_status = MagicMock()
        
        mock_resp_ocr = MagicMock()
        mock_resp_ocr.json.return_value = {
            "words_result": [{
                "words": "目标文字",
                "location": {"left": 0, "top": 0, "width": 100, "height": 50},
                "probability": {"average": 0.95}
            }]
        }
        mock_resp_ocr.raise_for_status = MagicMock()

        with patch('ocr_service.requests.post', side_effect=[mock_resp_token, mock_resp_ocr]):
            from ocr_service import BaiduOCR
            ocr = BaiduOCR("api_key", "secret_key")
            mock_img = MagicMock(spec=Image.Image)
            result = ocr.find_text_on_screen(mock_img, "目标文字")
            assert result == (50, 25)

    def test_find_text_on_screen_not_found(self):
        mock_resp_token = MagicMock()
        mock_resp_token.json.return_value = {"access_token": "test_token", "expires_in": 2592000}
        mock_resp_token.raise_for_status = MagicMock()
        
        mock_resp_ocr = MagicMock()
        mock_resp_ocr.json.return_value = {"words_result": []}
        mock_resp_ocr.raise_for_status = MagicMock()

        with patch('ocr_service.requests.post', side_effect=[mock_resp_token, mock_resp_ocr]):
            from ocr_service import BaiduOCR
            ocr = BaiduOCR("api_key", "secret_key")
            mock_img = MagicMock(spec=Image.Image)
            result = ocr.find_text_on_screen(mock_img, "目标文字")
            assert result is None


class TestCreateOCREngine:
    def test_create_local_ocr(self):
        mock_ocr = MagicMock()
        with patch('rapidocr_onnxruntime.RapidOCR', return_value=mock_ocr):
            from ocr_service import create_ocr_engine, RapidLocalOCR
            engine = create_ocr_engine("local")
            assert isinstance(engine, RapidLocalOCR)

    def test_create_baidu_ocr(self):
        with patch('ocr_service.BaiduOCR') as mock_baidu:
            from ocr_service import create_ocr_engine
            engine = create_ocr_engine("baidu", "api_key", "secret_key")
            mock_baidu.assert_called_once_with("api_key", "secret_key")

    def test_create_baidu_ocr_missing_keys(self):
        from ocr_service import create_ocr_engine
        with pytest.raises(ValueError):
            create_ocr_engine("baidu")

    def test_create_unknown_provider(self):
        from ocr_service import create_ocr_engine
        with pytest.raises(ValueError):
            create_ocr_engine("unknown")
