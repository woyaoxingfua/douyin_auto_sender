"""DearPyGui 主界面

设计语言：
  - 暖黑 #121110 背景 + 琥珀橙 #f59e0b 强调
  - 标题用 Noto Serif SC（已注册），正文用系统中文
  - 直角优先，少装饰，数据密度高
  - 不复制SaaS卡片墙，每个tab有自己的节奏
"""
import os
import sys
import json
import time
import shutil
import threading
import contextlib
import logging
import subprocess
import ctypes
import ctypes.wintypes
from datetime import datetime
from typing import List, Dict, Optional

import dearpygui.dearpygui as dpg
import psutil

# 把项目根目录加到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_utils import (
    project_path,
    COMMON_CITIES, search_city_by_name, create_default_friend_template,
)
from config_store import config_store
from process_monitor import ProcessMonitor
from send_log import (
    log_send, get_recent_records, get_today_stats, get_stats_by_date, clear_all,
)
from message_manager import MessageManager, DEFAULT_PRESETS
from douyin_monitor import (
    is_douyin_running, get_douyin_info, get_douyin_screenshot_rect,
    is_douyin_foreground,
)
from font_loader import setup_chinese_fonts, get_font, bind_to_item
from region_selector import select_region, capture_screen_to_file, crop_image_to_file, get_screen_origin


@contextlib.contextmanager
def _dpg_locked():
    """ DearPyGui 非线程安全：工作线程修改 UI 前必须先锁住全局 mutex，否则会段错误/渲染错乱。"""
    dpg.lock_mutex()
    try:
        yield
    finally:
        dpg.unlock_mutex()


# ─── 颜色与主题 ───

C_BG          = (18, 17, 16)      # 暖黑 #121110
C_BG_SOFT     = (29, 27, 25)
C_BG_PANEL    = (24, 22, 20)
C_BORDER      = (54, 50, 44)
C_BORDER_HOT  = (245, 158, 11)    # 琥珀
C_TEXT        = (220, 215, 205)   # 暖白
C_TEXT_DIM    = (138, 130, 116)
C_TEXT_MUTE   = (94, 88, 78)
C_AMBER       = (245, 158, 11)    # 主强调
C_AMBER_DIM   = (180, 110, 0)
C_GREEN       = (74, 222, 128)    # 成功
C_RED         = (239, 68, 68)     # 失败
C_YELLOW      = (250, 204, 21)    # 警告
C_BLUE        = (96, 165, 250)    # 信息

# ─── 亮色主题 ───
L_BG          = (245, 245, 245)
L_BG_SOFT     = (235, 235, 235)
L_BG_PANEL    = (240, 240, 240)
L_BORDER      = (200, 200, 200)
L_TEXT        = (50, 50, 50)
L_TEXT_DIM    = (120, 120, 120)
L_TEXT_MUTE   = (160, 160, 160)
L_AMBER       = (217, 119, 6)
L_AMBER_DIM   = (180, 100, 0)
L_GREEN       = (22, 163, 74)
L_RED         = (220, 38, 38)
L_YELLOW      = (202, 138, 4)
L_BLUE        = (37, 99, 235)


# ─── 自定义日志Handler：logging → 界面文本框 + Mini窗 ───

class DPGLogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            ts = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
            prefix = {'ERROR': '✗ ', 'CRITICAL': '✗ ', 'WARNING': '! ',
                      'DEBUG': '· '}.get(level, '· ')
            log_line = f"{ts} {prefix}{msg}"

            # 转发到 Mini 悬浮窗（线程安全，通过队列）
            if self.app.mini_window:
                try:
                    self.app.mini_window.append_log(log_line)
                except Exception:
                    pass

            if not dpg.is_dearpygui_running():
                return
            if not self.app.tag('log_text'):
                return
            try:
                with _dpg_locked():
                    current = dpg.get_value(self.app.tag('log_text'))
                    lines = current.split('\n')
                    if len(lines) > 1500:
                        current = '\n'.join(lines[-1000:])
                    dpg.set_value(self.app.tag('log_text'), current + log_line + '\n')
            except Exception:
                pass
        except Exception:
            self.handleError(record)


# ─── 辅助：dpid包装 ───

# ─── 主应用 ───

class DPGApp:
    def __init__(self, logger, mini_window=None):
        self.logger = logger
        self.worker = None
        self._last_run_date = None
        self.log_handler = None
        self._tags = {}
        self.process_monitor = ProcessMonitor()
        self.message_manager = MessageManager()
        self.presets = []
        self.active_preset_id = 'weather'
        self.mini_window = mini_window

        # mini 模式状态
        self._mini_mode = False
        self._today_send_count = 0
        self._current_friend = "-"
        self._next_run_countdown = "-"
        self._task_running = False
        self._stop_flag = threading.Event()
        self._dpg_hwnd = None  # DPG 主窗口句柄，build() 后缓存

        # 拖拽框选状态
        self._dragging_region = None  # (key, start_x, start_y)

        self._load_scheduler_config()

    # tag 索引辅助
    def tag(self, key):
        return self._tags.get(key)

    def set_tag(self, key, value):
        self._tags[key] = value

    @staticmethod
    def _get_listbox_index(label, items):
        """DearPyGui listbox 返回 label 字符串，转换为在 items 中的 index"""
        if not isinstance(label, str) or not label:
            return -1
        try:
            return next((i for i, item in enumerate(items) if item == label), -1)
        except Exception:
            return -1

    def build(self):
        self._build_theme()
        self._build_main_window()
        # 注册日志handler
        self.log_handler = DPGLogHandler(self)
        self.log_handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(self.log_handler)

        # 报警回调
        self.process_monitor.start()
        self.process_monitor.add_callback(self._on_process_alert)

        # 设置小窗恢复回调
        if self.mini_window:
            self.mini_window.set_restore_callback(self._exit_mini_mode)

        # 缓存 DPG 主窗口句柄（用于 Mini 模式隐藏/恢复）
        self._cache_dpg_hwnd()

        self._start_background_tasks()

    def _cache_dpg_hwnd(self):
        """在 viewport 显示后，查找并缓存 DPG 主窗口句柄。"""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "Douyin Weather Assistant v6.0")
            if hwnd:
                self._dpg_hwnd = hwnd
                self.logger.debug(f"已缓存 DPG 主窗口句柄: hwnd={hwnd}")
            else:
                self.logger.warning("无法找到 DPG 主窗口句柄，Mini 模式将使用 minimize_viewport 回退")
        except Exception as e:
            self.logger.warning(f"缓存 DPG 主窗口句柄失败: {e}")

    # ─── 主题 ───

    def _build_theme(self):
        # 暗色主题
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                # 背景
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, C_BG)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, C_BG_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, C_BG_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, C_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, C_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, C_BG_SOFT)
                # 文字
                dpg.add_theme_color(dpg.mvThemeCol_Text, C_TEXT)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, C_TEXT_MUTE)
                # 按钮
                dpg.add_theme_color(dpg.mvThemeCol_Button, C_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, C_AMBER_DIM)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, C_AMBER)
                # 输入框
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, C_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (40, 36, 32))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (45, 40, 35))
                # 边框
                dpg.add_theme_color(dpg.mvThemeCol_Border, C_BORDER)
                dpg.add_theme_color(dpg.mvThemeCol_Separator, C_BORDER)
                # Tab
                dpg.add_theme_color(dpg.mvThemeCol_Tab, C_BG)
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, C_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, C_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabSelected, C_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabSelectedOverline, C_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabDimmedSelected, C_AMBER_DIM)
                # Header (列表/树)
                dpg.add_theme_color(dpg.mvThemeCol_Header, C_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, C_AMBER_DIM)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, C_AMBER)
                # 滚动条
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, C_BG)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, C_BORDER)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, C_TEXT_MUTE)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, C_TEXT_DIM)
                # Checkbox / radio
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, C_AMBER)
                # 直角与紧凑
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 16)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, 6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 12)
                dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 8)
        self.set_tag('dark_theme', global_theme)

        # 亮色主题
        with dpg.theme() as light_theme:
            with dpg.theme_component(dpg.mvAll):
                # 背景
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, L_BG)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, L_BG_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, L_BG_PANEL)
                dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, L_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, L_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, L_BG_SOFT)
                # 文字
                dpg.add_theme_color(dpg.mvThemeCol_Text, L_TEXT)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, L_TEXT_MUTE)
                # 按钮
                dpg.add_theme_color(dpg.mvThemeCol_Button, L_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, L_AMBER_DIM)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, L_AMBER)
                # 输入框
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, L_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (225, 225, 225))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (220, 220, 220))
                # 边框
                dpg.add_theme_color(dpg.mvThemeCol_Border, L_BORDER)
                dpg.add_theme_color(dpg.mvThemeCol_Separator, L_BORDER)
                # Tab
                dpg.add_theme_color(dpg.mvThemeCol_Tab, L_BG)
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, L_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, L_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabSelected, L_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabSelectedOverline, L_AMBER)
                dpg.add_theme_color(dpg.mvThemeCol_TabDimmedSelected, L_AMBER_DIM)
                # Header (列表/树)
                dpg.add_theme_color(dpg.mvThemeCol_Header, L_BG_SOFT)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, L_AMBER_DIM)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, L_AMBER)
                # 滚动条
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, L_BG)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, L_BORDER)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, L_TEXT_MUTE)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, L_TEXT_DIM)
                # Checkbox / radio
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, L_AMBER)
                # 直角与紧凑
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 16)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, 6, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 12)
                dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 8)
        self.set_tag('light_theme', light_theme)

        # 读取 config 决定初始主题
        cfg = config_store.get()
        theme_name = cfg.get('ui', {}).get('theme', '暗色')
        if theme_name == '亮色':
            dpg.bind_theme(self.tag('light_theme'))
            self._current_theme = '亮色'
        else:
            dpg.bind_theme(self.tag('dark_theme'))
            self._current_theme = '暗色'

    # ─── 顶层窗口 ───

    def _build_main_window(self):
        with dpg.window(tag='main_window', no_title_bar=True, no_resize=True,
                        no_move=True):
            # 顶部Header
            with dpg.group(horizontal=True):
                title = dpg.add_text("抖音天气助手", color=C_AMBER)
                bind_to_item(title, 24)
                dpg.add_text("·  v6.0", color=C_TEXT_DIM)
                dpg.add_spacer(width=20)
                # 状态指示
                self.set_tag('header_douyin', dpg.add_text("抖音: 探测中", color=C_TEXT_DIM))
                dpg.add_spacer(width=20)
                self.set_tag('header_proc', dpg.add_text("内存: -- MB  CPU: --%  线程: --",
                                                        color=C_TEXT_DIM))
                dpg.add_spacer(width=20)
                self.set_tag('header_alert', dpg.add_text("", color=C_RED))
                dpg.add_spacer(width=20)
                # mini 模式切换按钮
                self.set_tag('mini_mode_btn', dpg.add_button(
                    label="🗕 小窗",
                    callback=self._toggle_mini_mode,
                    width=70,
                ))
            dpg.add_separator()

            with dpg.tab_bar():
                with dpg.tab(label="  仪表盘  "):
                    self._build_dashboard()
                with dpg.tab(label="  好友  "):
                    self._build_friends()
                with dpg.tab(label="  消息预设  "):
                    self._build_messages()
                with dpg.tab(label="  抖音界面  "):
                    self._build_ui_config()
                with dpg.tab(label="  API 配置  "):
                    self._build_api_config()
                with dpg.tab(label="  监控  "):
                    self._build_monitor()
                with dpg.tab(label="  调度  "):
                    self._build_scheduler()
                with dpg.tab(label="  发送记录  "):
                    self._build_send_history()

            dpg.add_separator()
            with dpg.group(horizontal=True):
                self.set_tag('status_text', dpg.add_text("就绪", color=C_TEXT))
                dpg.add_spacer(width=20)
                self.set_tag('mode_text', dpg.add_text("OCR: 本地", color=C_BLUE))
                dpg.add_spacer(width=20)
                self.set_tag('time_text', dpg.add_text("", color=C_TEXT_DIM))

        dpg.set_primary_window('main_window', True)

    # ─── 仪表盘 ───

    def _build_dashboard(self):
        # 顶部三块大数字
        with dpg.group(horizontal=True):
            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("今日已发送", color=C_TEXT_DIM)
                self.set_tag('big_today', dpg.add_text("0", color=C_AMBER))
                bind_to_item(self.tag('big_today'), 42)
                dpg.add_text("条", color=C_TEXT_DIM)
                dpg.add_spacer(height=2)
                self.set_tag('dash_today_detail', dpg.add_text("成功 0  ·  失败 0", color=C_TEXT_DIM))

            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("抖音窗口", color=C_TEXT_DIM)
                self.set_tag('big_douyin', dpg.add_text("—", color=C_TEXT_DIM))
                bind_to_item(self.tag('big_douyin'), 24)
                dpg.add_spacer(height=4)
                self.set_tag('dash_douyin_pos', dpg.add_text("位置: --", color=C_TEXT_DIM))
                self.set_tag('dash_douyin_size', dpg.add_text("尺寸: --", color=C_TEXT_DIM))
                self.set_tag('dash_douyin_fg', dpg.add_text("前台: --", color=C_TEXT_DIM))

            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("调度", color=C_TEXT_DIM)
                self.set_tag('big_schedule', dpg.add_text("08:00", color=C_AMBER))
                bind_to_item(self.tag('big_schedule'), 42)
                dpg.add_spacer(height=2)
                self.set_tag('dash_schedule_status', dpg.add_text("已启用", color=C_GREEN))

        dpg.add_spacer(height=12)

        # 操作区
        with dpg.child_window(border=True, height=120):
            dpg.add_text("操作", color=C_AMBER)
            with dpg.group(horizontal=True):
                dpg.add_button(label="立即执行任务", width=160, height=36,
                               callback=self._run_task_now)
                dpg.add_button(label="测试连接", width=120, height=36,
                               callback=self._test_all_connections)
                dpg.add_button(label="打开日志文件", width=120, height=36,
                               callback=lambda: self._open_file(project_path('run.log')))
                dpg.add_button(label="打开配置目录", width=120, height=36,
                               callback=lambda: self._open_dir(project_path('.')))

            dpg.add_spacer(height=8)
            dpg.add_text("窗口尺寸", color=C_TEXT_DIM)
            with dpg.group(horizontal=True):
                self.set_tag('window_mode_radio',
                             dpg.add_radio_button(["normal", "compact"],
                                                  horizontal=True, default_value="normal"))
                dpg.add_button(label="应用", width=80, height=24,
                               callback=self._apply_window_mode)
                dpg.add_text("重启后保留此设置", color=C_TEXT_MUTE)

            dpg.add_spacer(height=8)
            dpg.add_text("配色方案", color=C_TEXT_DIM)
            with dpg.group(horizontal=True):
                self.set_tag('theme_combo',
                             dpg.add_combo(["暗色", "亮色"],
                                           default_value=getattr(self, '_current_theme', '暗色'),
                                           width=120, callback=self._on_theme_change))

        self._refresh_dashboard()

    # ─── 好友管理 ───

    def _build_friends(self):
        with dpg.group(horizontal=True):
            # 左：好友列表
            with dpg.child_window(width=300, border=True):
                dpg.add_text("好友列表", color=C_AMBER)
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_button(label="+ 新建", width=80, height=26,
                                   callback=self._new_friend)
                    dpg.add_button(label="导入示例", width=80, height=26,
                                   callback=self._import_example_friends)
                    dpg.add_button(label="删除", width=60, height=26,
                                   callback=self._delete_friend)
                dpg.add_spacer(height=4)
                self.set_tag('friends_list', dpg.add_listbox(
                    [], num_items=20, callback=self._on_friend_select))
                dpg.add_spacer(height=4)
                dpg.add_text("共 0 个", color=C_TEXT_DIM, tag='friends_count_text')

            # 右：好友详情/编辑
            with dpg.child_window(border=True):
                dpg.add_text("好友详情", color=C_AMBER)
                dpg.add_separator()
                self.set_tag('friend_nickname',
                             dpg.add_input_text(label="昵称 (抖音上显示的名字)",
                                                width=400, hint="必填"))
                self.set_tag('friend_city_name',
                             dpg.add_input_text(label="城市名", width=200,
                                                hint="如: 北京"))
                self.set_tag('friend_location_id',
                             dpg.add_input_text(label="城市 ID (和风天气)",
                                                width=200, hint="如: 101010100"))

                # 城市速查
                with dpg.group(horizontal=True):
                    dpg.add_text("城市速查:", color=C_TEXT_DIM)
                    self.set_tag('city_search_input',
                                 dpg.add_input_text(hint="输入城市名关键字", width=160,
                                                    callback=self._on_city_search))
                self.set_tag('city_results_text',
                             dpg.add_text("北京 101010100  ·  上海 101020100  ·  广州 101280101",
                                          color=C_TEXT_DIM, wrap=0))

                dpg.add_spacer(height=8)
                # 头像预览区域
                with dpg.group(horizontal=True, tag='friend_avatar_preview_group'):
                    dpg.add_text("头像预览:", color=C_TEXT_DIM)
                    dpg.add_text("无头像", color=C_TEXT_MUTE, tag='friend_avatar_img')
                dpg.add_spacer(height=4)
                dpg.add_text("识别方式（任选其一）", color=C_TEXT_DIM)
                self.set_tag('friend_avatar_text',
                             dpg.add_input_text(label="OCR 文字（好友头像下方的昵称文字）",
                                                width=400,
                                                hint="用 OCR 时填，文字必须能在头像下方看到"))
                with dpg.group(horizontal=True):
                    self.set_tag('friend_avatar_path_text',
                                 dpg.add_text("(未选择)", color=C_TEXT_DIM))
                    dpg.add_button(label="从剪贴板粘贴", width=120,
                                   callback=lambda: self._paste_friend_avatar())
                    dpg.add_button(label="从文件选择", width=120,
                                   callback=lambda: self._pick_friend_avatar())
                    dpg.add_button(label="从屏幕截取", width=120,
                                   callback=lambda: self._capture_friend_avatar())

                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="保存修改", width=160, height=32,
                                   callback=self._save_friend)
                    dpg.add_button(label="保存并新建", width=120, height=32,
                                   callback=self._save_and_new_friend)
                dpg.add_spacer(height=4)
                dpg.add_text("提示: location_id 必填；avatar_text 与 avatar_image 至少填一个。",
                             color=C_TEXT_MUTE)

    def _load_friends(self):
        cfg = config_store.get()
        self.friends = cfg.get('friends', [])
        labels = [f.get('nickname', '?') for f in self.friends]
        dpg.configure_item(self.tag('friends_list'), items=labels)
        dpg.set_value('friends_count_text', f"共 {len(self.friends)} 个")

    def _on_friend_select(self, sender, app_data):
        # DearPyGui listbox callback 返回的是选中项的 label 字符串
        nickname = app_data if isinstance(app_data, str) else ''
        try:
            idx = next((i for i, f in enumerate(self.friends)
                        if f.get('nickname') == nickname), -1)
        except Exception:
            idx = -1
        if idx < 0 or idx >= len(self.friends):
            return
        f = self.friends[idx]
        dpg.set_value(self.tag('friend_nickname'), f.get('nickname', ''))
        dpg.set_value(self.tag('friend_city_name'), f.get('city_name', ''))
        dpg.set_value(self.tag('friend_location_id'), f.get('location_id', ''))
        dpg.set_value(self.tag('friend_avatar_text'), f.get('avatar_text', ''))
        self._current_friend_index = idx
        self._current_friend_avatar = f.get('avatar_image', '')
        dpg.set_value(self.tag('friend_avatar_path_text'),
                      self._current_friend_avatar or '(未选择)')
        # 更新头像预览
        self._update_friend_avatar_preview(self._current_friend_avatar)

    def _update_friend_avatar_preview(self, avatar_path):
        """更新好友头像预览区域"""
        # 删除旧纹理
        if dpg.does_item_exist('friend_avatar_tex'):
            dpg.delete_item('friend_avatar_tex')
        # 清空预览 group 里的子项
        if dpg.does_item_exist('friend_avatar_preview_group'):
            dpg.delete_item('friend_avatar_preview_group', children_only=True)
            parent = 'friend_avatar_preview_group'
        else:
            return

        # 支持相对路径（如 friend_avatars/xxx.png）
        if avatar_path and not os.path.isabs(avatar_path):
            abs_path = project_path(*avatar_path.replace('\\', '/').split('/'))
        else:
            abs_path = avatar_path

        if avatar_path and os.path.isfile(abs_path):
            try:
                from PIL import Image
                img = Image.open(abs_path)
                # 缩放到 80x80 以内
                img.thumbnail((80, 80))
                img = img.convert('RGBA')
                w, h = img.size
                tex_data = self._img_to_rgba(img)
                with dpg.texture_registry():
                    dpg.add_static_texture(w, h, tex_data, tag='friend_avatar_tex')
                with dpg.group(horizontal=True, parent=parent):
                    dpg.add_text("头像预览:", color=C_TEXT_DIM)
                    dpg.add_image('friend_avatar_tex', width=w, height=h)
            except Exception:
                with dpg.group(horizontal=True, parent=parent):
                    dpg.add_text("头像预览:", color=C_TEXT_DIM)
                    dpg.add_text("无头像", color=C_TEXT_MUTE)
        else:
            with dpg.group(horizontal=True, parent=parent):
                dpg.add_text("头像预览:", color=C_TEXT_DIM)
                dpg.add_text("无头像", color=C_TEXT_MUTE)

    def _new_friend(self, sender=None, app_data=None):
        self._current_friend_index = -1
        dpg.set_value(self.tag('friend_nickname'), '')
        dpg.set_value(self.tag('friend_city_name'), '北京')
        dpg.set_value(self.tag('friend_location_id'), '101010100')
        dpg.set_value(self.tag('friend_avatar_text'), '')
        self._current_friend_avatar = ''
        dpg.set_value(self.tag('friend_avatar_path_text'), '(未选择)')

    def _import_example_friends(self, sender=None, app_data=None):
        """导入三个示例好友"""
        cfg = config_store.get()
        friends = cfg.get('friends', [])
        example = [
            create_default_friend_template("示例A", "北京"),
            create_default_friend_template("示例B", "上海"),
            create_default_friend_template("示例C", "广州"),
        ]
        # 避免重复
        existing = {f.get('nickname') for f in friends}
        added = 0
        for f in example:
            if f['nickname'] not in existing:
                friends.append(f)
                added += 1
        cfg['friends'] = friends
        config_store.save(cfg)
        self.friends = friends
        self._load_friends()
        if added == 0:
            self._show_toast("示例好友已存在，无需重复导入")
        else:
            self._show_toast(f"已添加 {added} 个示例好友")

    def _delete_friend(self, sender=None, app_data=None):
        friend_labels = [f.get('nickname', '?') for f in self.friends]
        sel = self._get_listbox_index(dpg.get_value(self.tag('friends_list')), friend_labels)
        if sel < 0:
            self._show_toast("请先选中一个好友")
            return
        deleted = self.friends.pop(sel)
        cfg = config_store.get()
        cfg['friends'] = self.friends
        config_store.save(cfg)
        self._load_friends()
        self._show_toast(f"已删除: {deleted.get('nickname', '?')}")

    def _save_friend(self, sender=None, app_data=None, then_new=False):
        nickname = dpg.get_value(self.tag('friend_nickname')).strip()
        city_name = dpg.get_value(self.tag('friend_city_name')).strip()
        location_id = dpg.get_value(self.tag('friend_location_id')).strip()
        avatar_text = dpg.get_value(self.tag('friend_avatar_text')).strip()
        avatar_image = getattr(self, '_current_friend_avatar', '')

        if not nickname:
            self._show_toast("昵称必填")
            return
        if not location_id:
            self._show_toast("城市 ID 必填")
            return

        new_friend = {
            "nickname": nickname,
            "city_name": city_name or f"ID:{location_id}",
            "location_id": location_id,
            # 保留旧版 city 字段，确保从 v6.0 切回 master 仍可读取
            "city": location_id,
            "avatar_text": avatar_text,
            "avatar_image": avatar_image,
        }

        cfg = config_store.get()
        friends = cfg.get('friends', [])
        idx = getattr(self, '_current_friend_index', -1)
        if isinstance(idx, int) and 0 <= idx < len(friends):
            friends[idx] = new_friend
        else:
            friends.append(new_friend)
        cfg['friends'] = friends
        config_store.save(cfg)
        self.friends = friends
        self._load_friends()
        self._show_toast(f"已保存: {nickname}")
        if then_new:
            self._new_friend()

    def _save_and_new_friend(self, sender=None, app_data=None):
        self._save_friend(then_new=True)

    def _paste_friend_avatar(self):
        """从剪贴板粘贴图片作为好友头像"""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if img is None:
                self._show_toast("剪贴板没有图片")
                return
            if not isinstance(img, Image.Image):
                self._show_toast("剪贴板内容不是图片")
                return
            target_dir = project_path('control_images', 'avatars')
            os.makedirs(target_dir, exist_ok=True)
            ts = int(time.time() * 1000)
            dest = os.path.join(target_dir, f"avatar_{ts}.png")
            img.save(dest)
            self._current_friend_avatar = dest
            dpg.set_value(self.tag('friend_avatar_path_text'), dest)
            self._show_toast("已从剪贴板粘贴")
        except Exception as e:
            self._show_toast(f"粘贴失败: {e}")

    def _pick_friend_avatar(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.askopenfilename(
                title="选择好友头像截图",
                filetypes=[("PNG", "*.png"), ("JPG", "*.jpg"), ("所有", "*.*")])
            root.destroy()
            if not fp:
                return
            target_dir = project_path('control_images', 'avatars')
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, f"avatar_{int(time.time() * 1000)}.png")
            shutil.copy2(fp, dest)
            self._current_friend_avatar = dest
            dpg.set_value(self.tag('friend_avatar_path_text'), dest)
            self._show_toast("头像已保存")
        except Exception as e:
            self._show_toast(f"选择失败: {e}")

    def _capture_friend_avatar(self):
        """从抖音窗口中框选头像区域"""
        result = select_region()
        if not result:
            return
        # 存到 control_images/avatars
        target_dir = project_path('control_images', 'avatars')
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, f"avatar_{int(time.time() * 1000)}.png")
        if crop_image_to_file(result.get('preview_path', ''), dest,
                              result['x'] - get_screen_origin()[0],
                              result['y'] - get_screen_origin()[1],
                              result['w'], result['h']):
            self._current_friend_avatar = dest
            dpg.set_value(self.tag('friend_avatar_path_text'), dest)
            self._show_toast("已从屏幕截取头像")
        else:
            # 退而求其次：直接框选区保存
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(result['x'], result['y'],
                                           result['x'] + result['w'],
                                           result['y'] + result['h']))
                img.save(dest)
                self._current_friend_avatar = dest
                dpg.set_value(self.tag('friend_avatar_path_text'), dest)
                self._show_toast("已从屏幕截取头像")
            except Exception as e:
                self._show_toast(f"截取失败: {e}")

    def _on_city_search(self, sender, app_data):
        results = search_city_by_name(app_data)
        text = "  ·  ".join([f"{c} {cid}" for c, cid in results[:10]]) or "未找到"
        dpg.set_value(self.tag('city_results_text'), text)

    # ─── 消息预设 ───

    def _build_messages(self):
        with dpg.group(horizontal=True):
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
                self.set_tag('presets_list', dpg.add_listbox(
                    [], num_items=15, callback=self._on_preset_select))
                dpg.add_spacer(height=4)
                dpg.add_text("当前激活:", color=C_TEXT_DIM)
                self.set_tag('active_preset_text', dpg.add_text("—", color=C_GREEN))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="设为当前", width=100, height=24,
                                   callback=self._set_active_preset)
                    dpg.add_button(label="导入/导出", width=100, height=24,
                                   callback=self._show_preset_io_menu)
                dpg.add_spacer(height=6)
                dpg.add_text("模板预览:", color=C_TEXT_DIM)
                dpg.add_input_text(readonly=True, multiline=True, width=-1, height=100,
                                   tag='preset_preview_text', default_value='')

            with dpg.child_window(border=True):
                dpg.add_text("编辑预设", color=C_AMBER)
                dpg.add_separator()
                self.set_tag('preset_id_label', dpg.add_text("ID: —", color=C_TEXT_DIM))
                self.set_tag('preset_name',
                             dpg.add_input_text(label="预设名", width=400))
                self.set_tag('preset_use_weather',
                             dpg.add_checkbox(label="使用天气 API（拉取真实天气数据）"))
                self.set_tag('preset_template',
                             dpg.add_input_text(label="消息模板（支持多行）",
                                                multiline=True, width=-1, height=160))
                dpg.add_text("可用变量: {nickname}  {city_name}  {text_day}  {text_night}  "
                             "{temp_min}  {temp_max}  {wind_dir}  {wind_scale}  {custom_text}",
                             color=C_TEXT_DIM, wrap=0)
                dpg.add_spacer(height=8)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="保存预设", width=140, height=30,
                                   callback=self._save_preset)
                    dpg.add_button(label="预览消息", width=120, height=30,
                                   callback=self._preview_preset)

        self._load_presets()

    def _load_presets(self):
        try:
            data = self.message_manager.load_all()
            self.presets = data.get('presets', [])
            self.active_preset_id = data.get('active_preset', 'weather')
        except Exception as e:
            self.logger.error(f"加载预设失败: {e}")
            self.presets = []
            self.active_preset_id = 'weather'
        dpg.configure_item(self.tag('presets_list'),
                           items=[p.get('name', '?') for p in self.presets])
        # 显示当前激活
        name = next((p.get('name') for p in self.presets
                     if p.get('id') == self.active_preset_id), '—')
        dpg.set_value(self.tag('active_preset_text'), name)
        # 自动选中第一个预设并触发预览
        if self.presets:
            first_name = self.presets[0].get('name', '')
            dpg.set_value(self.tag('presets_list'), first_name)
            self._on_preset_select(None, first_name)

    def _on_preset_select(self, sender, app_data):
        # DearPyGui listbox callback 返回的是选中项的 label 字符串
        name = app_data if isinstance(app_data, str) else ''
        try:
            idx = next((i for i, p in enumerate(self.presets)
                        if p.get('name') == name), -1)
        except Exception:
            idx = -1
        if idx < 0 or idx >= len(self.presets):
            return
        p = self.presets[idx]
        dpg.set_value(self.tag('preset_id_label'),
                      f"ID: {p.get('id', '?')}")
        dpg.set_value(self.tag('preset_name'), p.get('name', ''))
        dpg.set_value(self.tag('preset_use_weather'),
                      bool(p.get('use_weather_api', False)))
        dpg.set_value(self.tag('preset_template'), p.get('template', ''))
        self._current_preset_index = idx
        # 更新预设模板预览
        if dpg.does_item_exist('preset_preview_text'):
            dpg.set_value('preset_preview_text', p.get('template', ''))

    def _new_preset(self, sender=None, app_data=None):
        new_p = {
            "id": f"preset_{int(time.time())}",
            "name": "新预设",
            "use_weather_api": False,
            "template": "Hi {nickname}，这是一条消息。",
            "variables": ["nickname"],
        }
        self.presets.append(new_p)
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        new_name = new_p.get('name', '')
        dpg.set_value(self.tag('presets_list'), new_name)
        self._on_preset_select(None, new_name)
        self._show_toast("已创建新预设")

    def _dup_preset(self, sender=None, app_data=None):
        preset_labels = [p.get('name', '?') for p in self.presets]
        sel = self._get_listbox_index(dpg.get_value(self.tag('presets_list')), preset_labels)
        if sel < 0:
            self._show_toast("请先选中一个预设")
            return
        src = dict(self.presets[sel])
        src['id'] = f"preset_{int(time.time())}"
        src['name'] = src['name'] + " (副本)"
        self.presets.append(src)
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        self._show_toast("已复制")

    def _delete_preset(self, sender=None, app_data=None):
        preset_labels = [p.get('name', '?') for p in self.presets]
        sel = self._get_listbox_index(dpg.get_value(self.tag('presets_list')), preset_labels)
        if sel < 0:
            self._show_toast("请先选中一个预设")
            return
        if len(self.presets) <= 1:
            self._show_toast("至少保留 1 个预设")
            return
        deleted = self.presets.pop(sel)
        if self.active_preset_id == deleted.get('id'):
            self.active_preset_id = self.presets[0]['id']
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        self._show_toast(f"已删除: {deleted.get('name')}")

    def _save_preset(self, sender=None, app_data=None):
        preset_labels = [p.get('name', '?') for p in self.presets]
        sel = self._get_listbox_index(dpg.get_value(self.tag('presets_list')), preset_labels)
        if sel < 0:
            self._show_toast("请先选中一个预设")
            return
        self.presets[sel]['name'] = dpg.get_value(self.tag('preset_name')).strip()
        self.presets[sel]['use_weather_api'] = bool(
            dpg.get_value(self.tag('preset_use_weather')))
        self.presets[sel]['template'] = dpg.get_value(self.tag('preset_template'))
        # 自动提取变量
        import re
        tmpl = self.presets[sel]['template']
        vars_ = re.findall(r'\{(\w+)\}', tmpl)
        self.presets[sel]['variables'] = list(dict.fromkeys(vars_))
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        saved_name = self.presets[sel].get('name', '')
        dpg.set_value(self.tag('presets_list'), saved_name)
        self._show_toast("已保存")

    def _set_active_preset(self, sender=None, app_data=None):
        preset_labels = [p.get('name', '?') for p in self.presets]
        sel = self._get_listbox_index(dpg.get_value(self.tag('presets_list')), preset_labels)
        if sel < 0:
            self._show_toast("请先选中一个预设")
            return
        self.active_preset_id = self.presets[sel]['id']
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        self._show_toast(f"已切换到: {self.presets[sel].get('name')}")

    def _preview_preset(self, sender=None, app_data=None):
        preset_labels = [p.get('name', '?') for p in self.presets]
        sel = self._get_listbox_index(dpg.get_value(self.tag('presets_list')), preset_labels)
        if sel < 0:
            self._show_toast("请先选中一个预设")
            return
        p = self.presets[sel]
        cfg = config_store.get()
        friends = cfg.get('friends', [])
        if not friends:
            self._show_toast("好友列表为空，无法预览（先在「好友」tab添加）")
            return
        f = friends[0]
        # 简单变量替换
        try:
            sample = {
                'nickname': f.get('nickname', '朋友'),
                'city_name': f.get('city_name', '北京'),
                'text_day': '晴',
                'text_night': '多云',
                'temp_min': '15',
                'temp_max': '25',
                'wind_dir': '东南风',
                'wind_scale': '3',
                'custom_text': '记得完成今天的任务',
            }
            preview_text = p['template'].format(**sample)
        except KeyError as e:
            preview_text = f"模板里缺少变量: {e}"
        except Exception as e:
            preview_text = f"模板错误: {e}"

        # 弹窗预览
        self._show_modal("消息预览", preview_text, width=520, height=260)

    def _show_preset_io_menu(self, sender, app_data):
        with dpg.window(label="导入/导出预设", modal=True, width=400, height=180,
                        pos=[200, 200]) as modal:
            dpg.add_text("选择操作")
            dpg.add_separator()
            dpg.add_button(label="从 JSON 文件导入", width=-1, height=32,
                           callback=lambda: (self._import_presets(modal), None))
            dpg.add_button(label="导出所有预设到 JSON", width=-1, height=32,
                           callback=lambda: (self._export_presets(modal), None))
            dpg.add_button(label="恢复默认 6 个模板（覆盖现有）", width=-1, height=32,
                           callback=lambda: (self._restore_default_presets(modal), None))
            dpg.add_spacer(height=6)
            dpg.add_button(label="关闭", width=-1, height=28,
                           callback=lambda: dpg.delete_item(modal))

    def _restore_default_presets(self, parent=None):
        self.presets = [dict(p) for p in DEFAULT_PRESETS]
        self.active_preset_id = 'weather'
        self.message_manager.save_all(self.presets, self.active_preset_id)
        self._load_presets()
        if parent:
            dpg.delete_item(parent)
        self._show_toast("已恢复默认模板")

    def _import_presets(self, parent=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.askopenfilename(
                title="选择预设文件",
                filetypes=[("JSON", "*.json")])
            root.destroy()
            if not fp:
                return
            success = self.message_manager.import_presets(fp)
            if success:
                self._load_presets()
                self._show_toast("导入成功")
            else:
                self._show_toast("导入失败")
        except Exception as e:
            self._show_toast(f"导入失败: {e}")
        if parent:
            dpg.delete_item(parent)

    def _export_presets(self, parent=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.asksaveasfilename(
                title="导出预设",
                defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            root.destroy()
            if not fp:
                return
            success = self.message_manager.export_presets(fp)
            if success:
                self._show_toast(f"已导出到 {os.path.basename(fp)}")
            else:
                self._show_toast("导出失败")
        except Exception as e:
            self._show_toast(f"导出失败: {e}")
        if parent:
            dpg.delete_item(parent)

    # ─── 抖音界面配置 ───

    def _build_ui_config(self):
        with dpg.tab_bar():
            with dpg.tab(label="控制图像"):
                self._build_image_config()
            with dpg.tab(label="OCR 文字"):
                self._build_ocr_text_config()
            with dpg.tab(label="交互策略"):
                self._build_interaction_config()
            with dpg.tab(label="屏幕区域（可视化框选）"):
                self._build_region_config()
            with dpg.tab(label="滚动条匹配"):
                self._build_scrollbar_config()

    def _build_image_config(self):
        dpg.add_text("控制图像（图像匹配模式使用）", color=C_AMBER)
        dpg.add_text("点击「截图选定区域」从抖音窗口里框选控件；「从文件」可批量导入；"
                     "「从剪贴板」粘贴你刚截的图。", color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()
        dpg.add_text("新版抖音的发送/退出按钮已变为图标，建议优先使用图像匹配。", color=C_TEXT_DIM)
        dpg.add_spacer(height=8)

        # 主控制图像
        self._build_image_table([
            ('douyin_sixin_icon.png', '私信图标', '点击进入/悬停打开私信列表'),
            ('douyin_send_button.png', '发送按钮', '点击发送消息'),
            ('douyin_exit_chat_button.png', '退出会话', '点击返回好友列表'),
        ], "主控制图像")

    def _build_interaction_config(self):
        """新版抖音交互策略配置"""
        dpg.add_text("新版抖音交互策略", color=C_AMBER)
        dpg.add_text("根据你的抖音客户端版本选择最合适的识别与交互方式。", color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()
        dpg.add_spacer(height=8)

        cfg = config_store.get()

        self.set_tag('cfg_enter_mode', dpg.add_combo(
            label="私信入口模式",
            items=["auto", "hover", "click"],
            default_value=cfg.get('enter_private_msg_mode', 'auto'),
            width=200,
        ))
        dpg.add_text("auto = 先悬停 1 秒再点击；hover = 仅悬停；click = 仅点击", color=C_TEXT_DIM, wrap=520)
        dpg.add_spacer(height=6)

        self.set_tag('cfg_send_mode', dpg.add_combo(
            label="发送按钮识别",
            items=["image", "ocr", "both"],
            default_value=cfg.get('send_button_mode', 'image'),
            width=200,
        ))
        dpg.add_text("image = 仅图像匹配；ocr = 仅 OCR 文字；both = 图像优先", color=C_TEXT_DIM, wrap=520)
        dpg.add_spacer(height=6)

        self.set_tag('cfg_exit_mode', dpg.add_combo(
            label="退出会话识别",
            items=["auto", "image", "ocr", "text"],
            default_value=cfg.get('exit_session_mode', 'auto'),
            width=200,
        ))
        dpg.add_text("auto = 先图像再文字；image/ocr/text = 单一策略", color=C_TEXT_DIM, wrap=520)
        dpg.add_spacer(height=6)

        self.set_tag('cfg_scroll_amount', dpg.add_input_int(
            label="好友列表滚动步长",
            default_value=cfg.get('scroll_amount', -3),
            min_value=-10,
            max_value=10,
            width=120,
        ))
        dpg.add_text("负数向下滚动，推荐 -3（滚轮单位）。不需要再拖动滚动条。", color=C_TEXT_DIM, wrap=520)
        dpg.add_spacer(height=12)

        dpg.add_button(
            label="保存交互策略",
            callback=self._save_interaction_config,
            width=140,
            height=28,
        )

    def _save_interaction_config(self, sender=None, app_data=None):
        cfg = config_store.get()
        cfg['enter_private_msg_mode'] = dpg.get_value(self.tag('cfg_enter_mode'))
        cfg['send_button_mode'] = dpg.get_value(self.tag('cfg_send_mode'))
        cfg['exit_session_mode'] = dpg.get_value(self.tag('cfg_exit_mode'))
        cfg['scroll_amount'] = dpg.get_value(self.tag('cfg_scroll_amount'))
        config_store.save(cfg)
        self._show_toast("交互策略已保存")

    def _build_scrollbar_config(self):
        """滚动条图像专门做一栏，逻辑独立"""
        dpg.add_text("滚动条图像", color=C_AMBER)
        dpg.add_text("聊天列表滚动条用于在大量聊天中翻页。", color=C_TEXT_DIM)
        dpg.add_separator()
        self._build_image_table([
            ('douyin_scrollbar.png', '滚动条', '可拖动的小条'),
            ('douyin_scroll_top.png', '滚动到顶部', '回到列表顶部'),
        ], "滚动条")

    def _build_image_table(self, images, group_label):
        dpg.add_text(group_label, color=C_TEXT_DIM)
        # 用 child_window + group 实现列表
        with dpg.child_window(border=True, height=180):
            for filename, name, desc in images:
                with dpg.group(horizontal=True):
                    dpg.add_text(name, color=C_TEXT)
                    dpg.add_text(desc, color=C_TEXT_DIM)
                    path = project_path('control_images', filename)
                    status = "✓" if os.path.exists(path) else "✗"
                    color = C_GREEN if os.path.exists(path) else C_RED
                    dpg.add_text(status, color=color)
                    dpg.add_text(path if os.path.exists(path) else "(未配置)",
                                 color=C_TEXT_DIM)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="截图选定区域", width=130, height=24,
                                   user_data=filename,
                                   callback=lambda s, a, fn=filename: self._capture_control_image(fn))
                    dpg.add_button(label="从文件", width=80, height=24,
                                   user_data=filename,
                                   callback=lambda s, a, fn=filename: self._pick_control_image(fn))
                    dpg.add_button(label="从剪贴板", width=80, height=24,
                                   user_data=filename,
                                   callback=lambda s, a, fn=filename: self._paste_control_image(fn))
                    dpg.add_button(label="预览", width=60, height=24,
                                   user_data=filename,
                                   callback=lambda s, a, fn=filename: self._preview_control_image(fn))
                dpg.add_separator()
        dpg.add_spacer(height=6)

    def _capture_control_image(self, filename):
        """从屏幕框选区域，作为控制图像"""
        result = select_region()
        if not result:
            return
        target_dir = project_path('control_images')
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, filename)
        try:
            from PIL import ImageGrab
            origin_x, origin_y = get_screen_origin()
            img = ImageGrab.grab(bbox=(result['x'], result['y'],
                                       result['x'] + result['w'],
                                       result['y'] + result['h']))
            img.save(dest)
            self._show_toast(f"已保存: {filename}")
            self._refresh_image_table()
        except Exception as e:
            self._show_toast(f"截取失败: {e}")

    def _pick_control_image(self, filename):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.askopenfilename(
                title=f"选择 {filename}",
                filetypes=[("图片", "*.png *.jpg *.jpeg")])
            root.destroy()
            if not fp:
                return
            target_dir = project_path('control_images')
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, filename)
            shutil.copy2(fp, dest)
            self._show_toast(f"已保存: {filename}")
            self._refresh_image_table()
        except Exception as e:
            self._show_toast(f"失败: {e}")

    def _paste_control_image(self, filename):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if not isinstance(img, Image.Image):
                self._show_toast("剪贴板没有图片")
                return
            target_dir = project_path('control_images')
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, filename)
            img.save(dest)
            self._show_toast(f"已从剪贴板保存: {filename}")
            self._refresh_image_table()
        except Exception as e:
            self._show_toast(f"失败: {e}")

    def _preview_control_image(self, filename):
        path = project_path('control_images', filename)
        if not os.path.exists(path):
            self._show_toast("图像未配置")
            return
        self._show_image_modal(path)

    def _refresh_image_table(self):
        # 简单做法：删除所有 child 重建
        # 这里改为只刷新状态（后续可重写为细粒度刷新）
        # 为简单直接重建 image_table group
        # 找到 image_table 容器并删除其子项
        # DPG没简单办法删子项，所以最稳妥是重新 build image config
        # 这里用一个轻量方案：把状态文字保存在 self.image_status_texts
        if hasattr(self, '_image_status_texts'):
            for fn, widget_id in self._image_status_texts.items():
                path = project_path('control_images', fn)
                if os.path.exists(path):
                    dpg.set_value(widget_id, "✓")
                    dpg.configure_item(widget_id, color=C_GREEN)
                else:
                    dpg.set_value(widget_id, "✗")
                    dpg.configure_item(widget_id, color=C_RED)

    def _show_image_modal(self, path):
        try:
            from PIL import Image
            img = Image.open(path)
            # 缩放
            max_w, max_h = 800, 500
            img.thumbnail((max_w, max_h))
            w, h = img.size
            tmp_path = os.path.join(os.path.dirname(path), f"preview_{int(time.time())}.png")
            img.save(tmp_path)

            # 加载为纹理
            with dpg.texture_registry():
                tex_id = dpg.add_static_texture(w, h, self._img_to_rgba(img), tag=f"tex_{int(time.time()*1000)}")

            with dpg.window(label=f"预览: {os.path.basename(path)}",
                            modal=True, width=w + 40, height=h + 80,
                            pos=[150, 100]) as modal_win:
                dpg.add_image(tex_id, width=w, height=h)
                dpg.add_button(label="关闭", width=100, height=28,
                               callback=lambda: (dpg.delete_item(tex_id),
                                                 dpg.delete_item(modal_win)))
        except Exception as e:
            self._show_toast(f"预览失败: {e}")

    @staticmethod
    def _img_to_rgba(img):
        import numpy as np
        arr = np.array(img.convert('RGBA'), dtype=np.float32) / 255.0
        return arr.flatten().tolist()

    def _build_ocr_text_config(self):
        dpg.add_text("OCR 文字（OCR 模式使用）", color=C_AMBER)
        dpg.add_text("下面是程序需要在屏幕上识别的关键字。请用抖音的对应截图去设置。",
                     color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()
        cfg = config_store.get()
        ocr_texts = cfg.get('ocr_texts', {})
        self.set_tag('ocr_sixin',
                     dpg.add_input_text(label="私信/消息", width=300,
                                        default_value=ocr_texts.get('ocr_text_sixin', '消息')))
        self.set_tag('ocr_send',
                     dpg.add_input_text(label="发送按钮文字", width=300,
                                        default_value=ocr_texts.get('ocr_text_send', '发送')))
        self.set_tag('ocr_exit',
                     dpg.add_input_text(label="退出会话文字", width=300,
                                        default_value=ocr_texts.get('ocr_text_exit', '退出会话')))
        self.set_tag('ocr_input_placeholder',
                     dpg.add_input_text(label="聊天输入框占位文字", width=300,
                                        default_value=ocr_texts.get('ocr_text_input', '输入消息...')))
        dpg.add_spacer(height=8)
        dpg.add_button(label="保存 OCR 文字", width=160, height=30,
                       callback=self._save_ocr_texts)
        dpg.add_text("提示：如果你输入「消息」看到的是「????」，那是因为窗口还没显示。",
                     color=C_TEXT_MUTE, wrap=520)

    def _save_ocr_texts(self, sender=None, app_data=None):
        try:
            cfg = config_store.get()
            cfg['ocr_texts'] = {
                'ocr_text_sixin': dpg.get_value(self.tag('ocr_sixin')),
                'ocr_text_send': dpg.get_value(self.tag('ocr_send')),
                'ocr_text_exit': dpg.get_value(self.tag('ocr_exit')),
                'ocr_text_input': dpg.get_value(self.tag('ocr_input_placeholder')),
            }
            config_store.save(cfg)
            self._show_toast("已保存")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    def _build_region_config(self):
        dpg.add_text("屏幕区域", color=C_AMBER)
        dpg.add_text("点击「框选」按钮，从屏幕上拖拽框出对应区域。", color=C_TEXT_DIM)
        dpg.add_text("百分比会按当前屏幕分辨率自动换算，下次分辨率变了也会跟着变。",
                     color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()
        cfg = config_store.get()
        regions = cfg.get('ui_regions', {
            "top_bar": {"x_pct": 0.65, "y_pct": 0.0, "w_pct": 0.25, "h_pct": 0.10},
            "friend_list": {"x_pct": 0.75, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.85},
            "chat_bottom": {"x_pct": 0.30, "y_pct": 0.85, "w_pct": 0.65, "h_pct": 0.10},
            "chat_top": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.10},
        })

        # 拖动预览画板
        with dpg.group(horizontal=True):
            with dpg.child_window(width=480, height=380, border=True):
                dpg.add_text("屏幕预览（拖动框选）", color=C_TEXT_DIM)
                # 用 drawing API 画屏幕
                self.set_tag('region_drawlist',
                             dpg.add_drawlist(width=460, height=320))
                self.set_tag('region_help',
                             dpg.add_text("先点下方「截屏」按钮", color=C_TEXT_MUTE))
                dpg.add_button(label="截屏", width=120, height=28,
                               callback=self._refresh_region_preview)
                dpg.add_button(label="重置", width=80, height=28,
                               callback=self._reset_region_preview)

            with dpg.child_window(border=True):
                dpg.add_text("区域配置", color=C_TEXT_DIM)
                dpg.add_separator()
                self.region_widgets = {}
                region_labels = [
                    ('top_bar', '顶部 Bar（私信图标）'),
                    ('friend_list', '好友列表'),
                    ('chat_bottom', '聊天底部（发送区）'),
                    ('chat_top', '聊天顶部（退出）'),
                ]
                for key, label in region_labels:
                    dpg.add_text(label)
                    with dpg.group(horizontal=True):
                        self.region_widgets[f"{key}_x"] = dpg.add_input_text(
                            label="X%", width=70,
                            default_value=f"{regions.get(key, {}).get('x_pct', 0.0):.3f}")
                        self.region_widgets[f"{key}_y"] = dpg.add_input_text(
                            label="Y%", width=70,
                            default_value=f"{regions.get(key, {}).get('y_pct', 0.0):.3f}")
                        self.region_widgets[f"{key}_w"] = dpg.add_input_text(
                            label="W%", width=70,
                            default_value=f"{regions.get(key, {}).get('w_pct', 0.1):.3f}")
                        self.region_widgets[f"{key}_h"] = dpg.add_input_text(
                            label="H%", width=70,
                            default_value=f"{regions.get(key, {}).get('h_pct', 0.1):.3f}")
                        dpg.add_button(label="框选", width=50, height=22,
                                       user_data=key,
                                       callback=lambda s, a, k=key: self._pick_region_for(k))
                    dpg.add_separator()
                dpg.add_spacer(height=4)
                dpg.add_button(label="保存区域配置", width=160, height=30,
                               callback=self._save_regions)

        self._refresh_region_preview()

    def _refresh_region_preview(self, sender=None, app_data=None):
        """截屏并画到 drawlist 上，让用户直观看到当前位置"""
        try:
            from PIL import Image
            screen_path = project_path('last_screen.png')
            if not capture_screen_to_file(screen_path):
                dpg.set_value(self.tag('region_help'), "截屏失败")
                return
            img = Image.open(screen_path)
            sw, sh = img.size
            # 缩放到 460x320
            target_w, target_h = 460, 320
            scale = min(target_w / sw, target_h / sh)
            disp_w, disp_h = int(sw * scale), int(sh * scale)
            img_disp = img.resize((disp_w, disp_h))

            # 加载为纹理
            import numpy as np
            arr = np.array(img_disp.convert('RGBA'), dtype=np.float32) / 255.0
            self._region_texture_data = arr.flatten().tolist()
            dpg.delete_item(self.tag('region_drawlist'), children_only=True)
            # 删除旧纹理避免内存泄漏
            if dpg.does_item_exist('region_tex'):
                dpg.delete_item('region_tex')
            with dpg.texture_registry():
                dpg.add_static_texture(disp_w, disp_h, self._region_texture_data,
                                       tag='region_tex')
            dpg.draw_image('region_tex', (0, 0), (disp_w, disp_h),
                           parent=self.tag('region_drawlist'))
            # 画当前已有的区域
            self._draw_existing_regions(disp_w, disp_h, sw, sh)
            dpg.set_value(self.tag('region_help'),
                          f"屏幕: {sw}x{sh}  显示: {disp_w}x{disp_h}  "
                          f"缩放: {scale:.3f}  ·  抖音窗口:"
                          f" {self._get_douyin_rect_text()}")
        except Exception as e:
            dpg.set_value(self.tag('region_help'), f"截屏失败: {e}")

    def _reset_region_preview(self, sender=None, app_data=None):
        dpg.delete_item(self.tag('region_drawlist'), children_only=True)

    def _get_douyin_rect_text(self):
        info = get_douyin_info()
        if not info or not info.get('window'):
            return "未检测到"
        w = info['window']
        return f"{w['x']},{w['y']} {w['w']}x{w['h']}"

    def _draw_existing_regions(self, disp_w, disp_h, screen_w, screen_h):
        cfg = config_store.get()
        regions = cfg.get('ui_regions', {})
        scale_x = disp_w / screen_w
        scale_y = disp_h / screen_h
        colors = {
            'top_bar': (245, 158, 11, 200),
            'friend_list': (96, 165, 250, 200),
            'chat_bottom': (74, 222, 128, 200),
            'chat_top': (239, 68, 68, 200),
        }
        for key, color in colors.items():
            r = regions.get(key)
            if not r:
                continue
            x = r['x_pct'] * screen_w * scale_x
            y = r['y_pct'] * screen_h * scale_y
            w = r['w_pct'] * screen_w * scale_x
            h = r['h_pct'] * screen_h * scale_y
            dpg.draw_rectangle((x, y), (x + w, y + h),
                               color=color, thickness=2,
                               parent=self.tag('region_drawlist'))
            dpg.draw_text((x + 4, y + 4), key, color=color,
                          parent=self.tag('region_drawlist'))

    def _pick_region_for(self, key):
        """用全屏框选器选一个区域，写到对应 key"""
        result = select_region()
        if not result:
            return
        cfg = config_store.get()
        regions = cfg.get('ui_regions', {})
        regions[key] = {
            'x_pct': result['x_pct'],
            'y_pct': result['y_pct'],
            'w_pct': result['w_pct'],
            'h_pct': result['h_pct'],
        }
        cfg['ui_regions'] = regions
        config_store.save(cfg)
        # 刷新input
        dpg.set_value(self.region_widgets[f"{key}_x"], f"{result['x_pct']:.3f}")
        dpg.set_value(self.region_widgets[f"{key}_y"], f"{result['y_pct']:.3f}")
        dpg.set_value(self.region_widgets[f"{key}_w"], f"{result['w_pct']:.3f}")
        dpg.set_value(self.region_widgets[f"{key}_h"], f"{result['h_pct']:.3f}")
        self._refresh_region_preview()
        self._show_toast(f"已更新 {key}")

    def _save_regions(self, sender=None, app_data=None):
        try:
            cfg = config_store.get()
            regions = {}
            for key in ['top_bar', 'friend_list', 'chat_bottom', 'chat_top']:
                regions[key] = {
                    'x_pct': float(dpg.get_value(self.region_widgets[f"{key}_x"])),
                    'y_pct': float(dpg.get_value(self.region_widgets[f"{key}_y"])),
                    'w_pct': float(dpg.get_value(self.region_widgets[f"{key}_w"])),
                    'h_pct': float(dpg.get_value(self.region_widgets[f"{key}_h"])),
                }
            cfg['ui_regions'] = regions
            config_store.save(cfg)
            self._show_toast("已保存")
            self._refresh_region_preview()
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

    # ─── API 配置 ───

    def _build_api_config(self):
        cfg = config_store.get()
        dpg.add_text("API 配置", color=C_AMBER)
        dpg.add_separator()

        # 和风天气
        dpg.add_text("和风天气 API", color=C_TEXT_DIM)
        self.set_tag('api_host',
                     dpg.add_input_text(label="API Host", width=400,
                                        default_value=cfg.get('api_host', 'devapi.qweather.com'),
                                        hint="如: devapi.qweather.com"))
        self.set_tag('api_key',
                     dpg.add_input_text(label="API Key", password=True, width=400,
                                        default_value=cfg.get('api_key', '')))
        dpg.add_button(label="测试和风连接", width=160, height=28,
                       callback=self._test_qweather)

        dpg.add_spacer(height=12)
        dpg.add_text("OCR 配置", color=C_TEXT_DIM)
        # OCR 引擎选择
        ocr_engine = cfg.get('ocr_engine', 'rapidocr')
        ocr_engine_map = {'rapidocr': '本地RapidOCR', 'baidu': '百度云OCR', 'none': '不使用OCR(仅图像匹配)'}
        ocr_engine_default = ocr_engine_map.get(ocr_engine, '本地RapidOCR')
        self.set_tag('ocr_engine_combo',
                     dpg.add_combo(["本地RapidOCR", "百度云OCR", "不使用OCR(仅图像匹配)"],
                                   default_value=ocr_engine_default, width=300))
        self.set_tag('ocr_model_dir',
                     dpg.add_input_text(label="本地OCR模型目录 (可选)", width=400,
                                        default_value=cfg.get('ocr_model_dir', ''),
                                        hint="留空使用默认模型路径"))
        self.set_tag('ocr_api_key',
                     dpg.add_input_text(label="百度 OCR API Key", password=True, width=400,
                                        default_value=cfg.get('ocr_api_key', '')))
        self.set_tag('ocr_secret',
                     dpg.add_input_text(label="百度 OCR Secret", password=True, width=400,
                                        default_value=cfg.get('ocr_secret_key', '')))
        dpg.add_button(label="测试百度 OCR", width=160, height=28,
                       callback=self._test_baidu_ocr)
        dpg.add_button(label="测试本地 OCR", width=160, height=28,
                       callback=self._test_local_ocr)

        dpg.add_spacer(height=12)
        dpg.add_button(label="保存 API 配置", width=200, height=36,
                       callback=self._save_api_config)

    def _test_qweather(self, sender=None, app_data=None):
        host = dpg.get_value(self.tag('api_host')).strip()
        key = dpg.get_value(self.tag('api_key')).strip()
        if not host or not key:
            self._show_toast("请先填 Host 和 Key")
            return
        try:
            import requests
            url = f"https://{host}/v7/weather/now?location=101010100&key={key}"
            r = requests.get(url, timeout=5)
            d = r.json()
            if str(d.get('code')) == '200':
                self._show_toast(f"✓ 连接成功 · 当前: {d['now']['text']}, {d['now']['temp']}℃")
            else:
                self._show_toast(f"✗ 错误码: {d.get('code')}")
        except Exception as e:
            self._show_toast(f"✗ {e}")

    def _test_baidu_ocr(self, sender=None, app_data=None):
        ak = dpg.get_value(self.tag('ocr_api_key')).strip()
        sk = dpg.get_value(self.tag('ocr_secret')).strip()
        if not ak or not sk:
            self._show_toast("请先填 Key 和 Secret")
            return
        try:
            import requests
            r = requests.post('https://aip.baidubce.com/oauth/2.0/token',
                              params={'grant_type': 'client_credentials',
                                      'client_id': ak, 'client_secret': sk},
                              timeout=5)
            d = r.json()
            if 'access_token' in d:
                self._show_toast("✓ 百度 OCR 连接成功")
            else:
                self._show_toast(f"✗ {d.get('error_description', '失败')}")
        except Exception as e:
            self._show_toast(f"✗ {e}")

    def _test_local_ocr(self, sender=None, app_data=None):
        try:
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            # 截屏做测试
            from PIL import ImageGrab
            import io
            screen_path = project_path('last_screen.png')
            if capture_screen_to_file(screen_path):
                result = ocr.find_text_on_screen(
                    ImageGrab.grab(), '抖音', region=None, confidence_threshold=0.5)
                self._show_toast(f"✓ 本地 OCR 可用 (识别结果: {result})")
            else:
                self._show_toast("⚠ 本地 OCR 已加载，截屏失败请重试")
        except Exception as e:
            self._show_toast(f"✗ {e}")

    def _save_api_config(self, sender=None, app_data=None):
        try:
            cfg = config_store.get()
            cfg['api_host'] = dpg.get_value(self.tag('api_host')).strip()
            cfg['api_key'] = dpg.get_value(self.tag('api_key')).strip()
            # OCR 引擎选择
            ocr_choice = dpg.get_value(self.tag('ocr_engine_combo'))
            if ocr_choice == "本地RapidOCR":
                cfg['use_local_ocr'] = True
                cfg['ocr_engine'] = 'rapidocr'
            elif ocr_choice == "百度云OCR":
                cfg['use_local_ocr'] = False
                cfg['ocr_engine'] = 'baidu'
            else:  # 不使用OCR(仅图像匹配)
                cfg['use_local_ocr'] = False
                cfg['ocr_engine'] = 'none'
            cfg['ocr_model_dir'] = dpg.get_value(self.tag('ocr_model_dir')).strip()
            cfg['ocr_api_key'] = dpg.get_value(self.tag('ocr_api_key')).strip()
            cfg['ocr_secret_key'] = dpg.get_value(self.tag('ocr_secret')).strip()
            config_store.save(cfg)
            self._show_toast("已保存")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    # ─── 监控 ───

    def _build_monitor(self):
        dpg.add_text("进程监控", color=C_AMBER)
        dpg.add_text("本页面监控本程序主进程+所有子进程的内存和CPU占用，"
                     "超过阈值会立即在下方报警。", color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()

        cfg = config_store.get()
        mon = cfg.get('process_monitor', {})

        with dpg.group(horizontal=True):
            with dpg.child_window(width=420, border=True):
                dpg.add_text("实时指标", color=C_TEXT_DIM)
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    dpg.add_text("总内存:", color=C_TEXT)
                    self.set_tag('mon_mem', dpg.add_text("— MB", color=C_AMBER))
                with dpg.group(horizontal=True):
                    dpg.add_text("总 CPU:", color=C_TEXT)
                    self.set_tag('mon_cpu', dpg.add_text("— %", color=C_AMBER))
                with dpg.group(horizontal=True):
                    dpg.add_text("子进程数:", color=C_TEXT)
                    self.set_tag('mon_children', dpg.add_text("—", color=C_TEXT))
                with dpg.group(horizontal=True):
                    dpg.add_text("线程数:", color=C_TEXT)
                    self.set_tag('mon_threads', dpg.add_text("—", color=C_TEXT))
                dpg.add_separator()
                dpg.add_text("阈值设置", color=C_TEXT_DIM)
                self.set_tag('mon_enabled',
                             dpg.add_checkbox(label="启用监控",
                                              default_value=mon.get('enabled', True)))
                self.set_tag('mon_max_mem',
                             dpg.add_input_int(label="最大内存 (MB)", width=200,
                                               default_value=mon.get('max_memory_mb', 500)))
                self.set_tag('mon_max_cpu',
                             dpg.add_input_int(label="最大 CPU (%)", width=200,
                                               default_value=mon.get('max_cpu_percent', 80)))
                self.set_tag('mon_interval',
                             dpg.add_input_int(label="检查间隔 (秒)", width=200, min_value=5,
                                               default_value=mon.get('check_interval_sec', 30)))
                self.set_tag('mon_log_level',
                             dpg.add_combo(label="日志级别",
                                           items=["DEBUG", "INFO", "WARNING"],
                                           default_value=cfg.get('log_level', 'INFO'),
                                           width=200))
                dpg.add_text("DEBUG 模式会输出坐标、识别结果、重试次数等详细信息", color=C_TEXT_DIM, wrap=380)
                dpg.add_button(label="保存并应用", width=160, height=30,
                               callback=self._save_monitor_config)
                dpg.add_button(label="立即检测一次", width=160, height=30,
                               callback=self._refresh_monitor)

            with dpg.child_window(border=True):
                dpg.add_text("报警历史", color=C_TEXT_DIM)
                dpg.add_separator()
                self.set_tag('mon_alerts',
                             dpg.add_input_text(multiline=True, readonly=True,
                                                width=-1, height=240))
                dpg.add_text("子进程列表", color=C_TEXT_DIM)
                self.set_tag('mon_children_text',
                             dpg.add_text("—", color=C_TEXT_DIM, wrap=0))
                dpg.add_separator()
                dpg.add_text("运行日志", color=C_TEXT_DIM)
                self.set_tag('log_text',
                             dpg.add_input_text(multiline=True, readonly=True,
                                                width=-1, height=200))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="清空日志", width=80, height=24,
                                   callback=self._clear_logs)
                    dpg.add_button(label="导出日志", width=80, height=24,
                                   callback=self._export_logs)

        self.process_monitor.start()
        self._refresh_monitor()

    def _save_monitor_config(self, sender=None, app_data=None):
        try:
            cfg = config_store.get()
            cfg['process_monitor'] = {
                'enabled': bool(dpg.get_value(self.tag('mon_enabled'))),
                'max_memory_mb': int(dpg.get_value(self.tag('mon_max_mem'))),
                'max_cpu_percent': int(dpg.get_value(self.tag('mon_max_cpu'))),
                'check_interval_sec': max(5, int(dpg.get_value(self.tag('mon_interval')))),
            }
            cfg['log_level'] = dpg.get_value(self.tag('mon_log_level'))
            config_store.save(cfg)
            config_store.apply_log_level()
            self.process_monitor.stop()
            self.process_monitor._load_config()
            self.process_monitor.start()
            self._show_toast("已保存并应用")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    def _refresh_monitor(self, sender=None, app_data=None):
        stats = self.process_monitor.get_main_proc_stats()
        dpg.set_value(self.tag('mon_mem'), f"{stats['total_memory_mb']:.0f} MB")
        dpg.set_value(self.tag('mon_cpu'), f"{stats['total_cpu_percent']:.1f} %")
        dpg.set_value(self.tag('mon_children'), str(stats['child_count']))
        dpg.set_value(self.tag('mon_threads'), str(stats['thread_count']))
        children = stats.get('children', [])
        if children:
            txt = "\n".join([f"  PID {c['pid']:>6} · {c['name']:<20} · {c['memory_mb']:>5.0f} MB · {c['cpu_percent']:>5.1f}%"
                             for c in children])
        else:
            txt = "（无子进程）"
        dpg.set_value(self.tag('mon_children_text'), txt)

    def _on_process_alert(self, alert_type, message, data):
        # 在监控页报警区显示（由 process_monitor 工作线程回调，需锁 DPG mutex）
        try:
            ts = time.strftime('%H:%M:%S')
            line = f"[{ts}] {message}"
            header = f"⚠ {message[:40]}"
            with _dpg_locked():
                current = dpg.get_value(self.tag('mon_alerts'))
                dpg.set_value(self.tag('mon_alerts'), current + line + '\n')
                dpg.set_value(self.tag('header_alert'), header)
        except Exception:
            pass

    def _clear_logs(self, sender=None, app_data=None):
        dpg.set_value(self.tag('log_text'), '')

    def _export_logs(self, sender=None, app_data=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.asksaveasfilename(
                title="导出日志", defaultextension=".log",
                filetypes=[("Log", "*.log"), ("Text", "*.txt")])
            root.destroy()
            if not fp:
                return
            content = dpg.get_value(self.tag('log_text'))
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(content)
            self._show_toast(f"已导出: {os.path.basename(fp)}")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    # ─── 调度 ───

    def _build_scheduler(self):
        cfg = config_store.get()
        dpg.add_text("调度设置", color=C_AMBER)
        dpg.add_text("到时间后自动执行「仪表盘」里配置的任务。",
                     color=C_TEXT_DIM, wrap=520)
        dpg.add_separator()

        self.set_tag('sched_enabled',
                     dpg.add_checkbox(label="启用调度", default_value=cfg.get('scheduler_enabled', True)))
        self.set_tag('sched_time',
                     dpg.add_input_text(label="执行时间 (HH:MM)", width=160,
                                        default_value=cfg.get('schedule_time', '08:00')))
        dpg.add_button(label="保存", width=120, height=30, callback=self._save_scheduler)
        dpg.add_separator()

        dpg.add_text("近 7 天统计", color=C_TEXT_DIM)
        self.set_tag('sched_stats', dpg.add_input_text(
            multiline=True, readonly=True, width=-1, height=160))
        self._refresh_scheduler_stats()

    def _save_scheduler(self, sender=None, app_data=None):
        try:
            cfg = config_store.get()
            cfg['scheduler_enabled'] = bool(dpg.get_value(self.tag('sched_enabled')))
            cfg['schedule_time'] = dpg.get_value(self.tag('sched_time')).strip() or '08:00'
            config_store.save(cfg)
            self.scheduler_enabled = cfg['scheduler_enabled']
            self.scheduled_time = cfg['schedule_time']
            self._show_toast("已保存")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    def _refresh_scheduler_stats(self, sender=None, app_data=None):
        stats = get_stats_by_date(days=7)
        lines = [f"  {s['date']}  ·  发送 {s['total']:>3} 条  ·  成功 {s['success']:>3}  ·  失败 {s['failed']:>3}"
                 for s in stats]
        dpg.set_value(self.tag('sched_stats'), '\n'.join(lines))

    # ─── 发送记录 ───

    def _build_send_history(self):
        dpg.add_text("发送记录", color=C_AMBER)
        dpg.add_separator()

        with dpg.group(horizontal=True):
            self.set_tag('hist_total', dpg.add_text("今日: 0", color=C_TEXT))
            dpg.add_spacer(width=20)
            self.set_tag('hist_success', dpg.add_text("成功: 0", color=C_GREEN))
            dpg.add_spacer(width=20)
            self.set_tag('hist_failed', dpg.add_text("失败: 0", color=C_RED))

        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_button(label="刷新", width=80, height=26,
                           callback=self._refresh_send_history)
            dpg.add_button(label="清空所有记录", width=120, height=26,
                           callback=self._confirm_clear_history)
            dpg.add_button(label="导出 CSV", width=100, height=26,
                           callback=self._export_history_csv)

        dpg.add_separator()
        # 表头
        with dpg.group(horizontal=True):
            dpg.add_text("时间", color=C_TEXT_DIM)
            dpg.add_text("好友", color=C_TEXT_DIM)
            dpg.add_text("结果", color=C_TEXT_DIM)
            dpg.add_text("方法", color=C_TEXT_DIM)
            dpg.add_text("耗时", color=C_TEXT_DIM)
            dpg.add_text("消息预览", color=C_TEXT_DIM)
        dpg.add_separator()
        self.set_tag('history_table',
                     dpg.add_input_text(multiline=True, readonly=True,
                                        width=-1, height=400))
        self._refresh_send_history()

    def _refresh_send_history(self, sender=None, app_data=None):
        stats = get_today_stats()
        records = get_recent_records(limit=200)

        with _dpg_locked():
            dpg.set_value(self.tag('hist_total'), f"今日: {stats['total']}")
            dpg.set_value(self.tag('hist_success'), f"成功: {stats['success']}")
            dpg.set_value(self.tag('hist_failed'), f"失败: {stats['failed']}")

            if not records:
                dpg.set_value(self.tag('history_table'), "  暂无发送记录")
                return
            lines = []
            for r in reversed(records):
                ts = r.get('ts', '')[:19]
                friend = r.get('friend', '')
                success = "✓" if r.get('success') else "✗"
                method = r.get('method', '')
                duration = f"{r.get('duration_ms', 0)}ms"
                preview = (r.get('message_preview', '') or '')[:60].replace('\n', ' ')
                color_marker = ""  # 我们这里不渲染颜色，只渲染文本
                lines.append(f"{ts}  {friend:<10}  {success:<3}  {method:<8}  {duration:<8}  {preview}")
            dpg.set_value(self.tag('history_table'), '\n'.join(lines))

    def _confirm_clear_history(self, sender=None, app_data=None):
        with dpg.window(label="确认", modal=True, width=320, height=140, pos=[300, 200]) as m:
            dpg.add_text("确定要清空所有发送记录吗？\n此操作不可恢复。", color=C_RED)
            with dpg.group(horizontal=True):
                dpg.add_button(label="取消", width=100, height=28,
                               callback=lambda: dpg.delete_item(m))
                dpg.add_button(label="确认清空", width=100, height=28,
                               callback=lambda: (clear_all(),
                                                 self._refresh_send_history(),
                                                 dpg.delete_item(m)))

    def _export_history_csv(self, sender=None, app_data=None):
        try:
            import tkinter as tk
            from tkinter import filedialog
            import csv
            root = tk.Tk()
            root.withdraw()
            fp = filedialog.asksaveasfilename(
                title="导出 CSV", defaultextension=".csv",
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
                        r.get('ts', ''),
                        r.get('friend', ''),
                        '成功' if r.get('success') else '失败',
                        r.get('method', ''),
                        r.get('duration_ms', 0),
                        r.get('message_preview', ''),
                        r.get('error_msg', ''),
                    ])
            self._show_toast(f"已导出 {len(records)} 条到 {os.path.basename(fp)}")
        except Exception as e:
            self._show_toast(f"失败: {e}")

    # ─── 窗口模式 ───

    def _apply_window_mode(self, sender=None, app_data=None):
        mode = dpg.get_value(self.tag('window_mode_radio'))
        sizes = {"normal": (1280, 800), "compact": (900, 600)}
        w, h = sizes.get(mode, (1280, 800))
        dpg.set_viewport_width(w)
        dpg.set_viewport_height(h)
        cfg = config_store.get()
        ui = cfg.setdefault('ui', {})
        ui['window_mode'] = mode
        config_store.save(cfg)
        self._show_toast(f"已切换到 {mode}  ({w}x{h})")

    def _on_theme_change(self, sender=None, app_data=None):
        theme_name = dpg.get_value(self.tag('theme_combo'))
        if theme_name == '亮色':
            dpg.bind_theme(self.tag('light_theme'))
            self._current_theme = '亮色'
        else:
            dpg.bind_theme(self.tag('dark_theme'))
            self._current_theme = '暗色'
        cfg = config_store.get()
        ui = cfg.setdefault('ui', {})
        ui['theme'] = self._current_theme
        config_store.save(cfg)
        self._show_toast(f"已切换到{self._current_theme}主题")

    # ─── 任务执行 ───

    def _run_task_now(self, sender=None, app_data=None):
        if self.worker and self.worker.is_alive():
            self._show_toast("任务正在运行中")
            return
        self._stop_flag.clear()
        # 启动任务时自动进入 Mini 悬浮窗，避免主窗口遮挡抖音
        if self.mini_window:
            self._enter_mini_mode()
        self.worker = threading.Thread(target=self._run_task_thread, daemon=True)
        self.worker.start()

    def _stop_task(self):
        """请求停止当前任务（设置标志，任务线程在下个好友前检查）。"""
        if self._task_running:
            self._stop_flag.set()
            self.logger.info("⏹ 已请求停止任务，将在当前好友处理完成后终止")
            if self.mini_window:
                self.mini_window.append_log(f"{datetime.now().strftime('%H:%M:%S')} ! 用户请求停止任务")
        else:
            self.logger.info("没有正在运行的任务")

    def _run_task_thread(self):
        self._task_running = True
        self._stop_flag.clear()
        self._update_mini_window()
        try:
            with _dpg_locked():
                dpg.set_value(self.tag('status_text'), "▶ 任务执行中...")
            self.logger.info("▶ 开始执行自动化任务")
            from douyin_bot import run_bot_task, set_stop_flag
            set_stop_flag(self._stop_flag)
            run_bot_task()
            if self._stop_flag.is_set():
                with _dpg_locked():
                    dpg.set_value(self.tag('status_text'), "⏹ 任务已停止")
                self.logger.info("⏹ 任务已用户停止")
            else:
                with _dpg_locked():
                    dpg.set_value(self.tag('status_text'), "✓ 任务完成")
                self.logger.info("✓ 任务完成")
        except Exception as e:
            with _dpg_locked():
                dpg.set_value(self.tag('status_text'), f"✗ 失败: {e}")
            self.logger.error(f"任务失败: {e}")
        finally:
            self._task_running = False
            self._update_mini_window()
        self._refresh_send_history()

    def _test_all_connections(self, sender=None, app_data=None):
        self._test_qweather()
        self._refresh_dashboard()

    # ─── 仪表盘刷新 ───

    def _refresh_dashboard(self, sender=None, app_data=None):
        stats = get_today_stats()
        dpg.set_value(self.tag('big_today'), str(stats['success']))
        dpg.set_value(self.tag('dash_today_detail'),
                      f"成功 {stats['success']}  ·  失败 {stats['failed']}  ·  共 {stats['total']}")

        info = get_douyin_info()
        if info:
            dpg.set_value(self.tag('big_douyin'), "运行中" if info else "—")
            dpg.configure_item(self.tag('big_douyin'), color=C_GREEN if info else C_RED)
            if info.get('window'):
                w = info['window']
                dpg.set_value(self.tag('dash_douyin_pos'), f"位置: {w['x']}, {w['y']}")
                dpg.set_value(self.tag('dash_douyin_size'), f"尺寸: {w['w']} x {w['h']}")
                fg = is_douyin_foreground()
                dpg.set_value(self.tag('dash_douyin_fg'),
                              f"前台: {'是' if fg else '否'}  ·  标题: {w['title'][:30]}")
            else:
                dpg.set_value(self.tag('dash_douyin_pos'), "位置: — (窗口未找到)")
                dpg.set_value(self.tag('dash_douyin_size'), "尺寸: —")
                dpg.set_value(self.tag('dash_douyin_fg'), "前台: —")
        else:
            dpg.set_value(self.tag('big_douyin'), "未运行")
            dpg.configure_item(self.tag('big_douyin'), color=C_TEXT_DIM)
            dpg.set_value(self.tag('dash_douyin_pos'), "位置: —")
            dpg.set_value(self.tag('dash_douyin_size'), "尺寸: —")
            dpg.set_value(self.tag('dash_douyin_fg'), "前台: —")

        dpg.set_value(self.tag('big_schedule'), self.scheduled_time)
        dpg.set_value(self.tag('dash_schedule_status'),
                      "已启用" if self.scheduler_enabled else "已禁用")
        dpg.configure_item(self.tag('dash_schedule_status'),
                           color=C_GREEN if self.scheduler_enabled else C_TEXT_DIM)

    # ─── 后台线程 ───

    def _start_background_tasks(self):
        def update():
            while dpg.is_dearpygui_running():
                try:
                    # 先在工作线程收集数据（不碰 DPG）
                    stats = self.process_monitor.get_main_proc_stats()
                    douyin_info = get_douyin_info()
                    now = datetime.now()
                    time_str = now.strftime('%Y-%m-%d %H:%M:%S')

                    # 统一在锁内更新 UI
                    with _dpg_locked():
                        if dpg.does_item_exist(self.tag('header_proc')):
                            dpg.set_value(self.tag('header_proc'),
                                          f"内存: {stats['total_memory_mb']:.0f} MB  "
                                          f"CPU: {stats['total_cpu_percent']:.1f}%  "
                                          f"线程: {stats['thread_count']}")
                        if dpg.does_item_exist(self.tag('header_douyin')):
                            if douyin_info and douyin_info.get('window'):
                                dpg.set_value(self.tag('header_douyin'),
                                              f"抖音: ✓ ({douyin_info['window']['w']}x{douyin_info['window']['h']})")
                                dpg.configure_item(self.tag('header_douyin'), color=C_GREEN)
                            else:
                                dpg.set_value(self.tag('header_douyin'), "抖音: ✗")
                                dpg.configure_item(self.tag('header_douyin'), color=C_TEXT_DIM)
                        if dpg.does_item_exist(self.tag('time_text')):
                            dpg.set_value(self.tag('time_text'), time_str)

                    # 调度检查（不碰 DPG，安全）
                    today = now.strftime('%Y-%m-%d')
                    if self.scheduler_enabled and now.strftime('%H:%M') == self.scheduled_time \
                            and self._last_run_date != today:
                        self._last_run_date = today
                        self.logger.info(f"⏰ 到达调度时间 {self.scheduled_time}, 自动执行")
                        self._run_task_now()

                    # 刷新 Mini 悬浮窗数据
                    if self.mini_window:
                        try:
                            stats = get_today_stats()
                            self._today_send_count = stats.get('success', 0)
                            if self.scheduler_enabled:
                                self._next_run_countdown = f"{self.scheduled_time}"
                            else:
                                self._next_run_countdown = "调度已禁用"
                            self._update_mini_window()
                            # 检查 Mini 窗停止请求
                            if self.mini_window.stop_requested.is_set():
                                self.mini_window.stop_requested.clear()
                                self.logger.info("收到 Mini 窗停止请求")
                                self._stop_task()
                            # 检查 Mini 窗恢复请求
                            if self.mini_window.restore_requested.is_set():
                                self.mini_window.restore_requested.clear()
                                self.logger.info("收到 Mini 窗恢复请求")
                                self._exit_mini_mode()
                        except Exception as e:
                            self.logger.debug(f"Mini 窗更新异常: {e}")
                except Exception as e:
                    self.logger.debug(f"后台任务异常: {e}", exc_info=True)
                # 控制循环速度
                time.sleep(1)
        threading.Thread(target=update, daemon=True).start()

    # ─── 调度配置加载 ───

    def _load_scheduler_config(self):
        try:
            cfg = config_store.get()
            self.scheduled_time = cfg.get('schedule_time', '08:00')
            self.scheduler_enabled = cfg.get('scheduler_enabled', True)
        except Exception:
            pass

    # ─── 通用 UI 助手 ───

    def _show_toast(self, message, duration_ms=2000):
        """底部短提示"""
        tag = f"toast_{int(time.time() * 1000)}"
        with dpg.window(label="提示", modal=False, width=320, height=80,
                        pos=[400, 350], tag=tag, no_resize=True, no_collapse=True,
                        no_title_bar=False):
            dpg.add_text(message, wrap=300)
            dpg.add_button(label="好", width=80, height=24,
                           callback=lambda: dpg.delete_item(tag))
        def close():
            time.sleep(duration_ms / 1000)
            if dpg.does_item_exist(tag):
                try:
                    dpg.delete_item(tag)
                except Exception:
                    pass
        threading.Thread(target=close, daemon=True).start()

    def _toggle_mini_mode(self, sender=None, app_data=None):
        if not self.mini_window:
            self._show_toast("小窗功能未初始化")
            return
        if self._mini_mode:
            self._exit_mini_mode()
        else:
            self._enter_mini_mode()

    def _hide_main_window(self):
        """隐藏 DPG 主窗口：优先用 Win32 ShowWindow SW_HIDE，失败则回退 minimize_viewport。"""
        try:
            if self._dpg_hwnd:
                ctypes.windll.user32.ShowWindow(self._dpg_hwnd, 0)  # SW_HIDE
                self.logger.info("DPG 主窗口已隐藏")
            else:
                dpg.minimize_viewport()
                self.logger.info("DPG 主窗口已最小化（无 hwnd 缓存）")
        except Exception as e:
            self.logger.error(f"隐藏主窗口失败: {e}")

    def _show_main_window(self):
        """恢复 DPG 主窗口：优先用 Win32 ShowWindow SW_RESTORE，失败则回退 maximize_viewport。"""
        try:
            if self._dpg_hwnd:
                ctypes.windll.user32.ShowWindow(self._dpg_hwnd, 9)  # SW_RESTORE
                self.logger.info("DPG 主窗口已恢复")
            else:
                dpg.maximize_viewport()
                self.logger.info("DPG 主窗口已最大化恢复（无 hwnd 缓存）")
        except Exception as e:
            self.logger.error(f"恢复主窗口失败: {e}")

    def _enter_mini_mode(self):
        self._mini_mode = True
        self.logger.info("正在切换到 Mini 悬浮窗...")
        self._hide_main_window()
        self._update_mini_window()
        with _dpg_locked():
            if dpg.does_item_exist(self.tag('mini_mode_btn')):
                dpg.set_item_label(self.tag('mini_mode_btn'), "⛶ 恢复")
        self.logger.info("已切换到 Mini 悬浮窗，主窗口已最小化")

    def _exit_mini_mode(self):
        self._mini_mode = False
        self.logger.info("正在恢复主窗口...")
        if self.mini_window:
            self.mini_window.hide()
        self._show_main_window()
        with _dpg_locked():
            if dpg.does_item_exist(self.tag('mini_mode_btn')):
                dpg.set_item_label(self.tag('mini_mode_btn'), "🗕 小窗")
        self.logger.info("主窗口已恢复")

    def _update_mini_window(self):
        if not self.mini_window or not self._mini_mode:
            return
        status = "运行中" if self._task_running else "就绪"
        color = '#4caf50' if not self._task_running else '#f59e0b'
        self.mini_window.update_status(
            status=status,
            today_count=self._today_send_count,
            current_friend=self._current_friend,
            countdown=self._next_run_countdown,
            status_color=color,
        )

    def _show_modal(self, title, content, width=500, height=300):
        tag = f"modal_{int(time.time() * 1000)}"
        with dpg.window(label=title, modal=True, width=width, height=height,
                        pos=[200, 150], tag=tag):
            dpg.add_text(content, wrap=width - 30)
            dpg.add_button(label="关闭", width=100, height=28,
                           callback=lambda: dpg.delete_item(tag))

    def _open_file(self, path):
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self._show_toast(f"打开失败: {e}")

    def _open_dir(self, path):
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])
        except Exception as e:
            self._show_toast(f"打开失败: {e}")
