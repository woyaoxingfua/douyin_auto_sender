"""仪表盘页面：今日发送统计、抖音状态、调度信息、快捷操作"""

import dearpygui.dearpygui as dpg

from config_utils import project_path
from send_log import get_today_stats
from douyin_monitor import get_douyin_info, is_douyin_foreground
from font_loader import bind_to_item


class DashboardPage:
    def __init__(self, app):
        self.app = app

    def build(self):
        with dpg.group(horizontal=True):
            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("今日已发送", color=self.app.C_TEXT_DIM)
                self.app.set_tag('big_today', dpg.add_text("0", color=self.app.C_AMBER))
                bind_to_item(self.app.tag('big_today'), 42)
                dpg.add_text("条", color=self.app.C_TEXT_DIM)
                dpg.add_spacer(height=2)
                self.app.set_tag('dash_today_detail', dpg.add_text("成功 0  ·  失败 0", color=self.app.C_TEXT_DIM))

            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("抖音窗口", color=self.app.C_TEXT_DIM)
                self.app.set_tag('big_douyin', dpg.add_text("—", color=self.app.C_TEXT_DIM))
                bind_to_item(self.app.tag('big_douyin'), 24)
                dpg.add_spacer(height=4)
                self.app.set_tag('dash_douyin_pos', dpg.add_text("位置: --", color=self.app.C_TEXT_DIM))
                self.app.set_tag('dash_douyin_size', dpg.add_text("尺寸: --", color=self.app.C_TEXT_DIM))
                self.app.set_tag('dash_douyin_fg', dpg.add_text("前台: --", color=self.app.C_TEXT_DIM))

            with dpg.child_window(width=290, height=160, border=True):
                dpg.add_text("调度", color=self.app.C_TEXT_DIM)
                self.app.set_tag('big_schedule', dpg.add_text("08:00", color=self.app.C_AMBER))
                bind_to_item(self.app.tag('big_schedule'), 42)
                dpg.add_spacer(height=2)
                self.app.set_tag('dash_schedule_status', dpg.add_text("已启用", color=self.app.C_GREEN))

        dpg.add_spacer(height=12)

        with dpg.child_window(border=True, height=120):
            dpg.add_text("操作", color=self.app.C_AMBER)
            with dpg.group(horizontal=True):
                dpg.add_button(label="立即执行任务", width=160, height=36, callback=self.app._run_task_now)
                dpg.add_button(label="测试连接", width=120, height=36, callback=self.app._test_all_connections)
                dpg.add_button(label="打开日志文件", width=120, height=36, callback=lambda: self.app._open_file(project_path('run.log')))
                dpg.add_button(label="打开配置目录", width=120, height=36, callback=lambda: self.app._open_dir(project_path('.')))

            dpg.add_spacer(height=8)
            dpg.add_text("窗口模式", color=self.app.C_TEXT_DIM)
            with dpg.group(horizontal=True):
                self.app.set_tag('window_mode_radio', dpg.add_radio_button(["normal", "compact", "mini"], horizontal=True, default_value="normal"))
                dpg.add_button(label="应用", width=80, height=24, callback=self.app._apply_window_mode)
                dpg.add_text("重启后保留此设置", color=self.app.C_TEXT_MUTE)

            dpg.add_spacer(height=8)
            dpg.add_text("配色方案", color=self.app.C_TEXT_DIM)
            with dpg.group(horizontal=True):
                self.app.set_tag('theme_combo', dpg.add_combo(["暗色", "亮色"], default_value=getattr(self.app, '_current_theme', '暗色'), width=120, callback=self.app._on_theme_change))

        self.refresh()

    def refresh(self):
        stats = get_today_stats()
        dpg.set_value(self.app.tag('big_today'), str(stats['success']))
        dpg.set_value(self.app.tag('dash_today_detail'), f"成功 {stats['success']}  ·  失败 {stats['failed']}  ·  共 {stats['total']}")

        info = get_douyin_info()
        if info:
            dpg.set_value(self.app.tag('big_douyin'), "运行中" if info else "—")
            dpg.configure_item(self.app.tag('big_douyin'), color=self.app.C_GREEN if info else self.app.C_RED)
            if info.get('window'):
                w = info['window']
                dpg.set_value(self.app.tag('dash_douyin_pos'), f"位置: {w['x']}, {w['y']}")
                dpg.set_value(self.app.tag('dash_douyin_size'), f"尺寸: {w['w']} x {w['h']}")
                fg = is_douyin_foreground()
                dpg.set_value(self.app.tag('dash_douyin_fg'), f"前台: {'是' if fg else '否'}  ·  标题: {w['title'][:30]}")
            else:
                dpg.set_value(self.app.tag('dash_douyin_pos'), "位置: — (窗口未找到)")
                dpg.set_value(self.app.tag('dash_douyin_size'), "尺寸: —")
                dpg.set_value(self.app.tag('dash_douyin_fg'), "前台: —")
        else:
            dpg.set_value(self.app.tag('big_douyin'), "未运行")
            dpg.configure_item(self.app.tag('big_douyin'), color=self.app.C_TEXT_DIM)
            dpg.set_value(self.app.tag('dash_douyin_pos'), "位置: —")
            dpg.set_value(self.app.tag('dash_douyin_size'), "尺寸: —")
            dpg.set_value(self.app.tag('dash_douyin_fg'), "前台: —")

        dpg.set_value(self.app.tag('big_schedule'), self.app.scheduled_time)
        dpg.set_value(self.app.tag('dash_schedule_status'), "已启用" if self.app.scheduler_enabled else "已禁用")
        dpg.configure_item(self.app.tag('dash_schedule_status'), color=self.app.C_GREEN if self.app.scheduler_enabled else self.app.C_TEXT_DIM)
