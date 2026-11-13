import sys
import os
import signal
import logging
import locale
from logging.handlers import RotatingFileHandler

# 强制UTF-8（修复DPG输入中文"消息"显示问号）
os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
except Exception:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        pass

import dearpygui.dearpygui as dpg

from config_utils import project_path
from config_store import config_store
from font_loader import setup_chinese_fonts, get_font
from ui.mini_window import MiniStatusWindow

# 先建context再注册字体（顺序很重要）
dpg.create_context()


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

    # 应用配置文件中的日志级别
    try:
        config_store.apply_log_level()
    except Exception as e:
        logger.warning(f"应用日志级别失败: {e}")

    return logger


def load_window_config():
    try:
        ui_cfg = config_store.get().get('ui', {})
        mode = ui_cfg.get('window_mode', 'normal')
        if mode == 'compact':
            return ui_cfg.get('compact_size', [900, 600])
        return [1280, 800]
    except Exception:
        return [1280, 800]


def main():
    logger = setup_logging()
    logger.info("抖音天气助手 v6.0 启动中...")

    # 字体必须在viewport之前注册
    setup_chinese_fonts(default_size=16, large_size=24, huge_size=42)

    size = load_window_config()

    dpg.create_viewport(
        title="Douyin Weather Assistant v6.0",
        width=size[0],
        height=size[1],
        min_width=900,
        min_height=600,
        resizable=True,
    )

    from ui.dpg_app import DPGApp
    try:
        mini_window = MiniStatusWindow()
    except Exception as e:
        # tkinter 不可用等情况不应导致主程序无法启动
        logger.warning(f"Mini 悬浮窗不可用: {e}")
        mini_window = None
    app = DPGApp(logger, mini_window=mini_window)
    app.build()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
