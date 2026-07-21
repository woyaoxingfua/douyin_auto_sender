import json
import os
import time
from datetime import datetime

from config_utils import project_path

HISTORY_FILE = project_path('send_history.json')


def _load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {"records": []}


def _save_history(data):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def log_send(friend, message, success, method="image", duration_ms=0, error=None):
    data = _load_history()
    record = {
        "timestamp": datetime.now().isoformat(),
        "friend": friend,
        "message_preview": message[:100] if message else "",
        "success": success,
        "method": method,
        "duration_ms": duration_ms,
    }
    if error:
        record["error"] = str(error)

    data["records"].append(record)

    if len(data["records"]) > 500:
        data["records"] = data["records"][-500:]

    _save_history(data)


def get_today_stats():
    data = _load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    today_records = [r for r in data["records"] if r["timestamp"].startswith(today)]

    total = len(today_records)
    success = sum(1 for r in today_records if r.get("success"))
    failed = total - success

    return {"total": total, "success": success, "failed": failed}


def get_recent_records(limit=20):
    data = _load_history()
    return data["records"][-limit:]
