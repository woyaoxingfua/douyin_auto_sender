import sys
import os
import signal
import logging
import json
from logging.handlers import RotatingFileHandler

import dearpygui.dearpygui as dpg

from config_utils import project_path, load_config

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

    return logger


def load_chinese_font():
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None


def load_window_config():
    try:
        cfg = load_config()
        ui_cfg = cfg.get('ui', {})
        mode = ui_cfg.get('window_mode', 'normal')
        if mode == 'compact':
            return ui_cfg.get('compact_size', [900, 600])
        elif mode == 'mini':
            return ui_cfg.get('mini_size', [500, 400])
        return [1100, 750]
    except Exception:
        return [1100, 750]


def main():
    logger = setup_logging()
    logger.info("抖音天气助手 v6.0 启动中...")

    size = load_window_config()

    font_path = load_chinese_font()
    if font_path:
        with dpg.font_registry():
            with dpg.font(font_path, 16) as default_font:
                pass
        dpg.bind_font(default_font)

    dpg.create_viewport(
        title="抖音天气助手 v6.0",
        width=size[0],
        height=size[1],
        min_width=500,
        min_height=400,
        resizable=True,
    )

    from ui.dpg_app import DPGApp
    app = DPGApp(logger)
    app.build()

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
