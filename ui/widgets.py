# -*- coding: utf-8 -*-
"""通用 UI 小件（从 dpg_app.py 拆出）：tag 管理 / 日志桥 / toast / 弹窗。"""
import logging
import threading
import time
from datetime import datetime
from contextlib import contextmanager

import dearpygui.dearpygui as dpg


@contextmanager
def dpg_locked():
    """DearPyGui 非线程安全：工作线程改 UI 前必须锁全局 mutex。"""
    dpg.lock_mutex()
    try:
        yield
    finally:
        dpg.unlock_mutex()


class TagStore:
    """轻量 tag 索引（替代 v6 里散落各处的 set_tag/tag）。"""

    def __init__(self):
        self._tags = {}

    def set(self, key, value):
        self._tags[key] = value

    def get(self, key):
        return self._tags.get(key)

    def exists(self, key):
        v = self._tags.get(key)
        return v is not None and dpg.does_item_exist(v)


class GuiLogHandler(logging.Handler):
    """logging -> 界面日志框 + Mini 悬浮窗（线程安全）。"""

    MAX_LINES = 1500

    def __init__(self, tag_store: TagStore, mini_window=None):
        super().__init__()
        self.tags = tag_store
        self.mini = mini_window

    def emit(self, record):
        try:
            msg = self.format(record)
            ts = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
            prefix = {'ERROR': '✗ ', 'CRITICAL': '✗ ', 'WARNING': '! ',
                      'DEBUG': '· '}.get(record.levelname, '· ')
            line = f"{ts} {prefix}{msg}"

            if self.mini:
                try:
                    self.mini.append_log(line)
                except Exception:
                    pass

            if not dpg.is_dearpygui_running() or not self.tags.exists('log_text'):
                return
            try:
                with dpg_locked():
                    current = dpg.get_value(self.tags.get('log_text'))
                    lines = current.split('\n')
                    if len(lines) > self.MAX_LINES:
                        current = '\n'.join(lines[-1000:])
                    dpg.set_value(self.tags.get('log_text'), current + line + '\n')
            except Exception:
                pass
        except Exception:
            self.handleError(record)


def show_toast(message: str, duration_ms: int = 2000):
    """底部短提示（自动关闭）。"""
    tag = f"toast_{int(time.time() * 1000)}"

    def _close(_s=None, _a=None):
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

    with dpg.window(label="提示", modal=False, width=320, height=80,
                    pos=[400, 350], tag=tag, no_resize=True, no_collapse=True):
        dpg.add_text(message, wrap=300)
        dpg.add_button(label="好", width=80, height=24, callback=_close)

    def _auto_close():
        time.sleep(duration_ms / 1000)
        _close()

    threading.Thread(target=_auto_close, daemon=True).start()


def show_modal(title: str, content: str, width: int = 500, height: int = 300):
    """模态确认弹窗。"""
    tag = f"modal_{int(time.time() * 1000)}"
    with dpg.window(label=title, modal=True, width=width, height=height,
                    pos=[200, 150], tag=tag):
        dpg.add_text(content, wrap=width - 30)
        dpg.add_button(label="关闭", width=100, height=28,
                       callback=lambda: dpg.delete_item(tag))
