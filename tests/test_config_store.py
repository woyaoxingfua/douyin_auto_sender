"""ConfigStore 新增配置项测试。

覆盖新版抖音 UI 适配所需的交互策略与日志级别配置：
- enter_private_msg_mode / send_button_mode / exit_session_mode
- scroll_amount 类型转换与默认值
- log_level 与 apply_log_level
- 向后兼容：旧配置文件缺失新键时返回默认值
"""
import json
import logging
import os

import pytest

from core.config import ConfigStore, config_store


@pytest.fixture
def fresh_store(tmp_path, monkeypatch):
    """提供一个独立的 ConfigStore 实例，并在临时配置目录中运行。"""
    # 重置单例，避免测试间状态污染
    ConfigStore._instance = None

    def fake_project_path(*parts):
        return str(tmp_path.joinpath(*parts))

    monkeypatch.setattr("core.config.project_path", fake_project_path)

    store = ConfigStore()
    yield store

    # 清理：恢复 logging 级别，避免影响后续测试
    logging.getLogger().setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.WARNING)

    ConfigStore._instance = None


class TestNewConfigDefaults:
    def test_enter_private_msg_mode_default(self, fresh_store):
        assert fresh_store.get_enter_private_msg_mode() == "auto"

    def test_send_button_mode_default(self, fresh_store):
        assert fresh_store.get_send_button_mode() == "image"

    def test_exit_session_mode_default(self, fresh_store):
        assert fresh_store.get_exit_session_mode() == "auto"

    def test_scroll_amount_default(self, fresh_store):
        assert fresh_store.get_scroll_amount() == -3

    def test_log_level_default(self, fresh_store):
        assert fresh_store.get_log_level() == "DEBUG"


class TestConfigPersistence:
    def test_save_and_load_new_config_items(self, fresh_store):
        fresh_store.save({
            "enter_private_msg_mode": "hover",
            "send_button_mode": "ocr",
            "exit_session_mode": "text",
            "scroll_amount": -5,
            "log_level": "DEBUG",
        })

        assert fresh_store.get_enter_private_msg_mode() == "hover"
        assert fresh_store.get_send_button_mode() == "ocr"
        assert fresh_store.get_exit_session_mode() == "text"
        assert fresh_store.get_scroll_amount() == -5
        assert fresh_store.get_log_level() == "DEBUG"

    def test_scroll_amount_converts_string_to_int(self, fresh_store):
        fresh_store.save({"scroll_amount": "-7"})
        assert fresh_store.get_scroll_amount() == -7

    def test_scroll_amount_falls_back_on_invalid_value(self, fresh_store):
        fresh_store.save({"scroll_amount": "not_a_number"})
        assert fresh_store.get_scroll_amount() == -3

    def test_backward_compatibility_with_old_config_file(self, fresh_store, tmp_path):
        """旧配置文件中不存在新键时，应使用默认值。"""
        cfg_path = tmp_path.joinpath("config.json")
        cfg_path.write_text(json.dumps({
            "api_host": "example.com",
            "api_key": "secret",
        }), encoding="utf-8")

        fresh_store.reload()

        assert fresh_store.get_enter_private_msg_mode() == "auto"
        assert fresh_store.get_send_button_mode() == "image"
        assert fresh_store.get_exit_session_mode() == "auto"
        assert fresh_store.get_scroll_amount() == -3
        assert fresh_store.get_log_level() == "DEBUG"


class TestLogLevelApplication:
    def test_apply_log_level_sets_root_logger(self, fresh_store):
        fresh_store.save({"log_level": "DEBUG"})
        fresh_store.apply_log_level()
        assert logging.getLogger().level == logging.DEBUG

    def test_apply_log_level_sets_handlers(self, fresh_store):
        logger = logging.getLogger()
        fresh_store.save({"log_level": "ERROR"})
        fresh_store.apply_log_level()
        for handler in logger.handlers:
            assert handler.level == logging.ERROR

    def test_apply_log_level_invalid_name_falls_back_to_info(self, fresh_store):
        fresh_store.save({"log_level": "UNKNOWN_LEVEL"})
        fresh_store.apply_log_level()
        assert logging.getLogger().level == logging.INFO


class TestGetMethod:
    def test_get_without_key_returns_full_config(self, fresh_store):
        config = fresh_store.get()
        assert isinstance(config, dict)
        assert "enter_private_msg_mode" in config

    def test_get_with_key_returns_value(self, fresh_store):
        assert fresh_store.get("send_button_mode") == "image"


class TestSaveSafety:
    """save() 的数据安全：部分保存不能丢数据，环境变量密钥不能落盘。"""

    FRIEND = {
        "nickname": "小明",
        "city_name": "北京",
        "location_id": "101010100",
        "avatar_text": "小明",
        "avatar_image": "",
    }

    def test_partial_save_preserves_friends(self, fresh_store):
        fresh_store.save({"friends": [self.FRIEND], "api_key": "disk-key"})
        # 模拟某个 UI 页面只保存了一个键
        fresh_store.save({"scroll_amount": -5})

        friends = fresh_store.get("friends")
        assert len(friends) == 1
        assert friends[0]["nickname"] == "小明"
        assert fresh_store.get("api_key") == "disk-key"

    def test_env_override_value_not_persisted(self, fresh_store, monkeypatch, tmp_path):
        monkeypatch.setenv("DOUYIN_WEATHER_API_KEY", "env-secret")
        fresh_store.save({"api_key": "disk-key"})

        # UI 拿到的 config 里 api_key 已被环境变量覆盖（运行时优先级正确）
        assert fresh_store.get("api_key") == "env-secret"

        # UI 原样保存（改了别的键）——环境变量的值不能被写进 config.json
        cfg = fresh_store.get()
        cfg["scroll_amount"] = -7
        fresh_store.save(cfg)

        cfg_path = tmp_path.joinpath("config.json")
        on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert on_disk["api_key"] == "disk-key"
        assert on_disk["scroll_amount"] == -7

    def test_explicit_api_key_change_is_persisted(self, fresh_store, monkeypatch, tmp_path):
        monkeypatch.setenv("DOUYIN_WEATHER_API_KEY", "env-secret")
        fresh_store.save({"api_key": "disk-key"})

        # 用户在 UI 里显式输入了新 key —— 应该照写不误
        cfg = fresh_store.get()
        cfg["api_key"] = "user-typed-new"
        fresh_store.save(cfg)

        cfg_path = tmp_path.joinpath("config.json")
        on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert on_disk["api_key"] == "user-typed-new"
