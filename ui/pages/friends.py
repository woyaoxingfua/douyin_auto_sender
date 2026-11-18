# -*- coding: utf-8 -*-
"""好友管理页：列表 / 编辑 / 城市 ID 速查 / OCR 文字识别方式。

v7 变化：不再有"头像截图 + 屏幕区域百分比"那套配置 —— 识别走窗口绑定 +
状态机 + OCR 文字，好友只需填「列表里显示的名字」。旧字段保留兼容读取。
"""
import os

import dearpygui.dearpygui as dpg

from core.config import (config_store, project_path, COMMON_CITIES,
                         search_city_by_name)
from ui.theme import C_AMBER, C_TEXT_DIM, C_TEXT_MUTE, C_GREEN, C_RED
from ui.widgets import TagStore, show_toast


class FriendsPage:
    def __init__(self, tags: TagStore):
        self.tags = tags
        self.friends = []
        self._current_index = -1

    def build(self):
        with dpg.group(horizontal=True):
            # 左：列表
            with dpg.child_window(width=300, border=True):
                dpg.add_text("好友列表", color=C_AMBER)
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_button(label="+ 新建", width=80, height=26,
                                   callback=self._new_friend)
                    dpg.add_button(label="删除", width=60, height=26,
                                   callback=self._delete_friend)
                dpg.add_spacer(height=4)
                self.tags.set('friends_list', dpg.add_listbox(
                    [], num_items=18, callback=self._on_select))
                self.tags.set('friends_count',
                              dpg.add_text("共 0 个", color=C_TEXT_DIM))

            # 右：编辑
            with dpg.child_window(border=True):
                dpg.add_text("好友详情", color=C_AMBER)
                dpg.add_text("v7 识别方式 = OCR 文字（好友在私信列表显示的名字），"
                             "不需要再截头像/配屏幕区域", color=C_TEXT_DIM, wrap=520)
                dpg.add_separator()
                self.tags.set('friend_nickname',
                              dpg.add_input_text(label="昵称（必填）",
                                                 width=360, hint="好友显示名"))
                self.tags.set('friend_city_name',
                              dpg.add_input_text(label="城市名", width=200, hint="如: 项城"))
                self.tags.set('friend_location_id',
                              dpg.add_input_text(label="城市 ID (和风天气)",
                                                 width=200, hint="如: 101181407"))
                dpg.add_spacer(height=6)
                with dpg.group(horizontal=True):
                    dpg.add_text("城市速查:", color=C_TEXT_DIM)
                    self.tags.set('city_search',
                                  dpg.add_input_text(hint="输入城市名", width=160,
                                                     callback=self._on_city_search))
                self.tags.set('city_results',
                              dpg.add_text("  ·  ".join(f"{c} {cid}"
                                                        for c, cid in COMMON_CITIES[:6]),
                                           color=C_TEXT_DIM, wrap=0))
                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="保存修改", width=140, height=30,
                                   callback=self._save_friend)
                    dpg.add_button(label="保存并新建", width=120, height=30,
                                   callback=self._save_and_new)
        self.reload()

    # ─── 数据 ───

    def reload(self):
        self.friends = config_store.get_friends()
        labels = [f.get('nickname', '?') for f in self.friends]
        dpg.configure_item(self.tags.get('friends_list'), items=labels)
        dpg.set_value(self.tags.get('friends_count'), f"共 {len(self.friends)} 个")

    def _on_select(self, sender, app_data):
        nickname = app_data if isinstance(app_data, str) else ''
        try:
            idx = next(i for i, f in enumerate(self.friends)
                       if f.get('nickname') == nickname)
        except StopIteration:
            return
        self._current_index = idx
        f = self.friends[idx]
        dpg.set_value(self.tags.get('friend_nickname'), f.get('nickname', ''))
        dpg.set_value(self.tags.get('friend_city_name'), f.get('city_name', ''))
        dpg.set_value(self.tags.get('friend_location_id'), f.get('location_id', ''))

    def _new_friend(self, sender=None, app_data=None):
        self._current_index = -1
        dpg.set_value(self.tags.get('friend_nickname'), '')
        dpg.set_value(self.tags.get('friend_city_name'), '北京')
        dpg.set_value(self.tags.get('friend_location_id'), '101010100')

    def _save_friend(self, sender=None, app_data=None, then_new=False):
        nickname = dpg.get_value(self.tags.get('friend_nickname')).strip()
        city_name = dpg.get_value(self.tags.get('friend_city_name')).strip()
        location_id = dpg.get_value(self.tags.get('friend_location_id')).strip()
        if not nickname:
            show_toast("昵称必填")
            return
        if not location_id:
            show_toast("城市 ID 必填（用速查表）")
            return

        friend = {
            "nickname": nickname,
            "city_name": city_name or f"ID:{location_id}",
            "location_id": location_id,
            "city": location_id,
            # v7 识别统一走 OCR 文字 = 昵称；保留旧字段兼容老分支
            "avatar_text": nickname,
            "avatar_image": "",
        }
        cfg = config_store.get()
        friends = cfg.get('friends', [])
        if 0 <= self._current_index < len(friends):
            friends[self._current_index] = friend
        else:
            friends.append(friend)
        cfg['friends'] = friends
        config_store.save(cfg)
        self.reload()
        show_toast(f"已保存: {nickname}")
        if then_new:
            self._new_friend()

    def _save_and_new(self, sender=None, app_data=None):
        self._save_friend(then_new=True)

    def _delete_friend(self, sender=None, app_data=None):
        sel = dpg.get_value(self.tags.get('friends_list'))
        try:
            idx = next(i for i, f in enumerate(self.friends)
                       if f.get('nickname') == sel)
        except StopIteration:
            show_toast("请先选中一个好友")
            return
        deleted = self.friends.pop(idx)
        cfg = config_store.get()
        cfg['friends'] = self.friends
        config_store.save(cfg)
        self.reload()
        show_toast(f"已删除: {deleted.get('nickname', '?')}")

    def _on_city_search(self, sender, app_data):
        results = search_city_by_name(app_data)
        text = "  ·  ".join(f"{c} {cid}" for c, cid in results[:8]) or "未找到"
        dpg.set_value(self.tags.get('city_results'), text)
