"""message_manager 单元测试

验证消息预设库的加载、激活、模板格式化与变量提取。
"""
import json
import os
import tempfile

import pytest

import message_manager


@pytest.fixture
def temp_messages_file(monkeypatch):
    """每个测试用独立临时 messages.json"""
    tmp_dir = tempfile.mkdtemp()
    msg_path = os.path.join(tmp_dir, 'messages.json')
    monkeypatch.setattr(message_manager, 'MESSAGES_FILE', msg_path)
    yield msg_path
    if os.path.exists(msg_path):
        os.remove(msg_path)


def test_default_presets_loaded_when_file_missing(temp_messages_file):
    """无 messages.json 时应加载 DEFAULT_PRESETS 并写回"""
    mgr = message_manager.MessageManager()
    assert len(mgr.presets) == len(message_manager.DEFAULT_PRESETS)
    assert mgr.active_preset_id == 'weather'
    # 文件应被自动创建
    assert os.path.exists(temp_messages_file)


def test_active_preset_returns_weather_by_default(temp_messages_file):
    mgr = message_manager.MessageManager()
    active = mgr.get_active_preset()
    assert active is not None
    assert active['id'] == 'weather'
    assert active['use_weather_api'] is True


def test_set_active_persists_across_instances(temp_messages_file):
    mgr = message_manager.MessageManager()
    mgr.set_active('good_morning')
    # 新实例应读到已持久化的激活ID
    mgr2 = message_manager.MessageManager()
    assert mgr2.active_preset_id == 'good_morning'
    assert mgr2.get_active_preset()['id'] == 'good_morning'


def test_add_preset_assigns_unique_id_and_extracts_variables(temp_messages_file):
    mgr = message_manager.MessageManager()
    before = len(mgr.presets)
    new = mgr.add_preset(
        name="自定义",
        template="你好 {nickname}，今天 {city_name} 天气不错",
        use_weather_api=False,
    )
    assert new['id'].startswith("preset_")
    assert new['name'] == "自定义"
    assert "nickname" in new['variables']
    assert "city_name" in new['variables']
    assert len(mgr.presets) == before + 1


def test_format_message_replaces_variables(temp_messages_file):
    mgr = message_manager.MessageManager()
    # 用 good_morning 预设（只含 nickname 变量）
    msg = mgr.format_message('good_morning', {'nickname': '小明'})
    assert "小明" in msg
    assert "早上好" in msg


def test_format_message_returns_template_on_missing_variable(temp_messages_file):
    mgr = message_manager.MessageManager()
    # reminder 预设需要 custom_text，故意不提供
    result = mgr.format_message('reminder', {'nickname': '小明'})
    # 缺变量时应返回原模板而不是抛异常
    assert result is not None


def test_delete_preset_resets_active_when_deleting_active(temp_messages_file):
    mgr = message_manager.MessageManager()
    mgr.set_active('good_night')
    mgr.delete_preset('good_night')
    # 删除激活预设后应回退到第一个
    assert mgr.active_preset_id == mgr.presets[0]['id']


def test_export_then_import_presets_roundtrip(temp_messages_file):
    mgr = message_manager.MessageManager()
    export_path = os.path.join(os.path.dirname(temp_messages_file), 'export.json')
    assert mgr.export_presets(export_path) is True
    # 导入到新管理器
    mgr2 = message_manager.MessageManager()
    count = mgr2.import_presets(export_path)
    assert count > 0
    os.remove(export_path)


def test_extract_variables_handles_duplicate_and_multiple(temp_messages_file):
    mgr = message_manager.MessageManager()
    vars_ = mgr._extract_variables("Hi {nickname} {nickname} {city_name} {temp_max}")
    # 应去重
    assert len(vars_) == 3
    assert set(vars_) == {"nickname", "city_name", "temp_max"}
