# -*- coding: utf-8 -*-
"""DearPyGui 应用薄壳（v7 重写：从 2238 行 dpg_app.py 瘦身为组装器）。

职责只剩三件事：
  1. 组装：主题 + 状态栏 + 六个 tab（页面类各自负责内容）
  2. 任务线程：run/stop 与 Mini 窗状态同步
  3. 后台循环：定时采样刷新（dashboard/monitor 交替，节流 2.5s）
"""
import ctypes
import logging
import threading
import time
from datetime import datetime

import dearpygui.dearpygui as dpg

from core.config import config_store, project_path
from services.scheduler import Scheduler
from ui.fonts import setup_chinese_fonts
from ui.mini_window import MiniStatusWindow
from ui.pages.dashboard import DashboardPage
from ui.pages.friends import FriendsPage
from ui.pages.history import HistoryPage
from ui.pages.messages import MessagesPage
from ui.pages.monitor import MonitorPage
from ui.pages.settings import SettingsPage
from ui.theme import build_themes
from ui.widgets import TagStore, GuiLogHandler, dpg_locked, show_toast

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Douyin Weather Assistant v7"


class App:
    def __init__(self, logger: logging.Logger, mini_window=None):
        self.logger = logger
        self.tags = TagStore()
        self.mini = mini_window
        self.themes = build_themes()
        self.scheduler = Scheduler()
        self.scheduler.on_fire = self.run_task

        # 任务状态
        self.worker = None
        self._task_running = False
        self._stop_flag = threading.Event()
        self._current_friend = "-"
        self._dpg_hwnd = None

        # 页面
        self.page_dashboard = DashboardPage(
            self.tags, run_task=self.run_task, stop_task=self.stop_task,
            is_task_running=lambda: self._task_running)
        self.page_friends = FriendsPage(self.tags)
        self.page_messages = MessagesPage(self.tags)
        self.page_monitor = MonitorPage(self.tags)
        self.page_history = HistoryPage(self.tags)
        self.page_settings = SettingsPage(
            self.tags, apply_theme=self.apply_theme, scheduler=self.scheduler)

    # ─── 组装 ───

    def build(self):
        self._apply_saved_theme()
        self._build_main_window()

        # 日志桥
        handler = GuiLogHandler(self.tags, self.mini)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

        # Mini 窗恢复回调
        if self.mini:
            self.mini.set_restore_callback(self.restore_from_mini)

        self._cache_hwnd()

        # 调度器
        try:
            cfg = config_store.get()
            self.scheduler.configure(cfg.get('scheduler_enabled', True),
                                     cfg.get('schedule_time', '08:00'))
        except Exception as e:
            self.logger.warning(f"调度配置异常: {e}")
        self.scheduler.start()

        self._start_background_loop()

    def _build_main_window(self):
        with dpg.window(label=WINDOW_TITLE, tag="primary"):
            with dpg.group(horizontal=True):
                self.tags.set('header_douyin', dpg.add_text("抖音: —"))
                dpg.add_spacer(width=20)
                self.tags.set('header_proc', dpg.add_text("内存: —"))
                dpg.add_spacer(width=20)
                self.tags.set('time_text', dpg.add_text(""))
                dpg.add_spacer(width=20)
                dpg.add_button(label="🗕 小窗", width=80, height=22,
                               callback=lambda s, a: self.enter_mini_mode())
                dpg.add_button(label="⏹ 停止任务", width=100, height=22,
                               callback=lambda s, a: self.stop_task())

            with dpg.tab_bar():
                with dpg.tab(label="仪表盘"):
                    self.page_dashboard.build()
                with dpg.tab(label="好友"):
                    self.page_friends.build()
                with dpg.tab(label="消息预设"):
                    self.page_messages.build()
                with dpg.tab(label="设置"):
                    self.page_settings.build()
                with dpg.tab(label="监控"):
                    self.page_monitor.build()
                with dpg.tab(label="发送记录"):
                    self.page_history.build()

    def _apply_saved_theme(self):
        try:
            name = config_store.get().get('ui', {}).get('theme', '暗色')
            dpg.bind_theme(self.themes['light' if name == '亮色' else 'dark'])
        except Exception:
            dpg.bind_theme(self.themes['dark'])

    def apply_theme(self, name: str):
        dpg.bind_theme(self.themes['light' if name == '亮色' else 'dark'])

    def _cache_hwnd(self):
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                self._dpg_hwnd = hwnd
        except Exception:
            pass

    # ─── 任务执行 ───

    def run_task(self, friend_name=None):
        """启动任务线程（friend_name 可选单好友）。"""
        if self.worker and self.worker.is_alive():
            show_toast("任务正在运行中")
            return
        self._stop_flag.clear()
        self._enter_mini_safely()
        self.worker = threading.Thread(
            target=self._task_thread, args=(friend_name,), daemon=True)
        self.worker.start()

    def stop_task(self):
        if self._task_running:
            self._stop_flag.set()
            self.logger.info("⏹ 已请求停止任务")
            show_toast("已请求停止任务")
        else:
            show_toast("没有正在运行的任务")

    def _task_thread(self, friend_name=None):
        self._task_running = True
        self._update_mini()
        try:
            self.logger.info("▶ 开始执行自动化任务 (v7 pipeline)")
            from core.bot import run_friend, build_message
            from core.window_capture import WindowCapture
            from core.ocr import RapidLocalOCR
            from core.page_state import PageDetector

            cap = WindowCapture.find_douyin(timeout=10)
            if cap is None:
                self.logger.error("❌ 未找到抖音窗口，任务取消")
                return
            detector = PageDetector(RapidLocalOCR())

            friends = config_store.get_friends()
            if friend_name:
                friends = [f for f in friends if f.get('nickname') == friend_name]
            if not friends:
                self.logger.error("❌ 好友列表为空（或指定好友不存在）")
                return

            ok = 0
            for friend in friends:
                if self._stop_flag.is_set():
                    self.logger.info("⏹ 任务已被用户停止")
                    break
                self._current_friend = friend.get('nickname', '?')
                self._update_mini()
                message = build_message(friend)
                if not message:
                    self.logger.warning(f"跳过 {self._current_friend}: 消息生成为空")
                    continue
                result = run_friend(cap, detector, friend, message,
                                    stop_check=self._stop_flag.is_set)
                if result.get('success'):
                    ok += 1
                if result.get('stopped'):
                    break
            self.logger.info(f"🎉 任务完成: 成功 {ok}/{len(friends)}")
        except Exception as e:
            self.logger.error(f"任务失败: {e}", exc_info=True)
        finally:
            self._task_running = False
            self._current_friend = "-"
            self._update_mini()
            self._refresh_history_safe()

    # ─── Mini 窗 ───

    def _enter_mini_safely(self):
        if not self.mini:
            return
        try:
            self.mini.show()
        except Exception as e:
            self.logger.debug(f"Mini 窗显示失败: {e}")

    def enter_mini_mode(self):
        self._enter_mini_safely()
        try:
            if self._dpg_hwnd:
                ctypes.windll.user32.ShowWindow(self._dpg_hwnd, 0)  # SW_HIDE
        except Exception as e:
            self.logger.error(f"隐藏主窗口失败: {e}")

    def restore_from_mini(self):
        try:
            if self._dpg_hwnd:
                ctypes.windll.user32.ShowWindow(self._dpg_hwnd, 9)  # SW_RESTORE
            if self.mini:
                self.mini.hide()
        except Exception as e:
            self.logger.error(f"恢复主窗口失败: {e}")

    def _update_mini(self):
        if not self.mini:
            return
        try:
            self.mini.update_status(
                status="运行中" if self._task_running else "就绪",
                today_count=self._today_count(),
                current_friend=self._current_friend,
                countdown=self._next_run_text(),
                status_color='#f59e0b' if self._task_running else '#4caf50',
            )
        except Exception as e:
            self.logger.debug(f"Mini 更新失败: {e}")

    def _today_count(self):
        try:
            from services.send_log import get_today_stats
            return get_today_stats().get('success', 0)
        except Exception:
            return 0

    def _next_run_text(self):
        if self.scheduler.enabled:
            return self.scheduler.time_str
        return "调度已禁用"

    # ─── 后台刷新循环 ───

    def _refresh_history_safe(self):
        try:
            with dpg_locked():
                if self.tags.exists('history_table'):
                    self.page_history.refresh()
        except Exception:
            pass

    def _start_background_loop(self):
        """双档节流：重采样 2.5s 一次；Mini 窗请求 0.2s 检查。"""
        def loop():
            last_heavy = 0.0
            while dpg.is_dearpygui_running():
                try:
                    now = time.monotonic()
                    if now - last_heavy >= 2.5:
                        last_heavy = now
                        with dpg_locked():
                            if self.tags.exists('big_today'):
                                self.page_dashboard.refresh()
                            if self.tags.exists('mon_mem'):
                                self.page_monitor.refresh()
                            if self.tags.exists('time_text'):
                                dpg.set_value(self.tags.get('time_text'),
                                             datetime.now().strftime('%H:%M:%S'))

                    if self.mini:
                        self._update_mini()
                        if self.mini.stop_requested.is_set():
                            self.mini.stop_requested.clear()
                            self.stop_task()
                        if self.mini.restore_requested.is_set():
                            self.mini.restore_requested.clear()
                            self.restore_from_mini()
                except Exception as e:
                    self.logger.debug(f"后台循环异常: {e}")
                time.sleep(0.2)

        threading.Thread(target=loop, daemon=True).start()

    def destroy(self):
        self.scheduler.stop()
        if self.mini:
            try:
                self.mini.destroy()
            except Exception:
                pass
