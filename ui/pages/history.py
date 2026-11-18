# -*- coding: utf-8 -*-
"""发送记录页：今日统计 / 记录列表 / 导出 CSV / 清空。"""
import csv

import dearpygui.dearpygui as dpg

from services.send_log import (get_recent_records, get_today_stats,
                               get_stats_by_date, clear_all)
from ui.theme import C_AMBER, C_GREEN, C_RED, C_TEXT_DIM
from ui.widgets import TagStore, show_toast, show_modal


class HistoryPage:
    def __init__(self, tags: TagStore):
        self.tags = tags

    def build(self):
        dpg.add_text("发送记录", color=C_AMBER)
        dpg.add_separator()
        with dpg.group(horizontal=True):
            self.tags.set('hist_total', dpg.add_text("今日: 0"))
            dpg.add_spacer(width=16)
            self.tags.set('hist_success', dpg.add_text("成功: 0", color=C_GREEN))
            dpg.add_spacer(width=16)
            self.tags.set('hist_failed', dpg.add_text("失败: 0", color=C_RED))
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_button(label="刷新", width=80, height=26,
                           callback=lambda s, a: self.refresh())
            dpg.add_button(label="导出 CSV", width=100, height=26,
                           callback=self._export_csv)
            dpg.add_button(label="清空记录", width=100, height=26,
                           callback=self._confirm_clear)
        dpg.add_separator()
        self.tags.set('hist_stats', dpg.add_text("", color=C_TEXT_DIM, wrap=0))
        dpg.add_separator()
        self.tags.set('history_table',
                      dpg.add_input_text(multiline=True, readonly=True,
                                         width=-1, height=380))
        self.refresh()

    def refresh(self):
        stats = get_today_stats()
        dpg.set_value(self.tags.get('hist_total'), f"今日: {stats['total']}")
        dpg.set_value(self.tags.get('hist_success'), f"成功: {stats['success']}")
        dpg.set_value(self.tags.get('hist_failed'), f"失败: {stats['failed']}")

        by_date = get_stats_by_date(days=7)
        dpg.set_value(self.tags.get('hist_stats'),
                      "近7天: " + "  ".join(f"{s['date'][5:]}✓{s['success']}/✗{s['failed']}"
                                            for s in reversed(by_date)))

        records = get_recent_records(limit=200)
        if not records:
            dpg.set_value(self.tags.get('history_table'), "  暂无发送记录")
            return
        lines = []
        for r in reversed(records):
            ts = (r.get('ts') or '')[:19]
            mark = "✓" if r.get('success') else "✗"
            preview = (r.get('message_preview', '') or '')[:50].replace('\n', ' ')
            lines.append(f"{ts}  {mark} {r.get('friend', ''):<10}  "
                         f"{r.get('method', ''):<12}  {r.get('duration_ms', 0)}ms  {preview}")
        dpg.set_value(self.tags.get('history_table'), '\n'.join(lines))

    def _export_csv(self, sender=None, app_data=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            from core.config import project_path
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.asksaveasfilename(
                title="导出 CSV", defaultextension=".csv",
                initialdir=project_path("."),
                filetypes=[("CSV", "*.csv")])
            root.destroy()
            if not fp:
                return
            records = get_recent_records(limit=10000)
            with open(fp, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['时间', '好友', '结果', '方法', '耗时ms', '消息预览', '错误'])
                for r in records:
                    writer.writerow([
                        r.get('ts', ''), r.get('friend', ''),
                        '成功' if r.get('success') else '失败',
                        r.get('method', ''), r.get('duration_ms', 0),
                        r.get('message_preview', ''), r.get('error_msg', ''),
                    ])
            show_toast(f"已导出 {len(records)} 条")
        except Exception as e:
            show_toast(f"失败: {e}")

    def _confirm_clear(self, sender=None, app_data=None):
        tag = f"confirm_clear_{id(self)}"
        with dpg.window(label="确认", modal=True, width=320, height=140,
                        pos=[300, 200], tag=tag) as m:
            dpg.add_text("确定清空所有发送记录吗？\n此操作不可恢复。", color=C_RED)

            def _do_clear():
                clear_all()
                self.refresh()
                dpg.delete_item(m)

            with dpg.group(horizontal=True):
                dpg.add_button(label="取消", width=100, height=28,
                               callback=lambda: dpg.delete_item(m))
                dpg.add_button(label="确认清空", width=100, height=28,
                               callback=_do_clear)
