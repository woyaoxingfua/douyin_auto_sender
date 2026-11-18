# -*- coding: utf-8 -*-
"""监控页：进程指标 + 运行日志（从 dpg_app 拆出）。"""
import dearpygui.dearpygui as dpg

from services.process_stats import get_process_stats
from ui.theme import C_AMBER, C_TEXT_DIM
from ui.widgets import TagStore


class MonitorPage:
    def __init__(self, tags: TagStore):
        self.tags = tags

    def build(self):
        dpg.add_text("进程监控", color=C_AMBER)
        dpg.add_text("本进程 + 子进程的内存/CPU（按需采样，无常驻报警线程）",
                     color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()
        with dpg.group(horizontal=True):
            with dpg.child_window(width=380, border=True):
                self.tags.set('mon_mem', dpg.add_text("内存: —", color=C_AMBER))
                self.tags.set('mon_cpu', dpg.add_text("CPU: —", color=C_AMBER))
                self.tags.set('mon_threads', dpg.add_text("线程: —", color=C_TEXT_DIM))
                self.tags.set('mon_children', dpg.add_text("子进程: 0", color=C_TEXT_DIM))
                dpg.add_button(label="立即采样", width=110, height=26,
                               callback=lambda s, a: self.refresh())

        dpg.add_spacer(height=6)
        dpg.add_text("运行日志", color=C_AMBER)
        dpg.add_button(label="清空显示", width=110, height=24,
                       callback=lambda s, a: dpg.set_value(self.tags.get('log_text'), ''))
        self.tags.set('log_text',
                      dpg.add_input_text(multiline=True, readonly=True,
                                         width=-1, height=420))

    def refresh(self):
        stats = get_process_stats()
        dpg.set_value(self.tags.get('mon_mem'),
                      f"内存: {stats['total_memory_mb']:.0f} MB")
        dpg.set_value(self.tags.get('mon_cpu'),
                      f"CPU: {stats['total_cpu_percent']:.1f} %")
        dpg.set_value(self.tags.get('mon_threads'),
                      f"线程: {stats['thread_count']}")
        dpg.set_value(self.tags.get('mon_children'),
                      f"子进程: {stats['child_count']}")
