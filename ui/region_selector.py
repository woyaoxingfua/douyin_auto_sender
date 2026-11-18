"""屏幕区域可视化选择器

启动一个全屏透明覆盖层，让用户拖拽鼠标框选区域，然后返回 (x, y, w, h, x_pct, y_pct, w_pct, h_pct)
"""
import os
import time
import threading
import ctypes
import ctypes.wintypes
import logging
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)


# Win32
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
GetSystemMetrics = user32.GetSystemMetrics
GetDC = user32.GetDC
ReleaseDC = user32.ReleaseDC
GetDesktopWindow = user32.GetDesktopWindow
SetForegroundWindow = user32.SetForegroundWindow

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def get_screen_size() -> Tuple[int, int]:
    w = GetSystemMetrics(SM_CXVIRTUALSCREEN) or GetSystemMetrics(SM_CXSCREEN)
    h = GetSystemMetrics(SM_CYVIRTUALSCREEN) or GetSystemMetrics(SM_CYSCREEN)
    return w, h


def get_screen_origin() -> Tuple[int, int]:
    return GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN)


def region_to_pct(x, y, w, h, screen_w, screen_h):
    return {
        'x': x, 'y': y, 'w': w, 'h': h,
        'x_pct': round(x / screen_w, 4),
        'y_pct': round(y / screen_h, 4),
        'w_pct': round(w / screen_w, 4),
        'h_pct': round(h / screen_h, 4),
    }


def select_region() -> Optional[Dict]:
    """阻塞式区域选择：用户拖拽鼠标框选屏幕区域，按Esc取消

    返回 dict: {x, y, w, h, x_pct, y_pct, w_pct, h_pct, preview_path}
    或 None（用户取消）
    """
    # 最小化的Tk选择器
    try:
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image, ImageDraw, ImageGrab

        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口

        screen_w, screen_h = get_screen_size()
        origin_x, origin_y = get_screen_origin()

        # 全屏透明覆盖窗口
        overlay = tk.Toplevel(root)
        overlay.title("框选区域")
        overlay.attributes('-fullscreen', True)
        overlay.attributes('-alpha', 0.25)
        overlay.attributes('-topmost', True)
        # 透明背景
        overlay.configure(bg='black')
        overlay.config(cursor='cross')

        canvas = tk.Canvas(overlay, width=screen_w, height=screen_h,
                           bg='black', highlightthickness=0)
        canvas.pack()

        # 先截取一张屏幕作为背景
        try:
            screenshot = ImageGrab.grab(bbox=(origin_x, origin_y,
                                              origin_x + screen_w,
                                              origin_y + screen_h))
            bg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'last_screen.png')
            screenshot.save(bg_path)
        except Exception:
            bg_path = None

        # 提示文字
        info_text = tk.Label(overlay,
                             text="拖拽鼠标框选区域 · 按 Esc 取消 · 完成后回车确认",
                             font=('Microsoft YaHei', 14, 'bold'),
                             fg='#00ff88', bg='black')
        info_text.place(x=20, y=20)

        state = {'start_x': 0, 'start_y': 0, 'rect_id': None,
                 'result': None, 'confirmed': False}

        def on_press(e):
            state['start_x'] = e.x
            state['start_y'] = e.y
            if state['rect_id']:
                canvas.delete(state['rect_id'])
            state['rect_id'] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y,
                outline='#00ff88', width=2, dash=(4, 2)
            )

        def on_drag(e):
            if state['rect_id']:
                canvas.coords(state['rect_id'],
                              state['start_x'], state['start_y'], e.x, e.y)

        def on_release(e):
            x1, y1 = state['start_x'], state['start_y']
            x2, y2 = e.x, e.y
            x, y = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            if w < 10 or h < 10:
                return
            # 在原坐标基础上加上屏幕origin
            real_x = x + origin_x
            real_y = y + origin_y
            state['result'] = (real_x, real_y, w, h)

        def on_enter(e):
            if state['result']:
                state['confirmed'] = True
                overlay.quit()

        def on_esc(e):
            state['result'] = None
            state['confirmed'] = True
            overlay.quit()

        canvas.bind('<ButtonPress-1>', on_press)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_release)
        overlay.bind('<Return>', on_enter)
        overlay.bind('<Escape>', on_esc)
        info_text.focus_set()

        try:
            overlay.mainloop()
        except Exception:
            pass

        try:
            overlay.destroy()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

        if not state['result']:
            return None

        x, y, w, h = state['result']
        return {
            **region_to_pct(x, y, w, h, get_screen_size()[0], get_screen_size()[1]),
            'preview_path': bg_path,
        }

    except Exception as e:
        logger.error(f"区域选择失败: {e}")
        return None


def capture_screen_to_file(path: str) -> bool:
    """截屏保存到文件"""
    try:
        from PIL import ImageGrab
        screen_w, screen_h = get_screen_size()
        origin_x, origin_y = get_screen_origin()
        img = ImageGrab.grab(bbox=(origin_x, origin_y,
                                   origin_x + screen_w,
                                   origin_y + screen_h))
        img.save(path)
        return True
    except Exception as e:
        logger.error(f"截屏失败: {e}")
        return False


def crop_image_to_file(src_path: str, dst_path: str, x, y, w, h) -> bool:
    """从图像裁剪一块保存"""
    try:
        from PIL import Image
        img = Image.open(src_path)
        cropped = img.crop((x, y, x + w, y + h))
        cropped.save(dst_path)
        return True
    except Exception as e:
        logger.error(f"裁剪图像失败: {e}")
        return False
