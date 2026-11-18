# -*- coding: utf-8 -*-
"""设置页：API 配置 / 调度 / 主题 / 日志级别（v7 收拢为一个页，不再分 5 个 tab）。"""
import logging

import dearpygui.dearpygui as dpg

from core.config import config_store
from services.scheduler import normalize_time
from ui.theme import C_AMBER, C_TEXT_DIM
from ui.widgets import TagStore, show_toast


class SettingsPage:
    """需要注入：apply_theme(name) / scheduler（配置写回后同步调度器）。"""

    def __init__(self, tags: TagStore, apply_theme, scheduler):
        self.tags = tags
        self.apply_theme = apply_theme
        self.scheduler = scheduler

    def build(self):
        cfg = config_store.get()

        dpg.add_text("和风天气 API", color=C_AMBER)
        self.tags.set('api_host',
                      dpg.add_input_text(label="API Host", width=400,
                                         default_value=cfg.get('api_host', '')))
        self.tags.set('api_key',
                      dpg.add_input_text(label="API Key", password=True, width=400,
                                         default_value=cfg.get('api_key', '')))
        dpg.add_button(label="测试连接", width=120, height=28,
                       callback=self._test_qweather)
        dpg.add_spacer(height=10)

        dpg.add_text("调度", color=C_AMBER)
        self.tags.set('sched_enabled',
                      dpg.add_checkbox(label="启用每日调度",
                                       default_value=cfg.get('scheduler_enabled', True)))
        self.tags.set('sched_time',
                      dpg.add_input_text(label="执行时间 (HH:MM)", width=160,
                                         default_value=cfg.get('schedule_time', '08:00')))
        dpg.add_button(label="保存调度", width=120, height=28,
                       callback=self._save_scheduler)
        dpg.add_spacer(height=10)

        dpg.add_text("外观与日志", color=C_AMBER)
        self.tags.set('theme_combo',
                      dpg.add_combo(["暗色", "亮色"], width=120,
                                    default_value=cfg.get('ui', {}).get('theme', '暗色'),
                                    callback=self._on_theme_change))
        self.tags.set('log_level',
                      dpg.add_combo(["DEBUG", "INFO", "WARNING"], width=120,
                                    label="日志级别",
                                    default_value=cfg.get('log_level', 'INFO')))
        dpg.add_button(label="保存并应用", width=120, height=28,
                       callback=self._save_logging)

    # ─── 回调 ───

    def _test_qweather(self, sender=None, app_data=None):
        import requests
        host = dpg.get_value(self.tags.get('api_host')).strip()
        key = dpg.get_value(self.tags.get('api_key')).strip()
        if not host or not key:
            show_toast("请先填 Host 和 Key")
            return
        try:
            r = requests.get(f"https://{host}/v7/weather/now",
                             params={'location': '101010100', 'key': key}, timeout=5)
            d = r.json()
            if str(d.get('code')) == '200':
                show_toast(f"✓ 连接成功 · 北京当前: {d['now']['text']} {d['now']['temp']}℃")
            else:
                show_toast(f"✗ 错误码: {d.get('code')}")
        except Exception as e:
            show_toast(f"✗ {e}")

    def _save_scheduler(self, sender=None, app_data=None):
        sched_time = normalize_time(dpg.get_value(self.tags.get('sched_time')))
        if sched_time is None:
            show_toast("时间格式应为 HH:MM，如 08:00")
            return
        enabled = bool(dpg.get_value(self.tags.get('sched_enabled')))
        cfg = config_store.get()
        cfg['scheduler_enabled'] = enabled
        cfg['schedule_time'] = sched_time
        config_store.save(cfg)
        self.scheduler.configure(enabled=enabled, time_str=sched_time)
        dpg.set_value(self.tags.get('sched_time'), sched_time)
        show_toast(f"调度已保存: {sched_time}" if enabled else "调度已禁用")

    def _on_theme_change(self, sender=None, app_data=None):
        theme = dpg.get_value(self.tags.get('theme_combo'))
        self.apply_theme(theme)
        cfg = config_store.get()
        cfg.setdefault('ui', {})['theme'] = theme
        config_store.save(cfg)
        show_toast(f"已切换到{theme}主题")

    def _save_logging(self, sender=None, app_data=None):
        level = dpg.get_value(self.tags.get('log_level'))
        cfg = config_store.get()
        cfg['log_level'] = level
        config_store.save(cfg)
        config_store.apply_log_level()
        show_toast(f"日志级别已应用: {level}")
