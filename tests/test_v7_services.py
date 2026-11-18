"""v7 重写新增模块的测试：调度器 / 动作层 / 进程统计。

- services.scheduler.normalize_time: '8:00' 这类输入必须归一化（v6 踩过的坑）
- core.actions.WindowActions: 窗口坐标 -> 屏幕坐标的换算与动作派发
- services.process_stats: 采样结构完整性
"""
import threading

import pytest

from services.scheduler import Scheduler, normalize_time
from services.process_stats import get_process_stats


# ---------------- normalize_time ----------------

def test_normalize_time_pads():
    assert normalize_time("8:00") == "08:00"
    assert normalize_time("9:5") == "09:05"


def test_normalize_time_keeps_valid():
    assert normalize_time("08:30") == "08:30"
    assert normalize_time(" 23:59 ") == "23:59"
    assert normalize_time("") == "08:00"
    assert normalize_time(None) == "08:00"


def test_normalize_time_rejects_invalid():
    assert normalize_time("25:00") is None
    assert normalize_time("12:60") is None
    assert normalize_time("abc") is None
    assert normalize_time("08:00:00") is None


# ---------------- Scheduler ----------------

def test_scheduler_configure_rejects_bad_time():
    sched = Scheduler()
    with pytest.raises(ValueError):
        sched.configure(enabled=True, time_str="25:99")


def test_scheduler_fires_at_configured_time(monkeypatch):
    """把"现在"设为调度时间，start 后极短时间内应触发一次且仅一次。"""
    from datetime import datetime
    sched = Scheduler(poll_seconds=0.05)
    fired = threading.Event()
    calls = {"n": 0}

    def cb():
        calls["n"] += 1
        fired.set()

    sched.on_fire = cb
    sched.configure(enabled=True, time_str=datetime.now().strftime('%H:%M'))
    sched.start()
    try:
        assert fired.wait(timeout=3), "调度未在预期时间内触发"
        # 同一天内不重复触发：等一小段确认无二次调用
        import time as _t
        _t.sleep(0.2)
        assert calls["n"] == 1
    finally:
        sched.stop()


def test_scheduler_disabled_never_fires():
    sched = Scheduler(poll_seconds=0.05)
    calls = {"n": 0}
    sched.on_fire = lambda: calls.__setitem__("n", calls["n"] + 1)
    sched.configure(enabled=False, time_str="00:00")
    sched.start()
    import time as _t
    _t.sleep(0.3)
    sched.stop()
    assert calls["n"] == 0


# ---------------- WindowActions ----------------

class FakeCap:
    """to_screen: (x+100, y+50)。"""

    def to_screen(self, x, y):
        return (x + 100, y + 50)


def test_actions_click_converts_coords():
    import core.actions as actions_mod
    from core.actions import WindowActions

    act = WindowActions(FakeCap())
    with pytest.MonkeyPatch.context() as mp:
        clicks = []
        mp.setattr(actions_mod.pyautogui, "click",
                   lambda x, y: clicks.append((x, y)))
        mp.setattr(actions_mod.time, "sleep", lambda s: None)
        act.click(50, 10)
    assert clicks == [(150, 60)]


def test_actions_press_and_hotkey_dispatch():
    import core.actions as actions_mod
    from core.actions import WindowActions

    act = WindowActions(FakeCap())
    with pytest.MonkeyPatch.context() as mp:
        pressed = []
        hotkeys = []
        mp.setattr(actions_mod.pyautogui, "press", lambda k: pressed.append(k))
        mp.setattr(actions_mod.pyautogui, "hotkey",
                   lambda *ks: hotkeys.append(ks))
        act.press("esc")
        act.hotkey("ctrl", "v")
    assert pressed == ["esc"]
    assert hotkeys == [("ctrl", "v")]


def test_actions_paste_text_verifies_clipboard():
    import core.actions as actions_mod
    from core.actions import WindowActions

    act = WindowActions(FakeCap())
    clip = {"text": ""}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(actions_mod.pyautogui, "click", lambda *a, **k: None)
        mp.setattr(actions_mod.pyautogui, "press", lambda *a, **k: None)
        mp.setattr(actions_mod.pyautogui, "hotkey", lambda *a, **k: None)
        mp.setattr(actions_mod.time, "sleep", lambda s: None)
        mp.setattr(actions_mod.pyperclip, "copy",
                   lambda t: clip.__setitem__("text", t))
        mp.setattr(actions_mod.pyperclip, "paste", lambda: clip["text"])
        assert act.paste_text(10, 10, "早上好") is True
        assert clip["text"] == "早上好"


# ---------------- process_stats ----------------

def test_process_stats_shape():
    stats = get_process_stats()
    for key in ("main_pid", "total_memory_mb", "total_cpu_percent",
                "child_count", "thread_count", "children"):
        assert key in stats
    assert stats["total_memory_mb"] > 0
    assert stats["thread_count"] >= 1
