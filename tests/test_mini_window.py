"""Mini 悬浮状态窗测试。

新版 MiniStatusWindow 在独立线程中运行 tkinter mainloop，
外部线程通过 queue.Queue 传递更新请求。
按钮用 tkinter.Button + command，标志位用 threading.Event。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


try:
    from ui.mini_window import MiniStatusWindow
    TKINTER_AVAILABLE = True
except Exception:
    TKINTER_AVAILABLE = False


@pytest.fixture
def mini():
    if not TKINTER_AVAILABLE:
        pytest.skip("tkinter 不可用")
    try:
        window = MiniStatusWindow()
    except Exception as e:
        pytest.skip(f"无法创建 MiniStatusWindow: {e}")
    yield window
    try:
        window.destroy()
    except Exception:
        pass


class TestMiniStatusWindow:
    def test_initial_flags(self, mini):
        assert mini.restore_requested.is_set() is False
        assert mini.stop_requested.is_set() is False
        assert mini.WIDTH == 260
        assert mini.HEIGHT == 240

    def test_update_status_queued(self, mini):
        mini.update_status(
            status="运行中",
            today_count=12,
            current_friend="小红",
            countdown="00:42",
            status_color="#f59e0b",
        )
        action, data = mini._pending.get(timeout=1)
        assert action == 'update'
        assert data['status'] == "运行中"
        assert data['today_count'] == 12
        assert data['current_friend'] == "小红"
        assert data['countdown'] == "00:42"
        assert data['status_color'] == "#f59e0b"

    def test_append_log_queued(self, mini):
        mini.append_log("12:00:01 · 测试日志")
        action, data = mini._pending.get(timeout=1)
        assert action == 'log'
        assert data == "12:00:01 · 测试日志"

    def test_show_queued(self, mini):
        mini.show()
        action, data = mini._pending.get(timeout=1)
        assert action == 'show'

    def test_hide_queued(self, mini):
        mini.hide()
        action, data = mini._pending.get(timeout=1)
        assert action == 'hide'

    def test_restore_sets_event(self, mini):
        """_on_restore 在 tkinter 线程中调用，设置 threading.Event。"""
        mini._on_restore()
        assert mini.restore_requested.is_set() is True

    def test_stop_sets_event(self, mini):
        """_on_stop 在 tkinter 线程中调用，设置 threading.Event。"""
        mini._on_stop()
        assert mini.stop_requested.is_set() is True

    def test_event_clear(self, mini):
        """Event 可以被 clear，模拟后台线程消费后重置。"""
        mini._on_stop()
        assert mini.stop_requested.is_set() is True
        mini.stop_requested.clear()
        assert mini.stop_requested.is_set() is False

    def test_set_restore_callback(self, mini):
        def cb():
            pass
        mini.set_restore_callback(cb)
        assert mini._restore_callback is cb
