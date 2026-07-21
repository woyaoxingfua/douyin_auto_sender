import os
import time
import logging
import psutil

logger = logging.getLogger(__name__)

DOUYIN_PROCESS_NAMES = ['douyin.exe', '抖音.exe', 'douyinhelper.exe']


def find_douyin_process():
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            proc_name = proc.info['name'].lower()
            for target in DOUYIN_PROCESS_NAMES:
                if target.lower() in proc_name:
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def is_douyin_running():
    return find_douyin_process() is not None


def wait_for_douyin(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        if is_douyin_running():
            logger.info("检测到抖音进程已启动")
            return True
        time.sleep(2)
    logger.warning(f"等待抖音启动超时 ({timeout}秒)")
    return False


def get_douyin_info():
    proc = find_douyin_process()
    if not proc:
        return None

    try:
        with proc.oneshot():
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
                "cpu_percent": proc.cpu_percent(interval=0),
                "create_time": proc.create_time(),
            }
    except Exception:
        return {"pid": proc.pid, "name": proc.name()}
