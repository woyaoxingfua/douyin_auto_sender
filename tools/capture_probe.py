# -*- coding: utf-8 -*-
"""零动作探针：验证 v7 窗口绑定截图 + 页面状态识别（不点击、不滚动、不按键）。

夜间无人值守可安全运行。用法：

    .venv/Scripts/python.exe tools/capture_probe.py            # 全套检查
    .venv/Scripts/python.exe tools/capture_probe.py --loop 5  # 连续 5 轮观察状态稳定性

输出：
  1. 三种截图模式（print/bitblt/screen）逐个验证，保存 probe_capture_*.png
  2. 用最优截图跑页面状态识别（HOME/MESSAGE_LIST/CHAT_OPEN/UNKNOWN）
  3. 打印窗口 rect / 截图模式 / 识别到的锚点坐标
"""
import argparse
import os
import sys
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

import logging  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    parser = argparse.ArgumentParser(description="v7 零动作探针")
    parser.add_argument('--loop', type=int, default=1, help='连续观察轮数（默认 1）')
    parser.add_argument('--interval', type=float, default=2.0, help='轮间隔秒数')
    parser.add_argument('--save-dir', default=PROJECT, help='截图保存目录')
    args = parser.parse_args()

    from window_capture import demo_probe, WindowCapture
    from page_state import PageDetector
    from ocr_service import RapidLocalOCR

    print("=" * 60)
    print("  v7 零动作探针（不点击/不滚动/不按键，安全）")
    print("=" * 60)

    info = demo_probe(save_dir=args.save_dir)
    if not info.get("ok"):
        print(f"\n✗ {info.get('error')} —— 请先打开抖音 PC 客户端（窗口可见）")
        sys.exit(2)

    print(f"\n窗口: hwnd={info['hwnd']}  标题={info['title']!r}")
    print(f"DWM 真实边界: {info['rect']}")
    print("\n截图模式验证：")
    best_mode = None
    for mode, result in info["modes"].items():
        mark = "✓" if result.get("valid") else "✗"
        extra = result.get("saved") or result.get("error", "")
        print(f"  [{mark}] {mode:<7} size={result.get('size')}  {extra}")
        if result.get("valid") and best_mode is None:
            best_mode = mode
    if not best_mode:
        print("\n✗ 三种截图模式全部失败，请检查：窗口是否最小化/抖音版本")
        sys.exit(3)

    # 用可用模式跑状态识别
    from window_capture import find_douyin_hwnd
    hwnd = info["hwnd"]
    cap = WindowCapture(hwnd, capture_mode=best_mode)
    detector = PageDetector(RapidLocalOCR())

    for i in range(args.loop):
        img = cap.capture()
        if img is None:
            print(f"\n第 {i + 1} 轮截图失败")
            continue
        img.save(os.path.join(args.save_dir, "last_probe.png"))
        state, anchors = detector.detect(img)
        print(f"\n第 {i + 1}/{args.loop} 轮：")
        print(f"  实际截图模式: {cap._last_mode}  尺寸: {img.size}")
        print(f"  页面状态: {state}")
        if anchors:
            for k, v in anchors.items():
                print(f"  锚点 {k}: 窗口坐标 {v}")
        else:
            print("  （无锚点——若状态是 UNKNOWN，把 last_probe.png 发给维护者看看）")
        if args.loop > 1 and i < args.loop - 1:
            time.sleep(args.interval)

    print("\n探针完成：以上状态即 v7 流水线每步决策的依据。")
    print("下一步真机测试: python bot_v2.py --friend 王佳豪")


if __name__ == "__main__":
    main()
