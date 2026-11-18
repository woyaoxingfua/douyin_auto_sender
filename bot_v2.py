# -*- coding: utf-8 -*-
"""v7 自动化主流程：窗口绑定 + 状态机流水线。

与 douyin_bot.py(v6) 的本质区别：

  v6: 全屏截图 -> 固定屏幕百分比区域 -> 直接找图/OCR -> 盲目点击
  v7: 绑定抖音 HWND -> 每步先 detect 页面状态 -> 状态匹配才执行对应动作
      -> 任何一步状态不符走恢复链（回首页/回消息列表）而不是硬试

节点图（正常路径）：
  AssertHome -> EnterMessageList -> AssertMessageList -> OpenFriendChat
            -> AssertChatOpen -> PasteMessage -> ClickSend -> ExitChat -> Done

恢复路由示例：
  OpenFriendChat 找不到好友 -> next 超时 -> 回滚列表顶部重试
  AssertChatOpen 超时 -> on_error: BackToMessageList

运行入口：
  python bot_v2.py --friend 王佳豪          # 单好友（真机测试推荐先跑这个）
  python bot_v2.py --now                   # 全量
  python bot_v2.py --probe                 # 零动作探针（只截图+识别+打印状态）
"""
import argparse
import logging
import time
from typing import Dict, Optional

import pyautogui
import pyperclip

from config_store import config_store
from ocr_service import RapidLocalOCR
from page_state import PageDetector, HOME, MESSAGE_LIST, CHAT_OPEN, UNKNOWN
from pipeline import PipelineContext, PipelineEngine, PipelineNode
from send_log import log_send
from window_capture import WindowCapture, move_window_to_secondary_screen

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True

FRIEND_LIST_ROI = (0.63, 0.05, 0.35, 0.93)   # 消息页右侧会话列表
SEND_BTN_ROI = (0.60, 0.80, 0.38, 0.18)      # 聊天窗底部发送区


# ─── 状态断言节点（recognition = 页面检测，action = DoNothing） ───

class AssertPageNode(PipelineNode):
    """断言当前处于某个页面状态；命中即通过（无动作）。

    这是 Maa "先识别后行动"的直接体现：状态不对，后面的节点
    根本不会被触发，杜绝 v6 "在小窗里找全屏按钮"式的盲操作。
    """

    def __init__(self, expected_state: str, detector: PageDetector,
                 capture: WindowCapture, timeout: float = 8.0, **kw):
        super().__init__(timeout=timeout, **kw)
        self.expected = expected_state
        self.detector = detector
        self.capture = capture
        self.name = f"Assert{expected_state.title()}"

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        img = self.capture.capture()
        if img is None:
            return None
        state, anchors = self.detector.detect(img)
        ctx.set("last_state", state)
        if state == self.expected:
            return {"state": state, "anchors": anchors}
        return None


class EnterMessageListNode(PipelineNode):
    """从首页进入消息列表：点击顶部「消息」入口。"""

    name = "EnterMessageList"

    def __init__(self, detector: PageDetector, capture: WindowCapture, **kw):
        super().__init__(timeout=6.0, **kw)
        self.detector = detector
        self.capture = capture

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        img = self.capture.capture()
        if img is None:
            return None
        state, anchors = self.detector.detect(img)
        if state == HOME and anchors.get('sixin_entry'):
            return anchors
        # 已在消息列表（上次没退干净）也算命中，直接过
        if state == MESSAGE_LIST:
            return {"already_there": True}
        return None

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        if anchors.get("already_there"):
            return True
        entry = anchors.get('sixin_entry')
        if not entry:
            return False
        self._click_window(entry)
        time.sleep(1.0)   # 等列表页加载
        return True

    def _click_window(self, point):
        """窗口坐标 -> 屏幕坐标点击。"""
        sx, sy = self.capture.to_screen(*point)
        pyautogui.click(sx, sy)
        logger.info(f"点击(窗口坐标 {point} -> 屏幕 ({sx},{sy}))")


class OpenFriendChatNode(PipelineNode):
    """在消息列表里找到目标好友并打开聊天。

    容错策略（学 Maa 的 order_by + 重试）：
      1. 每次查找前把列表滚回顶部；
      2. 列表 ROI 内 OCR 找好友名；
      3. 找不到 -> 向下滚一屏重试（带步数上限）；
      4. 仍找不到 -> 判定失败（走 on_error 回消息列表）。
    """

    name = "OpenFriendChat"

    def __init__(self, detector: PageDetector, capture: WindowCapture,
                 friend_name: str, max_scroll_pages: int = 10, **kw):
        super().__init__(timeout=15.0, **kw)
        self.detector = detector
        self.capture = capture
        self.friend_name = friend_name
        self.max_scroll_pages = max_scroll_pages

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        img = self.capture.capture()
        if img is None:
            return None
        state, anchors = self.detector.detect(img)
        if state != MESSAGE_LIST:
            return None
        # 列表 ROI 内找好友名
        from page_state import _roi_crop, _ocr_blocks, _find_text, _normalize
        W, H = img.size
        list_img = _roi_crop(img, FRIEND_LIST_ROI)
        blocks = _ocr_blocks(list_img, self.detector.ocr)
        target = _find_text(blocks, self.friend_name)
        if target:
            win_x = int(FRIEND_LIST_ROI[0] * W + target[0])
            win_y = int(FRIEND_LIST_ROI[1] * H + target[1])
            return {"friend_center": (win_x, win_y)}
        return None

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        center = anchors.get("friend_center")
        if not center:
            return False
        self._click_window(center)
        time.sleep(1.5)   # 等聊天窗打开
        return True

    def _click_window(self, point):
        sx, sy = self.capture.to_screen(*point)
        pyautogui.click(sx, sy)
        logger.info(f"点击好友 {self.friend_name} @ 窗口 {point} -> 屏幕 ({sx},{sy})")

    # 列表滚动：由 engine 在 recognize 未命中时通过 timeout 轮询自然重试；
    # 轮询间隙由外部 hook 滚动 —— 简化：find 阶段在 recognize 里内联滚动
    def scroll_list(self, amount=-5):
        cx = int((FRIEND_LIST_ROI[0] + FRIEND_LIST_ROI[2] / 2) * self.capture.rect[2])
        cy = int((FRIEND_LIST_ROI[1] + FRIEND_LIST_ROI[3] / 2) * self.capture.rect[3])
        sx, sy = self.capture.to_screen(cx, cy)
        pyautogui.moveTo(sx, sy)
        pyautogui.scroll(amount)
        logger.info(f"列表滚动 {amount}")


class PasteMessageNode(PipelineNode):
    """聊天窗内粘贴消息文本。"""

    name = "PasteMessage"

    def __init__(self, capture: WindowCapture, message: str, **kw):
        super().__init__(timeout=5.0, **kw)
        self.capture = capture
        self.message = message

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        # 前置节点已断言 CHAT_OPEN；这里只确认窗口还在
        if not self.capture.is_ready():
            return None
        return {"ok": True}

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        # 点击输入区（聊天窗下半中央），粘贴文本
        rect = self.capture.rect
        if not rect:
            return False
        ix = int(rect[2] * 0.72)
        iy = int(rect[3] * 0.88)
        sx, sy = self.capture.to_screen(ix, iy)
        pyautogui.click(sx, sy)
        time.sleep(0.3)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('backspace')
        pyperclip.copy(self.message)
        time.sleep(0.2)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        logger.info(f"已粘贴消息 ({len(self.message)} 字)")
        return True


class ClickSendNode(PipelineNode):
    """点击发送按钮：ROI 内 OCR 找「发送」，找不到按回车兜底。"""

    name = "ClickSend"

    def __init__(self, detector: PageDetector, capture: WindowCapture, **kw):
        super().__init__(timeout=6.0, **kw)
        self.detector = detector
        self.capture = capture

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        img = self.capture.capture()
        if img is None:
            return None
        from page_state import _roi_crop, _ocr_blocks, _find_text
        W, H = img.size
        btn_img = _roi_crop(img, SEND_BTN_ROI)
        blocks = _ocr_blocks(btn_img, self.detector.ocr)
        center = _find_text(blocks, "发送")
        if center:
            win_x = int(SEND_BTN_ROI[0] * W + center[0])
            win_y = int(SEND_BTN_ROI[1] * H + center[1])
            return {"send_center": (win_x, win_y)}
        return None

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        center = anchors.get("send_center")
        if center:
            sx, sy = self.capture.to_screen(*center)
            pyautogui.click(sx, sy)
            logger.info(f"点击发送按钮 @ 屏幕 ({sx},{sy})")
            return True
        # OCR 没找到按钮：回车兜底（抖音输入框 Enter 即发送）
        pyautogui.press('enter')
        logger.info("未找到发送按钮，按 Enter 兜底发送")
        return True


class ExitChatNode(PipelineNode):
    """退出聊天：优先点「退出会话」，失败按 Esc。"""

    name = "ExitChat"

    def __init__(self, detector: PageDetector, capture: WindowCapture, **kw):
        super().__init__(timeout=5.0, **kw)
        self.detector = detector
        self.capture = capture

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        img = self.capture.capture()
        if img is None:
            return None
        state, anchors = self.detector.detect(img)
        if state == CHAT_OPEN and anchors.get('chat_exit'):
            return anchors
        # 已经退出来了（自动关闭）
        if state == MESSAGE_LIST:
            return {"already_out": True}
        return None

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        if anchors.get("already_out"):
            return True
        exit_pt = anchors.get('chat_exit')
        if exit_pt:
            sx, sy = self.capture.to_screen(*exit_pt)
            pyautogui.click(sx, sy)
            time.sleep(0.8)
            return True
        return False


class ScrollForFriendNode(PipelineNode):
    """恢复链节点：滚回列表顶部（给 OpenFriendChat 重试前复位用）。"""

    name = "ScrollListTop"

    def __init__(self, capture: WindowCapture, **kw):
        super().__init__(timeout=3.0, **kw)
        self.capture = capture

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        # 消息列表状态下无条件命中
        return {"scroll_to_top": True} if ctx.get("last_state") == MESSAGE_LIST else None

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        rect = self.capture.rect
        if not rect:
            return False
        cx = int((FRIEND_LIST_ROI[0] + FRIEND_LIST_ROI[2] / 2) * rect[2])
        cy = int((FRIEND_LIST_ROI[1] + FRIEND_LIST_ROI[3] / 2) * rect[3])
        sx, sy = self.capture.to_screen(cx, cy)
        pyautogui.moveTo(sx, sy)
        for _ in range(3):
            pyautogui.scroll(15)
            time.sleep(0.15)
        return True


# ─── 组装与运行 ───

def build_pipeline(capture: WindowCapture, detector: PageDetector,
                   friend_name: str, message: str) -> PipelineNode:
    """组装单好友发送流水线，返回入口节点。

    恢复链设计（Maa on_error 语义）：
      找不到好友        -> 滚回顶部重试
      聊天页断言失败    -> 回列表重找（防点了没反应/点了别人）
      粘贴/发送失败     -> 退出聊天收尾，本好友判失败
    """
    assert_home = AssertPageNode(HOME, detector, capture, timeout=6.0)
    enter_list = EnterMessageListNode(detector, capture)
    assert_list = AssertPageNode(MESSAGE_LIST, detector, capture, timeout=6.0)
    scroll_top = ScrollForFriendNode(capture)
    open_chat = OpenFriendChatNode(detector, capture, friend_name)
    assert_chat = AssertPageNode(CHAT_OPEN, detector, capture, timeout=6.0)
    paste = PasteMessageNode(capture, message)
    send = ClickSendNode(detector, capture)
    exit_chat = ExitChatNode(detector, capture)

    assert_home.next = [enter_list]
    enter_list.next = [assert_list]
    assert_list.next = [open_chat]

    open_chat.next = [assert_chat]
    open_chat.on_error = [scroll_top]          # 找不到：滚回顶部再试
    scroll_top.next = [open_chat]

    assert_chat.next = [paste]
    paste.next = [send]
    # 粘贴/发送失败：退出聊天收尾（不留悬空会话影响下一个好友）
    paste.on_error = [exit_chat]
    send.on_error = [exit_chat]

    send.next = [exit_chat]
    exit_chat.next = []   # 正常结束

    return assert_home


def run_friend(capture: WindowCapture, detector: PageDetector,
               friend: Dict, message: str, stop_check=None) -> Dict:
    """给单个好友跑一遍完整流水线，返回结果 dict。"""
    name = friend.get('nickname', '?')
    start = time.time()
    entry = build_pipeline(capture, detector, name, message)
    engine = PipelineEngine(stop_check=stop_check)
    ctx = engine.run(entry)

    duration_ms = int((time.time() - start) * 1000)
    finished = ctx.get("finished_node") == "ExitChat" or ctx.get("last_state") == MESSAGE_LIST
    result = {
        "friend": name,
        "success": bool(finished and not ctx.get("stopped")),
        "stopped": bool(ctx.get("stopped")),
        "nodes": list(ctx.history),
        "duration_ms": duration_ms,
    }
    log_send(friend=name, success=result["success"], method="v7-pipeline",
             message=message, duration_ms=duration_ms)
    logger.info(f"{'✅' if result['success'] else '❌'} {name}: "
                f"路径={ctx.history} ({duration_ms}ms)")
    return result


def build_message(friend: Dict) -> Optional[str]:
    """生成消息文本（复用 v6 的预设/天气逻辑，走纯文本预设更稳）。"""
    from message_manager import MessageManager
    mgr = MessageManager()
    preset = mgr.get_active_preset()
    if not preset:
        return None
    if preset.get('use_weather_api'):
        from weather_service import get_weather_data
        cfg = config_store.get()
        try:
            return get_weather_data(
                friend.get('city_name', ''), friend.get('nickname', ''),
                cfg.get('api_key', ''), cfg.get('api_host', ''),
                friend.get('location_id', ''), preset.get('template'))
        except Exception as e:
            logger.error(f"天气接口失败: {e}")
            return None
    return mgr.format_message(preset['id'], {"nickname": friend.get('nickname', '')})


def main():
    parser = argparse.ArgumentParser(description="v7 窗口绑定版抖音助手")
    parser.add_argument('--friend', type=str, help='指定单个好友昵称')
    parser.add_argument('--now', action='store_true', help='处理配置里全部好友')
    parser.add_argument('--probe', action='store_true', help='零动作探针：只截图+状态识别')
    parser.add_argument('--to-secondary', action='store_true',
                        help='启动时把抖音窗口挪到副屏')
    parser.add_argument('--scroll-pages', type=int, default=10)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    # 绑定窗口（10 秒内找不到直接退出，不进全屏回退模式）
    cap = WindowCapture.find_douyin(timeout=10)
    if cap is None:
        logging.error("❌ 未找到抖音窗口，v7 不做全屏回退（这正是 v6 的坑），请先打开抖音")
        return

    if args.to_secondary:
        move_window_to_secondary_screen(cap.hwnd)
        time.sleep(0.5)

    detector = PageDetector(RapidLocalOCR())

    if args.probe:
        # 零动作：截图 + 状态识别，验证窗口绑定/OCR 链路
        img = cap.capture()
        state, anchors = detector.detect(img)
        print(f"截图模式: {cap._last_mode}, 尺寸: {img.size if img else None}")
        print(f"识别状态: {state}")
        print(f"锚点(窗口坐标): {anchors}")
        img.save("last_probe.png")
        print("已保存 last_probe.png")
        return

    friends = config_store.get_friends()
    if args.friend:
        friends = [f for f in friends if f.get('nickname') == args.friend]
        if not friends:
            logging.error(f"❌ 配置中找不到好友: {args.friend}")
            return
    if not friends:
        logging.error("❌ 好友列表为空")
        return

    logging.info(f"待发送好友: {len(friends)} 人, 截图模式: {cap.capture_mode}")
    logging.info("⏳ 3 秒后开始（请勿移动鼠标）...")
    time.sleep(3)

    results = []
    for friend in friends:
        message = build_message(friend)
        if not message:
            logging.warning(f"跳过 {friend.get('nickname')}: 消息生成为空")
            continue
        results.append(run_friend(cap, detector, friend, message))

    ok = sum(1 for r in results if r["success"])
    logging.info(f"🎉 完成: 成功 {ok}/{len(results)}")
    for r in results:
        logging.info(f"  {'✓' if r['success'] else '✗'} {r['friend']} ({r['duration_ms']}ms)")


if __name__ == "__main__":
    main()
