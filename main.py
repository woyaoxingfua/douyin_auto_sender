# -*- coding: utf-8 -*-
"""v7 主入口（薄壳）：日志 + 字体 + DearPyGui 生命周期。

所有逻辑都在 core/ services/ ui/ 里，这里只剩装配。
"""
import logging
import os
import signal
from logging.handlers import RotatingFileHandler

# DPG 中文输入修复
os.environ['PYTHONIOENCODING'] = 'utf-8'

import dearpygui.dearpygui as dpg  # noqa: E402

from core.config import config_store, project_path  # noqa: E402
from ui.fonts import setup_chinese_fonts  # noqa: E402


def setup_logging() -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = RotatingFileHandler(
        project_path('run.log'), maxBytes=1_000_000, backupCount=3,
        encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(console)

    try:
        config_store.apply_log_level()
    except Exception as e:
        logger.warning(f"应用日志级别失败: {e}")
    return logger


def load_window_size():
    try:
        ui_cfg = config_store.get().get('ui', {})
        if ui_cfg.get('window_mode') == 'compact':
            return ui_cfg.get('compact_size', [900, 600])
    except Exception:
        pass
    return [1280, 800]


def main():
    logger = setup_logging()
    logger.info("抖音天气助手 v7 启动中...")

    # 字体必须在 viewport 之前注册
    setup_chinese_fonts(default_size=16, large_size=24, huge_size=42)
    dpg.create_context()

    size = load_window_size()
    dpg.create_viewport(
        title="Douyin Weather Assistant v7",
        width=size[0], height=size[1],
        min_width=900, min_height=600, resizable=True,
    )

    from ui.app import App
    mini = None
    try:
        from ui.mini_window import MiniStatusWindow
        mini = MiniStatusWindow()
    except Exception as e:
        logger.warning(f"Mini 悬浮窗不可用: {e}")

    app = App(logger, mini_window=mini)
    app.build()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    try:
        dpg.start_dearpygui()
    finally:
        app.destroy()
        dpg.destroy_context()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
