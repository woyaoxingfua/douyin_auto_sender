import json
import os
import time
import shutil
import threading
import logging
import requests
from datetime import datetime

import dearpygui.dearpygui as dpg
import psutil

from config_utils import project_path, load_config, save_config


class DPGApp:
    def __init__(self, logger):
        self.logger = logger
        self.worker = None
        self.douyin_running = False
        self.scheduled_time = "08:00"
        self.scheduler_enabled = True
        self._last_run_date = None
        self._upload_target = None
        self._load_scheduler_config()

    def build(self):
        with dpg.theme() as light_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (248, 249, 250))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (73, 80, 87))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (173, 181, 189))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (134, 142, 150))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (173, 181, 189))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (134, 142, 150))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (233, 236, 239))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (220, 223, 227))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (222, 226, 230))
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (248, 249, 250))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (9, 171, 59))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, (9, 171, 59))
                dpg.add_theme_color(dpg.mvThemeCol_TabSelected, (9, 171, 59))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (233, 236, 239))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (222, 226, 230))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (209, 213, 218))
                dpg.add_theme_color(dpg.mvThemeCol_Separator, (222, 226, 230))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (248, 249, 250))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (173, 181, 189))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (134, 142, 150))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (108, 117, 125))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 6)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 16, 16)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
        dpg.bind_theme(light_theme)

        dpg.add_file_dialog(
            tag="file_dialog",
            show=False,
            callback=self._on_file_selected,
            width=500,
            height=400,
            modal=True,
        )

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
                self.status_text = dpg.add_text("就绪")
                dpg.add_spacer(width=20)
                self.douyin_status = dpg.add_text("抖音: 检测中...", color=(255, 193, 7))
                dpg.add_spacer(width=20)
                self.process_text = dpg.add_text("内存: --MB  CPU: --%")

        dpg.set_primary_window("main_window", True)
        self._start_background_tasks()

    def _build_dashboard(self):
        with dpg.group(horizontal=True):
            with dpg.child_window(width=220, height=120):
                dpg.add_text("好友数量")
                self.friends_count = dpg.add_text("0", color=(9, 171, 59))
                dpg.add_text("识别模式")
                self.ocr_mode_text = dpg.add_text("图像识别", color=(13, 110, 253))

            with dpg.child_window(width=220, height=120):
                dpg.add_text("调度状态")
                self.schedule_status = dpg.add_text("未启用", color=(220, 53, 69))
                dpg.add_text("执行时间")
                self.schedule_time = dpg.add_text("08:00", color=(123, 44, 191))

            with dpg.child_window(width=220, height=120):
                dpg.add_text("抖音状态")
                self.douyin_dashboard_status = dpg.add_text("检测中...", color=(255, 193, 7))
                dpg.add_text("今日已发送")
                self.sent_count = dpg.add_text("0", color=(9, 171, 59))

        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True):
            dpg.add_button(label="立即执行任务", callback=self._run_task_now, width=150, height=35)
            dpg.add_button(label="刷新状态", callback=self._refresh_dashboard, width=100, height=35)
        self._refresh_dashboard()

    def _build_config(self):
        with dpg.child_window():
            dpg.add_text("天气API配置")
            self.api_host_input = dpg.add_input_text(label="API Host", width=400)
            self.api_key_input = dpg.add_input_text(label="API Key", width=400, password=True)
            dpg.add_button(label="测试连接", callback=self._test_api, width=100)
            dpg.add_spacer(height=10)

            dpg.add_text("消息模板")
            self.message_template_input = dpg.add_input_text(
                multiline=True, width=-1, height=100,
                default_value="Hi {nickname}，你所在的{city_name}今天..."
            )
            dpg.add_text("变量: {nickname}, {city_name}, {text_day}, {temp_max}, {temp_min}")

            dpg.add_spacer(height=10)
            dpg.add_text("OCR配置")
            self.use_local_ocr = dpg.add_checkbox(label="启用本地OCR识别（推荐）", default_value=True)
            self.ocr_api_key_input = dpg.add_input_text(label="百度OCR Key", width=350, password=True)
            self.ocr_secret_input = dpg.add_input_text(label="百度OCR Secret", width=350, password=True)
            dpg.add_button(label="测试OCR", callback=self._test_ocr, width=100)

            dpg.add_spacer(height=10)
            dpg.add_button(label="保存配置", callback=self._save_config, width=150, height=35)
        self._load_config_values()

    def _test_api(self, sender, app_data):
        host = dpg.get_value(self.api_host_input).strip()
        key = dpg.get_value(self.api_key_input).strip()
        if not host or not key:
            self._show_toast("请先填写 API Host 和 API Key")
            return
        try:
            url = f"https://{host}/v7/weather/now?location=101010100&key={key}"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            if data.get("code") == "200":
                self._show_toast("API 连接成功！")
            else:
                self._show_toast(f"API 返回错误码: {data.get('code')}")
        except Exception as e:
            self._show_toast(f"连接失败: {e}")

    def _test_ocr(self, sender, app_data):
        api_key = dpg.get_value(self.ocr_api_key_input).strip()
        secret = dpg.get_value(self.ocr_secret_input).strip()
        if not api_key or not secret:
            self._show_toast("请先填写 OCR API Key 和 Secret Key")
            return
        try:
            token_url = "https://aip.baidubce.com/oauth/2.0/token"
            resp = requests.post(token_url, params={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret,
            }, timeout=5)
            data = resp.json()
            if "access_token" in data:
                self._show_toast("百度OCR 连接成功！")
            else:
                self._show_toast(f"获取Token失败: {data.get('error_description', 'unknown')}")
        except Exception as e:
            self._show_toast(f"连接失败: {e}")

    def _build_messages(self):
        with dpg.child_window():
            dpg.add_text("消息预设库")
            with dpg.group(horizontal=True):
                dpg.add_button(label="新建预设", callback=self._new_preset, width=100)
                dpg.add_button(label="导入", callback=self._import_presets, width=80)
                dpg.add_button(label="导出", callback=self._export_presets, width=80)
            dpg.add_spacer(height=5)
            self.presets_list = dpg.add_listbox([], width=-1, num_items=8, callback=self._on_preset_select)
            dpg.add_spacer(height=5)
            dpg.add_text("编辑预设")
            self.preset_name_input = dpg.add_input_text(label="名称", width=300)
            self.preset_weather_check = dpg.add_checkbox(label="使用天气API")
            self.preset_template_input = dpg.add_input_text(label="消息模板", multiline=True, width=-1, height=80)
            with dpg.group(horizontal=True):
                dpg.add_button(label="保存预设", callback=self._save_preset, width=120)
                dpg.add_button(label="删除预设", callback=self._delete_preset, width=120)
        self._load_presets()

    def _build_ui_config(self):
        with dpg.child_window():
            dpg.add_text("抖音界面配置")
            with dpg.tab_bar():
                with dpg.tab(label="控制图像"):
                    self._build_image_config()
                with dpg.tab(label="OCR文字"):
                    self._build_ocr_text_config()
                with dpg.tab(label="屏幕区域"):
                    self._build_region_config()

    def _build_image_config(self):
        dpg.add_text("控制图像用于图像匹配模式，点击上传按钮选择图片文件")
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
                color = (9, 171, 59) if os.path.exists(path) else (220, 53, 69)
                self.image_widgets[filename] = dpg.add_text(status, color=color)
                dpg.add_button(
                    label="选择文件",
                    callback=self._open_file_dialog,
                    user_data=filename,
                    width=80,
                )

    def _open_file_dialog(self, sender, app_data):
        self._upload_target = app_data
        dpg.show_item("file_dialog")

    def _on_file_dialog(self, sender, app_data):
        self._upload_target = sender

    def _on_file_selected(self, sender, app_data):
        if not app_data or not self._upload_target:
            return

        file_path = app_data.get('file_path_name', '')
        if not file_path or not os.path.exists(file_path):
            return

        target_dir = project_path('control_images')
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, self._upload_target)

        try:
            shutil.copy2(file_path, dest)
            status = "已配置"
            color = (9, 171, 59)
            dpg.set_value(self.image_widgets[self._upload_target], status)
            dpg.configure_item(self.image_widgets[self._upload_target], color=color)
            self._show_toast(f"已保存: {self._upload_target}")
        except Exception as e:
            self._show_toast(f"保存失败: {e}")

        self._upload_target = None

    def _build_ocr_text_config(self):
        dpg.add_text("OCR识别文字配置")
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
        dpg.add_text("屏幕区域配置（百分比 0.0~1.0）")
        regions = [
            ("top_bar", "私信图标区域", 0.65, 0.0, 0.25, 0.10),
            ("friend_list", "好友列表区域", 0.75, 0.10, 0.25, 0.85),
            ("chat_bottom", "发送按钮区域", 0.30, 0.85, 0.65, 0.10),
            ("chat_top", "退出会话区域", 0.70, 0.10, 0.25, 0.10),
        ]
        self.region_widgets = {}
        for key, name, x, y, w, h in regions:
            dpg.add_text(name)
            with dpg.group(horizontal=True):
                self.region_widgets[f"{key}_x"] = dpg.add_input_text(label="X", default_value=str(x), width=60)
                self.region_widgets[f"{key}_y"] = dpg.add_input_text(label="Y", default_value=str(y), width=60)
                self.region_widgets[f"{key}_w"] = dpg.add_input_text(label="宽", default_value=str(w), width=60)
                self.region_widgets[f"{key}_h"] = dpg.add_input_text(label="高", default_value=str(h), width=60)
        dpg.add_button(label="保存区域配置", callback=self._save_regions, width=120)

    def _build_monitor(self):
        with dpg.child_window():
            dpg.add_text("任务监控")
            with dpg.group(horizontal=True):
                self.proc_memory = dpg.add_text("内存: --MB")
                dpg.add_text("|")
                self.proc_cpu = dpg.add_text("CPU: --%")
            dpg.add_spacer(height=5)
            dpg.add_text("运行日志:")
            self.log_window = dpg.add_input_text(multiline=True, width=-1, height=400, readonly=True)
            with dpg.group(horizontal=True):
                dpg.add_button(label="清除日志", callback=self._clear_logs, width=100)
                dpg.add_button(label="导出日志", callback=self._export_logs, width=100)

    def _build_scheduler(self):
        with dpg.child_window():
            dpg.add_text("调度设置")
            self.scheduler_enabled_check = dpg.add_checkbox(label="启用定时调度", default_value=self.scheduler_enabled)
            self.schedule_time_input = dpg.add_input_text(label="执行时间 (HH:MM)", default_value=self.scheduled_time, width=150)
            dpg.add_button(label="保存调度设置", callback=self._save_scheduler, width=150)
            dpg.add_spacer(height=10)
            dpg.add_text("进程监控")
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
        color = (9, 171, 59) if found else (220, 53, 69)
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

    def _clear_logs(self, sender, app_data):
        dpg.set_value(self.log_window, "")

    def _export_logs(self, sender, app_data):
        self._show_toast("日志导出待实现")

    def _show_toast(self, message):
        tag = f"toast_{int(time.time())}"
        with dpg.window(label="提示", modal=False, width=300, height=100, pos=[400, 300], tag=tag):
            dpg.add_text(message)
            dpg.add_button(label="确定", width=80, callback=lambda: dpg.delete_item(tag))

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
