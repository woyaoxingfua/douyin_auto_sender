"""发送日志：基于SQLite的发送记录

表结构：
  send_log(id, ts, friend, success, method, duration_ms, message_preview, error_msg)

每天0点自动按月归档。
"""
import os
import sqlite3
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'send_log.db')
_lock = threading.Lock()


def _get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _lock:
        conn = _get_conn()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS send_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    friend TEXT,
                    success INTEGER NOT NULL,
                    method TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    message_preview TEXT,
                    error_msg TEXT
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_ts ON send_log(ts)')
            conn.commit()
        finally:
                conn.close()


_init_db()


def _migrate_from_json():
    """从旧的 send_log.json 迁移数据到SQLite，迁移完成后备份原文件"""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'send_log.json')
    if not os.path.exists(json_path):
        return
    try:
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        records = data.get('records', []) if isinstance(data, dict) else []
        if not records:
            return
        with _lock:
            conn = _get_conn()
            try:
                for r in records:
                    conn.execute(
                        '''INSERT INTO send_log (ts, friend, success, method, duration_ms, message_preview, error_msg)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (r.get('ts', datetime.now().isoformat(timespec='seconds')),
                         r.get('friend', ''),
                         1 if r.get('success') else 0,
                         r.get('method', ''),
                         r.get('duration_ms', 0),
                         str(r.get('message', ''))[:200],
                         r.get('error', ''))
                    )
                conn.commit()
            finally:
                conn.close()
        # 备份原文件
        backup = json_path + '.bak'
        if not os.path.exists(backup):
            import shutil
            shutil.copy2(json_path, backup)
        os.remove(json_path)
        logger.info(f"已从旧 send_log.json 迁移 {len(records)} 条记录到SQLite")
    except Exception as e:
        logger.debug(f"迁移旧日志失败: {e}")


_migrate_from_json()


def log_send(friend: str, success: bool, method: str = '',
             message: str = '', duration_ms: int = 0,
             error_msg: str = ''):
    """记录一条发送结果"""
    try:
        with _lock:
            conn = _get_conn()
            try:
                conn.execute(
                    '''INSERT INTO send_log (ts, friend, success, method, duration_ms, message_preview, error_msg)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (datetime.now().isoformat(timespec='seconds'), friend,
                     1 if success else 0, method, duration_ms,
                     message[:200], error_msg)
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"写入发送记录失败: {e}")


def get_recent_records(limit: int = 50, friend: Optional[str] = None) -> List[Dict]:
    """获取最近N条记录"""
    with _lock:
        conn = _get_conn()
        try:
            if friend:
                cur = conn.execute(
                    'SELECT * FROM send_log WHERE friend = ? ORDER BY id DESC LIMIT ?',
                    (friend, limit)
                )
            else:
                cur = conn.execute(
                    'SELECT * FROM send_log ORDER BY id DESC LIMIT ?',
                    (limit,)
                )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_today_stats() -> Dict:
    """今日发送统计"""
    today = datetime.now().strftime('%Y-%m-%d')
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                'SELECT COUNT(*) AS total, '
                'SUM(success) AS success_cnt, '
                'SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed_cnt '
                'FROM send_log WHERE ts LIKE ?',
                (f'{today}%',)
            )
            row = cur.fetchone()
            return {
                'total': row['total'] or 0,
                'success': row['success_cnt'] or 0,
                'failed': row['failed_cnt'] or 0,
            }
        finally:
            conn.close()


def get_stats_by_date(days: int = 7) -> List[Dict]:
    """按天统计最近N天的发送情况"""
    results = []
    with _lock:
        conn = _get_conn()
        try:
            for i in range(days):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                cur = conn.execute(
                    'SELECT COUNT(*) AS total, '
                    'SUM(success) AS success_cnt, '
                    'SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failed_cnt '
                    'FROM send_log WHERE ts LIKE ?',
                    (f'{d}%',)
                )
                row = cur.fetchone()
                results.append({
                    'date': d,
                    'total': row['total'] or 0,
                    'success': row['success_cnt'] or 0,
                    'failed': row['failed_cnt'] or 0,
                })
            return results
        finally:
            conn.close()


def clear_all():
    """清空所有记录（危险操作，需二次确认）"""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute('DELETE FROM send_log')
            conn.commit()
        finally:
            conn.close()
