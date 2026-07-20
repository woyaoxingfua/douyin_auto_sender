import os
import json
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QMessageBox, QFrame, QScrollArea,
    QTabWidget, QListWidget, QListWidgetItem, QFileDialog,
    QGridLayout, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
import pyautogui

from config_utils import project_path

CONTROL_IMAGES_DIR = project_path('control_images')

DEFAULT_REGIONS = {
    "top_bar": {"x_pct": 0.70, "y_pct": 0.0, "w_pct": 0.15, "h_pct": 0.12},
    "friend_list": {"x_pct": 0.75, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.85},
    "chat_bottom": {"x_pct": 0.30, "y_pct": 0.85, "w_pct": 0.65, "h_pct": 0.10},
    "chat_top": {"x_pct": 0.70, "y_pct": 0.10, "w_pct": 0.25, "h_pct": 0.10},
}

CONTROL_IMAGE_ITEMS = [
    ("douyin_sixin_icon.png", "私信图标", "抖音右上角「消息」/「私信」按钮的截图"),
    ("douyin_send_button.png", "发送按钮", "聊天窗口底部「发送」按钮的截图"),
    ("douyin_exit_chat_button.png", "退出会话", "聊天窗口顶部「退出会话」按钮的截图"),
    ("douyin_scroll_bar.png", "滚动条", "好友列表滚动条的截图（可选）"),
]

OCR_TEXT_ITEMS = [
    ("ocr_text_sixin", "私信/消息", "点击进入私信列表的文字", "消息"),
    ("ocr_text_send", "发送", "发送消息按钮上的文字", "发送"),
    ("ocr_text_exit", "退出会话", "退出聊天按钮上的文字", "退出会话"),
]


class UIConfigPage(QWidget):
    config_saved = Signal()

    def __init__(self):
        super().__init__()
        self.region_edits = {}
        self.image_labels = {}
        self.ocr_edits = {}
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("抖音界面配置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        subtitle = QLabel("管理控制图像、OCR识别文字和屏幕区域配置")
        subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 8px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        screen_info = QLabel(
            f"当前屏幕分辨率: {pyautogui.size().width} x {pyautogui.size().height}"
        )
        screen_info.setStyleSheet(
            "background-color: #e8f5e9; border: 1px solid #a5d6a7; "
            "border-radius: 5px; padding: 8px 12px; color: #2e7d32; font-weight: bold;"
        )
        layout.addWidget(screen_info)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        image_tab = QWidget()
        tabs.addTab(image_tab, "🖼 控制图像")
        self._build_image_tab(image_tab)

        ocr_tab = QWidget()
        tabs.addTab(ocr_tab, "🔍 OCR文字")
        self._build_ocr_tab(ocr_tab)

        region_tab = QWidget()
        tabs.addTab(region_tab, "📐 屏幕区域")
        self._build_region_tab(region_tab)

        layout.addWidget(tabs, 1)

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

        tip = QLabel("💡 根据当前使用的识别模式，配置对应的资源")
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
        save_btn.clicked.connect(self._save_all)
        bottom_layout.addWidget(save_btn)

        layout.addWidget(bottom_bar)

    def _build_image_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "控制图像用于「图像识别模式」。截取抖音界面上的按钮图片，程序通过匹配这些图片来定位按钮。\n"
            "截图要求：只截取按钮本身，不要包含周围区域，背景尽量干净。"
        )
        info.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setSpacing(12)

        for i, (filename, name, desc) in enumerate(CONTROL_IMAGE_ITEMS):
            card = self._create_image_card(filename, name, desc)
            grid.addWidget(card, i // 2, i % 2)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_image_card(self, filename, name, desc):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e8ecef;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(f"📌 {name}")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        header.addWidget(title)
        header.addStretch()

        filename_label = QLabel(filename)
        filename_label.setStyleSheet("color: #909399; font-size: 11px;")
        header.addWidget(filename_label)
        layout.addLayout(header)

        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        preview_frame = QFrame()
        preview_frame.setStyleSheet("background-color: #f5f7fa; border-radius: 4px; padding: 8px;")
        preview_frame.setMinimumHeight(80)
        preview_layout = QVBoxLayout(preview_frame)

        img_label = QLabel("未配置")
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setStyleSheet("color: #909399; font-size: 12px;")
        preview_layout.addWidget(img_label)

        layout.addWidget(preview_frame)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        paste_btn = QPushButton("📋 粘贴截图")
        paste_btn.setStyleSheet("background-color: #3498db; color: white; border-color: #3498db;")
        paste_btn.clicked.connect(lambda _, fn=filename, lbl=img_label: self._paste_from_clipboard(fn, lbl))
        btn_row.addWidget(paste_btn)

        upload_btn = QPushButton("📤 上传文件")
        upload_btn.clicked.connect(lambda _, fn=filename, lbl=img_label: self._upload_image(fn, lbl))
        btn_row.addWidget(upload_btn)

        view_btn = QPushButton("👁 查看")
        view_btn.clicked.connect(lambda _, fn=filename: self._view_image(fn))
        btn_row.addWidget(view_btn)

        delete_btn = QPushButton("🗑 删除")
        delete_btn.setStyleSheet("color: #e74c3c;")
        delete_btn.clicked.connect(lambda _, fn=filename, lbl=img_label: self._delete_image(fn, lbl))
        btn_row.addWidget(delete_btn)

        layout.addLayout(btn_row)

        self.image_labels[filename] = img_label
        self._update_image_preview(filename, img_label)

        return card

    def _upload_image(self, filename, label):
        filepath, _ = QFileDialog.getOpenFileName(
            self, f"选择 {filename} 的截图",
            "", "Images (*.png *.jpg *.bmp);;All files (*.*)"
        )
        if not filepath:
            return

        os.makedirs(CONTROL_IMAGES_DIR, exist_ok=True)
        dest = os.path.join(CONTROL_IMAGES_DIR, filename)
        try:
            shutil.copy2(filepath, dest)
            self._update_image_preview(filename, label)
            QMessageBox.information(self, "成功", f"{filename} 已更新！")
        except Exception as e:
            QMessageBox.critical(self, "失败", f"复制文件失败: {e}")

    def _paste_from_clipboard(self, filename, label):
        clipboard = QApplication.clipboard()
        pixmap = clipboard.pixmap()

        if pixmap.isNull():
            QMessageBox.warning(self, "剪贴板为空",
                "剪贴板中没有图片。\n\n请先用截图工具（如Win+Shift+S）截取图片，然后再点击粘贴。")
            return

        os.makedirs(CONTROL_IMAGES_DIR, exist_ok=True)
        dest = os.path.join(CONTROL_IMAGES_DIR, filename)
        try:
            pixmap.save(dest, "PNG")
            self._update_image_preview(filename, label)
            QMessageBox.information(self, "成功",
                f"已从剪贴板粘贴并保存为 {filename}\n尺寸: {pixmap.width()} x {pixmap.height()}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存图片失败: {e}")

    def _view_image(self, filename):
        filepath = os.path.join(CONTROL_IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "未找到", f"{filename} 不存在，请先上传。")
            return

        pixmap = QPixmap(filepath)
        if pixmap.isNull():
            QMessageBox.critical(self, "错误", "无法加载图片。")
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle(f"查看 - {filename}")
        dialog.setText(f"图片尺寸: {pixmap.width()} x {pixmap.height()}")
        scaled = pixmap.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        dialog.setIconPixmap(scaled)
        dialog.exec()

    def _delete_image(self, filename, label):
        filepath = os.path.join(CONTROL_IMAGES_DIR, filename)
        if not os.path.exists(filepath):
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {filename} 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                os.remove(filepath)
                label.setText("未配置")
                label.setStyleSheet("color: #909399; font-size: 12px;")
                QMessageBox.information(self, "已删除", f"{filename} 已删除。")
            except Exception as e:
                QMessageBox.critical(self, "删除失败", str(e))

    def _update_image_preview(self, filename, label):
        filepath = os.path.join(CONTROL_IMAGES_DIR, filename)
        if os.path.exists(filepath):
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                scaled = pixmap.scaled(120, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                label.setPixmap(scaled)
                label.setStyleSheet("")
                return
        label.setText("未配置")
        label.setStyleSheet("color: #909399; font-size: 12px;")

    def _build_ocr_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "OCR识别文字用于「OCR文字识别模式」。程序通过识别屏幕上的文字来定位按钮。\n"
            "如果抖音更新了界面文字，可以在这里修改。"
        )
        info.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("识别文字配置")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(12)

        for key, name, desc, default in OCR_TEXT_ITEMS:
            row = QHBoxLayout()
            row.setSpacing(12)

            label = QLabel(f"{name}:")
            label.setFixedWidth(100)
            label.setStyleSheet("font-weight: bold;")
            row.addWidget(label)

            edit = QLineEdit()
            edit.setPlaceholderText(default)
            edit.setText(default)
            row.addWidget(edit, 1)

            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
            desc_label.setFixedWidth(200)
            row.addWidget(desc_label)

            group_layout.addLayout(row)
            self.ocr_edits[key] = (edit, default)

        layout.addWidget(group)

        test_group = QGroupBox("测试OCR识别")
        test_layout = QHBoxLayout(test_group)

        test_input = QLineEdit()
        test_input.setPlaceholderText("输入要测试识别的文字...")
        test_layout.addWidget(test_input, 1)

        test_btn = QPushButton("🔍 测试")
        test_btn.clicked.connect(lambda: self._test_ocr_text(test_input.text()))
        test_layout.addWidget(test_btn)

        layout.addWidget(test_group)
        layout.addStretch()

    def _test_ocr_text(self, text):
        if not text.strip():
            QMessageBox.warning(self, "提示", "请输入要测试的文字。")
            return

        try:
            from ocr_service import RapidLocalOCR
            ocr = RapidLocalOCR()
            screenshot = pyautogui.screenshot()
            result = ocr.find_text_on_screen(screenshot, text, confidence_threshold=0.5)
            if result:
                QMessageBox.information(self, "识别成功",
                    f"在屏幕上找到了文字「{text}」\n位置: ({result[0]}, {result[1]})")
            else:
                QMessageBox.warning(self, "未找到",
                    f"未在屏幕上找到文字「{text}」\n请确保抖音窗口可见且文字在屏幕内。")
        except ImportError:
            QMessageBox.warning(self, "未安装", "RapidOCR未安装，请运行: pip install rapidocr_onnxruntime")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"OCR测试失败: {e}")

    def _build_region_tab(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "屏幕区域用于限定程序在屏幕的哪个范围查找按钮。\n"
            "所有值为屏幕百分比（0.0~1.0），左上角为原点。"
        )
        info.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)

        regions = [
            ("top_bar", "私信图标区域", "抖音右上角「私信」按钮所在的区域"),
            ("friend_list", "好友列表区域", "右侧好友列表区域，用于滚动查找好友"),
            ("chat_bottom", "发送按钮区域", "聊天窗口底部区域，包含「发送」按钮"),
            ("chat_top", "退出会话区域", "聊天窗口顶部区域，包含「退出会话」按钮"),
        ]

        for key, title, desc in regions:
            group = self._create_region_group(key, title, desc)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_region_group(self, key, title, description):
        group = QGroupBox(title)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)

        desc = QLabel(description)
        desc.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        desc.setWordWrap(True)
        group_layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(12)

        edits = {}
        for field, label_text in [("x_pct", "X%"), ("y_pct", "Y%"), ("w_pct", "宽%"), ("h_pct", "高%")]:
            lbl = QLabel(label_text)
            lbl.setFixedWidth(30)
            edit = QLineEdit()
            edit.setFixedWidth(80)
            edit.setPlaceholderText("0.0~1.0")
            edits[field] = edit
            row.addWidget(lbl)
            row.addWidget(edit)

        row.addStretch()

        preview_btn = QPushButton("👁 预览")
        preview_btn.clicked.connect(lambda _, k=key: self._preview_region(k))
        row.addWidget(preview_btn)

        group_layout.addLayout(row)
        self.region_edits[key] = edits
        return group

    def _preview_region(self, key):
        edits = self.region_edits.get(key)
        if not edits:
            return

        try:
            x_pct = float(edits["x_pct"].text() or "0")
            y_pct = float(edits["y_pct"].text() or "0")
            w_pct = float(edits["w_pct"].text() or "0.1")
            h_pct = float(edits["h_pct"].text() or "0.1")
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字（0.0~1.0）")
            return

        screen_w, screen_h = pyautogui.size()
        x = int(x_pct * screen_w)
        y = int(y_pct * screen_h)
        w = int(w_pct * screen_w)
        h = int(h_pct * screen_h)

        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout as VL

            img = pyautogui.screenshot(region=(x, y, w, h))
            buf = __import__('io').BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            qimg = QImage()
            qimg.loadFromData(buf.read())
            pixmap = QPixmap.fromImage(qimg)

            dialog = QDialog(self)
            dialog.setWindowTitle(f"预览区域 - {key}")
            dialog.setMinimumSize(max(300, w + 40), max(200, h + 60))

            dl = VL(dialog)
            img_label = QLabel()
            img_label.setPixmap(pixmap.scaled(
                dialog.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            img_label.setAlignment(Qt.AlignCenter)
            dl.addWidget(img_label)

            info_label = QLabel(f"区域: x={x}, y={y}, w={w}, h={h}")
            info_label.setStyleSheet("color: #7f8c8d; font-size: 12px; padding: 4px;")
            info_label.setAlignment(Qt.AlignCenter)
            dl.addWidget(info_label)

            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "预览失败", f"无法截图预览: {e}")

    def _load_config(self):
        cfg_path = project_path('config.json')
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        regions = cfg.get('ui_regions', DEFAULT_REGIONS)
        for key, edits in self.region_edits.items():
            r = regions.get(key, DEFAULT_REGIONS.get(key, {}))
            edits["x_pct"].setText(str(r.get("x_pct", 0)))
            edits["y_pct"].setText(str(r.get("y_pct", 0)))
            edits["w_pct"].setText(str(r.get("w_pct", 0.1)))
            edits["h_pct"].setText(str(r.get("h_pct", 0.1)))

        ocr_texts = cfg.get('ocr_texts', {})
        for key, (edit, default) in self.ocr_edits.items():
            edit.setText(ocr_texts.get(key, default))

    def _save_all(self):
        cfg_path = project_path('config.json')
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

        regions = {}
        for key, edits in self.region_edits.items():
            try:
                regions[key] = {
                    "x_pct": float(edits["x_pct"].text() or "0"),
                    "y_pct": float(edits["y_pct"].text() or "0"),
                    "w_pct": float(edits["w_pct"].text() or "0.1"),
                    "h_pct": float(edits["h_pct"].text() or "0.1"),
                }
            except ValueError:
                QMessageBox.warning(self, "输入错误", f"区域 {key} 包含无效数字，请检查。")
                return

        cfg['ui_regions'] = regions

        ocr_texts = {}
        for key, (edit, _) in self.ocr_edits.items():
            ocr_texts[key] = edit.text().strip()
        cfg['ocr_texts'] = ocr_texts

        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入配置文件失败: {e}")
            return

        QMessageBox.information(self, "成功", "所有配置已保存！")
        self.config_saved.emit()
