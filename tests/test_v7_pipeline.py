"""v7 离线测试：页面状态检测 + 流水线引擎（全部基于 7-28 真实截图，不碰屏幕）。

素材来源：last_screen.png 是 2026-07-28 抖音真实运行的全屏截图（1920x1080），
按 DWM 边界 (95, 11, 1730, 997) 裁出窗口内容即为"消息列表页"样本；
再用窗口相对 ROI 合成"首页"样本（裁掉消息列表特征区不可行，改用特征断言验证）。
"""
import os
import sys
import time
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from page_state import (HOME, MESSAGE_LIST, CHAT_OPEN, UNKNOWN,  # noqa: E402
                        PageDetector, _roi_crop, _normalize)
from pipeline import PipelineContext, PipelineEngine, PipelineNode  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULLSCREEN = os.path.join(PROJECT_ROOT, "last_screen.png")
WIN_RECT = (95, 11, 1730, 997)   # 7-28 run.log 记录的抖音窗口 DWM 边界


@pytest.fixture(scope="module")
def real_ocr():
    from ocr_service import RapidLocalOCR
    return RapidLocalOCR()


@pytest.fixture(scope="module")
def message_list_img():
    """7-28 全屏截图裁出抖音窗口内容 = 消息列表页样本。"""
    img = Image.open(FULLSCREEN)
    return img.crop((WIN_RECT[0], WIN_RECT[1],
                     WIN_RECT[0] + WIN_RECT[2], WIN_RECT[1] + WIN_RECT[3]))


# ---------------- 归一化 ----------------

def test_normalize_variants():
    assert _normalize("王 佳 豪") == "王佳豪"
    assert _normalize("Ａｂｃ") == "abc"
    assert _normalize(None) == ""


# ---------------- 真实截图状态识别 ----------------

@pytest.mark.skipif(not os.path.exists(FULLSCREEN),
                    reason="缺少 7-28 真实截图 last_screen.png")
def test_detect_home_with_message_flyout_from_real_screenshot(real_ocr, message_list_img):
    """7-28 截图实况：抖音首页 + 右侧消息浮层（列表含王佳豪/于翔/禾岸，
    聊天窗未打开、无"退出会话"按钮）。

    按状态判定规则应为 HOME（顶部导航有"消息"入口），而不是 MESSAGE_LIST
    ——这正是 v7 相比 v6 的关键改进：v6 把这种形态当消息页盲目操作。
    """
    det = PageDetector(real_ocr)
    state, anchors = det.detect(message_list_img)
    assert state == HOME, f"7-28 截图应为 HOME，实际 {state}"
    assert anchors.get('sixin_entry') is not None, "应定位到私信入口锚点"
    # 锚点必须在窗口范围内
    W, H = message_list_img.size
    ex, ey = anchors['sixin_entry']
    assert 0 <= ex <= W and 0 <= ey <= H


@pytest.mark.skipif(not os.path.exists(FULLSCREEN),
                    reason="缺少 7-28 真实截图 last_screen.png")
def test_anchors_not_clustered_at_origin(real_ocr, message_list_img):
    """回归 v6 坐标偏移 bug：ROI 裁剪后锚点必须加回 ROI 偏移，
    不能落在窗口左上角。"""
    det = PageDetector(real_ocr)
    state, anchors = det.detect(message_list_img)
    ex, ey = anchors['sixin_entry']
    # 私信入口在窗口顶部导航（y ~40px 量级但 x 靠右），
    # v6 偏移丢失 bug 的特征是 y 接近 0 或坐标等于 ROI 内相对值
    W, H = message_list_img.size
    assert ex > W * 0.5, f"锚点 x={ex} 异常（私信入口应在右半区）"
    assert ey >= 0 and ey < H * 0.2, "锚点 y 应在顶部导航条内"


@pytest.mark.skipif(not os.path.exists(os.path.join(PROJECT_ROOT, "last_friend_list.png")),
                    reason="缺少 7-28 消息浮层截图 last_friend_list.png")
def test_find_friend_in_message_flyout(real_ocr):
    """用 7-28 消息浮层截图（last_friend_list.png，含王佳豪/于翔/禾岸）验证
    好友查找链路：归一化 OCR 应能定位王佳豪。"""
    from PIL import Image
    img = Image.open(os.path.join(PROJECT_ROOT, "last_friend_list.png"))
    from page_state import _ocr_blocks, _find_text
    blocks = _ocr_blocks(img, real_ocr)
    assert _find_text(blocks, "王佳豪") is not None
    assert _find_text(blocks, "搜索") is not None


@pytest.mark.skipif(not os.path.exists(FULLSCREEN),
                    reason="缺少 7-28 真实截图 last_screen.png")
def test_fullscreen_is_home_not_message_list(real_ocr, message_list_img):
    """7-28 全屏截图实况是【纯首页】（右侧无消息浮层，ROI 里是视频内容和
    自家 Mini 窗）—— v7 应识别为 HOME，这正是对 v6 盲操作的修正。"""
    det = PageDetector(real_ocr)
    state, anchors = det.detect(message_list_img)
    assert state == HOME
    assert anchors.get('sixin_entry') is not None


# ---------------- 流水线引擎（纯 mock，验证 Maa 语义） ----------------

class MockNode(PipelineNode):
    """可编程 mock 节点：按脚本返回识别结果/动作结果。

    脚本耗尽后保持最后一项（模拟"稳定命中"），避免轮询把脚本吃光。
    """

    def __init__(self, name, recognize_results=None, action_results=None):
        super().__init__(timeout=0.5)
        self.name = name
        self._recognize_results = list(recognize_results or [{}])
        self._action_results = list(action_results or [True])
        self.action_calls = 0

    def recognize(self, ctx):
        if not self._recognize_results:
            return None
        if len(self._recognize_results) == 1:
            return self._recognize_results[0]
        return self._recognize_results.pop(0)

    def action(self, ctx, anchors):
        self.action_calls += 1
        if not self._action_results:
            return False
        if len(self._action_results) == 1:
            return self._action_results[0]
        return self._action_results.pop(0)


def test_pipeline_simple_chain():
    """A -> B -> C 正常路径：按序命中并执行动作。"""
    a, b, c = MockNode("A"), MockNode("B"), MockNode("C")
    a.next = [b]
    b.next = [c]
    c.next = []

    ctx = PipelineEngine().run(a)
    assert ctx.get("finished_node") == "C"
    assert [n.action_calls for n in (a, b, c)] == [1, 1, 1]


def test_pipeline_next_probe_then_hit():
    """顺序探测：前几轮 B 未命中，之后命中（模拟页面加载延迟）。

    Maa 语义：next 探测的超时预算归【当前节点】的 timeout 管
    （等待"下一个状态出现"的时限），所以 A.timeout 给足。
    """
    a, b = MockNode("A"), MockNode("B")
    a.timeout = 3.0                              # A 等 B 出现的预算
    b._recognize_results = [None, None, {}]      # B 前两轮未命中，之后稳定命中
    b.timeout = 3.0
    a.next = [b]
    b.next = []

    start = time.time()
    ctx = PipelineEngine().run(a)
    assert ctx.get("finished_node") == "B"
    assert time.time() - start >= 0.8   # 确实轮询等待了
    assert b.action_calls == 1


def test_pipeline_action_failure_goes_on_error():
    """action 失败 -> on_error 恢复链。"""
    a = MockNode("A", action_results=[False])
    recover = MockNode("Recover")
    a.on_error = [recover]
    recover.next = []

    ctx = PipelineEngine().run(a)
    assert ctx.get("finished_node") == "Recover"


def test_pipeline_timeout_no_recovery_terminates():
    """next 超时且无恢复链 -> 终止并标记 failed_node。

    新引擎语义：入口 A 命中后探测 next=[B]，B 永不命中，
    A 超时 -> A 无 on_error -> failed_node=A。
    """
    a = MockNode("A")
    b = MockNode("B", recognize_results=[None])   # 永不命中
    a.next = [b]
    a.timeout = 0.5
    b.timeout = 0.5
    b.next = []
    b.on_error = []
    a.on_error = []

    ctx = PipelineEngine().run(a)
    assert ctx.get("failed_node") == "A"


def test_pipeline_stop_check_interrupts():
    """stop_check 立刻中断流水线。"""
    a, b = MockNode("A"), MockNode("B")
    a.next = [b]
    b.next = []

    engine = PipelineEngine(stop_check=lambda: True)
    ctx = engine.run(a)
    assert ctx.get("stopped") is True
    assert b.action_calls == 0


def test_pipeline_loop_guard():
    """A->B->A 死循环触发保险丝终止。"""
    a, b = MockNode("A"), MockNode("B")
    a.next = [b]
    b.next = [a]

    engine = PipelineEngine()
    engine.MAX_STEPS = 10
    ctx = engine.run(a)
    assert ctx.get("loop_guard") is True


def test_pipeline_history_records_path():
    """history 完整记录执行路径（诊断留痕）。"""
    a, b, c = MockNode("A"), MockNode("B"), MockNode("C")
    a.next = [b]
    b.next = [c]
    c.next = []

    ctx = PipelineEngine().run(a)
    assert ctx.history == ["A", "B", "C"]


# ---------------- bot_v2 节点逻辑（mock capture/ocr） ----------------

class FakeCapture:
    """零依赖假截图器：返回预置图片，记录坐标换算。"""

    def __init__(self, img, rect=(100, 50, 1730, 997)):
        self._img = img
        self._rect = rect
        self._last_mode = "print"
        self.capture_mode = "print"

    @property
    def rect(self):
        return self._rect

    def is_ready(self):
        return True

    def capture(self):
        return self._img.copy()

    def to_screen(self, x, y):
        return (self._rect[0] + x, self._rect[1] + y)


class FakeDetector:
    """按脚本推进页面状态。"""

    def __init__(self, states):
        self._states = list(states)
        self.ocr = None

    def detect(self, img):
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]


def test_assert_page_node_only_hits_expected_state(message_list_img):
    """AssertPageNode 只在目标状态命中（v7 核心：先断言后行动）。"""
    from bot_v2 import AssertPageNode
    from page_state import MESSAGE_LIST

    det = FakeDetector([(MESSAGE_LIST, {})])
    cap = FakeCapture(message_list_img)

    node = AssertPageNode(MESSAGE_LIST, det, cap, timeout=1.0)
    assert node.recognize(PipelineContext()) is not None

    node_home = AssertPageNode("HOME", det, cap, timeout=1.0)
    assert node_home.recognize(PipelineContext()) is None


def test_enter_message_list_clicks_window_coords(message_list_img):
    """EnterMessageList 命中首页时点击的是窗口坐标换算出的屏幕坐标。"""
    from bot_v2 import EnterMessageListNode

    det = FakeDetector([(HOME, {'sixin_entry': (800, 40)})])
    cap = FakeCapture(message_list_img)

    node = EnterMessageListNode(det, cap)
    anchors = node.recognize(PipelineContext())
    assert anchors is not None

    with patch('bot_v2.pyautogui.click') as mock_click:
        with patch('bot_v2.time.sleep'):
            assert node.action(PipelineContext(), anchors) is True
        sx, sy = mock_click.call_args[0]
    # FakeCapture rect=(100,50)：窗口(800,40) -> 屏幕(900,90)
    assert (sx, sy) == (900, 90)


def test_full_v7_pipeline_with_fake_states(message_list_img):
    """端到端（mock 状态推进）：整条 v7 流水线按预期走完并点击正确位置。

    新引擎语义：入口 AssertHome 命中即执行（无动作），随后每个 next 节点
    命中即执行 action —— FakeDetector 的状态按消耗顺序推进。
    """
    from bot_v2 import build_pipeline

    states = [
        (HOME, {'sixin_entry': (800, 40)}),          # 1 AssertHome 命中
        (HOME, {'sixin_entry': (800, 40)}),          # 2 EnterMessageList 识别+点击
        (MESSAGE_LIST, {'search_box': (900, 120)}),  # 3 AssertMessageList
        (MESSAGE_LIST, {'search_box': (900, 120)}),  # 4 OpenFriendChat 识别+点击
        (CHAT_OPEN, {'chat_exit': (1500, 90)}),      # 5 AssertChatOpen
        (CHAT_OPEN, {'chat_exit': (1500, 90)}),      # 6 PasteMessage（粘贴）
        (CHAT_OPEN, {'chat_exit': (1500, 90)}),      # 7 ClickSend 识别+点击
        (CHAT_OPEN, {'chat_exit': (1500, 90)}),      # 8 ExitChat 识别+点击
        (MESSAGE_LIST, {}),                          # （如需再识别已回列表）
    ]
    det = FakeDetector(states)
    cap = FakeCapture(message_list_img, rect=(100, 50, 1730, 997))

    clicks = []
    with patch('bot_v2.pyautogui.click', side_effect=lambda x, y: clicks.append((x, y))), \
         patch('bot_v2.pyautogui.moveTo'), \
         patch('bot_v2.pyautogui.scroll'), \
         patch('bot_v2.pyautogui.press'), \
         patch('bot_v2.pyautogui.hotkey'), \
         patch('bot_v2.pyperclip.copy'), \
         patch('bot_v2.time.sleep'):
        # OpenFriendChat 需要在列表里 OCR 到好友名：让 detector 的 ocr 返回脚本
        det.ocr = FakeOcrForFriend()

        entry = build_pipeline(cap, det, "王佳豪", "测试消息")
        engine = PipelineEngine()
        ctx = engine.run(entry)

    assert ctx.get("finished_node") == "ExitChat", f"路径异常: {ctx.history}"
    # 第一个点击 = 消息入口 (100+800, 50+40)
    assert clicks[0] == (900, 90)
    # ExitChat 的点击 = 退出按钮 (100+1500, 50+90)
    assert (1600, 140) in clicks


class FakeOcrForFriend:
    """对列表 ROI 返回王佳豪位置的假 OCR。"""

    def recognize_text_with_bbox(self, img, region=None):
        # 裁剪后的小图上王佳豪在 (300, 250) —— 加回 ROI 偏移由节点完成
        return [{"words": "王佳豪", "confidence": 0.99,
                 "center": (300, 250)}]
