import os
import requests
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QTabWidget, QGroupBox,
    QRadioButton, QCheckBox, QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, Signal

from config_utils import (
    CONFIG_PATH, DEFAULT_MESSAGE_TEMPLATE,
    load_config, normalize_config, save_config, project_path
)


DEFAULT_AVATAR_DIR = project_path('friend_avatars')
os.makedirs(DEFAULT_AVATAR_DIR, exist_ok=True)
os.makedirs(project_path('control_images'), exist_ok=True)


class ConfigPage(QWidget):
    config_saved = Signal()

    def __init__(self):
        super().__init__()
        self.friends_data: List[Dict[str, str]] = []
        self.selected_city_info: Optional[Dict[str, str]] = None
        self.city_lookup_results: List[Dict[str, str]] = []
        self.use_local_ocr = None

        self._build_ui()
        self._load_config()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        title = QLabel("配置管理")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        subtitle = QLabel("管理天气API、OCR配置和好友信息")
        subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 8px;")
        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        content = QHBoxLayout()
        content.setSpacing(16)

        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(8)

        left_title = QLabel("已配置好友列表")
        left_title.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 14px;")
        left_layout.addWidget(left_title)

        self.friends_listbox = QListWidget()
        self.friends_listbox.setMinimumWidth(260)
        self.friends_listbox.currentRowChanged.connect(self._on_friend_select)
        left_layout.addWidget(self.friends_listbox, 1)

        del_btn = QPushButton("🗑 删除选中好友")
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #fef0f0;
                color: #e74c3c;
                border: 1px solid #fbc4c4;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #fde2e2;
            }
        """)
        del_btn.clicked.connect(self._delete_friend)
        left_layout.addWidget(del_btn)

        content.addWidget(left_panel)

        right_panel = QTabWidget()
        right_panel.setDocumentMode(True)

        weather_tab = QWidget()
        right_panel.addTab(weather_tab, "🌤 天气API")
        self._build_weather_tab(weather_tab)

        ocr_tab = QWidget()
        right_panel.addTab(ocr_tab, "🔍 OCR配置")
        self._build_ocr_tab(ocr_tab)

        friend_tab = QWidget()
        right_panel.addTab(friend_tab, "👥 好友管理")
        self._build_friend_tab(friend_tab)

        content.addWidget(right_panel, 1)

        main_layout.addLayout(content, 1)

        bottom_bar = QFrame()
        bottom_bar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 12px 16px;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        tip = QLabel("💡 修改后记得点击保存按钮")
        tip.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        bottom_layout.addWidget(tip)
        bottom_layout.addStretch()

        save_btn = QPushButton("💾 保存所有配置")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: 1px solid #1abc9c;
                border-radius: 5px;
                padding: 10px 28px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #16a085;
                border-color: #16a085;
            }
        """)
        save_btn.clicked.connect(self._save_config)
        bottom_layout.addWidget(save_btn)

        main_layout.addWidget(bottom_bar)

    def _build_weather_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        api_group = QGroupBox("天气API配置")
        api_layout = QVBoxLayout(api_group)
        api_layout.setSpacing(10)

        host_row = QHBoxLayout()
        host_label = QLabel("API Host:")
        host_label.setFixedWidth(90)
        self.api_host_edit = QLineEdit()
        self.api_host_edit.setPlaceholderText("例如：devapi.qweather.com")
        host_row.addWidget(host_label)
        host_row.addWidget(self.api_host_edit, 1)
        api_layout.addLayout(host_row)

        key_row = QHBoxLayout()
        key_label = QLabel("API Key:")
        key_label.setFixedWidth(90)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("输入和风天气API Key")
        key_row.addWidget(key_label)
        key_row.addWidget(self.api_key_edit, 1)
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_api)
        key_row.addWidget(test_btn)
        api_layout.addLayout(key_row)

        layout.addWidget(api_group)

        tmpl_group = QGroupBox("消息模板配置")
        tmpl_layout = QVBoxLayout(tmpl_group)
        tmpl_layout.setSpacing(8)

        tmpl_label = QLabel("天气播报模板:")
        tmpl_layout.addWidget(tmpl_label)

        self.message_template_edit = QTextEdit()
        self.message_template_edit.setFixedHeight(100)
        self.message_template_edit.setPlaceholderText("输入消息模板，支持变量...")
        tmpl_layout.addWidget(self.message_template_edit)

        vars_label = QLabel(
            "可用变量: {nickname}, {city_name}, {text_day}, {text_night}, "
            "{temp_max}, {temp_min}, {wind_dir}, {wind_scale}"
        )
        vars_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        vars_label.setWordWrap(True)
        tmpl_layout.addWidget(vars_label)

        layout.addWidget(tmpl_group)
        layout.addStretch()

    def _build_ocr_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        local_group = QGroupBox("💚 本地OCR识别（推荐）")
        local_layout = QVBoxLayout(local_group)
        local_layout.setSpacing(8)

        self.use_local_ocr = QCheckBox("启用本地OCR识别（离线，无需API）")
        self.use_local_ocr.setChecked(True)
        local_layout.addWidget(self.use_local_ocr)

        local_info = QLabel(
            "基于PaddleOCR的轻量级本地OCR引擎，无需网络即可使用。\n"
            "首次运行会自动下载模型（约10MB），之后完全离线工作。\n"
            "支持文字检测和边界提取，定位更精准。"
        )
        local_info.setStyleSheet("color: #27ae60; font-size: 12px; line-height: 1.6;")
        local_info.setWordWrap(True)
        local_layout.addWidget(local_info)

        layout.addWidget(local_group)

        baidu_group = QGroupBox("🟡 百度OCR配置（备选）")
        baidu_layout = QVBoxLayout(baidu_group)
        baidu_layout.setSpacing(10)

        baidu_key_row = QHBoxLayout()
        baidu_key_label = QLabel("OCR API Key:")
        baidu_key_label.setFixedWidth(110)
        self.ocr_api_key_edit = QLineEdit()
        baidu_key_row.addWidget(baidu_key_label)
        baidu_key_row.addWidget(self.ocr_api_key_edit, 1)
        baidu_layout.addLayout(baidu_key_row)

        baidu_secret_row = QHBoxLayout()
        baidu_secret_label = QLabel("OCR Secret Key:")
        baidu_secret_label.setFixedWidth(110)
        self.ocr_secret_key_edit = QLineEdit()
        self.ocr_secret_key_edit.setEchoMode(QLineEdit.Password)
        baidu_secret_row.addWidget(baidu_secret_label)
        baidu_secret_row.addWidget(self.ocr_secret_key_edit, 1)
        test_ocr_btn = QPushButton("测试连接")
        test_ocr_btn.clicked.connect(self._test_ocr)
        baidu_secret_row.addWidget(test_ocr_btn)
        baidu_layout.addLayout(baidu_secret_row)

        baidu_info = QLabel(
            "当PaddleOCR不可用时，自动切换到百度OCR。\n"
            "访问 https://ai.baidu.com/tech/ocr 获取API Key（每月2000次免费）。"
        )
        baidu_info.setStyleSheet("color: #7f8c8d; font-size: 12px; line-height: 1.6;")
        baidu_info.setWordWrap(True)
        baidu_layout.addWidget(baidu_info)

        layout.addWidget(baidu_group)
        layout.addStretch()

    def _build_friend_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        city_group = QGroupBox("🔍 查找城市ID")
        city_layout = QVBoxLayout(city_group)
        city_layout.setSpacing(8)

        city_row = QHBoxLayout()
        city_label = QLabel("输入城市名:")
        self.city_search_edit = QLineEdit()
        self.city_search_edit.setPlaceholderText("如：北京、上海、广州")
        search_btn = QPushButton("查询ID")
        search_btn.clicked.connect(self._search_city_id)
        city_row.addWidget(city_label)
        city_row.addWidget(self.city_search_edit, 1)
        city_row.addWidget(search_btn)
        city_layout.addLayout(city_row)

        self.city_results_list = QListWidget()
        self.city_results_list.setFixedHeight(100)
        self.city_results_list.currentRowChanged.connect(self._on_city_result_select)
        city_layout.addWidget(self.city_results_list)

        layout.addWidget(city_group)

        info_group = QGroupBox("✏️ 编辑好友信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        nick_row = QHBoxLayout()
        nick_label = QLabel("好友昵称:")
        nick_label.setFixedWidth(100)
        self.nickname_edit = QLineEdit()
        nick_row.addWidget(nick_label)
        nick_row.addWidget(self.nickname_edit, 1)
        info_layout.addLayout(nick_row)

        city_sel_row = QHBoxLayout()
        city_sel_label = QLabel("城市信息:")
        city_sel_label.setFixedWidth(100)
        self.selected_city_label = QLabel("(请先从上方查询并选择)")
        self.selected_city_label.setStyleSheet("""
            QLabel {
                background-color: #f5f7fa;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 7px 10px;
                color: #909399;
            }
        """)
        city_sel_row.addWidget(city_sel_label)
        city_sel_row.addWidget(self.selected_city_label, 1)
        info_layout.addLayout(city_sel_row)

        mode_row = QHBoxLayout()
        mode_label = QLabel("识别方式:")
        mode_label.setFixedWidth(100)
        self.mode_image = QRadioButton("图像识别")
        self.mode_text = QRadioButton("OCR文字识别")
        self.mode_image.setChecked(True)
        self.mode_image.toggled.connect(self._on_mode_change)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_image)
        mode_row.addWidget(self.mode_text)
        mode_row.addStretch()
        info_layout.addLayout(mode_row)

        avatar_row = QHBoxLayout()
        avatar_label = QLabel("头像截图:")
        avatar_label.setFixedWidth(100)
        self.avatar_path_label = QLabel("未选择")
        self.avatar_path_label.setStyleSheet("""
            QLabel {
                background-color: #f5f7fa;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 7px 10px;
                color: #909399;
            }
        """)
        self.avatar_select_btn = QPushButton("选择...")
        self.avatar_select_btn.clicked.connect(self._select_avatar)
        avatar_row.addWidget(avatar_label)
        avatar_row.addWidget(self.avatar_path_label, 1)
        avatar_row.addWidget(self.avatar_select_btn)
        info_layout.addLayout(avatar_row)

        text_row = QHBoxLayout()
        text_label = QLabel("OCR文字:")
        text_label.setFixedWidth(100)
        self.avatar_text_edit = QLineEdit()
        self.avatar_text_edit.setPlaceholderText("好友在列表中显示的文字")
        text_row.addWidget(text_label)
        text_row.addWidget(self.avatar_text_edit, 1)
        info_layout.addLayout(text_row)

        text_tip = QLabel("(OCR模式下，在好友列表中识别的文字，如好友昵称)")
        text_tip.setStyleSheet("color: #909399; font-size: 12px; margin-left: 100px;")
        info_layout.addWidget(text_tip)

        action_row = QHBoxLayout()
        action_row.addStretch()
        add_btn = QPushButton("➕ 添加为新好友")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: 1px solid #1abc9c;
                border-radius: 5px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
        """)
        add_btn.clicked.connect(self._add_friend)
        update_btn = QPushButton("✏️ 更新选中好友")
        update_btn.clicked.connect(self._update_friend)
        action_row.addWidget(add_btn)
        action_row.addWidget(update_btn)
        info_layout.addLayout(action_row)

        layout.addWidget(info_group)
        layout.addStretch()

        self._on_mode_change()

    def _on_mode_change(self):
        is_image = self.mode_image.isChecked()
        self.avatar_select_btn.setEnabled(is_image)
        self.avatar_text_edit.setEnabled(not is_image)

    def _test_api(self):
        api_host = self.api_host_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        if not (api_host and api_key):
            QMessageBox.warning(self, "信息不完整", "请先填写API Host和API Key！")
            return

        try:
            test_location_id = "101010100"
            test_url = f"https://{api_host}/v7/weather/now?location={test_location_id}&key={api_key}"
            response = requests.get(test_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("code") == "200":
                QMessageBox.information(self, "测试成功", "和风天气API连接成功！")
            else:
                QMessageBox.critical(self, "测试失败",
                    f"API返回错误码: {data.get('code')}。\n请检查API Key和Host是否正确。")
        except requests.exceptions.Timeout:
            QMessageBox.critical(self, "测试失败", "连接超时，请检查网络或API Host是否可达。")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "测试失败",
                f"连接和风天气API时发生错误: {e}\n请检查API Host是否正确，以及网络连接。")

    def _test_ocr(self):
        api_key = self.ocr_api_key_edit.text().strip()
        secret_key = self.ocr_secret_key_edit.text().strip()
        if not (api_key and secret_key):
            QMessageBox.warning(self, "信息不完整", "请先填写OCR API Key和Secret Key！")
            return

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
                QMessageBox.information(self, "测试成功", "百度OCR API连接成功！")
            else:
                QMessageBox.critical(self, "测试失败",
                    f"获取Token失败: {data.get('error_description', 'unknown')}")
        except requests.exceptions.Timeout:
            QMessageBox.critical(self, "测试失败", "连接超时，请检查网络连接。")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "测试失败", f"连接百度OCR API时发生错误: {e}")

    def _search_city_id(self):
        city_name = self.city_search_edit.text().strip()
        api_host = self.api_host_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        if not (city_name and api_host and api_key):
            QMessageBox.critical(self, "错误", "请先填写完整的API Host, API Key和要查询的城市名！")
            return

        self.city_results_list.clear()
        self.selected_city_info = None

        try:
            geo_url = f"https://{api_host}/geo/v2/city/lookup"
            params = {'location': city_name, 'key': api_key, 'lang': 'zh'}
            response = requests.get(geo_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            if data.get("code") == "200" and data.get("location"):
                self.city_lookup_results = data["location"]
                for loc in self.city_lookup_results:
                    display_text = f"{loc['name']}, {loc['adm1']}, {loc['country']} | ID: {loc['id']}"
                    self.city_results_list.addItem(display_text)
            else:
                QMessageBox.information(self, "查询结果",
                    f"未找到城市 '{city_name}'。返回码: {data.get('code')}")
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "网络错误", f"查询城市ID时出错: {e}")

    def _on_city_result_select(self, index):
        if index < 0 or index >= len(self.city_lookup_results):
            return
        self.selected_city_info = self.city_lookup_results[index]
        self.selected_city_label.setText(f"{self.selected_city_info['name']} (ID: {self.selected_city_info['id']})")
        self.selected_city_label.setStyleSheet("""
            QLabel {
                background-color: #e8f5e9;
                border: 1px solid #a5d6a7;
                border-radius: 4px;
                padding: 7px 10px;
                color: #2e7d32;
                font-weight: bold;
            }
        """)

    def _on_friend_select(self, index):
        if index < 0 or index >= len(self.friends_data):
            return
        friend = self.friends_data[index]
        self._clear_entries()
        self.nickname_edit.setText(friend['nickname'])
        self.selected_city_label.setText(f"{friend['city_name']} (ID: {friend['location_id']})")
        self.selected_city_label.setStyleSheet("""
            QLabel {
                background-color: #e8f5e9;
                border: 1px solid #a5d6a7;
                border-radius: 4px;
                padding: 7px 10px;
                color: #2e7d32;
                font-weight: bold;
            }
        """)

        if friend.get('avatar_text'):
            self.mode_text.setChecked(True)
            self.avatar_text_edit.setText(friend['avatar_text'])
        elif friend.get('avatar_image'):
            self.mode_image.setChecked(True)
            self.avatar_path_label.setText(friend['avatar_image'])
            self.avatar_path_label.setStyleSheet("""
                QLabel {
                    background-color: #f5f7fa;
                    border: 1px solid #dcdfe6;
                    border-radius: 4px;
                    padding: 7px 10px;
                    color: #2c3e50;
                }
            """)

        self._on_mode_change()
        self.selected_city_info = {"name": friend['city_name'], "id": friend['location_id']}

    def _select_avatar(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择好友头像截图", DEFAULT_AVATAR_DIR,
            "PNG files (*.png);;All files (*.*)"
        )
        if filepath:
            absolute_path = os.path.abspath(filepath)
            avatar_root = os.path.abspath(DEFAULT_AVATAR_DIR)
            if os.path.commonpath([absolute_path, avatar_root]) != avatar_root:
                QMessageBox.critical(self, "路径错误",
                    "请将头像图片保存在项目的 friend_avatars 文件夹内再选择！")
                return
            relative_path = os.path.relpath(absolute_path, project_path()).replace("\\", "/")
            self.avatar_path_label.setText(relative_path)
            self.avatar_path_label.setStyleSheet("""
                QLabel {
                    background-color: #f5f7fa;
                    border: 1px solid #dcdfe6;
                    border-radius: 4px;
                    padding: 7px 10px;
                    color: #2c3e50;
                }
            """)

    def _get_info_from_form(self):
        nickname = self.nickname_edit.text().strip()
        avatar = self.avatar_path_label.text()
        avatar_text = self.avatar_text_edit.text().strip()
        city_info = self.selected_city_info
        mode = "image" if self.mode_image.isChecked() else "text"

        if not nickname or not city_info:
            QMessageBox.warning(self, "信息不完整", "请确保已填写昵称，并已查询和选择城市！")
            return None, None, None, None

        if mode == "image" and avatar == '未选择':
            QMessageBox.warning(self, "信息不完整", "图像识别模式下，请选择好友头像截图！")
            return None, None, None, None

        if mode == "text" and not avatar_text:
            QMessageBox.warning(self, "信息不完整", "OCR文字识别模式下，请输入好友在列表中显示的文字！")
            return None, None, None, None

        return nickname, avatar, city_info, avatar_text

    def _add_friend(self):
        nickname, avatar, city_info, avatar_text = self._get_info_from_form()
        if not nickname:
            return

        if any(friend.get('nickname') == nickname for friend in self.friends_data):
            QMessageBox.warning(self, "重复昵称",
                f"已存在昵称为 '{nickname}' 的好友，请使用\"更新选中好友\"或改名后再添加。")
            return

        mode = "image" if self.mode_image.isChecked() else "text"
        new_friend = {
            "nickname": nickname,
            "city_name": city_info['name'],
            "location_id": city_info['id'],
            "avatar_image": avatar if mode == "image" else "",
            "avatar_text": avatar_text if mode == "text" else ""
        }
        self.friends_data.append(new_friend)
        self._refresh_friends_listbox()
        self._clear_entries()
        QMessageBox.information(self, "成功", f"好友 '{nickname}' 已添加！")

    def _update_friend(self):
        index = self.friends_listbox.currentRow()
        if index < 0:
            QMessageBox.warning(self, "未选择", "请先在左侧列表选择一个要更新的好友！")
            return

        nickname, avatar, city_info, avatar_text = self._get_info_from_form()
        if not nickname:
            return

        mode = "image" if self.mode_image.isChecked() else "text"
        self.friends_data[index] = {
            "nickname": nickname, "city_name": city_info['name'],
            "location_id": city_info['id'],
            "avatar_image": avatar if mode == "image" else "",
            "avatar_text": avatar_text if mode == "text" else ""
        }
        self._refresh_friends_listbox()
        self.friends_listbox.setCurrentRow(index)
        QMessageBox.information(self, "成功", "好友信息已更新！")

    def _delete_friend(self):
        index = self.friends_listbox.currentRow()
        if index < 0:
            QMessageBox.warning(self, "未选择", "请先在左侧列表选择一个要删除的好友！")
            return
        reply = QMessageBox.question(self, "确认删除",
            f"确定要删除好友 '{self.friends_data[index]['nickname']}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.friends_data[index]
            self._refresh_friends_listbox()
            self._clear_entries()

    def _refresh_friends_listbox(self):
        self.friends_listbox.clear()
        for friend in self.friends_data:
            nickname = friend['nickname']
            city_name = friend.get('city_name', '未知')
            if friend.get('avatar_text'):
                display_text = f"{nickname} → {city_name} [OCR: {friend['avatar_text']}]"
            elif friend.get('avatar_image'):
                display_text = f"{nickname} → {city_name} [头像: {os.path.basename(friend['avatar_image'])}]"
            else:
                display_text = f"{nickname} → {city_name} [未配置]"
            self.friends_listbox.addItem(display_text)

    def _load_config(self):
        try:
            raw_config = load_config(CONFIG_PATH)
        except ValueError as e:
            QMessageBox.critical(self, "配置文件错误",
                f"读取配置失败：{e}\n将使用空配置启动。")
            raw_config = {}

        config, warnings = normalize_config(raw_config)
        if warnings:
            QMessageBox.warning(self, "配置兼容提示", "\n".join(warnings))

        self.api_host_edit.setText(config.get('api_host', ''))
        self.api_key_edit.setText(config.get('api_key', ''))
        self.use_local_ocr.setChecked(config.get('use_local_ocr', True))
        self.ocr_api_key_edit.setText(config.get('ocr_api_key', ''))
        self.ocr_secret_key_edit.setText(config.get('ocr_secret_key', ''))
        self.friends_data = config.get('friends', [])
        self._refresh_friends_listbox()

        template = config.get('message_template', '') or DEFAULT_MESSAGE_TEMPLATE
        self.message_template_edit.setPlainText(template)

    def _clear_entries(self):
        self.nickname_edit.clear()
        self.selected_city_label.setText("(请先从上方查询并选择)")
        self.selected_city_label.setStyleSheet("""
            QLabel {
                background-color: #f5f7fa;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 7px 10px;
                color: #909399;
            }
        """)
        self.avatar_path_label.setText("未选择")
        self.avatar_path_label.setStyleSheet("""
            QLabel {
                background-color: #f5f7fa;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                padding: 7px 10px;
                color: #909399;
            }
        """)
        self.avatar_text_edit.clear()
        self.mode_image.setChecked(True)
        self._on_mode_change()
        self.selected_city_info = None

    def _save_config(self):
        api_host = self.api_host_edit.text().strip()
        if not api_host:
            QMessageBox.warning(self, "信息不完整", "请先填写 API Host。")
            return

        if not self.friends_data:
            reply = QMessageBox.question(self, "好友列表为空",
                "当前没有配置任何好友，仍要保存吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        config_data = {
            'api_host': api_host,
            'api_key': self.api_key_edit.text().strip(),
            'message_template': self.message_template_edit.toPlainText().strip(),
            'use_local_ocr': self.use_local_ocr.isChecked(),
            'ocr_api_key': self.ocr_api_key_edit.text().strip(),
            'ocr_secret_key': self.ocr_secret_key_edit.text().strip(),
            'friends': self.friends_data
        }

        try:
            save_config(config_data, CONFIG_PATH)
        except OSError as e:
            QMessageBox.critical(self, "保存失败", f"写入配置文件失败: {e}")
            return

        QMessageBox.information(self, "成功", f"配置已成功保存到 {CONFIG_PATH}")
        self.config_saved.emit()
