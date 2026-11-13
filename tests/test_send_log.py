"""send_log 单元测试

验证 SQLite 发送记录的写入与查询，同时回归 douyin_bot 调用 log_send 的参数顺序。
"""
import os
import sqlite3
import tempfile
from datetime import datetime

import pytest

import send_log


@pytest.fixture
def temp_db(monkeypatch):
    """每个测试用独立临时数据库，避免污染项目 send_log.db"""
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, 'test_send_log.db')
    monkeypatch.setattr(send_log, 'DB_FILE', db_path)
    send_log._init_db()
    yield db_path
    # 清理
    if os.path.exists(db_path):
        os.remove(db_path)


def test_log_send_writes_record_with_correct_fields(temp_db):
    """回归测试：log_send 必须按关键字段顺序写入，覆盖 douyin_bot 的调用方式"""
    send_log.log_send(
        friend="小明",
        success=True,
        method="hybrid",
        message="Hi 小明，北京今天晴",
        duration_ms=1500,
    )
    records = send_log.get_recent_records(limit=10)
    assert len(records) == 1
    r = records[0]
    assert r['friend'] == "小明"
    assert r['success'] == 1
    assert r['method'] == "hybrid"
    assert r['duration_ms'] == 1500
    assert "小明" in r['message_preview']


def test_log_send_failure_record_marks_success_zero(temp_db):
    """发送失败时 success 必须落库为 0，不能因参数错位被写成字符串"""
    send_log.log_send(
        friend="小红",
        success=False,
        method="hybrid",
        message="发送失败的消息",
        duration_ms=200,
        error_msg="找不到发送按钮",
    )
    stats = send_log.get_today_stats()
    assert stats['total'] == 1
    assert stats['failed'] == 1
    assert stats['success'] == 0


def test_log_send_accepts_keyword_args_only(temp_db):
    """确保 log_send 用纯关键字调用不报错（douyin_bot 当前调用方式）"""
    send_log.log_send(
        friend="关键词调用",
        success=True,
        method="ocr",
        message="msg",
        duration_ms=10,
    )
    assert send_log.get_today_stats()['success'] == 1


def test_get_recent_records_filters_by_friend(temp_db):
    send_log.log_send(friend="A", success=True, method="m", message="x")
    send_log.log_send(friend="B", success=True, method="m", message="y")
    send_log.log_send(friend="A", success=False, method="m", message="z")
    a_records = send_log.get_recent_records(limit=10, friend="A")
    assert len(a_records) == 2
    assert all(r['friend'] == "A" for r in a_records)


def test_get_stats_by_date_returns_n_days(temp_db):
    send_log.log_send(friend="A", success=True, method="m", message="x")
    stats = send_log.get_stats_by_date(days=3)
    assert len(stats) == 3
    today = stats[0]
    assert today['total'] == 1
    assert today['success'] == 1
