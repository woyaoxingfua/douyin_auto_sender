# -*- coding: utf-8 -*-
"""定时调度器（v7 重写：从 dpg_app 后台线程内联逻辑抽出来，可独立测试）。

极简实现：线程轮询系统时钟，到点触发回调。不用 schedule 库 —— 单一需求
（每天 HH:MM 一次）不值得引入第三方依赖，且这里的实现可中断、可改期。
"""
import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def normalize_time(raw) -> Optional[str]:
    """任意用户输入规范化为 'HH:MM'；非法返回 None。

    '8:00' 不规范化永远匹配不上 strftime('%H:%M')，调度会静默失效
    （v6 实测踩过的坑）。
    """
    raw = (raw or '').strip()
    if not raw:
        return '08:00'
    try:
        parts = raw.split(':')
        if len(parts) != 2:
            return None
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        return f"{hh:02d}:{mm:02d}"
    except ValueError:
        return None


class Scheduler:
    """每日 HH:MM 触发回调的后台调度器。

    用法：
        sched = Scheduler()
        sched.configure(enabled=True, time_str='08:00')
        sched.on_fire = my_task_callback
        sched.start()
        ...
        sched.stop()
    """

    def __init__(self, poll_seconds: float = 5.0):
        self.enabled = False
        self.time_str = '08:00'
        self.on_fire: Optional[Callable[[], None]] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_fire_date: Optional[str] = None
        self._poll_seconds = poll_seconds

    def configure(self, enabled: bool, time_str: str):
        """更新调度配置（运行中也可热更新）。"""
        norm = normalize_time(time_str)
        if norm is None:
            raise ValueError(f"非法调度时间: {time_str!r}（应为 HH:MM）")
        self.enabled = bool(enabled)
        self.time_str = norm
        logger.info(f"调度配置: enabled={self.enabled}, time={self.time_str}")

    def start(self):
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

    def _loop(self):
        """轮询时钟；同一天只触发一次。"""
        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                if (self.enabled and now.strftime('%H:%M') == self.time_str
                        and self._last_fire_date != today):
                    self._last_fire_date = today
                    logger.info(f"⏰ 到达调度时间 {self.time_str}，触发任务")
                    if self.on_fire:
                        try:
                            self.on_fire()
                        except Exception as e:
                            logger.error(f"调度回调异常: {e}")
            except Exception as e:
                logger.debug(f"调度循环异常: {e}")
            self._stop_event.wait(self._poll_seconds)
