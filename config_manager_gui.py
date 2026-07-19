import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import requests
from typing import Dict, List, Optional, cast

from config_utils import (
    CONFIG_PATH,
    DEFAULT_MESSAGE_TEMPLATE,
    load_config,
    normalize_config,
    save_config,
    project_path,
)

CONFIG_FILE = CONFIG_PATH
DEFAULT_AVATAR_DIR = project_path('friend_avatars')
os.makedirs(DEFAULT_AVATAR_DIR, exist_ok=True)
os.makedirs(project_path('control_images'), exist_ok=True)


class ConfigManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("抖音好友配置后台 v5.0 (OCR增强版)")
        self.geometry("900x700")

        self.friends_data: List[Dict[str, str]] = []
        self.api_key = tk.StringVar()
        self.api_host = tk.StringVar()
        self.message_template = tk.StringVar()
        self.ocr_api_key = tk.StringVar()
        self.ocr_secret_key = tk.StringVar()
        self.selected_city_info: Optional[Dict[str, str]] = None
        self.city_lookup_results: List[Dict[str, str]] = []

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(left_frame, text="已配置好友列表", font=("Helvetica", 12, "bold")).pack(fill="x", pady=5)
        self.friends_listbox = tk.Listbox(left_frame, height=20)
        self.friends_listbox.pack(expand=True, fill="both")
        self.friends_listbox.bind('<<ListboxSelect>>', self.on_friend_select)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)

        notebook = ttk.Notebook(right_frame)
        notebook.pack(fill="both", expand=True)

        weather_tab = ttk.Frame(notebook, padding="10")
        notebook.add(weather_tab, text="天气API")

        ocr_tab = ttk.Frame(notebook, padding="10")
        notebook.add(ocr_tab, text="OCR配置")

        friend_tab = ttk.Frame(notebook, padding="10")
        notebook.add(friend_tab, text="好友管理")

        api_frame = ttk.LabelFrame(weather_tab, text="天气API配置", padding="10")
        api_frame.pack(fill="x")
        ttk.Label(api_frame, text="API Host:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_host, width=30).grid(row=0, column=1, sticky="ew")
        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_key, width=30).grid(row=1, column=1, sticky="ew")
        ttk.Button(api_frame, text="测试连接", command=self.test_api_connectivity).grid(row=1, column=2, sticky="e", padx=(5,0))
        api_frame.grid_columnconfigure(1, weight=1)

        template_frame = ttk.LabelFrame(weather_tab, text="消息模板配置", padding="10")
        template_frame.pack(fill="x", pady=10)
        ttk.Label(template_frame, text="天气播报模板:").pack(anchor="w")
        self.message_template_text = tk.Text(template_frame, height=5, width=40)
        self.message_template_text.pack(fill="x", expand=True, pady=5)
        ttk.Label(template_frame, text="可用变量: {nickname}, {city_name}, {text_day}, {text_night}, {temp_max}, {temp_min}, {wind_dir}, {wind_scale}").pack(anchor="w", pady=2)
        template_frame.grid_columnconfigure(0, weight=1)

        paddle_frame = ttk.LabelFrame(ocr_tab, text="本地OCR识别 (推荐)", padding="10")
        paddle_frame.pack(fill="x")
        
        ttk.Checkbutton(paddle_frame, text="启用本地OCR识别（离线，无需API）", variable=self.use_local_ocr).grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        
        paddle_info = ttk.Label(paddle_frame, text=(
            "基于PaddleOCR的轻量级本地OCR引擎，无需网络即可使用。\n"
            "首次运行会自动下载模型（约10MB），之后完全离线工作。\n"
            "支持文字检测和边界提取，定位更精准。"
        ), wraplength=400, justify="left", foreground="green")
        paddle_info.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        
        ttk.Separator(ocr_tab, orient="horizontal").pack(fill="x", pady=10)
        
        baidu_frame = ttk.LabelFrame(ocr_tab, text="百度OCR配置 (备选)", padding="10")
        baidu_frame.pack(fill="x")
        ttk.Label(baidu_frame, text="OCR API Key:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(baidu_frame, textvariable=self.ocr_api_key, width=30).grid(row=0, column=1, sticky="ew")
        ttk.Label(baidu_frame, text="OCR Secret Key:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(baidu_frame, textvariable=self.ocr_secret_key, width=30, show="*").grid(row=1, column=1, sticky="ew")
        ttk.Button(baidu_frame, text="测试连接", command=self.test_ocr_connectivity).grid(row=1, column=2, sticky="e", padx=(5,0))
        baidu_frame.grid_columnconfigure(1, weight=1)
        
        baidu_info = ttk.Label(baidu_frame, text=(
            "当PaddleOCR不可用时，自动切换到百度OCR。\n"
            "访问 https://ai.baidu.com/tech/ocr 获取API Key（每月2000次免费）。"
        ), wraplength=400, justify="left", foreground="gray")
        baidu_info.grid(row=2, column=0, columnspan=3, sticky="w", pady=5)

        city_frame = ttk.LabelFrame(friend_tab, text="查找城市ID", padding="10")
        city_frame.pack(fill="x")
        ttk.Label(city_frame, text="输入城市名:").grid(row=0, column=0, padx=5)
        self.city_search_entry = ttk.Entry(city_frame, width=15)
        self.city_search_entry.grid(row=0, column=1, padx=5)
        ttk.Button(city_frame, text="查询ID", command=self.search_city_id).grid(row=0, column=2, padx=5)
        self.city_results_listbox = tk.Listbox(city_frame, height=4)
        self.city_results_listbox.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

        info_frame = ttk.LabelFrame(friend_tab, text="编辑好友信息", padding="10")
        info_frame.pack(fill="both", expand=True, pady=10)
        ttk.Label(info_frame, text="好友昵称:").grid(row=0, column=0, sticky="w", pady=5)
        self.nickname_entry = ttk.Entry(info_frame)
        self.nickname_entry.grid(row=0, column=1, sticky="ew", columnspan=2)
        ttk.Label(info_frame, text="城市信息:").grid(row=1, column=0, sticky="w", pady=5)
        self.selected_city_label = ttk.Label(info_frame, text="(请先从上方查询并选择)", relief="sunken")
        self.selected_city_label.grid(row=1, column=1, sticky="ew", columnspan=2)

        ttk.Label(info_frame, text="识别方式:").grid(row=2, column=0, sticky="w", pady=5)
        self.recognition_mode = tk.StringVar(value="image")
        mode_frame = ttk.Frame(info_frame)
        mode_frame.grid(row=2, column=1, sticky="ew", columnspan=2)
        ttk.Radiobutton(mode_frame, text="图像识别", variable=self.recognition_mode, value="image", command=self._on_mode_change).pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="OCR文字识别", variable=self.recognition_mode, value="text", command=self._on_mode_change).pack(side="left", padx=5)

        ttk.Label(info_frame, text="头像截图:").grid(row=3, column=0, sticky="w", pady=5)
        self.avatar_path_label = ttk.Label(info_frame, text="未选择", relief="sunken")
        self.avatar_path_label.grid(row=3, column=1, sticky="ew")
        self.avatar_select_btn = ttk.Button(info_frame, text="选择...", command=self.select_avatar)
        self.avatar_select_btn.grid(row=3, column=2, sticky="e", padx=(5,0))

        ttk.Label(info_frame, text="OCR文字:").grid(row=4, column=0, sticky="w", pady=5)
        self.avatar_text_entry = ttk.Entry(info_frame, width=30)
        self.avatar_text_entry.grid(row=4, column=1, sticky="ew", columnspan=2)
        ttk.Label(info_frame, text="(OCR模式下，在好友列表中识别的文字，如好友昵称)", foreground="gray").grid(row=5, column=1, sticky="w", columnspan=2)

        info_frame.grid_columnconfigure(1, weight=1)

        action_button_frame = ttk.Frame(info_frame)
        action_button_frame.grid(row=6, column=0, columnspan=3, pady=10)
        ttk.Button(action_button_frame, text="添加为新好友", command=self.add_friend).pack(side="left", padx=10, expand=True)
        ttk.Button(action_button_frame, text="更新选中好友", command=self.update_friend).pack(side="left", padx=10, expand=True)

        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.pack(side="bottom", fill="x", pady=5)
        ttk.Button(bottom_frame, text="删除选中好友", command=self.delete_friend).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(bottom_frame, text="️ 保存所有配置并退出", command=self.save_and_quit, style="Accent.TButton").pack(side="right", fill="x", expand=True, ipady=5)
        self.style = ttk.Style(self)
        self.style.configure("Accent.TButton", foreground="white", background="dodgerblue")

    def _on_mode_change(self):
        mode = self.recognition_mode.get()
        if mode == "image":
            self.avatar_select_btn.config(state="normal")
            self.avatar_text_entry.config(state="disabled")
        else:
            self.avatar_select_btn.config(state="disabled")
            self.avatar_text_entry.config(state="normal")

    def test_api_connectivity(self):
        api_host = self.api_host.get()
        api_key = self.api_key.get()

        if not (api_host and api_key):
            messagebox.showwarning("信息不完整", "请先填写API Host和API Key！")
            return

        messagebox.showinfo("测试连接", "正在尝试连接和风天气API，请稍候...")
        try:
            test_location_id = "101010100"
            test_url = f"https://{api_host}/v7/weather/now?location={test_location_id}&key={api_key}"
            response = requests.get(test_url, timeout=5)
            response.raise_for_status()

            data = response.json()
            if data.get("code") == "200":
                messagebox.showinfo("测试成功", "和风天气API连接成功！")
            else:
                messagebox.showerror("测试失败", f"API返回错误码: {data.get('code')}。\n请检查API Key和Host是否正确。")
        except requests.exceptions.Timeout:
            messagebox.showerror("测试失败", "连接超时，请检查网络或API Host是否可达。")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("测试失败", f"连接和风天气API时发生错误: {e}\n请检查API Host是否正确，以及网络连接。")

    def test_ocr_connectivity(self):
        api_key = self.ocr_api_key.get()
        secret_key = self.ocr_secret_key.get()

        if not (api_key and secret_key):
            messagebox.showwarning("信息不完整", "请先填写OCR API Key和Secret Key！")
            return

        messagebox.showinfo("测试连接", "正在尝试连接百度OCR API，请稍候...")
        try:
            token_url = "https://aip.baidubce.com/oauth/2.0/token"
            params = {
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret_key,
            }
            response = requests.post(token_url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()
            if "access_token" in data:
                messagebox.showinfo("测试成功", "百度OCR API连接成功！")
            else:
                messagebox.showerror("测试失败", f"获取Token失败: {data.get('error_description', 'unknown')}")
        except requests.exceptions.Timeout:
            messagebox.showerror("测试失败", "连接超时，请检查网络连接。")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("测试失败", f"连接百度OCR API时发生错误: {e}")

    def search_city_id(self):
        city_name = self.city_search_entry.get()
        api_host = self.api_host.get()
        api_key = self.api_key.get()
        if not (city_name and api_host and api_key):
            messagebox.showerror("错误", "请先填写完整的API Host, API Key和要查询的城市名！")
            return
        
        self.city_results_listbox.delete(0, tk.END)
        self.selected_city_info = None

        try:
            geo_url = f"https://{api_host}/geo/v2/city/lookup"
            params = {
                'location': city_name,
                'key': api_key,
                'lang': 'zh'
            }
            response = requests.get(geo_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == "200" and data.get("location"):
                self.city_lookup_results = cast(List[Dict[str, str]], data["location"])
                for i, loc in enumerate(self.city_lookup_results):
                    display_text = f"{loc['name']}, {loc['adm1']}, {loc['country']} | ID: {loc['id']}"
                    self.city_results_listbox.insert(tk.END, display_text)
                self.city_results_listbox.bind('<<ListboxSelect>>', lambda e: self.on_city_result_select())
            else:
                messagebox.showinfo("查询结果", f"未找到城市 '{city_name}'。返回码: {data.get('code')}")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("网络错误", f"查询城市ID时出错: {e}")

    def on_city_result_select(self):
        index = self._selected_index(self.city_results_listbox)
        if index is None:
            return
        self.selected_city_info = self.city_lookup_results[index]
        self.selected_city_label.config(text=f"{self.selected_city_info['name']} (ID: {self.selected_city_info['id']})")

    def on_friend_select(self, event):
        index = self._selected_index(self.friends_listbox)
        if index is None:
            return
        friend = self.friends_data[index]
        self.clear_entries()
        self.nickname_entry.insert(0, friend['nickname'])
        self.selected_city_label.config(text=f"{friend['city_name']} (ID: {friend['location_id']})")

        if friend.get('avatar_text'):
            self.recognition_mode.set("text")
            self.avatar_text_entry.insert(0, friend['avatar_text'])
        elif friend.get('avatar_image'):
            self.recognition_mode.set("image")
            self.avatar_path_label.config(text=friend['avatar_image'])

        self._on_mode_change()
        self.selected_city_info = {"name": friend['city_name'], "id": friend['location_id']}

    def select_avatar(self):
        filepath = filedialog.askopenfilename(
            title="选择好友头像截图", initialdir=DEFAULT_AVATAR_DIR,
            filetypes=(("PNG files", "*.png"), ("All files", "*.*"))
        )
        if filepath:
            absolute_path = os.path.abspath(filepath)
            avatar_root = os.path.abspath(DEFAULT_AVATAR_DIR)

            if os.path.commonpath([absolute_path, avatar_root]) != avatar_root:
                messagebox.showerror("路径错误", "请将头像图片保存在项目的 friend_avatars 文件夹内再选择！")
                return
            relative_path = os.path.relpath(absolute_path, project_path()).replace("\\", "/")
            self.avatar_path_label.config(text=relative_path)
    
    def _get_info_from_form(self):
        nickname = self.nickname_entry.get()
        avatar = self.avatar_path_label.cget("text")
        avatar_text = self.avatar_text_entry.get()
        city_info = self.selected_city_info
        mode = self.recognition_mode.get()
        
        if not nickname or not city_info:
            messagebox.showwarning("信息不完整", "请确保已填写昵称，并已查询和选择城市！")
            return None, None, None, None
        
        if mode == "image" and avatar == '未选择':
            messagebox.showwarning("信息不完整", "图像识别模式下，请选择好友头像截图！")
            return None, None, None, None
        
        if mode == "text" and not avatar_text.strip():
            messagebox.showwarning("信息不完整", "OCR文字识别模式下，请输入好友在列表中显示的文字！")
            return None, None, None, None
        
        return nickname, avatar, city_info, avatar_text

    def add_friend(self):
        nickname, avatar, city_info, avatar_text = self._get_info_from_form()
        if not nickname: return
        
        if any(friend.get('nickname') == nickname for friend in self.friends_data):
            messagebox.showwarning("重复昵称", f"已存在昵称为 '{nickname}' 的好友，请使用\u201c更新选中好友\u201d或改名后再添加。")
            return

        new_friend = {
            "nickname": nickname,
            "city_name": city_info['name'],
            "location_id": city_info['id'],
            "avatar_image": avatar if self.recognition_mode.get() == "image" else "",
            "avatar_text": avatar_text if self.recognition_mode.get() == "text" else ""
        }
        self.friends_data.append(new_friend)
        self.refresh_friends_listbox()
        self.clear_entries()

    def update_friend(self):
        index = self._selected_index(self.friends_listbox)
        if index is None:
            messagebox.showwarning("未选择", "请先在左侧列表选择一个要更新的好友！")
            return
        
        nickname, avatar, city_info, avatar_text = self._get_info_from_form()
        if not nickname: return

        self.friends_data[index] = {
            "nickname": nickname, "city_name": city_info['name'],
            "location_id": city_info['id'],
            "avatar_image": avatar if self.recognition_mode.get() == "image" else "",
            "avatar_text": avatar_text if self.recognition_mode.get() == "text" else ""
        }
        self.refresh_friends_listbox()
        self.friends_listbox.selection_set(index)
        messagebox.showinfo("成功", "好友信息已更新！")

    def delete_friend(self):
        index = self._selected_index(self.friends_listbox)
        if index is None:
            messagebox.showwarning("未选择", "请先在左侧列表选择一个要删除的好友！")
            return
        if messagebox.askyesno("确认删除", f"确定要删除好友 '{self.friends_data[index]['nickname']}' 吗？"):
            del self.friends_data[index]
            self.refresh_friends_listbox()
            self.clear_entries()

    def refresh_friends_listbox(self):
        self.friends_listbox.delete(0, tk.END)
        for friend in self.friends_data:
            nickname = friend['nickname']
            city_name = friend.get('city_name', '未知')
            
            if friend.get('avatar_text'):
                display_text = f"{nickname} -> {city_name} [OCR: {friend['avatar_text']}]"
            elif friend.get('avatar_image'):
                display_text = f"{nickname} -> {city_name} [头像: {os.path.basename(friend['avatar_image'])}]"
            else:
                display_text = f"{nickname} -> {city_name} [未配置识别方式]"
            
            self.friends_listbox.insert(tk.END, display_text)
            
    def load_config(self):
        try:
            raw_config = load_config(CONFIG_FILE)
        except ValueError as e:
            messagebox.showerror("配置文件错误", f"读取配置失败：{e}\n将使用空配置启动。")
            raw_config = {}

        config, warnings = normalize_config(raw_config)
        if warnings:
            messagebox.showwarning("配置兼容提示", "\n".join(warnings))

        self.api_host.set(config.get('api_host', ''))
        self.api_key.set(config.get('api_key', ''))
        self.message_template.set(config.get('message_template', ''))
        self.use_local_ocr.set(config.get('use_local_ocr', True))
        self.ocr_api_key.set(config.get('ocr_api_key', ''))
        self.ocr_secret_key.set(config.get('ocr_secret_key', ''))
        self.friends_data = cast(List[Dict[str, str]], config.get('friends', []))
        self.refresh_friends_listbox()

        if not self.message_template.get():
            self.message_template.set(DEFAULT_MESSAGE_TEMPLATE)
        self.message_template_text.delete(1.0, tk.END)
        self.message_template_text.insert(tk.END, self.message_template.get())

    def save_and_quit(self):
        api_host = self.api_host.get().strip()
        if not api_host:
            messagebox.showwarning("信息不完整", "请先填写 API Host。")
            return

        if not self.friends_data:
            if not messagebox.askyesno("好友列表为空", "当前没有配置任何好友，仍要保存并退出吗？"):
                return

        config_data = {
            'api_host': api_host,
            'api_key': self.api_key.get().strip(),
            'message_template': self.message_template_text.get(1.0, tk.END).strip(),
            'use_local_ocr': self.use_local_ocr.get(),
            'ocr_api_key': self.ocr_api_key.get().strip(),
            'ocr_secret_key': self.ocr_secret_key.get().strip(),
            'friends': self.friends_data
        }

        try:
            save_config(config_data, CONFIG_FILE)
        except OSError as e:
            messagebox.showerror("保存失败", f"写入配置文件失败: {e}")
            return

        messagebox.showinfo("成功", f"配置已成功保存到 {CONFIG_FILE}")
        self.destroy()

    def clear_entries(self):
        self.nickname_entry.delete(0, tk.END)
        self.selected_city_label.config(text="(请先从上方查询并选择)")
        self.avatar_path_label.config(text="未选择")
        self.avatar_text_entry.delete(0, tk.END)
        self.recognition_mode.set("image")
        self._on_mode_change()
        self.selected_city_info = None

    def _selected_index(self, listbox: tk.Listbox) -> Optional[int]:
        selection = listbox.curselection()
        if not selection:
            return None
        return int(selection[0])

if __name__ == "__main__":
    app = ConfigManager()
    app.mainloop()
