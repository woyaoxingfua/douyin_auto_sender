# -*- coding: utf-8 -*-
"""仪表盘页：今日统计 / 抖音窗口状态 / 立即执行 / 停止 / 探针。"""
import logging
from datetime import datetime

import dearpygui.dearpygui as dpg

from core.window_capture import find_douyin_hwnd, get_window_rect, \
    is_window_ready, _get_window_title
from services.send_log import get_today_stats
from ui.theme import C_AMBER, C_GREEN, C_RED, C_TEXT_DIM
from ui.widgets import TagStore, show_toast
from ui.fonts import bind_to_item

logger = logging.getLogger(__name__)


class DashboardPage:
    """需要注入：run_task() / stop_task() / is_task_running()。"""

    def __init__(self, tags: TagStore, run_task, stop_task, is_task_running):
        self.tags = tags
        self.run_task = run_task
        self.stop_task = stop_task
        self.is_task_running = is_task_running

    def build(self):
        with dpg.group(horizontal=True):
            with dpg.child_window(width=290, height=150, border=True):
                dpg.add_text("今日已发送", color=C_TEXT_DIM)
                self.tags.set('big_today', dpg.add_text("0", color=C_AMBER))
                bind_to_item(self.tags.get('big_today'), 42)
                dpg.add_text("条", color=C_TEXT_DIM)
                self.tags.set('dash_today_detail',
                              dpg.add_text("成功 0  ·  失败 0", color=C_TEXT_DIM))

            with dpg.child_window(width=290, height=150, border=True):
                dpg.add_text("抖音窗口 (HWND 绑定)", color=C_TEXT_DIM)
                self.tags.set('big_douyin', dpg.add_text("未检测", color=C_TEXT_DIM))
                bind_to_item(self.tags.get('big_douyin'), 24)
                self.tags.set('dash_douyin_detail',
                              dpg.add_text("—", color=C_TEXT_DIM, wrap=250))

            with dpg.child_window(width=290, height=150, border=True):
                dpg.add_text("任务状态", color=C_TEXT_DIM)
                self.tags.set('big_task', dpg.add_text("就绪", color=C_GREEN))
                bind_to_item(self.tags.get('big_task'), 24)
                self.tags.set('dash_task_detail',
                              dpg.add_text("—", color=C_TEXT_DIM, wrap=250))

        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            dpg.add_button(label="▶ 立即执行任务", width=150, height=34,
                           callback=self._on_run)
            dpg.add_button(label="⏹ 停止", width=100, height=34,
                           callback=self._on_stop)
            dpg.add_button(label="🔬 零动作探针", width=140, height=34,
                           callback=self._on_probe)
            dpg.add_button(label="🖥 挪到副屏", width=120, height=34,
                           callback=self._on_secondary)

    # ─── 回调 ───

    def _on_run(self, sender=None, app_data=None):
        if self.is_task_running():
            show_toast("任务正在运行中")
            return
        self.run_task()

    def _on_stop(self, sender=None, app_data=None):
        self.stop_task()

    def _on_probe(self, sender=None, app_data=None):
        """子进程跑零动作探针，结果写 run.log（不在 GUI 进程里碰 ctypes 截图细节）。"""
        import subprocess
        import sys
        from core.config import project_path
        show_toast("探针已启动，看监控页日志 / last_probe.png")
        subprocess.Popen([sys.executable, "-m", "tools.capture_probe"],
                         cwd=project_path("."))

    def _on_secondary(self, sender=None, app_data=None):
        from core.window_capture import move_window_to_secondary_screen
        hwnd = find_douyin_hwnd()
        if hwnd and move_window_to_secondary_screen(hwnd):
            show_toast("已挪到副屏")
        else:
            show_toast("未找到抖音窗口 / 无副屏")

    # ─── 刷新（后台线程调用，调用方负责加锁） ───

    def refresh(self):
        stats = get_today_stats()
        if self.tags.exists('big_today'):
            dpg.set_value(self.tags.get('big_today'), str(stats['success']))
            dpg.set_value(self.tags.get('dash_today_detail'),
                          f"成功 {stats['success']}  ·  失败 {stats['failed']}  ·  共 {stats['total']}")

        hwnd = find_douyin_hwnd()
        if hwnd:
            rect = get_window_rect(hwnd)
            title = _get_window_title(hwnd)
            dpg.set_value(self.tags.get('big_douyin'),
                          "已绑定" if is_window_ready(hwnd) else "已最小化")
            dpg.configure_item(self.tags.get('big_douyin'),
                               color=C_GREEN if is_window_ready(hwnd) else C_RED)
            dpg.set_value(self.tags.get('dash_douyin_detail'),
                          f"{title[:20]} @({rect[0]},{rect[1]}) {rect[2]}x{rect[3]}")
        else:
            dpg.set_value(self.tags.get('big_douyin'), "未检测")
            dpg.configure_item(self.tags.get('big_douyin'), color=C_TEXT_DIM)
            dpg.set_value(self.tags.get('dash_douyin_detail'), "—")

        running = self.is_task_running()
        dpg.set_value(self.tags.get('big_task'), "运行中" if running else "就绪")
        dpg.configure_item(self.tags.get('big_task'),
                           color=C_AMBER if running else C_GREEN)
        now = datetime.now().strftime('%H:%M:%S')
        dpg.set_value(self.tags.get('dash_task_detail'),
                      f"{'任务执行中' if running else '空闲'} · 刷新 {now}")
