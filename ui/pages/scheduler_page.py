from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QCheckBox, QTimeEdit, QPushButton, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTime


class SchedulerPage(QWidget):
    schedule_changed = Signal(str, bool)

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        title = QLabel("调度设置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2c3e50;")
        subtitle = QLabel("配置每日自动执行任务的时间")
        subtitle.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 12px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e8ecef;
                padding: 24px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(20)

        self.enable_check = QCheckBox("启用每日自动调度")
        self.enable_check.setStyleSheet("""
            QCheckBox {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #bdc3c7;
            }
            QCheckBox::indicator:checked {
                background-color: #1abc9c;
                border-color: #1abc9c;
            }
        """)
        self.enable_check.stateChanged.connect(self._on_changed)
        card_layout.addWidget(self.enable_check)

        time_row = QHBoxLayout()
        time_row.setSpacing(16)

        time_label = QLabel("执行时间：")
        time_label.setStyleSheet("font-size: 14px; color: #2c3e50;")

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(8, 0))
        self.time_edit.setStyleSheet("""
            QTimeEdit {
                padding: 8px 12px;
                font-size: 16px;
                font-weight: bold;
                min-width: 120px;
            }
        """)
        self.time_edit.timeChanged.connect(self._on_changed)

        time_row.addWidget(time_label)
        time_row.addWidget(self.time_edit)
        time_row.addStretch()

        card_layout.addLayout(time_row)

        tip_frame = QFrame()
        tip_frame.setStyleSheet("""
            QFrame {
                background-color: #fef9e7;
                border-radius: 6px;
                padding: 12px 16px;
                border-left: 4px solid #f39c12;
            }
        """)
        tip_layout = QVBoxLayout(tip_frame)
        tip_layout.setContentsMargins(0, 0, 0, 0)

        tip_title = QLabel("💡 温馨提示")
        tip_title.setStyleSheet("font-weight: bold; color: #f39c12; margin-bottom: 4px;")

        tip_text = QLabel(
            "启用调度后，程序会在每天设定的时间自动执行任务。\n"
            "请确保程序保持运行状态（可最小化到系统托盘）。\n"
            "执行时请确保抖音 PC 客户端已登录并可见。"
        )
        tip_text.setStyleSheet("color: #7f8c8d; font-size: 12px; line-height: 1.6;")
        tip_text.setWordWrap(True)

        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(tip_text)
        card_layout.addWidget(tip_frame)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.save_btn = QPushButton("💾 保存设置")
        self.save_btn.setStyleSheet("""
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
        self.save_btn.clicked.connect(self._save)
        btn_row.addWidget(self.save_btn)

        card_layout.addLayout(btn_row)
        card_layout.addStretch()

        layout.addWidget(card)
        layout.addStretch()

    def set_config(self, time_str, enabled):
        self.enable_check.blockSignals(True)
        self.time_edit.blockSignals(True)
        self.enable_check.setChecked(enabled)
        parts = time_str.split(':')
        if len(parts) == 2:
            self.time_edit.setTime(QTime(int(parts[0]), int(parts[1])))
        self.enable_check.blockSignals(False)
        self.time_edit.blockSignals(False)

    def _on_changed(self):
        pass

    def _save(self):
        time_str = self.time_edit.time().toString("HH:mm")
        enabled = self.enable_check.isChecked()
        self.schedule_changed.emit(time_str, enabled)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "保存成功", f"调度设置已保存：\n时间：{time_str}\n状态：{'启用' if enabled else '禁用'}")
