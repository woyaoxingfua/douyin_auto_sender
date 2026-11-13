# -*- coding: utf-8 -*-
"""离线端到端 dry-run：不开抖音、不动真实鼠标键盘。

原理：用 2026-07-28 真实运行时保存的 last_screen.png（1920x1080 全屏截图，
含抖音主界面）作为"虚拟屏幕"，把 pyautogui 的截图/定位/点击/滚动全部换成
针对虚拟屏幕的实现，天气接口与配置加载换成桩，然后跑真正的 run_bot_task()。

OCR 用真实 RapidOCR（对虚拟屏幕截图识别），图像匹配用真实 cv2 模板匹配 ——
识别链路是全真的，只有"执行动作"是记录不落地。

验证点（对应 2026-07-28 那次失败运行的问题）：
  A. 全链路场景：
     1. 私信入口定位：OCR 找 '消息' → 悬停+点击落在图标附近 (1474, 63)
     2. 好友定位：OCR 找 '王佳豪' → 点击落在 (1515, 332) 附近
        （而不是子图相对坐标 (233, 321) —— 验证区域偏移修复）
     3. 粘贴动作：ctrl+v 被执行
     4. 留痕：log_send 记录了王佳豪（静态屏幕无聊天窗，发送预期失败）
     5. 无识别方式的好友（示例A/B/C）被跳过，统计正确
  B. 强制发送成功场景：
     6. 发送成功后会走退出会话逻辑，兜底是按 Esc（不是 alt+f4）

用法：
    .venv/Scripts/python.exe tools/dry_run.py
退出码 0 = 全部通过。
"""
import json
import os
import shutil
import sys
import tempfile
import time
import traceback

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

# ── 2026-07-28 run.log 里的真实参数 ──
DOUYIN_RECT = (95, 11, 1730, 997)          # 抖音窗口位置尺寸
FRIEND_CLICK_EXPECT = (1515, 332)          # 王佳豪 在全屏截图中的 OCR 中心
SIXIN_CLICK_EXPECT = (1474, 63)            # '消息' 图标标签在全屏截图中的 OCR 中心

FRIENDS = [
    {"nickname": "王佳豪", "city_name": "项城", "location_id": "101181407",
     "avatar_text": "王佳豪", "avatar_image": ""},
    {"nickname": "示例A", "city_name": "北京", "location_id": "101010100",
     "avatar_text": "", "avatar_image": ""},
    {"nickname": "示例B", "city_name": "上海", "location_id": "101020100",
     "avatar_text": "", "avatar_image": ""},
]

SCREENSHOT_BACKUPS = {}  # path -> 备份临时文件（结束时还原）
records = {"clicks": [], "moves": [], "scrolls": [], "hotkeys": [],
           "presses": [], "sends": []}
clipboard = {"text": ""}


def banner(title):
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def near(pt, target, tol):
    return (abs(pt[0] - target[0]) <= tol) and (abs(pt[1] - target[1]) <= tol)


def setup_virtual_screen():
    """加载虚拟屏幕 + 备份会被 run_bot_task 覆盖保存的调试截图。"""
    from PIL import Image
    src = os.path.join(PROJECT, "last_screen.png")
    if not os.path.exists(src):
        print(f"✗ 缺少虚拟屏幕截图: {src}")
        sys.exit(2)
    screen = Image.open(src).convert("RGB")
    print(f"虚拟屏幕: {src} ({screen.size[0]}x{screen.size[1]})")

    for name in ("last_screen.png", "last_top_bar.png"):
        path = os.path.join(PROJECT, name)
        if os.path.exists(path):
            bak = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            shutil.copy2(path, bak.name)
            SCREENSHOT_BACKUPS[path] = bak.name
    return screen


def install_mocks(screen):
    """把 pyautogui / pyperclip / 天气 / 留痕 全部替换成虚拟实现。"""
    import cv2
    import numpy as np
    import pyautogui
    import pyperclip

    import douyin_bot
    import douyin_monitor
    from hybrid_recognizer import HybridRecognizer

    def fake_screenshot(region=None):
        if region:
            x, y, w, h = region
            return screen.crop((x, y, x + w, y + h))
        return screen.copy()

    def fake_locate_center(image_path, confidence=0.8, region=None, **kwargs):
        """模仿 pyautogui.locateCenterOnScreen：区域内模板匹配，返回绝对坐标。"""
        try:
            from PIL import Image
            template = Image.open(image_path).convert("RGB")
        except Exception:
            return None
        tw, th = template.size
        if region:
            x, y, w, h = region
            haystack = screen.crop((x, y, x + w, y + h))
        else:
            x, y = 0, 0
            haystack = screen
        hw, hh = haystack.size
        if tw > hw or th > hh:
            return None
        result = cv2.matchTemplate(np.array(haystack), np.array(template),
                                   cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= (confidence or 0.8):
            return (x + max_loc[0] + tw // 2, y + max_loc[1] + th // 2)
        return None

    def _as_point(args):
        """pyautogui.click((x, y)) 传的是单个元组；click(x, y) 是两个标量。"""
        if len(args) == 1 and isinstance(args[0], tuple):
            return args[0]
        return tuple(args)

    pyautogui.screenshot = fake_screenshot
    pyautogui.locateCenterOnScreen = fake_locate_center
    pyautogui.click = lambda *a, **k: records["clicks"].append(_as_point(a))
    pyautogui.moveTo = lambda *a, **k: records["moves"].append(_as_point(a))
    pyautogui.scroll = lambda *a, **k: records["scrolls"].append(a[0] if a else k.get("clicks", 0))
    pyautogui.hotkey = lambda *a, **k: records["hotkeys"].append(tuple(a))
    pyautogui.press = lambda *a, **k: records["presses"].append(a[0] if a else None)
    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = False

    pyperclip.copy = lambda text: clipboard.__setitem__("text", text)
    pyperclip.paste = lambda: clipboard["text"]

    # 抖音窗口/就绪检测：直接报告 07-28 的真实窗口
    douyin_monitor.get_douyin_screenshot_rect = lambda: DOUYIN_RECT
    douyin_bot.is_douyin_window_ready = lambda: True

    # 不覆盖调试截图（run_bot_task 每次都会存区域截图）
    douyin_bot._save_region_screenshot = lambda name, region: None

    # 留痕改为记录
    douyin_bot.log_send = lambda **kw: records["sends"].append(kw)

    # 配置/消息：受控的好友列表 + 固定文案（不打真实 API）
    class FakeMsgManager:
        def format_message(self, preset_id, variables):
            return f"[dry-run] 给 {variables.get('nickname')} 的测试消息"

    def fake_prepare_runtime():
        config = {"api_host": "dry-run", "api_key": "dry-run", "friends": FRIENDS}
        preset = {"id": "plain", "name": "纯文本", "use_weather_api": False,
                  "template": "[dry-run]"}
        return config, HybridRecognizer(), FakeMsgManager(), preset

    douyin_bot._prepare_runtime = fake_prepare_runtime

    # 倒计时/等待不再真实睡眠
    time.sleep = lambda s: None

    return douyin_bot


def dump_records():
    print(f"  clicks   ({len(records['clicks'])}): "
          + "; ".join(str(c) for c in records["clicks"][:20]))
    print(f"  moves    ({len(records['moves'])}): "
          + "; ".join(str(c) for c in records["moves"][:8]) + " ...")
    print(f"  scrolls  ({len(records['scrolls'])}): {records['scrolls'][:12]}")
    print(f"  hotkeys  : {records['hotkeys']}")
    print(f"  presses  : {records['presses']}")
    for s in records["sends"]:
        print(f"  log_send : friend={s.get('friend')} success={s.get('success')} "
              f"duration={s.get('duration_ms')}ms")


def scenario_a(douyin_bot):
    banner("场景 A：全链路（真实 OCR + 图像匹配，动作只记录）")
    for key in records:
        records[key].clear()
    douyin_bot.run_bot_task()

    dump_records()

    checks = []
    checks.append(("悬停+点击私信入口 '消息' 落在图标附近",
                   any(near(c, SIXIN_CLICK_EXPECT, 60) for c in records["clicks"])))
    friend_hit = any(near(c, FRIEND_CLICK_EXPECT, 40) for c in records["clicks"])
    checks.append((f"点击好友 '王佳豪' 落在 {FRIEND_CLICK_EXPECT} 附近（区域偏移修复）",
                   friend_hit))
    checks.append(("无点击落在子图相对坐标 (233,321) 附近（偏移丢失会点到这里）",
                   not any(near(c, (233, 321), 40) for c in records["clicks"])))
    checks.append(("执行了 ctrl+v 粘贴", ("ctrl", "v") in records["hotkeys"]))
    checks.append(("王佳豪 已留痕（静态屏幕无聊天窗，发送失败属预期）",
                   any(s.get("friend") == "王佳豪" for s in records["sends"])))
    checks.append(("示例A/B/C 未留痕（无识别方式直接跳过）",
                   not any(s.get("friend") in ("示例A", "示例B") for s in records["sends"])))
    return checks


def scenario_b(douyin_bot):
    banner("场景 B：强制发送成功 → 退出会话兜底走 Esc")
    for key in records:
        records[key].clear()
    # 静态屏幕里没有聊天窗/发送按钮，强制发送成功以演练退出路径
    douyin_bot._send_message_with_retry = lambda recognizer, message, max_retries=3: True
    douyin_bot.run_bot_task(only_friend="王佳豪")

    dump_records()

    checks = []
    checks.append(("王佳豪 发送留痕为成功",
                   any(s.get("friend") == "王佳豪" and s.get("success") for s in records["sends"])))
    checks.append(("退出会话兜底按了 Esc", "esc" in records["presses"]))
    checks.append(("没有 alt+f4（会关掉整个抖音客户端）",
                   not any(h == ("alt", "f4") for h in records["hotkeys"])))
    return checks


def restore_screenshots():
    for path, bak in SCREENSHOT_BACKUPS.items():
        try:
            shutil.copy2(bak, path)
            os.unlink(bak)
        except Exception:
            pass


def main():
    screen = setup_virtual_screen()
    douyin_bot = install_mocks(screen)
    all_ok = True
    try:
        for name, checks in (("A", scenario_a(douyin_bot)),
                             ("B", scenario_b(douyin_bot))):
            banner(f"场景 {name} 检查结果")
            for desc, ok in checks:
                print(f"  [{'✓' if ok else '✗'}] {desc}")
                all_ok = all_ok and ok
    except Exception:
        traceback.print_exc()
        dump_records()
        all_ok = False
    finally:
        restore_screenshots()

    banner("总评")
    print("  ✅ DRY-RUN 全部通过" if all_ok else "  ❌ 存在失败项，见上")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
