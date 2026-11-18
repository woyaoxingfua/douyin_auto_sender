# -*- coding: utf-8 -*-
"""主题与配色（从 dpg_app.py 拆出）。

暗色为默认；亮色供切换。全部直角（rounding=0）、高数据密度取向。
"""
import dearpygui.dearpygui as dpg

# ─── 暗色 ───
C_BG = (18, 17, 16)        # 暖黑 #121110
C_BG_SOFT = (29, 27, 25)
C_BG_PANEL = (24, 22, 20)
C_BORDER = (54, 50, 44)
C_TEXT = (220, 215, 205)   # 暖白
C_TEXT_DIM = (138, 130, 116)
C_TEXT_MUTE = (94, 88, 78)
C_AMBER = (245, 158, 11)   # 主强调
C_AMBER_DIM = (180, 110, 0)
C_GREEN = (74, 222, 128)
C_RED = (239, 68, 68)
C_YELLOW = (250, 204, 21)
C_BLUE = (96, 165, 250)

# ─── 亮色 ───
L_BG = (245, 245, 245)
L_BG_SOFT = (235, 235, 235)
L_BG_PANEL = (240, 240, 240)
L_BORDER = (200, 200, 200)
L_TEXT = (50, 50, 50)
L_TEXT_DIM = (120, 120, 120)
L_TEXT_MUTE = (160, 160, 160)
L_AMBER = (217, 119, 6)
L_AMBER_DIM = (180, 100, 0)
L_GREEN = (22, 163, 74)
L_RED = (220, 38, 38)
L_YELLOW = (202, 138, 4)
L_BLUE = (37, 99, 235)


def build_themes() -> dict:
    """构建暗/亮两套主题，返回 {'dark': tag, 'light': tag}。"""
    with dpg.theme() as dark:
        with dpg.theme_component(dpg.mvAll):
            _apply_common(dark_mode=True)
    with dpg.theme() as light:
        with dpg.theme_component(dpg.mvAll):
            _apply_common(dark_mode=False)
    return {'dark': dark, 'light': light}


def _apply_common(dark_mode: bool):
    bg, bg_soft, bg_panel = (C_BG, C_BG_SOFT, C_BG_PANEL) if dark_mode \
        else (L_BG, L_BG_SOFT, L_BG_PANEL)
    text, text_dim, text_mute = (C_TEXT, C_TEXT_DIM, C_TEXT_MUTE) if dark_mode \
        else (L_TEXT, L_TEXT_DIM, L_TEXT_MUTE)
    amber, amber_dim = (C_AMBER, C_AMBER_DIM) if dark_mode else (L_AMBER, L_AMBER_DIM)
    border = C_BORDER if dark_mode else L_BORDER

    dpg.add_theme_color(dpg.mvThemeCol_WindowBg, bg)
    dpg.add_theme_color(dpg.mvThemeCol_ChildBg, bg_panel)
    dpg.add_theme_color(dpg.mvThemeCol_PopupBg, bg_panel)
    dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_TitleBg, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_Text, text)
    dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, text_mute)
    dpg.add_theme_color(dpg.mvThemeCol_Button, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, amber_dim)
    dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, amber)
    dpg.add_theme_color(dpg.mvThemeCol_FrameBg, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (40, 36, 32) if dark_mode else (225, 225, 225))
    dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (45, 40, 35) if dark_mode else (220, 220, 220))
    dpg.add_theme_color(dpg.mvThemeCol_Border, border)
    dpg.add_theme_color(dpg.mvThemeCol_Separator, border)
    for tab_col in (dpg.mvThemeCol_Tab,):
        dpg.add_theme_color(tab_col, bg)
    for tab_col in (dpg.mvThemeCol_TabHovered, dpg.mvThemeCol_TabActive,
                    dpg.mvThemeCol_TabSelected, dpg.mvThemeCol_TabSelectedOverline,
                    dpg.mvThemeCol_TabDimmedSelected):
        dpg.add_theme_color(tab_col, amber if dark_mode else L_AMBER)
    dpg.add_theme_color(dpg.mvThemeCol_Header, bg_soft)
    dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, amber_dim)
    dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, amber)
    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, bg)
    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, border)
    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, text_mute)
    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, text_dim)
    dpg.add_theme_color(dpg.mvThemeCol_CheckMark, amber)

    # 直角优先 + 紧凑
    dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 0)
    dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 16)
    dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
    dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 6)
    dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, 6, 4)
    dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 12)
    dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 8)
