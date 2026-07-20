import os
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QListWidget, QListWidgetItem, QStatusBar, QLabel, QPushButton,
    QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon

from config_utils import project_path
from ui.pages.dashboard_page import DashboardPage
from ui.pages.config_page import ConfigPage
from ui.pages.monitor_page import MonitorPage
from ui.pages.scheduler_page import SchedulerPage
from ui.pages.ui_config_page import UIConfigPage
from ui.workers.bot_worker import BotWorker
from ui.styles import load_stylesheet


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖音天气助手 v5.0")
        self.setMinimumSize(1100, 750)
        self.resize(1200, 800)

        self.tray_icon = None
        self.worker = None
        self.log_handler = None
        self.scheduler_timer = None
        self.scheduled_time = "08:00"
        self.scheduler_enabled = True
        self._last_run_date = None

        self._init_ui()
        self._setup_scheduler()
        self.setStyleSheet(load_stylesheet())

    def _init_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QListWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar.setIconSize(QSize(20, 20))

        items = [
            ("📊  仪表盘", "dashboard"),
            ("⚙️  配置管理", "config"),
            ("📱  抖音界面", "ui_config"),
            ("📡  任务监控", "monitor"),
            ("⏰  调度设置", "scheduler"),
        ]
        for text, page_key in items:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, page_key)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            sidebar.addItem(item)

        sidebar.currentRowChanged.connect(self._on_page_changed)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")

        self.dashboard_page = DashboardPage()
        self.config_page = ConfigPage()
        self.ui_config_page = UIConfigPage()
        self.monitor_page = MonitorPage()
        self.scheduler_page = SchedulerPage()

        self.content_stack.addWidget(self.dashboard_page)
        self.content_stack.addWidget(self.config_page)
        self.content_stack.addWidget(self.ui_config_page)
        self.content_stack.addWidget(self.monitor_page)
        self.content_stack.addWidget(self.scheduler_page)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.content_stack)

        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        self.status_bar.addWidget(self.status_label, 1)

        self.run_btn = QPushButton("▶ 立即执行")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.runTaskNow)
        self.status_bar.addPermanentWidget(self.run_btn)

        sidebar.setCurrentRow(0)

        self.config_page.config_saved.connect(self._on_config_saved)
        self.scheduler_page.schedule_changed.connect(self._on_schedule_changed)

        self._update_dashboard_stats()

    def _on_page_changed(self, row):
        self.content_stack.setCurrentIndex(row)
        if row == 0:
            self._update_dashboard_stats()

    def setLogHandler(self, handler):
        self.log_handler = handler
        if self.log_handler:
            self.log_handler.log_message.connect(self.monitor_page.append_log)
            self.log_handler.log_message.connect(self._check_run_complete)

    def setTrayIcon(self, tray_icon):
        self.tray_icon = tray_icon

    def _setup_scheduler(self):
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.timeout.connect(self._check_schedule)
        self.scheduler_timer.start(30000)
        self._load_scheduler_config()

    def _load_scheduler_config(self):
        cfg_path = project_path('config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.scheduled_time = cfg.get('schedule_time', '08:00')
                self.scheduler_enabled = cfg.get('scheduler_enabled', True)
                self.scheduler_page.set_config(self.scheduled_time, self.scheduler_enabled)
            except Exception:
                pass

    def _save_scheduler_config(self):
        cfg_path = project_path('config.json')
        cfg = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            except Exception:
                pass
        cfg['schedule_time'] = self.scheduled_time
        cfg['scheduler_enabled'] = self.scheduler_enabled
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _on_schedule_changed(self, time_str, enabled):
        self.scheduled_time = time_str
        self.scheduler_enabled = enabled
        self._save_scheduler_config()
        self._update_dashboard_stats()

    def _check_schedule(self):
        if not self.scheduler_enabled:
            return
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")
        if current_time == self.scheduled_time and self._last_run_date != today:
            self._last_run_date = today
            if self.worker and self.worker.isRunning():
                return
            self.runTaskNow()

    def _check_run_complete(self, level, msg):
        if "所有任务执行完毕" in msg or "任务完成" in msg:
            self._update_dashboard_stats()

    def _on_config_saved(self):
        self._update_dashboard_stats()
        self.status_label.setText("配置已保存")

    def _update_dashboard_stats(self):
        self.dashboard_page.refresh_stats()
        self.dashboard_page.set_schedule_info(self.scheduled_time, self.scheduler_enabled)

    def runTaskNow(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "提示", "任务正在运行中，请稍候...")
            return

        reply = QMessageBox.question(
            self, "确认执行",
            "确定要立即执行任务吗？\n\n执行后有 10 秒时间切换到抖音 PC 客户端窗口。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.worker = BotWorker()
        self.worker.log.connect(self.monitor_page.append_log)
        self.worker.status.connect(self._on_status_update)
        self.worker.progress.connect(self.monitor_page.set_progress)
        self.worker.finished_ok.connect(self._on_task_finished)
        self.worker.failed.connect(self._on_task_failed)
        self.worker.start()

        self.content_stack.setCurrentIndex(3)
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ 运行中...")

    def _on_status_update(self, status):
        self.status_label.setText(status)
        self.monitor_page.set_status(status)

    def _on_task_finished(self):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶ 立即执行")
        self.status_label.setText("任务完成")
        self.monitor_page.set_status("任务完成")
        if self.tray_icon:
            self.tray_icon.showMessage(
                "抖音天气助手", "今日任务已完成！",
                self.tray_icon.icon(), 3000
            )

    def _on_task_failed(self, error_msg):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶ 立即执行")
        self.status_label.setText("任务失败")
        self.monitor_page.set_status(f"失败: {error_msg}")
        QMessageBox.critical(self, "任务失败", error_msg)

    def closeEvent(self, event):
        if self.tray_icon and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "抖音天气助手", "程序已最小化到系统托盘，双击图标可恢复窗口。",
                self.tray_icon.icon(), 2000
            )
        else:
            if self.worker and self.worker.isRunning():
                reply = QMessageBox.question(
                    self, "确认退出", "任务正在运行中，确定要退出吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
                self.worker.stop()
                self.worker.wait(3000)
            event.accept()
