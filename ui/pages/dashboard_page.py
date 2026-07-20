import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QPushButton
)
from PySide6.QtCore import Qt, Signal

from config_utils import project_path


class DashboardPage(QWidget):
    run_now_clicked = Signal()

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        title = QLabel("仪表盘")
        title.setProperty("class", "page-title")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        subtitle = QLabel("概览您的抖音天气助手运行状态")
        subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 20px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(16)

        self.friends_count = self._create_stat_card("好友数量", "0", "#1abc9c")
        self.ocr_mode = self._create_stat_card("识别模式", "未配置", "#3498db")
        self.schedule_status = self._create_stat_card("调度状态", "未启用", "#f39c12")
        self.schedule_time = self._create_stat_card("执行时间", "08:00", "#9b59b6")

        stats_grid.addWidget(self.friends_count, 0, 0)
        stats_grid.addWidget(self.ocr_mode, 0, 1)
        stats_grid.addWidget(self.schedule_status, 1, 0)
        stats_grid.addWidget(self.schedule_time, 1, 1)

        layout.addLayout(stats_grid)

        quick_card = QFrame()
        quick_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 20px;
            }
        """)
        quick_layout = QVBoxLayout(quick_card)

        quick_title = QLabel("快捷操作")
        quick_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; margin-bottom: 12px;")
        quick_layout.addWidget(quick_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.run_btn = QPushButton("▶ 立即执行任务")
        self.run_btn.setProperty("class", "primary")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #1abc9c;
                color: white;
                border: 1px solid #1abc9c;
                border-radius: 5px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #16a085;
                border-color: #16a085;
            }
        """)
        self.run_btn.clicked.connect(self.run_now_clicked)
        btn_row.addWidget(self.run_btn)

        self.tip_label = QLabel("提示：执行后请在 10 秒内切换到抖音 PC 客户端窗口")
        self.tip_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        btn_row.addWidget(self.tip_label)
        btn_row.addStretch()

        quick_layout.addLayout(btn_row)
        layout.addWidget(quick_card)

        layout.addStretch()

    def _create_stat_card(self, label, value, color):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 16px;
            }
        """)
        card.setMinimumHeight(100)
        lay = QVBoxLayout(card)
        lay.setSpacing(4)

        val_label = QLabel(value)
        val_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
        val_label.setAlignment(Qt.AlignCenter)
        val_label.setWordWrap(True)

        lbl_label = QLabel(label)
        lbl_label.setStyleSheet("font-size: 12px; color: #7f8c8d;")
        lbl_label.setAlignment(Qt.AlignCenter)

        lay.addWidget(val_label)
        lay.addWidget(lbl_label)

        card._value_label = val_label
        return card

    def refresh_stats(self):
        cfg_path = project_path('config.json')
        friends = 0
        use_local = True
        ocr_configured = False

        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                friends = len(cfg.get('friends', []))
                use_local = cfg.get('use_local_ocr', True)
                if use_local:
                    ocr_configured = True
                elif cfg.get('ocr_api_key') and cfg.get('ocr_secret_key'):
                    ocr_configured = True
            except Exception:
                pass

        self.friends_count._value_label.setText(str(friends))

        if ocr_configured:
            if use_local:
                self.ocr_mode._value_label.setText("本地OCR")
            else:
                self.ocr_mode._value_label.setText("百度OCR")
        else:
            self.ocr_mode._value_label.setText("图像识别")

    def set_schedule_info(self, time_str, enabled):
        self.schedule_time._value_label.setText(time_str)
        if enabled:
            self.schedule_status._value_label.setText("已启用")
            self.schedule_status._value_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #27ae60;")
        else:
            self.schedule_status._value_label.setText("已禁用")
            self.schedule_status._value_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #e74c3c;")
