"""douyin_bot 拆分后的纯逻辑函数测试。

只覆盖不依赖 pyautogui/屏幕交互的可测函数：
- _locate_friend: 好友定位决策（OCR 文字 / 头像图片 / 都缺失）
- _build_message: 消息生成决策（天气预设 / 普通预设 / 无预设）
"""
import os
import threading

import douyin_bot
from douyin_bot import _locate_friend, _build_message


class FakeRecognizer:
    """最小化的识别器替身，仅满足 _locate_friend/_build_message 的调用需求。"""

    def __init__(self, ocr_client=None):
        self.ocr_client = ocr_client


def _make_friend(nickname="小明", avatar_image="", avatar_text="",
                 city_name="北京", location_id="101010100"):
    return {
        "nickname": nickname,
        "city_name": city_name,
        "location_id": location_id,
        "avatar_image": avatar_image,
        "avatar_text": avatar_text,
    }


# ---------------- _locate_friend ----------------

def test_locate_friend_with_avatar_text_found(monkeypatch):
    monkeypatch.setattr(douyin_bot, "find_friend_with_scrolling", lambda *a, **k: True)
    friend = _make_friend(avatar_text="小明头像")
    assert _locate_friend(FakeRecognizer(), friend) is True


def test_locate_friend_with_avatar_text_not_found(monkeypatch):
    monkeypatch.setattr(douyin_bot, "find_friend_with_scrolling", lambda *a, **k: False)
    friend = _make_friend(avatar_text="小明头像")
    assert _locate_friend(FakeRecognizer(), friend) is False


def test_locate_friend_with_avatar_path_missing_file(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    friend = _make_friend(avatar_image="friend_avatars/alice.png")
    assert _locate_friend(FakeRecognizer(), friend) is False


def test_locate_friend_with_avatar_path_found(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(douyin_bot, "find_friend_with_scrolling", lambda *a, **k: True)
    friend = _make_friend(avatar_image="friend_avatars/alice.png")
    assert _locate_friend(FakeRecognizer(), friend) is True


def test_locate_friend_without_any_recognition_method():
    friend = _make_friend(avatar_image="", avatar_text="")
    assert _locate_friend(FakeRecognizer(), friend) is False


def test_locate_friend_prefers_avatar_text_over_image(monkeypatch):
    """当 avatar_text 与 avatar_image 同时存在时，应走 avatar_text 分支。"""
    calls = []

    def fake_find(recognizer, target, **kwargs):
        calls.append(target)
        return True

    monkeypatch.setattr(douyin_bot, "find_friend_with_scrolling", fake_find)
    friend = _make_friend(avatar_text="文字头像", avatar_image="img.png")
    assert _locate_friend(FakeRecognizer(), friend) is True
    assert calls == ["文字头像"]


# ---------------- _build_message ----------------

class FakeMsgManager:
    def __init__(self, result="模板消息"):
        self._result = result
        self.format_calls = []

    def format_message(self, preset_id, variables):
        self.format_calls.append((preset_id, variables))
        return self._result


def test_build_message_returns_none_when_no_preset():
    friend = _make_friend()
    assert _build_message(FakeMsgManager(), None, friend, "host", "key") is None


def test_build_message_with_weather_preset(monkeypatch):
    friend = _make_friend(nickname="小明", city_name="北京", location_id="101010100")
    preset = {"id": "weather", "use_weather_api": True, "template": "Hi {nickname}"}
    monkeypatch.setattr(douyin_bot, "get_weather_data",
                        lambda *a, **k: "Hi 小明，北京今天晴")
    msg = _build_message(FakeMsgManager(), preset, friend, "host", "key")
    assert msg == "Hi 小明，北京今天晴"


def test_build_message_weather_request_exception_returns_none(monkeypatch):
    from requests.exceptions import RequestException

    def raise_exc(*a, **k):
        raise RequestException("network down")

    friend = _make_friend()
    preset = {"id": "weather", "use_weather_api": True, "template": "Hi {nickname}"}
    monkeypatch.setattr(douyin_bot, "get_weather_data", raise_exc)
    msg = _build_message(FakeMsgManager(), preset, friend, "host", "key")
    assert msg is None


def test_build_message_with_plain_preset_calls_format_message():
    friend = _make_friend(nickname="小红")
    preset = {"id": "greet", "use_weather_api": False, "template": "早上好 {nickname}"}
    mgr = FakeMsgManager(result="早上好 小红")
    msg = _build_message(mgr, preset, friend, "host", "key")
    assert msg == "早上好 小红"
    assert mgr.format_calls == [("greet", {"nickname": "小红"})]


# ---------------- scroll_friend_list ----------------

class FakeRecognizerWithScroll:
    def __init__(self):
        self.scroll_calls = []

    def scroll_at(self, region=None, amount=-3):
        self.scroll_calls.append((region, amount))
        return True


def test_scroll_friend_list_uses_config_amount(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_scroll_amount", lambda: -4)
    engine = FakeRecognizerWithScroll()
    douyin_bot.scroll_friend_list(engine)
    assert len(engine.scroll_calls) == 1
    assert engine.scroll_calls[0][1] == -4


def test_scroll_friend_list_with_custom_amount(monkeypatch):
    engine = FakeRecognizerWithScroll()
    douyin_bot.scroll_friend_list(engine, amount=-10)
    assert engine.scroll_calls[0][1] == -10


# ---------------- _enter_friend_list ----------------

class FakeRecognizerForEnter:
    def __init__(self, result_sequence):
        self.results = list(result_sequence)
        self.calls = []

    def get_ocr_text(self, key):
        return "消息"

    def hover_or_click(self, target_text, region=None, timeout=5, confidence=0.6, mode="auto"):
        self.calls.append((target_text, mode))
        return self.results.pop(0) if self.results else False


def test_enter_friend_list_hover_mode(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_enter_private_msg_mode", lambda: "hover")
    recognizer = FakeRecognizerForEnter([True])
    assert douyin_bot._enter_friend_list(recognizer, max_retries=1) is True
    assert recognizer.calls == [("消息", "hover")]


def test_enter_friend_list_click_mode(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_enter_private_msg_mode", lambda: "click")
    recognizer = FakeRecognizerForEnter([True])
    assert douyin_bot._enter_friend_list(recognizer, max_retries=1) is True
    assert recognizer.calls == [("消息", "click")]


def test_enter_friend_list_failure(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_enter_private_msg_mode", lambda: "auto")
    recognizer = FakeRecognizerForEnter([False, False])
    assert douyin_bot._enter_friend_list(recognizer, max_retries=2) is False
    assert len(recognizer.calls) == 2


# ---------------- _send_message_with_retry ----------------

class FakeRecognizerForSend:
    def __init__(self, click_results):
        self.click_results = list(click_results)
        self.click_calls = []
        self.ocr_texts = {"ocr_text_send": "发送"}

    def get_ocr_text(self, key):
        return self.ocr_texts.get(key, "")

    def click_element(self, target_text, region=None, timeout=5, confidence=0.6, mode=None):
        self.click_calls.append((target_text, mode))
        return self.click_results.pop(0) if self.click_results else False

    def find_element(self, target_text, region=None, timeout=5, confidence=0.6, mode=None):
        return (100, 100)


def _install_clipboard_stub(monkeypatch, expected_message):
    """模拟剪贴板：copy 保存内容，paste 返回保存内容，使 _verify_paste 通过。"""
    clipboard = {"text": ""}

    def fake_copy(text):
        clipboard["text"] = text

    def fake_paste():
        return clipboard["text"] or expected_message

    monkeypatch.setattr(douyin_bot.pyperclip, "copy", fake_copy)
    monkeypatch.setattr(douyin_bot.pyperclip, "paste", fake_paste)


def test_send_message_with_retry_image_mode(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_send_button_mode", lambda: "image")
    _install_clipboard_stub(monkeypatch, "hello")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    monkeypatch.setattr(douyin_bot.pyautogui, "click", lambda *a, **k: None)
    recognizer = FakeRecognizerForSend([True])
    assert douyin_bot._send_message_with_retry(recognizer, "hello", max_retries=1) is True
    assert recognizer.click_calls == [("发送", "image")]


def test_send_message_with_retry_ocr_mode(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_send_button_mode", lambda: "ocr")
    _install_clipboard_stub(monkeypatch, "hello")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    monkeypatch.setattr(douyin_bot.pyautogui, "click", lambda *a, **k: None)
    recognizer = FakeRecognizerForSend([True])
    assert douyin_bot._send_message_with_retry(recognizer, "hello", max_retries=1) is True
    assert recognizer.click_calls == [("发送", "ocr")]


def test_send_message_with_retry_both_mode(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_send_button_mode", lambda: "both")
    _install_clipboard_stub(monkeypatch, "hello")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    monkeypatch.setattr(douyin_bot.pyautogui, "click", lambda *a, **k: None)
    recognizer = FakeRecognizerForSend([True])
    assert douyin_bot._send_message_with_retry(recognizer, "hello", max_retries=1) is True
    assert recognizer.click_calls == [("发送", "both")]


def test_send_message_with_retry_failure(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_send_button_mode", lambda: "image")
    _install_clipboard_stub(monkeypatch, "hello")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    monkeypatch.setattr(douyin_bot.pyautogui, "click", lambda *a, **k: None)
    recognizer = FakeRecognizerForSend([False])
    assert douyin_bot._send_message_with_retry(recognizer, "hello", max_retries=1) is False


# ---------------- _exit_session ----------------

class FakeRecognizerForExit:
    def __init__(self, click_results):
        self.click_results = list(click_results)
        self.click_calls = []
        self.ocr_texts = {"ocr_text_exit": "退出会话"}

    def get_ocr_text(self, key):
        return self.ocr_texts.get(key, "")

    def click_element(self, target_text, region=None, timeout=3, confidence=0.6, mode=None):
        self.click_calls.append((target_text, mode))
        return self.click_results.pop(0) if self.click_results else False


def test_exit_session_auto_prefers_image(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_exit_session_mode", lambda: "auto")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    recognizer = FakeRecognizerForExit([True])
    douyin_bot._exit_session(recognizer)
    assert recognizer.click_calls == [("退出会话", "image")]


def test_exit_session_auto_fallback_to_ocr(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_exit_session_mode", lambda: "auto")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    recognizer = FakeRecognizerForExit([False, True])
    douyin_bot._exit_session(recognizer)
    assert recognizer.click_calls == [("退出会话", "image"), ("退出会话", "ocr")]


def test_exit_session_text_mode_uses_ocr(monkeypatch):
    monkeypatch.setattr(douyin_bot.config_store, "get_exit_session_mode", lambda: "text")
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: None)
    recognizer = FakeRecognizerForExit([True])
    douyin_bot._exit_session(recognizer)
    assert recognizer.click_calls == [("退出会话", "ocr")]


def test_exit_session_fallback_presses_escape_not_alt_f4(monkeypatch):
    """图像和 OCR 都失败时，兜底必须是 Esc —— alt+f4 会关掉整个抖音客户端，
    导致后面的好友全部失败。"""
    pressed = []
    hotkeys = []
    monkeypatch.setattr(douyin_bot.config_store, "get_exit_session_mode", lambda: "auto")
    monkeypatch.setattr(douyin_bot.pyautogui, "press", lambda k: pressed.append(k))
    monkeypatch.setattr(douyin_bot.pyautogui, "hotkey", lambda *a, **k: hotkeys.append(a))
    recognizer = FakeRecognizerForExit([False, False])
    douyin_bot._exit_session(recognizer)
    assert pressed == ["esc"]
    assert hotkeys == []  # 不能再出现 alt+f4


# ---------------- _ensure_douyin_ready（等待期间响应停止） ----------------

def test_ensure_douyin_ready_immediate(monkeypatch):
    monkeypatch.setattr(douyin_bot, "is_douyin_window_ready", lambda: True)
    assert douyin_bot._ensure_douyin_ready() is True


def test_ensure_douyin_ready_stop_during_wait(monkeypatch):
    """等待抖音启动期间收到停止请求应立即返回 False，不能干等 120 秒。"""
    monkeypatch.setattr(douyin_bot, "is_douyin_window_ready", lambda: False)
    flag = threading.Event()
    flag.set()
    douyin_bot.set_stop_flag(flag)
    try:
        assert douyin_bot._ensure_douyin_ready(timeout=120) is False
    finally:
        douyin_bot.set_stop_flag(None)


def test_ensure_douyin_ready_becomes_ready(monkeypatch):
    calls = {"n": 0}

    def become_ready():
        calls["n"] += 1
        return calls["n"] >= 2  # 第二次探测时窗口就绪

    monkeypatch.setattr(douyin_bot, "is_douyin_window_ready", become_ready)
    monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
    assert douyin_bot._ensure_douyin_ready(timeout=10) is True


# ---------------- find_friend_with_scrolling（先滚回顶部） ----------------

class FakeScrollEngine:
    def __init__(self, click_result=True):
        self.scrolls = []
        self.clicks = []

    def scroll_at(self, region=None, amount=-3):
        self.scrolls.append(amount)

    def click_element(self, target, **kwargs):
        self.clicks.append(target)
        return True


def test_find_friend_scrolls_to_top_first(monkeypatch):
    """多好友连续发送时，查找前必须先把列表滚回顶部，
    否则上一个好友查找停在列表中/底部后，排在前面的好友永远找不到。"""
    monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
    engine = FakeScrollEngine()
    assert douyin_bot.find_friend_with_scrolling(engine, "小明") is True
    # 开头的正值滚动 = 滚回顶部
    assert engine.scrolls[:2] == [20, 20]
    assert engine.clicks == ["小明"]


def test_find_friend_scroll_to_top_respects_stop(monkeypatch):
    flag = threading.Event()
    flag.set()
    douyin_bot.set_stop_flag(flag)
    try:
        engine = FakeScrollEngine()
        monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
        assert douyin_bot.find_friend_with_scrolling(engine, "小明") is False
        assert engine.clicks == []  # 停止后不应继续点击
    finally:
        douyin_bot.set_stop_flag(None)


# ---------------- _process_friend（返回语义） ----------------

class DummyRecognizer:
    pass


def _run_process_friend(monkeypatch, *, enter=True, locate=True, message="msg", send_ok=True):
    friend = _make_friend(avatar_text="小明头像")  # 带识别方式才能走到 enter/locate
    monkeypatch.setattr(douyin_bot, "_enter_friend_list", lambda r, **k: enter)
    monkeypatch.setattr(douyin_bot, "_locate_friend", lambda r, f, **k: locate)
    monkeypatch.setattr(douyin_bot, "_build_message",
                        lambda *a, **k: message)
    monkeypatch.setattr(douyin_bot, "_send_and_finalize",
                        lambda *a, **k: send_ok)
    monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
    return douyin_bot._process_friend(
        DummyRecognizer(), friend, "host", "key", FakeMsgManager(),
        {"id": "p", "use_weather_api": False, "template": "t"})


def test_process_friend_skips_before_entering_list_when_no_recognition(monkeypatch):
    """无识别方式的好友应在进入好友列表之前跳过（省一次入口点击）。"""
    entered = []
    monkeypatch.setattr(douyin_bot, "_enter_friend_list",
                        lambda r, **k: entered.append(1) or True)
    monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
    result = douyin_bot._process_friend(
        DummyRecognizer(), _make_friend(), "host", "key",
        FakeMsgManager(), None)
    assert result == 'skipped'
    assert entered == []  # 没有进入好友列表


def test_process_friend_fatal_when_cannot_enter_list(monkeypatch):
    assert _run_process_friend(monkeypatch, enter=False) == 'fatal'


def test_process_friend_skipped_when_friend_not_found(monkeypatch):
    assert _run_process_friend(monkeypatch, locate=False) == 'skipped'


def test_process_friend_skipped_when_message_empty(monkeypatch):
    assert _run_process_friend(monkeypatch, message=None) == 'skipped'


def test_process_friend_sent_on_success(monkeypatch):
    assert _run_process_friend(monkeypatch, send_ok=True) == 'sent'


def test_process_friend_failed_when_send_fails(monkeypatch):
    assert _run_process_friend(monkeypatch, send_ok=False) == 'failed'


def test_process_friend_failed_on_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("炸了")

    monkeypatch.setattr(douyin_bot, "_enter_friend_list", boom)
    monkeypatch.setattr(douyin_bot, "log_send", lambda **k: None)
    monkeypatch.setattr(douyin_bot.time, "sleep", lambda s: None)
    result = douyin_bot._process_friend(
        DummyRecognizer(), _make_friend(avatar_text="小明头像"), "host", "key",
        FakeMsgManager(), None)
    assert result == 'failed'


# ---------------- 进度回调 ----------------

def test_progress_callback_invoked():
    received = []
    douyin_bot.set_progress_callback(lambda **kw: received.append(kw))
    try:
        douyin_bot._report_progress(stage='friend', friend='小明')
        douyin_bot._report_progress(stage='done')
    finally:
        douyin_bot.set_progress_callback(None)
    assert received == [{"stage": "friend", "friend": "小明"}, {"stage": "done"}]


# ---------------- stop flag ----------------

def test_stop_flag_not_set_by_default():
    import threading
    douyin_bot.set_stop_flag(None)
    assert douyin_bot._is_stop_requested() is False


def test_stop_flag_set():
    import threading
    flag = threading.Event()
    flag.set()
    douyin_bot.set_stop_flag(flag)
    assert douyin_bot._is_stop_requested() is True
    # 清理
    douyin_bot.set_stop_flag(None)


def test_stop_flag_clear():
    import threading
    flag = threading.Event()
    douyin_bot.set_stop_flag(flag)
    assert douyin_bot._is_stop_requested() is False
    flag.set()
    assert douyin_bot._is_stop_requested() is True
    # 清理
    douyin_bot.set_stop_flag(None)
