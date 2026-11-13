import pytest
import ctypes
import ctypes.wintypes
from unittest.mock import patch, MagicMock


class TestProcessMonitor:
    def test_is_douyin_running_true(self):
        mock_proc = MagicMock()
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            from douyin_monitor import is_douyin_running
            assert is_douyin_running() is True

    def test_is_douyin_running_false(self):
        with patch('douyin_monitor.find_douyin_process', return_value=None):
            with patch('douyin_monitor._find_douyin_window_by_title', return_value=None):
                from douyin_monitor import is_douyin_running
                assert is_douyin_running() is False

    def test_wait_for_douyin_success(self):
        with patch('douyin_monitor.is_douyin_running', return_value=True):
            with patch('douyin_monitor.is_douyin_window_ready', return_value=True):
                from douyin_monitor import wait_for_douyin
                result = wait_for_douyin(timeout=3)
                assert result is True

    def test_wait_for_douyin_timeout(self):
        with patch('douyin_monitor.is_douyin_running', return_value=False):
            with patch('douyin_monitor.time.sleep') as mock_sleep:
                from douyin_monitor import wait_for_douyin
                result = wait_for_douyin(timeout=1)
                assert result is False
                assert mock_sleep.call_count > 0

    def test_find_douyin_process_found(self):
        mock_proc = MagicMock()
        mock_proc.info = {'name': 'douyin.exe', 'pid': 12345}
        with patch('douyin_monitor.psutil.process_iter', return_value=[mock_proc]):
            from douyin_monitor import find_douyin_process
            result = find_douyin_process()
            assert result is not None

    def test_find_douyin_process_not_found(self):
        mock_proc = MagicMock()
        mock_proc.info = {'name': 'notepad.exe', 'pid': 12345}
        with patch('douyin_monitor.psutil.process_iter', return_value=[mock_proc]):
            from douyin_monitor import find_douyin_process
            result = find_douyin_process()
            assert result is None

    def test_is_douyin_window_ready_true(self):
        mock_proc = MagicMock()
        mock_win = {'w': 1000, 'h': 800}
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            with patch('douyin_monitor.find_douyin_window', return_value=mock_win):
                from douyin_monitor import is_douyin_window_ready
                assert is_douyin_window_ready() is True

    def test_is_douyin_window_ready_false_no_proc(self):
        with patch('douyin_monitor.find_douyin_process', return_value=None):
            with patch('douyin_monitor._find_douyin_window_by_title', return_value=None):
                from douyin_monitor import is_douyin_window_ready
                assert is_douyin_window_ready() is False

    def test_is_douyin_window_ready_false_small_window(self):
        mock_proc = MagicMock()
        mock_win = {'w': 50, 'h': 50}
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            with patch('douyin_monitor.find_douyin_window', return_value=mock_win):
                with patch('douyin_monitor._find_douyin_window_by_title', return_value=None):
                    from douyin_monitor import is_douyin_window_ready
                    assert is_douyin_window_ready() is False

    def test_get_douyin_info_success(self):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.name.return_value = 'douyin.exe'
        mock_proc.memory_info.return_value.rss = 1024 * 1024 * 100
        mock_proc.cpu_percent.return_value = 5.0
        mock_proc.create_time.return_value = 1234567890.0
        mock_win = {'title': '抖音', 'x': 100, 'y': 100, 'w': 1000, 'h': 800}
        
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            with patch('douyin_monitor.find_douyin_window', return_value=mock_win):
                from douyin_monitor import get_douyin_info
                result = get_douyin_info()
                assert result is not None
                assert result['pid'] == 12345
                assert result['name'] == 'douyin.exe'
                assert result['window'] is not None

    def test_get_douyin_info_no_proc(self):
        with patch('douyin_monitor.find_douyin_process', return_value=None):
            with patch('douyin_monitor._find_douyin_window_by_title', return_value=None):
                from douyin_monitor import get_douyin_info
                result = get_douyin_info()
                assert result is None

    def test_get_douyin_screenshot_rect(self):
        mock_proc = MagicMock()
        mock_win = {'x': 100, 'y': 100, 'w': 1000, 'h': 800}
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            with patch('douyin_monitor.find_douyin_window', return_value=mock_win):
                from douyin_monitor import get_douyin_screenshot_rect
                result = get_douyin_screenshot_rect()
                assert result == (100, 100, 1000, 800)

    def test_is_douyin_foreground_false(self):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with patch('douyin_monitor.find_douyin_process', return_value=mock_proc):
            with patch('douyin_monitor.GetForegroundWindow', return_value=9999):
                with patch('douyin_monitor.GetWindowThreadProcessId') as mock_get_pid:
                    mock_pid = MagicMock()
                    mock_pid.value = 99999
                    mock_get_pid.return_value = (0, mock_pid)
                    from douyin_monitor import is_douyin_foreground
                    assert is_douyin_foreground() is False
