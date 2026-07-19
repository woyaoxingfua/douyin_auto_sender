from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QProgressBar, QFrame, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor


class MonitorPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("任务监控")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        subtitle = QLabel("实时查看任务运行状态和日志输出")
        subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 12px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        status_card = QFrame()
        status_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 16px 20px;
            }
        """)
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(0, 0, 0, 0)

        status_label = QLabel("当前状态：")
        status_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.status_value = QLabel("待机中")
        self.status_value.setStyleSheet("color: #1abc9c; font-weight: bold;")
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_value)
        status_layout.addStretch()

        layout.addWidget(status_card)

        progress_card = QFrame()
        progress_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 16px 20px;
            }
        """)
        prog_layout = QVBoxLayout(progress_card)

        prog_label_row = QHBoxLayout()
        prog_title = QLabel("任务进度")
        prog_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        self.progress_text = QLabel("0 / 0")
        self.progress_text.setStyleSheet("color: #7f8c8d;")
        prog_label_row.addWidget(prog_title)
        prog_label_row.addStretch()
        prog_label_row.addWidget(self.progress_text)
        prog_layout.addLayout(prog_label_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        prog_layout.addWidget(self.progress_bar)

        layout.addWidget(progress_card)

        log_card = QFrame()
        log_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 16px 20px;
            }
        """)
        log_layout = QVBoxLayout(log_card)

        log_title_row = QHBoxLayout()
        log_title = QLabel("运行日志")
        log_title.setStyleSheet("font-weight: bold; color: #2c3e50;")
        log_title_row.addWidget(log_title)
        log_title_row.addStretch()

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 12px;
                background-color: #f5f7fa;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                color: #606266;
            }
            QPushButton:hover {
                background-color: #ecf0f1;
            }
        """)
        self.clear_btn.clicked.connect(self._clear_log)
        log_title_row.addWidget(self.clear_btn)

        log_layout.addLayout(log_title_row)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                border-radius: 6px;
                padding: 12px;
                font-family: "Consolas", "Monaco", "Courier New", monospace;
                font-size: 12px;
            }
        """)
        log_layout.addWidget(self.log_view)

        layout.addWidget(log_card, 1)

    def append_log(self, level, message):
        color_map = {
            "INFO": "#3498db",
            "WARNING": "#f39c12",
            "ERROR": "#e74c3c",
            "CRITICAL": "#e74c3c",
            "DEBUG": "#95a5a6",
        }
        color = color_map.get(level, "#d4d4d4")
        html = f'<span style="color: {color};">{message}</span>'
        self.log_view.append(html)
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def set_progress(self, current, total):
        self.progress_text.setText(f"{current} / {total}")
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)

    def set_status(self, status):
        self.status_value.setText(status)
        if "运行中" in status or "处理" in status or "等待" in status:
            self.status_value.setStyleSheet("color: #f39c12; font-weight: bold;")
        elif "完成" in status:
            self.status_value.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif "失败" in status:
            self.status_value.setStyleSheet("color: #e74c3c; font-weight: bold;")
        else:
            self.status_value.setStyleSheet("color: #1abc9c; font-weight: bold;")

    def _clear_log(self):
        self.log_view.clear()
