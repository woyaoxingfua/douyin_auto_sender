import sys
import os
import types

# 把项目根目录加入 sys.path，让测试可以直接 import 顶层模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _install_stub(name, attrs=None):
    """当真实模块不可导入（无 GUI 环境等）时，注入一个最小替身，保证被测模块能 import。"""
    try:
        __import__(name)
        return
    except ImportError:
        pass

    module = types.ModuleType(name)
    for key, value in (attrs or {}).items():
        setattr(module, key, value)
    sys.modules[name] = module


# pyautogui：douyin_bot 在模块加载时即调用 pyautogui.size() / 设置 PAUSE、FAILSAFE
_install_stub("pyautogui", {
    "PAUSE": 0,
    "FAILSAFE": False,
    "size": lambda: (1920, 1080),
    "moveTo": lambda *a, **k: None,
    "scroll": lambda *a, **k: None,
    "hotkey": lambda *a, **k: None,
    "press": lambda *a, **k: None,
    "click": lambda *a, **k: None,
})

# pyperclip：仅剪贴板读写
_install_stub("pyperclip", {
    "copy": lambda *a, **k: None,
    "paste": lambda *a, **k: "",
})
