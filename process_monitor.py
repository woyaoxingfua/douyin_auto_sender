import os
import time
import threading
import logging
import psutil

from config_utils import load_config

logger = logging.getLogger(__name__)


class ProcessMonitor:
    def __init__(self):
        self.enabled = True
        self.max_memory_mb = 500
        self.max_cpu_percent = 80
        self.check_interval = 30
        self._running = False
        self._thread = None
        self._load_config()

    def _load_config(self):
        try:
            cfg = load_config()
            monitor_cfg = cfg.get('process_monitor', {})
            self.enabled = monitor_cfg.get('enabled', True)
            self.max_memory_mb = monitor_cfg.get('max_memory_mb', 500)
            self.max_cpu_percent = monitor_cfg.get('max_cpu_percent', 80)
            self.check_interval = monitor_cfg.get('check_interval_sec', 30)
        except Exception:
            pass

    def start(self):
        if not self.enabled or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("进程监控已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("进程监控已停止")

    def _monitor_loop(self):
        while self._running:
            try:
                proc = psutil.Process(os.getpid())
                mem_mb = proc.memory_info().rss / 1024 / 1024
                cpu = proc.cpu_percent(interval=1)

                if mem_mb > self.max_memory_mb:
                    logger.warning(f"内存使用过高: {mem_mb:.0f}MB (限制: {self.max_memory_mb}MB)")

                if cpu > self.max_cpu_percent:
                    logger.warning(f"CPU使用过高: {cpu:.1f}% (限制: {self.max_cpu_percent}%)")

            except Exception as e:
                logger.debug(f"进程监控检查失败: {e}")

            time.sleep(self.check_interval)

    def get_stats(self):
        try:
            proc = psutil.Process(os.getpid())
            return {
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
                "cpu_percent": proc.cpu_percent(interval=0),
                "threads": proc.num_threads(),
                "fds": proc.num_fds() if hasattr(proc, 'num_fds') else 0,
            }
        except Exception:
            return {"memory_mb": 0, "cpu_percent": 0, "threads": 0, "fds": 0}
