# -*- coding: utf-8 -*-
"""动作层：所有鼠标/键盘操作的唯一出口（v7 重写）。

设计约束：
1. 全部接受【窗口相对坐标】——调用方永远不碰屏幕绝对坐标；
2. 每个动作自带日志（含坐标换算结果），事后可从 run.log 复盘；
3. pyautogui 集中在这里配置（PAUSE/FAILSAFE），别处不再 import pyautogui。

bot.py 的节点只调这一层，测试时 mock 本模块即可完全离线。
"""
import logging
import time

import pyautogui
import pyperclip

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = True   # 鼠标甩到屏幕左上角 = 紧急停止


class WindowActions:
    """绑定一个 WindowCapture 的动作集（窗口坐标 -> 屏幕坐标由 capture 换算）。"""

    def __init__(self, capture):
        self.capture = capture

    # ─── 基础 ───

    def _to_screen(self, win_x, win_y):
        return self.capture.to_screen(int(win_x), int(win_y))

    def click(self, win_x, win_y, pause: float = 0.0):
        sx, sy = self._to_screen(win_x, win_y)
        pyautogui.click(sx, sy)
        if pause:
            time.sleep(pause)
        logger.info(f"点击 窗口({win_x},{win_y}) -> 屏幕({sx},{sy})")
        return True

    def hover(self, win_x, win_y, seconds: float = 1.0):
        sx, sy = self._to_screen(win_x, win_y)
        pyautogui.moveTo(sx, sy)
        time.sleep(seconds)
        logger.info(f"悬停 窗口({win_x},{win_y}) -> 屏幕({sx},{sy}) {seconds}s")
        return True

    def scroll(self, win_x, win_y, amount: int):
        """在窗口坐标处滚轮，amount 负=向下。"""
        sx, sy = self._to_screen(win_x, win_y)
        pyautogui.moveTo(sx, sy)
        pyautogui.scroll(amount)
        logger.info(f"滚动 窗口({win_x},{win_y}) amount={amount}")
        return True

    def press(self, key: str):
        pyautogui.press(key)
        logger.info(f"按键 {key}")
        return True

    def hotkey(self, *keys):
        pyautogui.hotkey(*keys)
        logger.info(f"组合键 {'+'.join(keys)}")
        return True

    # ─── 组合动作 ───

    def click_and_wait(self, win_x, win_y, seconds: float):
        self.click(win_x, win_y)
        time.sleep(seconds)
        return True

    def paste_text(self, win_x, win_y, text: str) -> bool:
        """点输入区 -> 清空 -> 粘贴文本。返回是否执行完成。"""
        try:
            self.click(win_x, win_y, pause=0.3)
            self.hotkey('ctrl', 'a')
            self.press('backspace')
            pyperclip.copy(text)
            time.sleep(0.2)
            self.hotkey('ctrl', 'v')
            time.sleep(0.5)
            # 粘贴验证
            pasted = pyperclip.paste()
            if pasted is not None and text[:20] and text[:20] not in pasted:
                logger.warning(f"粘贴验证失败: 期望前20字不在剪贴板中")
                return False
            logger.info(f"已粘贴消息 ({len(text)} 字)")
            return True
        except Exception as e:
            logger.error(f"粘贴失败: {e}")
            return False

    def scroll_list_top(self, win_x, win_y, rounds: int = 3):
        """在列表坐标处滚回顶部。"""
        sx, sy = self._to_screen(win_x, win_y)
        pyautogui.moveTo(sx, sy)
        for _ in range(rounds):
            pyautogui.scroll(15)
            time.sleep(0.15)
        logger.info(f"已滚回列表顶部 窗口({win_x},{win_y})")
        return True
