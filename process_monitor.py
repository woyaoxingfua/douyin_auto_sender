"""进程监控：监控本程序主进程+子进程；超过阈值发出报警"""
import os
import time
import threading
import logging
import psutil
from collections import deque

from config_store import config_store

logger = logging.getLogger(__name__)


class ProcessMonitor:
    def __init__(self):
        self.enabled = True
        self.max_memory_mb = 500
        self.max_cpu_percent = 80
        self.check_interval = 30
        self._stop_event = threading.Event()
        self._thread = None
        self._callbacks = []
        self._history = deque(maxlen=200)  # 最近200条监控样本

    def _load_config(self):
        try:
            mon_cfg = config_store.get_process_monitor_config()
            self.enabled = mon_cfg.get('enabled', True)
            self.max_memory_mb = mon_cfg.get('max_memory_mb', 500)
            self.max_cpu_percent = mon_cfg.get('max_cpu_percent', 80)
            self.check_interval = max(5, mon_cfg.get('check_interval_sec', 30))
        except Exception:
            pass

    def add_callback(self, cb):
        """添加报警回调：cb(alert_type, message, data)"""
        self._callbacks.append(cb)

    def start(self):
        self._load_config()
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _emit(self, alert_type, message, data):
        for cb in self._callbacks:
            try:
                cb(alert_type, message, data)
            except Exception as e:
                logger.debug(f"报警回调异常: {e}")

    def get_main_proc_stats(self):
        """获取主进程+子进程聚合数据"""
        try:
            main = psutil.Process(os.getpid())
            tree = [main] + main.children(recursive=True)
            total_mem = 0.0
            total_cpu = 0.0
            children_info = []
            for p in tree:
                try:
                    with p.oneshot():
                        m = p.memory_info().rss / 1024 / 1024
                        c = p.cpu_percent(interval=0)
                        total_mem += m
                        total_cpu += c
                        children_info.append({
                            'pid': p.pid,
                            'name': p.name(),
                            'memory_mb': m,
                            'cpu_percent': c,
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return {
                'main_pid': main.pid,
                'total_memory_mb': total_mem,
                'total_cpu_percent': total_cpu,
                'child_count': len(tree) - 1,
                'thread_count': main.num_threads(),
                'children': children_info,
            }
        except Exception as e:
            return {
                'main_pid': os.getpid(),
                'total_memory_mb': 0.0,
                'total_cpu_percent': 0.0,
                'child_count': 0,
                'thread_count': 0,
                'children': [],
                'error': str(e),
            }

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.enabled:
                self._stop_event.wait(5)
                continue

            try:
                stats = self.get_main_proc_stats()
                self._history.append({
                    'time': time.time(),
                    'memory_mb': stats['total_memory_mb'],
                    'cpu_percent': stats['total_cpu_percent'],
                })

                mem = stats['total_memory_mb']
                cpu = stats['total_cpu_percent']
                ts = time.strftime('%H:%M:%S')

                if mem > self.max_memory_mb:
                    msg = f"[{ts}] 内存超阈值: 当前 {mem:.0f}MB > 阈值 {self.max_memory_mb}MB"
                    logger.warning(msg)
                    self._emit('memory', msg, stats)

                if cpu > self.max_cpu_percent:
                    msg = f"[{ts}] CPU超阈值: 当前 {cpu:.1f}% > 阈值 {self.max_cpu_percent}%"
                    logger.warning(msg)
                    self._emit('cpu', msg, stats)

            except Exception as e:
                logger.debug(f"进程监控异常: {e}")

            self._stop_event.wait(self.check_interval)

    def get_recent_history(self, n=20):
        return list(self._history)[-n:]
