import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import requests

CONFIG_FILE = 'config.json'
DEFAULT_AVATAR_DIR = 'friend_avatars'
# 确保必要的目录存在
os.makedirs(DEFAULT_AVATAR_DIR, exist_ok=True)
os.makedirs('control_images', exist_ok=True)


class ConfigManager(tk.Tk):
    """
    抖音好友配置管理GUI应用程序
    提供图形界面用于配置API信息和好友列表
    """
    def __init__(self):
        super().__init__()
        self.title("抖音好友配置后台 v4.1 (全功能版)")
        self.geometry("800x600")

        # 存储好友数据和API配置
        self.friends_data = []
        self.api_key = tk.StringVar()
        self.api_host = tk.StringVar()
        self.selected_city_info = None

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        """
        创建GUI界面组件
        """
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        # 左侧框架：显示已配置的好友列表
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(left_frame, text="已配置好友列表", font=("Helvetica", 12, "bold")).pack(fill="x", pady=5)
        self.friends_listbox = tk.Listbox(left_frame, height=20)
        self.friends_listbox.pack(expand=True, fill="both")
        self.friends_listbox.bind('<<ListboxSelect>>', self.on_friend_select)

        # 右侧框架：配置区域
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True)

        # API配置区域
        api_frame = ttk.LabelFrame(right_frame, text="1. 天气API配置", padding="10")
        api_frame.pack(fill="x")
        ttk.Label(api_frame, text="API Host:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_host, width=40).grid(row=0, column=1, sticky="ew")
        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_key, width=40).grid(row=1, column=1, sticky="ew")
        api_frame.grid_columnconfigure(1, weight=1)

        # 城市ID查询区域
        city_frame = ttk.LabelFrame(right_frame, text="2. 查找城市ID", padding="10")
        city_frame.pack(fill="x", pady=10)
        ttk.Label(city_frame, text="输入城市名:").grid(row=0, column=0, padx=5)
        self.city_search_entry = ttk.Entry(city_frame, width=15)
        self.city_search_entry.grid(row=0, column=1, padx=5)
        ttk.Button(city_frame, text="查询ID", command=self.search_city_id).grid(row=0, column=2, padx=5)
        self.city_results_listbox = tk.Listbox(city_frame, height=4)
        self.city_results_listbox.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

        # 好友信息编辑区域
        info_frame = ttk.LabelFrame(right_frame, text="3. 编辑好友信息", padding="10")
        info_frame.pack(fill="both", expand=True, pady=10)
        ttk.Label(info_frame, text="好友昵称:").grid(row=0, column=0, sticky="w", pady=5)
        self.nickname_entry = ttk.Entry(info_frame)
        self.nickname_entry.grid(row=0, column=1, sticky="ew", columnspan=2)
        ttk.Label(info_frame, text="城市信息:").grid(row=1, column=0, sticky="w", pady=5)
        self.selected_city_label = ttk.Label(info_frame, text="(请先从上方查询并选择)", relief="sunken")
        self.selected_city_label.grid(row=1, column=1, sticky="ew", columnspan=2)
        # 头像关联功能
        ttk.Label(info_frame, text="头像截图:").grid(row=2, column=0, sticky="w", pady=5)
        self.avatar_path_label = ttk.Label(info_frame, text="未选择", relief="sunken")
        self.avatar_path_label.grid(row=2, column=1, sticky="ew")
        ttk.Button(info_frame, text="选择...", command=self.select_avatar).grid(row=2, column=2, sticky="e", padx=(5,0))
        info_frame.grid_columnconfigure(1, weight=1)
        
        # 操作按钮区域
        action_button_frame = ttk.Frame(info_frame)
        action_button_frame.grid(row=3, column=0, columnspan=3, pady=10)
        ttk.Button(action_button_frame, text="添加为新好友", command=self.add_friend).pack(side="left", padx=10, expand=True)
        ttk.Button(action_button_frame, text="更新选中好友", command=self.update_friend).pack(side="left", padx=10, expand=True)

        ttk.Button(right_frame, text="删除选中好友", command=self.delete_friend).pack(side="bottom", fill="x", pady=5)
        ttk.Button(right_frame, text="️ 保存所有配置并退出", command=self.save_and_quit, style="Accent.TButton").pack(side="bottom", fill="x", ipady=5)
        self.style = ttk.Style(self)
        self.style.configure("Accent.TButton", foreground="white", background="dodgerblue")

    def search_city_id(self):
        """
        查询城市ID功能
        使用和风天气API根据城市名称查询城市信息
        """
        city_name = self.city_search_entry.get()
        api_host = self.api_host.get()
        api_key = self.api_key.get()
        if not (city_name and api_host and api_key):
            messagebox.showerror("错误", "请先填写完整的API Host, API Key和要查询的城市名！")
            return
        
        self.city_results_listbox.delete(0, tk.END)
        self.selected_city_info = None

        try:
            # 根据API文档修改请求URL和参数
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
                self.city_lookup_results = data["location"]
                for i, loc in enumerate(self.city_lookup_results):
                    display_text = f"{loc['name']}, {loc['adm1']}, {loc['country']} | ID: {loc['id']}"
                    self.city_results_listbox.insert(tk.END, display_text)
                self.city_results_listbox.bind('<<ListboxSelect>>', lambda e: self.on_city_result_select())
            else:
                messagebox.showinfo("查询结果", f"未找到城市 '{city_name}'。返回码: {data.get('code')}")
        except Exception as e:
            messagebox.showerror("网络错误", f"查询城市ID时出错: {e}")

    def on_city_result_select(self):
        """
        当在城市查询结果中选择一个城市时触发
        """
        selection_indices = self.city_results_listbox.curselection()
        if not selection_indices: return
        index = selection_indices[0]
        self.selected_city_info = self.city_lookup_results[index]
        self.selected_city_label.config(text=f"{self.selected_city_info['name']} (ID: {self.selected_city_info['id']})")

    def on_friend_select(self, event):
        """
        当在好友列表中选择一个好友时触发
        将选中的好友信息加载到编辑区域
        """
        selection_indices = self.friends_listbox.curselection()
        if not selection_indices: return
        index = selection_indices[0]
        friend = self.friends_data[index]
        self.clear_entries()
        self.nickname_entry.insert(0, friend['nickname'])
        self.selected_city_label.config(text=f"{friend['city_name']} (ID: {friend['location_id']})")
        self.avatar_path_label.config(text=friend.get('avatar_image', '未选择'))
        # 为了能更新，需要把城市信息也加载回来
        self.selected_city_info = {"name": friend['city_name'], "id": friend['location_id']}

    def select_avatar(self):
        """
        选择好友头像文件
        """
        filepath = filedialog.askopenfilename(
            title="选择好友头像截图", initialdir=DEFAULT_AVATAR_DIR,
            filetypes=(("PNG files", "*.png"), ("All files", "*.*"))
        )
        if filepath:
            relative_path = os.path.relpath(filepath).replace("\\", "/")
            if ".." in relative_path:
                messagebox.showerror("路径错误", "请将头像图片保存在项目的 friend_avatars 文件夹内再选择！")
                return
            self.avatar_path_label.config(text=relative_path)
    
    def _get_info_from_form(self):
        """
        从表单中获取信息并验证
        
        :return: 昵称、头像路径和城市信息的元组，如果验证失败则返回(None, None, None)
        """
        nickname = self.nickname_entry.get()
        avatar = self.avatar_path_label.cget("text")
        city_info = self.selected_city_info
        
        if not (nickname and city_info and avatar != '未选择'):
            messagebox.showwarning("信息不完整", "请确保已填写昵称，并已查询和选择城市，以及关联了头像截图！")
            return None, None, None
        
        return nickname, avatar, city_info

    def add_friend(self):
        """
        添加新好友到配置列表
        """
        nickname, avatar, city_info = self._get_info_from_form()
        if not nickname: return
        
        new_friend = {
            "nickname": nickname,
            "city_name": city_info['name'],
            "location_id": city_info['id'],
            "avatar_image": avatar
        }
        self.friends_data.append(new_friend)
        self.refresh_friends_listbox()
        self.clear_entries()

    def update_friend(self):
        """
        更新选中的好友信息
        """
        selection_indices = self.friends_listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("未选择", "请先在左侧列表选择一个要更新的好友！")
            return
        
        nickname, avatar, city_info = self._get_info_from_form()
        if not nickname: return

        index = selection_indices[0]
        self.friends_data[index] = {
            "nickname": nickname, "city_name": city_info['name'],
            "location_id": city_info['id'], "avatar_image": avatar
        }
        self.refresh_friends_listbox()
        self.friends_listbox.selection_set(index)
        messagebox.showinfo("成功", "好友信息已更新！")

    def delete_friend(self):
        """
        删除选中的好友
        """
        selection_indices = self.friends_listbox.curselection()
        if not selection_indices:
            messagebox.showwarning("未选择", "请先在左侧列表选择一个要删除的好友！")
            return
        if messagebox.askyesno("确认删除", f"确定要删除好友 '{self.friends_data[selection_indices[0]]['nickname']}' 吗？"):
            del self.friends_data[selection_indices[0]]
            self.refresh_friends_listbox()
            self.clear_entries()

    def refresh_friends_listbox(self):
        """
        刷新好友列表显示
        根据配置文件格式兼容性要求，支持新旧两种格式显示
        """
        self.friends_listbox.delete(0, tk.END)
        for friend in self.friends_data:
            # 兼容不同版本的配置文件格式
            if 'city_name' in friend and 'location_id' in friend:
                # 新格式 (V4.1)
                display_text = f"{friend['nickname']} -> {friend['city_name']} (头像: {os.path.basename(friend.get('avatar_image', '无'))})"
            elif 'city' in friend:
                # 旧格式 (V4.0及以前)
                city_info = friend['city']
                avatar_info = os.path.basename(friend.get('avatar_image', '无')) if friend.get('avatar_image') else '无'
                display_text = f"{friend['nickname']} -> 城市ID: {city_info} (头像: {avatar_info})"
            else:
                # 未知格式
                display_text = f"{friend['nickname']} -> 格式未知"
            self.friends_listbox.insert(tk.END, display_text)
            
    def load_config(self):
        """
        加载配置文件
        """
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.api_host.set(config.get('api_host', ''))
                self.api_key.set(config.get('api_key', ''))
                self.friends_data = config.get('friends', [])
                self.refresh_friends_listbox()

    def save_and_quit(self):
        """
        保存配置并退出程序
        """
        config_data = {
            'api_host': self.api_host.get(),
            'api_key': self.api_key.get(),
            'friends': self.friends_data
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("成功", f"配置已成功保存到 {CONFIG_FILE}")
        self.destroy()

    def clear_entries(self):
        """
        清空表单输入框
        """
        self.nickname_entry.delete(0, tk.END)
        self.selected_city_label.config(text="(请先从上方查询并选择)")
        self.avatar_path_label.config(text="未选择")
        self.selected_city_info = None

if __name__ == "__main__":
    app = ConfigManager()
    app.mainloop()