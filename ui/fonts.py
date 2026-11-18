"""中文字体加载器：检测系统已安装中文字体，注册到DearPyGui并支持多种字号"""
import os
import dearpygui.dearpygui as dpg


CANDIDATE_FONTS = [
    # Windows
    ("C:/Windows/Fonts/msyh.ttc", 0),       # 微软雅黑
    ("C:/Windows/Fonts/msyhbd.ttc", 0),     # 微软雅黑 Bold
    ("C:/Windows/Fonts/simhei.ttf", 0),     # 黑体
    ("C:/Windows/Fonts/simsun.ttc", 0),     # 宋体
    # macOS
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
    ("/Library/Fonts/Songti.ttc", 0),
    # Linux
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", 0),
]


def find_chinese_font_path():
    for path, _ in CANDIDATE_FONTS:
        if os.path.exists(path):
            return path
    return None


# 全局记录注册的字体句柄（key: size, value: font_id）
_FONT_HANDLES: dict = {}
# 默认字体（中等字号，作为全局绑定）
_DEFAULT_FONT = None
# 默认字体路径
_FONT_PATH = None


def setup_chinese_fonts(default_size: int = 16, large_size: int = 28, huge_size: int = 48):
    """注册中文字体到DPG，返回默认字体句柄。

    - default_size: 普通UI文字 (16)
    - large_size: 标题/区块名 (28)
    - huge_size: 仪表盘大数字 (48)
    """
    global _DEFAULT_FONT, _FONT_PATH

    _FONT_PATH = find_chinese_font_path()
    if not _FONT_PATH:
        # 找不到中文字体时，DPG会用豆腐块，至少记日志
        print("[font] 警告: 未找到系统中文字体，中文可能显示为方块")
        return None

    with dpg.font_registry():
        for size in (default_size, large_size, huge_size):
            font = dpg.add_font(_FONT_PATH, size)
            _FONT_HANDLES[size] = font

    _DEFAULT_FONT = _FONT_HANDLES[default_size]
    dpg.bind_font(_DEFAULT_FONT)
    return _DEFAULT_FONT


def get_font(size: int):
    """获取指定字号的中文字体（如果已注册）"""
    return _FONT_HANDLES.get(size, _DEFAULT_FONT)


def bind_to_item(item_id: int, size: int):
    """把特定字号的中文字体绑定到某个item上（用于大标题）"""
    font = get_font(size)
    if font is not None:
        dpg.bind_item_font(item_id, font)
