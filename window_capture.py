# -*- coding: utf-8 -*-
"""窗口绑定截图模块（v7 核心改造，学 MaaNTE/ok-nte 的 AutoSplit 流派）。

与旧版（douyin_bot 全屏截图 + 屏幕绝对坐标百分比）的根本区别：
  1. 一切以【窗口句柄 HWND】为锚：窗口在哪个屏幕、被移动到哪里，
     截图区域和点击坐标都自动跟随，副屏/主屏无差别；
  2. 截图优先走 PrintWindow —— 不要求窗口在前台（抖音在副屏、
     被遮挡时也能截到画面），失败才降级 BitBlt / 全屏裁剪；
  3. 所有坐标 API 一律"窗口相对坐标"，UI 区域配置也改为窗口相对，
     从根上消除"小窗模式还在全屏找按钮"这类坐标系错乱。

截图模式（capture_mode）：
  print  : PrintWindow(PW_RENDERFULLCONTENT) 后台截图，推荐
  bitblt : GetDC+BitBlt 前台截图（print 拿到黑图时降级用）
  screen : mss 全屏裁剪窗口区域（最后保底，要求窗口可见）

DPI：进程必须 DPI aware 才能拿到真实物理像素窗口尺寸，
     否则 GetWindowRect 会被系统缩放"骗"出一个虚拟坐标。
     本模块 import 时自动设置 DPI aware，并缓存每 HWND 的缩放比。
"""
import ctypes
import ctypes.wintypes
import logging
import os
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Win32 声明 ───

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32

SetProcessDPIAware = user32.SetProcessDPIAware
SetProcessDpiAwareness = ctypes.windll.shcore.SetProcessDpiAwareness if hasattr(ctypes.windll, "shcore") else None
GetWindowRect = user32.GetWindowRect
PrintWindow = user32.PrintWindow
GetDC = user32.GetDC
ReleaseDC = user32.ReleaseDC
FindWindowW = user32.FindWindowW
GetClientRect = user32.GetClientRect
ClientToScreen = user32.ClientToScreen
IsIconic = user32.IsIconic
IsWindowVisible = user32.IsWindowVisible
IsWindow = user32.IsWindow

PW_RENDERFULLCONTENT = 0x00000002

DOUYIN_WINDOW_KEYWORDS = ['抖音', 'Douyin', 'Aweme']
EXCLUDED_WINDOW_TITLES = ['Douyin Weather Assistant', '抖音天气助手', '文件资源管理器']

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

# 进程级 DPI aware 只设置一次
_DPI_SET = False
_dpi_lock = threading.Lock()


def _ensure_dpi_aware():
    """让本进程 DPI aware：GetWindowRect/截图才能拿到物理像素坐标。"""
    global _DPI_SET
    with _dpi_lock:
        if _DPI_SET:
            return
        try:
            # Per-Monitor DPI Aware V2（失败再退到旧 API）
            if SetProcessDpiAwareness:
                try:
                    SetProcessDpiAwareness(2)
                except Exception:
                    SetProcessDpiAwareness(1)
            else:
                SetProcessDPIAware()
        except Exception:
            try:
                SetProcessDPIAware()
            except Exception:
                pass
        _DPI_SET = True


_ensure_dpi_aware()


# ─── 窗口查找（复用 douyin_monitor 的判定口径，但返回 hwnd） ───

def _get_window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_window_pid(hwnd) -> int:
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def find_douyin_hwnd() -> Optional[int]:
    """枚举顶层窗口，按标题关键字找抖音主窗口，返回 hwnd（找不到返回 None）。

    选择策略与 douyin_monitor._find_douyin_window_by_title 一致：
    优先标题含中文"抖音"且未最小化，其次 Douyin/Aweme，取面积最大者。
    """
    results = []

    def callback(hwnd, _):
        try:
            if not IsWindowVisible(hwnd):
                return True
            title = _get_window_title(hwnd)
            if not title:
                return True
            if any(ex.lower() in title.lower() for ex in EXCLUDED_WINDOW_TITLES):
                return True
            matched = [kw for kw in DOUYIN_WINDOW_KEYWORDS if kw.lower() in title.lower()]
            if not matched:
                return True
            rect = ctypes.wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(rect))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w < 300 or h < 300:
                return True
            results.append({
                'hwnd': hwnd, 'title': title, 'matched': matched,
                'x': rect.left, 'y': rect.top, 'w': w, 'h': h,
                'is_iconic': bool(IsIconic(hwnd)),
            })
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)

    best, best_area = None, 0
    for win in results:
        if '抖音' in win['matched'] and not win['is_iconic']:
            area = win['w'] * win['h']
            if area > best_area:
                best, best_area = win, area
    if best is None:
        for win in results:
            if not win['is_iconic']:
                area = win['w'] * win['h']
                if area > best_area:
                    best, best_area = win, area
    return best['hwnd'] if best else None


# ─── DWM 真实边界：GetWindowRect 拿到的是含阴影的 inflated 边框 ───

def get_window_rect(hwnd) -> Optional[Tuple[int, int, int, int]]:
    """窗口真实内容边界 (x, y, w, h)。

    Win10+ 窗口有约 7px 不可见阴影边框，GetWindowRect 会把它算进去，
    导致截图右边/下边多一圈、点击坐标系统性偏移 ~7px。
    DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS) 才是真实边界。
    """
    try:
        rect = ctypes.wintypes.RECT()
        val = dwmapi.DwmGetWindowAttribute(
            hwnd, 2, ctypes.byref(rect), ctypes.sizeof(rect))  # DWMWA_EXTENDED_FRAME_BOUNDS=2
        if val == 0:  # S_OK
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        pass
    # 老系统回退
    try:
        rect = ctypes.wintypes.RECT()
        if GetWindowRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        pass
    return None


def is_window_ready(hwnd) -> bool:
    return bool(hwnd and IsWindow(hwnd) and IsWindowVisible(hwnd) and not IsIconic(hwnd))


def move_window_to_secondary_screen(hwnd) -> bool:
    """把抖音窗口挪到副屏（学游戏辅助"不占主屏"的做法）。

    副屏 = 虚拟桌面中不在主屏范围内的那块。没有副屏时返回 False。
    挪完立即返回，不等待。
    """
    try:
        sw = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        sh = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        ox = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        oy = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        mw = user32.GetSystemMetrics(0)    # 主屏宽
        mh = user32.GetSystemMetrics(1)     # 主屏高

        # 副屏区域 = 虚拟桌面去掉主屏（简单矩形假设：副屏在右侧或上下）
        secondary = None
        if ox + sw > mw and ox + sw - mw > 300:      # 右侧有副屏
            secondary = (mw, max(0, oy), ox + sw - mw - 20, sh - 20)
        elif oy + sh > mh and oy + sh - mh > 300:    # 下/上方有副屏
            secondary = (ox, mh, sw - 20, oy + sh - mh - 20)
        elif ox < 0:                                  # 副屏在左侧
            secondary = (ox, max(0, oy), -ox - 20, sh - 20)
        if not secondary:
            logger.info("未检测到副屏，窗口保持在当前位置")
            return False

        rect = get_window_rect(hwnd)
        if not rect:
            return False
        _, _, ww, wh = rect
        # 恢复最小化并移动到副屏左上角附近，留 40px 边距
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.2)
        target_x = secondary[0] + 40
        target_y = secondary[1] + 40
        user32.SetWindowPos(hwnd, 0, target_x, target_y,
                            max(ww, 900), max(wh, 640), 0x0004)  # SWP_NOZORDER
        logger.info(f"抖音窗口已安置到副屏: ({target_x},{target_y}) 区域={secondary}")
        return True
    except Exception as e:
        logger.warning(f"移动窗口到副屏失败: {e}")
        return False


# ─── 截图核心 ───

class WindowCapture:
    """绑定单个 HWND 的截图器。

    用法：
        cap = WindowCapture.find_douyin()      # 或 WindowCapture(hwnd)
        img = cap.capture()                    # PIL Image，窗口相对坐标系
        cx, cy = cap.to_screen(200, 100)       # 窗口坐标 -> 屏幕绝对坐标（点击用）

    capture() 返回值统一为"窗口内容图"，print/bitblt 模式下含标题栏，
    screen 模式裁的是 DWM 真实边界 —— 三种模式尺寸可能有几个像素差，
    后续模板/OCR 全部跑在窗口坐标上，不受影响。
    """

    CAPTURE_PRINT = "print"
    CAPTURE_BITBLT = "bitblt"
    CAPTURE_SCREEN = "screen"

    def __init__(self, hwnd: int, capture_mode: str = CAPTURE_PRINT):
        if not IsWindow(hwnd):
            raise ValueError(f"无效的窗口句柄: {hwnd}")
        self.hwnd = hwnd
        self.capture_mode = capture_mode
        self._last_mode = None

    # ── 工厂 ──

    @classmethod
    def find_douyin(cls, timeout: float = 10) -> Optional["WindowCapture"]:
        """找抖音窗口并绑定；找不到返回 None（不抛异常，方便 UI 提示）。"""
        start = time.time()
        while time.time() - start < timeout:
            hwnd = find_douyin_hwnd()
            if hwnd:
                try:
                    return cls(hwnd)
                except ValueError:
                    pass
            time.sleep(1)
        return None

    # ── 状态 ──

    @property
    def rect(self) -> Optional[Tuple[int, int, int, int]]:
        return get_window_rect(self.hwnd)

    def is_ready(self) -> bool:
        return is_window_ready(self.hwnd)

    # ── 坐标换算 ──

    def to_screen(self, x: int, y: int) -> Tuple[int, int]:
        """窗口相对坐标 -> 屏幕绝对坐标（点击动作用）。"""
        rect = self.rect
        if not rect:
            raise RuntimeError("窗口已失效，无法换算坐标")
        return (rect[0] + int(x), rect[1] + int(y))

    # ── 截图 ──

    def capture(self):
        """截窗口内容，返回 PIL Image。

        模式自动降级：print 黑图/失败 → bitblt → screen。
        记录 _last_mode 供探针/日志诊断当前实际在用哪种方式。
        """
        errors = []

        modes = [self.capture_mode]
        if self.capture_mode != self.CAPTURE_SCREEN:
            modes.append(self.CAPTURE_BITBLT)
        modes.append(self.CAPTURE_SCREEN)

        for mode in modes:
            try:
                img = getattr(self, f"_capture_{mode}")()
                if img is not None and self._looks_valid(img):
                    self._last_mode = mode
                    return img
                errors.append(f"{mode}: invalid frame")
            except Exception as e:
                errors.append(f"{mode}: {e}")

        logger.error(f"所有截图模式均失败 hwnd={self.hwnd}: {errors}")
        return None

    @staticmethod
    def _looks_valid(img) -> bool:
        """黑图/纯色图判定：全黑说明窗口被最小化或 PrintWindow 不支持。"""
        try:
            g = img.convert("L")
            extrema = g.getextrema()
            return extrema[1] > 8  # 最高亮度 > 8 才认为不是全黑
        except Exception:
            return True

    def _capture_print(self):
        """PrintWindow 后台截图：窗口可被遮挡/在副屏，推荐模式。"""
        from PIL import Image
        rect = self.rect
        if not rect:
            return None
        w, h = rect[2], rect[3]
        if w <= 0 or h <= 0:
            return None

        hwnd_dc = GetDC(self.hwnd)
        if not hwnd_dc:
            raise RuntimeError("GetDC 失败")
        try:
            mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            gdi32.SelectObject(mfc_dc, bitmap)
            result = PrintWindow(self.hwnd, mfc_dc, PW_RENDERFULLCONTENT)
            if result == 0:
                raise RuntimeError("PrintWindow 返回 0")
            # BITMAPINFO 头 + 逐行读取
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.wintypes.DWORD),
                    ("biWidth", ctypes.wintypes.LONG),
                    ("biHeight", ctypes.wintypes.LONG),
                    ("biPlanes", ctypes.wintypes.WORD),
                    ("biBitCount", ctypes.wintypes.WORD),
                    ("biCompression", ctypes.wintypes.DWORD),
                    ("biSizeImage", ctypes.wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.wintypes.LONG),
                    ("biYPelsPerMeter", ctypes.wintypes.LONG),
                    ("biClrUsed", ctypes.wintypes.DWORD),
                    ("biClrImportant", ctypes.wintypes.DWORD),
                ]
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h  # top-down
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0  # BI_RGB

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(mfc_dc, bitmap, 0, h, buf, ctypes.byref(bmi), 0)
            return Image.frombytes("RGBA", (w, h), buf.raw).convert("RGB")
        finally:
            try:
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mfc_dc)
            except Exception:
                pass
            ReleaseDC(self.hwnd, hwnd_dc)

    def _capture_bitblt(self):
        """BitBlt 前台截图：PrintWindow 黑图时的降级模式（要求窗口可见）。"""
        from PIL import Image
        rect = self.rect
        if not rect:
            return None
        w, h = rect[2], rect[3]
        hwnd_dc = GetDC(self.hwnd)
        if not hwnd_dc:
            raise RuntimeError("GetDC 失败")
        try:
            mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            gdi32.SelectObject(mfc_dc, bitmap)
            if not gdi32.BitBlt(mfc_dc, 0, 0, w, h, hwnd_dc, 0, 0, 0x00CC0020):  # SRCCOPY
                raise RuntimeError("BitBlt 失败")

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.wintypes.DWORD),
                    ("biWidth", ctypes.wintypes.LONG),
                    ("biHeight", ctypes.wintypes.LONG),
                    ("biPlanes", ctypes.wintypes.WORD),
                    ("biBitCount", ctypes.wintypes.WORD),
                    ("biCompression", ctypes.wintypes.DWORD),
                    ("biSizeImage", ctypes.wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.wintypes.LONG),
                    ("biYPelsPerMeter", ctypes.wintypes.LONG),
                    ("biClrUsed", ctypes.wintypes.DWORD),
                    ("biClrImportant", ctypes.wintypes.DWORD),
                ]
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(mfc_dc, bitmap, 0, h, buf, ctypes.byref(bmi), 0)
            return Image.frombytes("RGBA", (w, h), buf.raw).convert("RGB")
        finally:
            try:
                gdi32.DeleteObject(bitmap)
                gdi32.DeleteDC(mfc_dc)
            except Exception:
                pass
            ReleaseDC(self.hwnd, hwnd_dc)

    def _capture_screen(self):
        """全屏裁剪保底：截 DWM 真实边界区域（窗口必须可见，可被遮挡不可最小化）。"""
        rect = self.rect
        if not rect:
            return None
        x, y, w, h = rect
        try:
            import mss
            with mss.mss() as sct:
                shot = sct.grab({'left': x, 'top': y, 'width': w, 'height': h})
                from PIL import Image
                return Image.frombytes("RGB", shot.size, shot.rgb)
        except ImportError:
            # 没装 mss：用 PIL.ImageGrab
            from PIL import ImageGrab
            return ImageGrab.grab(bbox=(x, y, x + w, y + h))


def demo_probe(save_dir: str = ".") -> dict:
    """零点击探针：只截图+分析，不做任何鼠标键盘动作。

    给 tools/capture_probe.py 调用：夜间无人值守可安全运行，
    验证 hwnd 绑定、截图模式、DWM 边界是否正常。
    """
    hwnd = find_douyin_hwnd()
    if not hwnd:
        return {"ok": False, "error": "未找到抖音窗口"}

    info = {"ok": True, "hwnd": hwnd, "title": _get_window_title(hwnd),
            "rect": get_window_rect(hwnd), "modes": {}}

    cap = WindowCapture(hwnd)
    for mode in (WindowCapture.CAPTURE_PRINT, WindowCapture.CAPTURE_BITBLT,
                 WindowCapture.CAPTURE_SCREEN):
        try:
            cap.capture_mode = mode
            img = cap.capture()
            valid = img is not None and WindowCapture._looks_valid(img)
            info["modes"][mode] = {
                "valid": valid,
                "size": (img.size if img is not None else None),
            }
            if valid:
                out = os.path.join(save_dir, f"probe_capture_{mode}.png")
                img.save(out)
                info["modes"][mode]["saved"] = out
        except Exception as e:
            info["modes"][mode] = {"valid": False, "error": str(e)}
    return info
