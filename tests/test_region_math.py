"""屏幕坐标 -> 抖音窗口百分比 换算测试。

背景：ui_regions 的百分比是相对抖音窗口的（douyin_bot._get_ui_regions:
x = 窗口x + x_pct * 窗口宽），而 region_selector 框选返回屏幕绝对坐标。
两个坐标系必须用 screen_rect_to_window_pct 统一，否则框选区域执行时偏移。
"""
from douyin_monitor import screen_rect_to_window_pct


# 2026-07-28 实际运行时的窗口与区域（run.log）：
#   窗口 (95, 11, 1730, 997)，friend_list 绝对区域 (1282, 11, 541, 939)
#   对应配置 friend_list: x_pct=0.6862, y_pct=0.0, w_pct=0.3132, h_pct=0.9421
WINDOW = (95, 11, 1730, 997)


def test_matches_real_config_values():
    pct = screen_rect_to_window_pct(1282, 11, 541, 939, WINDOW)
    assert abs(pct['x_pct'] - 0.6862) < 0.001
    assert abs(pct['y_pct'] - 0.0) < 0.001
    assert abs(pct['w_pct'] - 0.3132) < 0.001
    assert abs(pct['h_pct'] - 0.9421) < 0.001


def test_identity_for_full_window():
    pct = screen_rect_to_window_pct(95, 11, 1730, 997, WINDOW)
    assert pct == {'x_pct': 0.0, 'y_pct': 0.0, 'w_pct': 1.0, 'h_pct': 1.0}


def test_clamps_selection_outside_window():
    # 选区在窗口左上方之外：百分比应钳制为 0，而不是负数
    pct = screen_rect_to_window_pct(0, 0, 50, 50, WINDOW)
    assert pct['x_pct'] == 0.0
    assert pct['y_pct'] == 0.0
    assert pct['w_pct'] > 0.0


def test_zero_sized_window_is_safe():
    pct = screen_rect_to_window_pct(10, 10, 5, 5, (0, 0, 0, 0))
    assert pct == {'x_pct': 0.0, 'y_pct': 0.0, 'w_pct': 0.0, 'h_pct': 0.0}
