import sys
import os
import signal
import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt

from config_utils import project_path
from ui.main_window import MainWindow
from ui.qt_log_handler import QtLogHandler


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = RotatingFileHandler(
        project_path('run.log'), maxBytes=1_000_000, backupCount=3, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

    return logger


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("抖音天气助手")
    app.setApplicationDisplayName("抖音天气助手")
    app.setOrganizationName("DouyinWeatherHelper")

    logger = setup_logging()
    qt_log_handler = QtLogHandler()
    logger.addHandler(qt_log_handler)

    try:
        icon_path = project_path('control_images', 'douyin_sixin_icon.png')
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

    window = MainWindow()
    window.setLogHandler(qt_log_handler)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.error("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
        QMessageBox.critical(None, "程序错误", f"发生未预期的错误：\n{exc_value}")

    sys.excepthook = handle_exception

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    tray_icon = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray_icon = QSystemTrayIcon(app.windowIcon(), app)
        tray_icon.setToolTip("抖音天气助手 - 正在运行")

        tray_menu = QMenu()
        show_action = QAction("显示主窗口", app)
        show_action.triggered.connect(window.showNormal)
        show_action.triggered.connect(window.activateWindow)
        tray_menu.addAction(show_action)

        run_action = QAction("立即执行任务", app)
        run_action.triggered.connect(window.runTaskNow)
        tray_menu.addAction(run_action)

        tray_menu.addSeparator()

        quit_action = QAction("退出", app)
        quit_action.triggered.connect(app.quit)
        tray_menu.addAction(quit_action)

        tray_icon.setContextMenu(tray_menu)
        tray_icon.activated.connect(
            lambda reason: window.showNormal() if reason == QSystemTrayIcon.DoubleClick else None
        )
        tray_icon.show()

        window.setTrayIcon(tray_icon)

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
