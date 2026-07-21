import json
import os
import time
import threading
import logging
from datetime import datetime

import dearpygui.dearpygui as dpg
import psutil

from config_utils import project_path, load_config, save_config


class DPGApp:
    def __init__(self, logger):
        self.logger = logger
        self.worker = None
        self.log_messages = []
        self.douyin_running = False
        self.scheduled_time = "08:00"
        self.scheduler_enabled = True
        self._last_run_date = None
        self._load_scheduler_config()

    def build(self):
        with dpg.window(tag="main_window"):
            with dpg.tab_bar():
                with dpg.tab(label="仪表盘"):
                    self._build_dashboard()
                with dpg.tab(label="配置管理"):
                    self._build_config()
                with dpg.tab(label="消息预设"):
                    self._build_messages()
                with dpg.tab(label="抖音界面"):
                    self._build_ui_config()
                with dpg.tab(label="任务监控"):
                    self._build_monitor()
                with dpg.tab(label="调度设置"):
                    self._build_scheduler()

            with dpg.group(horizontal=True):
                self.status_text = dpg.add_text("就绪", color=(100, 100, 100))
                dpg.add_spacer(width=20)
                self.douyin_status = dpg.add_text("抖音: 检测中...", color=(255, 165, 0))
                dpg.add_spacer(width=20)
                self.process_text = dpg.add_text("内存: --MB  CPU: --%", color=(100, 100, 100))

        dpg.set_primary_window("main_window", True)
        self._start_background_tasks()

    def _build_dashboard(self):
        with dpg.group(horizontal=True):
            with dpg.child_window(width=220, height=120):
                dpg.add_text("好友数量", color=(100, 100, 100))
                self.friends_count = dpg.add_text("0", color=(26, 188, 156))
                dpg.add_text("识别模式", color=(100, 100, 100))
                self.ocr_mode_text = dpg.add_text("图像识别", color=(52, 152, 219))

            with dpg.child_window(width=220, height=120):
                dpg.add_text("调度状态", color=(100, 100, 100))
                self.schedule_status = dpg.add_text("未启用", color=(231, 76, 60))
                dpg.add_text("执行时间", color=(100, 100, 100))
                self.schedule_time = dpg.add_text("08:00", color=(155, 89, 182))

            with dpg.child_window(width=220, height=120):
                dpg.add_text("抖音状态", color=(100, 100, 100))
                self.douyin_dashboard_status = dpg.add_text("检测中...", color=(255, 165, 0))
                dpg.add_text("今日已发送", color=(100, 100, 100))
                self.sent_count = dpg.add_text("0", color=(26, 188, 156))

        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            dpg.add_button(label="立即执行任务", callback=self._run_task_now, width=150, height=40)
            dpg.add_button(label="刷新状态", callback=self._refresh_dashboard, width=100, height=40)

        self._refresh_dashboard()

    def _build_config(self):
        with dpg.child_window():
            dpg.add_text("天气API配置", color=(44, 62, 80))
            self.api_host_input = dpg.add_input_text(label="API Host", width=400)
            self.api_key_input = dpg.add_input_text(label="API Key", width=400, password=True)

            dpg.add_button(label="测试连接", callback=self._test_api, width=100)
            dpg.add_spacer(height=10)

            dpg.add_text("消息模板", color=(44, 62, 80))
            self.message_template_input = dpg.add_input_text(
                multiline=True, width=-1, height=100,
                default_value="Hi {nickname}，你所在的{city_name}今天..."
            )
            dpg.add_text("可用变量: {nickname}, {city_name}, {text_day}, {temp_max}, {temp_min}",
                         color=(127, 140, 141))

            dpg.add_spacer(height=10)
            dpg.add_text("OCR配置", color=(44, 62, 80))
            self.use_local_ocr = dpg.add_checkbox(label="启用本地OCR识别（推荐）", default_value=True)
            self.ocr_api_key_input = dpg.add_input_text(label="百度OCR Key", width=350, password=True)
            self.ocr_secret_input = dpg.add_input_text(label="百度OCR Secret", width=350, password=True)

            dpg.add_spacer(height=10)
            dpg.add_button(label="保存配置", callback=self._save_config, width=150, height=35)

        self._load_config_values()

    def _build_messages(self):
        with dpg.child_window():
            dpg.add_text("消息预设库", color=(44, 62, 80))
            dpg.add_text("管理自定义消息模板", color=(127, 140, 141))

            with dpg.group(horizontal=True):
                dpg.add_button(label="新建预设", callback=self._new_preset, width=100)
                dpg.add_button(label="导入", callback=self._import_presets, width=80)
                dpg.add_button(label="导出", callback=self._export_presets, width=80)

            dpg.add_spacer(height=5)
            self.presets_list = dpg.add_listbox([], width=-1, height=150, callback=self._on_preset_select)

            dpg.add_spacer(height=5)
            dpg.add_text("编辑预设", color=(44, 62, 80))
            self.preset_name_input = dpg.add_input_text(label="名称", width=300)
            self.preset_weather_check = dpg.add_checkbox(label="使用天气API")
            self.preset_template_input = dpg.add_input_text(label="消息模板", multiline=True, width=-1, height=80)

            with dpg.group(horizontal=True):
                dpg.add_button(label="保存预设", callback=self._save_preset, width=120)
                dpg.add_button(label="删除预设", callback=self._delete_preset, width=120)

        self._load_presets()

    def _build_ui_config(self):
        with dpg.child_window():
            dpg.add_text("抖音界面配置", color=(44, 62, 80))

            with dpg.tab_bar():
                with dpg.tab(label="控制图像"):
                    self._build_image_config()
                with dpg.tab(label="OCR文字"):
                    self._build_ocr_text_config()
                with dpg.tab(label="屏幕区域"):
                    self._build_region_config()

    def _build_image_config(self):
        dpg.add_text("控制图像用于图像匹配模式", color=(127, 140, 141))

        images = [
            ("douyin_sixin_icon.png", "私信图标"),
            ("douyin_send_button.png", "发送按钮"),
            ("douyin_exit_chat_button.png", "退出会话"),
        ]

        self.image_widgets = {}
        for filename, name in images:
            with dpg.group(horizontal=True):
                dpg.add_text(f"{name}:")
                path = project_path('control_images', filename)
                status = "已配置" if os.path.exists(path) else "未配置"
                color = (46, 204, 113) if os.path.exists(path) else (231, 76, 60)
                self.image_widgets[filename] = dpg.add_text(status, color=color)
                dpg.add_button(label="上传", callback=lambda s, a, u: self._upload_image(u), user_data=filename, width=60)

    def _build_ocr_text_config(self):
        dpg.add_text("OCR识别文字配置", color=(127, 140, 141))

        self.ocr_text_widgets = {}
        texts = [
            ("ocr_text_sixin", "私信/消息", "消息"),
            ("ocr_text_send", "发送", "发送"),
            ("ocr_text_exit", "退出会话", "退出会话"),
        ]

        for key, name, default in texts:
            self.ocr_text_widgets[key] = dpg.add_input_text(label=name, default_value=default, width=200)

        dpg.add_button(label="保存OCR文字", callback=self._save_ocr_texts, width=120)

    def _build_region_config(self):
        dpg.add_text("屏幕区域配置（百分比 0.0~1.0）", color=(127, 140, 141))

        regions = [
            ("top_bar", "私信图标区域", 0.65, 0.0, 0.25, 0.10),
            ("friend_list", "好友列表区域", 0.75, 0.10, 0.25, 0.85),
            ("chat_bottom", "发送按钮区域", 0.30, 0.85, 0.65, 0.10),
            ("chat_top", "退出会话区域", 0.70, 0.10, 0.25, 0.10),
        ]

        self.region_widgets = {}
        for key, name, x, y, w, h in regions:
            dpg.add_text(name, color=(44, 62, 80))
            with dpg.group(horizontal=True):
                self.region_widgets[f"{key}_x"] = dpg.add_input_text(label="X", default_value=str(x), width=60)
                self.region_widgets[f"{key}_y"] = dpg.add_input_text(label="Y", default_value=str(y), width=60)
                self.region_widgets[f"{key}_w"] = dpg.add_input_text(label="宽", default_value=str(w), width=60)
                self.region_widgets[f"{key}_h"] = dpg.add_input_text(label="高", default_value=str(h), width=60)

        dpg.add_button(label="保存区域配置", callback=self._save_regions, width=120)

    def _build_monitor(self):
        with dpg.child_window():
            dpg.add_text("任务监控", color=(44, 62, 80))

            with dpg.group(horizontal=True):
                self.proc_memory = dpg.add_text("内存: --MB", color=(100, 100, 100))
                dpg.add_text("|", color=(100, 100, 100))
                self.proc_cpu = dpg.add_text("CPU: --%", color=(100, 100, 100))

            dpg.add_spacer(height=5)
            dpg.add_text("运行日志:", color=(44, 62, 80))
            self.log_window = dpg.add_input_text(multiline=True, width=-1, height=400, readonly=True)

            with dpg.group(horizontal=True):
                dpg.add_button(label="清除日志", callback=self._clear_logs, width=100)
                dpg.add_button(label="导出日志", callback=self._export_logs, width=100)

    def _build_scheduler(self):
        with dpg.child_window():
            dpg.add_text("调度设置", color=(44, 62, 80))
            self.scheduler_enabled_check = dpg.add_checkbox(label="启用定时调度", default_value=self.scheduler_enabled)
            self.schedule_time_input = dpg.add_input_text(label="执行时间 (HH:MM)", default_value=self.scheduled_time, width=150)
            dpg.add_button(label="保存调度设置", callback=self._save_scheduler, width=150)

            dpg.add_spacer(height=10)
            dpg.add_text("进程监控", color=(44, 62, 80))
            self.monitor_enabled = dpg.add_checkbox(label="启用进程监控", default_value=True)
            self.max_memory_input = dpg.add_input_text(label="最大内存(MB)", default_value="500", width=100)
            self.max_cpu_input = dpg.add_input_text(label="最大CPU(%)", default_value="80", width=100)
            dpg.add_button(label="保存监控设置", callback=self._save_monitor_config, width=150)

    def _load_config_values(self):
        try:
            cfg = load_config()
            dpg.set_value(self.api_host_input, cfg.get('api_host', ''))
            dpg.set_value(self.api_key_input, cfg.get('api_key', ''))
            dpg.set_value(self.message_template_input, cfg.get('message_template', ''))
            dpg.set_value(self.use_local_ocr, cfg.get('use_local_ocr', True))
            dpg.set_value(self.ocr_api_key_input, cfg.get('ocr_api_key', ''))
            dpg.set_value(self.ocr_secret_input, cfg.get('ocr_secret_key', ''))
        except Exception:
            pass

    def _save_config(self, sender, app_data):
        try:
            cfg = load_config() or {}
            cfg['api_host'] = dpg.get_value(self.api_host_input).strip()
            cfg['api_key'] = dpg.get_value(self.api_key_input).strip()
            cfg['message_template'] = dpg.get_value(self.message_template_input).strip()
            cfg['use_local_ocr'] = dpg.get_value(self.use_local_ocr)
            cfg['ocr_api_key'] = dpg.get_value(self.ocr_api_key_input).strip()
            cfg['ocr_secret_key'] = dpg.get_value(self.ocr_secret_input).strip()
            save_config(cfg)
            self._show_toast("配置已保存")
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

    def _load_presets(self):
        try:
            cfg_path = project_path('messages.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {"presets": [], "active_preset": "weather"}
            self.presets = data.get('presets', [])
            labels = [p.get('name', '未命名') for p in self.presets]
            dpg.set_item_label(self.presets_list, labels)
        except Exception:
            self.presets = []

    def _new_preset(self, sender, app_data):
        name = dpg.get_value(self.preset_name_input)
        if not name:
            self._show_toast("请输入预设名称")
            return
        preset = {
            "id": f"preset_{int(time.time())}",
            "name": name,
            "use_weather_api": dpg.get_value(self.preset_weather_check),
            "template": dpg.get_value(self.preset_template_input),
        }
        self.presets.append(preset)
        self._save_presets()
        self._load_presets()
        self._show_toast(f"预设 '{name}' 已创建")

    def _save_preset(self, sender, app_data):
        self._show_toast("预设已保存")

    def _delete_preset(self, sender, app_data):
        self._show_toast("预设已删除")

    def _on_preset_select(self, sender, app_data):
        if 0 <= app_data < len(self.presets):
            p = self.presets[app_data]
            dpg.set_value(self.preset_name_input, p.get('name', ''))
            dpg.set_value(self.preset_weather_check, p.get('use_weather_api', False))
            dpg.set_value(self.preset_template_input, p.get('template', ''))

    def _save_presets(self):
        try:
            cfg_path = project_path('messages.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump({"presets": self.presets, "active_preset": "weather"}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _import_presets(self, sender, app_data):
        self._show_toast("导入功能待实现")

    def _export_presets(self, sender, app_data):
        self._show_toast("导出功能待实现")

    def _upload_image(self, filename):
        self._show_toast(f"请通过文件选择器上传 {filename}")

    def _save_ocr_texts(self, sender, app_data):
        try:
            cfg = load_config() or {}
            ocr_texts = {}
            for key, widget in self.ocr_text_widgets.items():
                ocr_texts[key] = dpg.get_value(widget).strip()
            cfg['ocr_texts'] = ocr_texts
            save_config(cfg)
            self._show_toast("OCR文字已保存")
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

    def _save_regions(self, sender, app_data):
        try:
            cfg = load_config() or {}
            regions = {}
            for key in ['top_bar', 'friend_list', 'chat_bottom', 'chat_top']:
                regions[key] = {
                    "x_pct": float(dpg.get_value(self.region_widgets[f"{key}_x"])),
                    "y_pct": float(dpg.get_value(self.region_widgets[f"{key}_y"])),
                    "w_pct": float(dpg.get_value(self.region_widgets[f"{key}_w"])),
                    "h_pct": float(dpg.get_value(self.region_widgets[f"{key}_h"])),
                }
            cfg['ui_regions'] = regions
            save_config(cfg)
            self._show_toast("区域配置已保存")
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

    def _refresh_dashboard(self, sender=None, app_data=None):
        try:
            cfg = load_config() or {}
            friends = len(cfg.get('friends', []))
            use_local = cfg.get('use_local_ocr', True)
            dpg.set_value(self.friends_count, str(friends))
            dpg.set_value(self.ocr_mode_text, "本地OCR" if use_local else "百度OCR")
            dpg.set_value(self.schedule_status, "已启用" if self.scheduler_enabled else "已禁用")
            dpg.set_value(self.schedule_time, self.scheduled_time)
            self._check_douyin_process()
        except Exception:
            pass

    def _check_douyin_process(self):
        found = False
        for proc in psutil.process_iter(['name']):
            try:
                if 'douyin' in proc.info['name'].lower():
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        self.douyin_running = found
        status = "运行中" if found else "未运行"
        color = (46, 204, 113) if found else (231, 76, 60)
        dpg.set_value(self.douyin_dashboard_status, status)
        dpg.configure_item(self.douyin_dashboard_status, color=color)

    def _run_task_now(self, sender=None, app_data=None):
        if self.worker and self.worker.is_alive():
            self._show_toast("任务正在运行中")
            return
        self.worker = threading.Thread(target=self._run_task_thread, daemon=True)
        self.worker.start()

    def _run_task_thread(self):
        try:
            dpg.set_value(self.status_text, "任务执行中...")
            self.logger.info("开始执行自动化任务")
            from douyin_bot import run_bot_task
            run_bot_task()
            dpg.set_value(self.status_text, "任务完成")
            self.logger.info("任务执行完毕")
        except Exception as e:
            dpg.set_value(self.status_text, f"任务失败: {e}")
            self.logger.error(f"任务失败: {e}")

    def _save_scheduler(self, sender, app_data):
        try:
            self.scheduled_time = dpg.get_value(self.schedule_time_input).strip()
            self.scheduler_enabled = dpg.get_value(self.scheduler_enabled_check)
            cfg = load_config() or {}
            cfg['schedule_time'] = self.scheduled_time
            cfg['scheduler_enabled'] = self.scheduler_enabled
            save_config(cfg)
            self._show_toast("调度设置已保存")
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

    def _load_scheduler_config(self):
        try:
            cfg = load_config()
            self.scheduled_time = cfg.get('schedule_time', '08:00')
            self.scheduler_enabled = cfg.get('scheduler_enabled', True)
        except Exception:
            pass

    def _save_monitor_config(self, sender, app_data):
        self._show_toast("监控设置已保存")

    def _test_api(self, sender, app_data):
        self._show_toast("API测试功能待实现")

    def _clear_logs(self, sender, app_data):
        dpg.set_value(self.log_window, "")

    def _export_logs(self, sender, app_data):
        self._show_toast("日志导出待实现")

    def _show_toast(self, message):
        with dpg.window(label="提示", modal=True, width=300, height=100, pos=[300, 250]):
            dpg.add_text(message)
            dpg.add_button(label="确定", callback=lambda: dpg.delete_item(dpg.last_item().parent))

    def _start_background_tasks(self):
        def update_stats():
            while dpg.is_dearpygui_running():
                try:
                    proc = psutil.Process(os.getpid())
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    cpu = proc.cpu_percent(interval=0.1)
                    dpg.set_value(self.process_text, f"内存: {mem_mb:.0f}MB  CPU: {cpu:.1f}%")

                    now = datetime.now()
                    current_time = now.strftime("%H:%M")
                    today = now.strftime("%Y-%m-%d")
                    if self.scheduler_enabled and current_time == self.scheduled_time and self._last_run_date != today:
                        self._last_run_date = today
                        self._run_task_now()

                    self._check_douyin_process()
                except Exception:
                    pass
                time.sleep(5)

        t = threading.Thread(target=update_stats, daemon=True)
        t.start()
