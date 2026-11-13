"""DPGApp 纯逻辑助手函数测试（不启动 GUI）。"""
import pytest


@pytest.fixture(scope="module")
def dpg_app_cls():
    from ui.dpg_app import DPGApp
    return DPGApp


class TestNormalizeScheduleTime:
    """用户输入 "8:00" 这类时间必须规范化为 "08:00"，
    否则永远匹配不上 strftime('%H:%M')，调度静默失效。"""

    def test_pads_hour(self, dpg_app_cls):
        assert dpg_app_cls._normalize_schedule_time("8:00") == "08:00"
        assert dpg_app_cls._normalize_schedule_time("9:5") == "09:05"

    def test_keeps_valid(self, dpg_app_cls):
        assert dpg_app_cls._normalize_schedule_time("08:05") == "08:05"
        assert dpg_app_cls._normalize_schedule_time("23:59") == "23:59"
        assert dpg_app_cls._normalize_schedule_time("00:00") == "00:00"

    def test_strips_whitespace(self, dpg_app_cls):
        assert dpg_app_cls._normalize_schedule_time("  08:30  ") == "08:30"

    def test_empty_defaults_to_0800(self, dpg_app_cls):
        assert dpg_app_cls._normalize_schedule_time("") == "08:00"

    def test_invalid_returns_none(self, dpg_app_cls):
        assert dpg_app_cls._normalize_schedule_time("25:00") is None
        assert dpg_app_cls._normalize_schedule_time("12:60") is None
        assert dpg_app_cls._normalize_schedule_time("abc") is None
        assert dpg_app_cls._normalize_schedule_time("8") is None
        assert dpg_app_cls._normalize_schedule_time("08:00:00") is None
