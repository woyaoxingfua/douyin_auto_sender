# -*- coding: utf-8 -*-
"""消息预设页：预设库 CRUD / 激活切换 / 预览。"""
import dearpygui.dearpygui as dpg

from services.messages import MessageManager
from ui.theme import C_AMBER, C_GREEN, C_TEXT_DIM
from ui.widgets import TagStore, show_toast


class MessagesPage:
    def __init__(self, tags: TagStore):
        self.tags = tags
        self.mgr = MessageManager()
        self.presets = []
        self.active_id = 'weather'
        self._current_index = -1

    def build(self):
        with dpg.group(horizontal=True):
            # 左：预设库
            with dpg.child_window(width=300, border=True):
                dpg.add_text("消息预设库", color=C_AMBER)
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_button(label="+ 新建", width=70, height=24,
                                   callback=self._new_preset)
                    dpg.add_button(label="复制", width=60, height=24,
                                   callback=self._dup_preset)
                    dpg.add_button(label="删除", width=60, height=24,
                                   callback=self._delete_preset)
                dpg.add_spacer(height=4)
                self.tags.set('presets_list', dpg.add_listbox(
                    [], num_items=12, callback=self._on_select))
                dpg.add_spacer(height=4)
                dpg.add_text("当前激活:", color=C_TEXT_DIM)
                self.tags.set('active_preset',
                              dpg.add_text("—", color=C_GREEN))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="设为当前", width=100, height=24,
                                   callback=self._set_active)

            # 右：编辑
            with dpg.child_window(border=True):
                dpg.add_text("编辑预设", color=C_AMBER)
                dpg.add_text("变量: {nickname} {city_name} {text_day} {text_night} "
                             "{temp_min} {temp_max} {wind_dir} {wind_scale} {custom_text}",
                             color=C_TEXT_DIM, wrap=520)
                dpg.add_separator()
                self.tags.set('preset_name',
                              dpg.add_input_text(label="预设名", width=360))
                self.tags.set('preset_use_weather',
                              dpg.add_checkbox(label="使用天气 API（勾选后走天气模板）"))
                self.tags.set('preset_template',
                              dpg.add_input_text(label="模板", width=-1, height=120,
                                                 multiline=True))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="保存", width=100, height=28,
                                   callback=self._save_preset)
                    dpg.add_button(label="预览", width=100, height=28,
                                   callback=self._preview)
        self.reload()

    # ─── 数据 ───

    def reload(self):
        data = self.mgr.load_all()
        self.presets = data.get('presets', [])
        self.active_id = data.get('active_preset', 'weather')
        names = [p.get('name', '?') for p in self.presets]
        dpg.configure_item(self.tags.get('presets_list'), items=names)
        active_name = next((p.get('name') for p in self.presets
                            if p.get('id') == self.active_id), '—')
        dpg.set_value(self.tags.get('active_preset'), active_name)
        if self.presets:
            first = names[0]
            dpg.set_value(self.tags.get('presets_list'), first)
            self._on_select(None, first)

    def _index_of_selected(self):
        sel = dpg.get_value(self.tags.get('presets_list'))
        try:
            return next(i for i, p in enumerate(self.presets)
                        if p.get('name') == sel)
        except StopIteration:
            return -1

    def _on_select(self, sender, app_data):
        idx = self._index_of_selected()
        if idx < 0:
            return
        self._current_index = idx
        p = self.presets[idx]
        dpg.set_value(self.tags.get('preset_name'), p.get('name', ''))
        dpg.set_value(self.tags.get('preset_use_weather'),
                      bool(p.get('use_weather_api', False)))
        dpg.set_value(self.tags.get('preset_template'), p.get('template', ''))

    def _new_preset(self, sender=None, app_data=None):
        import time as _time
        preset = {"id": f"preset_{int(_time.time())}", "name": "新预设",
                  "use_weather_api": False,
                  "template": "Hi {nickname}，这是一条消息。",
                  "variables": ["nickname"]}
        self.presets.append(preset)
        self.mgr.save_all(self.presets, self.active_id)
        self.reload()
        show_toast("已创建新预设")

    def _dup_preset(self, sender=None, app_data=None):
        idx = self._index_of_selected()
        if idx < 0:
            show_toast("请先选中一个预设")
            return
        import time as _time
        src = dict(self.presets[idx])
        src['id'] = f"preset_{int(_time.time())}"
        src['name'] = src['name'] + " (副本)"
        self.presets.append(src)
        self.mgr.save_all(self.presets, self.active_id)
        self.reload()

    def _delete_preset(self, sender=None, app_data=None):
        idx = self._index_of_selected()
        if idx < 0:
            show_toast("请先选中一个预设")
            return
        if len(self.presets) <= 1:
            show_toast("至少保留 1 个预设")
            return
        deleted = self.presets.pop(idx)
        if self.active_id == deleted.get('id'):
            self.active_id = self.presets[0]['id']
        self.mgr.save_all(self.presets, self.active_id)
        self.reload()

    def _save_preset(self, sender=None, app_data=None):
        idx = self._index_of_selected()
        if idx < 0:
            show_toast("请先选中一个预设")
            return
        import re
        p = self.presets[idx]
        p['name'] = dpg.get_value(self.tags.get('preset_name')).strip()
        p['use_weather_api'] = bool(dpg.get_value(self.tags.get('preset_use_weather')))
        p['template'] = dpg.get_value(self.tags.get('preset_template'))
        p['variables'] = list(dict.fromkeys(re.findall(r'\{(\w+)\}', p['template'])))
        self.mgr.save_all(self.presets, self.active_id)
        self.reload()
        show_toast("已保存")

    def _set_active(self, sender=None, app_data=None):
        idx = self._index_of_selected()
        if idx < 0:
            show_toast("请先选中一个预设")
            return
        self.active_id = self.presets[idx]['id']
        self.mgr.set_active(self.active_id)
        self.reload()
        show_toast(f"已切换到: {self.presets[idx].get('name')}")

    def _preview(self, sender=None, app_data=None):
        idx = self._index_of_selected()
        if idx < 0:
            show_toast("请先选中一个预设")
            return
        template = self.presets[idx].get('template', '')
        sample = {
            'nickname': '王佳豪', 'city_name': '项城',
            'text_day': '晴', 'text_night': '多云',
            'temp_min': '15', 'temp_max': '25',
            'wind_dir': '东南风', 'wind_scale': '3',
            'custom_text': '记得完成今天的任务',
        }
        try:
            text = template.format(**sample)
        except KeyError as e:
            text = f"模板里缺少变量: {e}"
        from ui.widgets import show_modal
        show_modal("消息预览", text, width=520, height=260)
