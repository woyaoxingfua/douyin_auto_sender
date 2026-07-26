"""抖音进程/窗口监视：用于精准截图 + 提前给程序提供抖音窗口rect

不是只检查进程存在，而是要拿到：
  - 进程PID/名称/占用
  - 窗口句柄、窗口位置、窗口大小、是否前台、是否最小化
  - 自动等待抖音启动且窗口可见
"""
import os
import time
import logging
import ctypes
import ctypes.wintypes
from typing import Optional, Dict, List

import psutil

logger = logging.getLogger(__name__)

DOUYIN_PROCESS_NAMES = ['douyin.exe', '抖音.exe', 'douyinhelper.exe',
                        'aweme.exe', 'Aweme.exe', 'AwemePC.exe',
                        'douyinpc.exe', 'DouyinPC.exe',
                        'dyclient.exe', 'DYClient.exe']

# 抖音窗口标题关键字（任一匹配）
# 注意：不要加太宽泛的关键字（如 'dy'），否则容易误识别其他窗口
DOUYIN_WINDOW_KEYWORDS = ['抖音', 'Douyin', 'Aweme']

# 排除的窗口标题（自身 DPG 窗口、资源管理器等，避免误识别）
EXCLUDED_WINDOW_TITLES = ['Douyin Weather Assistant', '抖音天气助手', '文件资源管理器']


# ─── Win32 API 用于获取窗口位置/前台状态 ───

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
GetWindowRect = user32.GetWindowRect
GetForegroundWindow = user32.GetForegroundWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsIconic = user32.IsIconic  # 是否最小化

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)


def _enum_windows_for_pid(target_pid: int) -> List[Dict]:
    """枚举所有顶层窗口，筛选属于指定PID的窗口"""
    results: List[Dict] = []

    def callback(hwnd, lParam):
        try:
            # 拿窗口关联的PID
            pid = ctypes.wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != target_pid:
                return True
            # 必须是可见的
            if not IsWindowVisible(hwnd):
                return True
            # 拿标题
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            # 拿rect
            rect = ctypes.wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(rect))
            results.append({
                'hwnd': hwnd,
                'title': title,
                'x': rect.left,
                'y': rect.top,
                'w': rect.right - rect.left,
                'h': rect.bottom - rect.top,
                'pid': target_pid,
                'is_douyin': any(kw.lower() in title.lower() for kw in DOUYIN_WINDOW_KEYWORDS),
                'is_iconic': bool(IsIconic(hwnd)),
            })
        except Exception:
            pass
        return True

    EnumWindows(WNDENUMPROC(callback), 0)
    return results


def find_douyin_process():
    """查找抖音进程（按名称匹配）"""
    matched = []
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            proc_name = proc.info['name'].lower()
            for target in DOUYIN_PROCESS_NAMES:
                if target.lower() in proc_name:
                    matched.append((proc_name, proc.pid))
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def _find_douyin_window_by_title() -> Optional[Dict]:
    """兜底方案：枚举所有可见顶层窗口，按标题关键字匹配抖音窗口。

    当进程名匹配失败时（新版抖音改了进程名），通过窗口标题兜底。
    匹配要求标题明确含 "抖音" / "Douyin" / "Aweme" 之一，且窗口尺寸合理。
    """
    results: List[Dict] = []
    all_visible_windows: List[tuple] = []

    def callback(hwnd, lParam):
        try:
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            all_visible_windows.append((hwnd, title))

            # 排除自身 DPG 窗口
            if any(ex.lower() in title.lower() for ex in EXCLUDED_WINDOW_TITLES):
                return True

            # 标题必须明确含抖音关键字之一
            matched_keywords = [kw for kw in DOUYIN_WINDOW_KEYWORDS if kw.lower() in title.lower()]
            if not matched_keywords:
                return True

            rect = ctypes.wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # 窗口尺寸必须在合理范围内（抖音 PC 客户端不是全屏工具）
            if w < 300 or h < 300:
                return True
            # 排除异常巨大的窗口（通常是某种覆盖层/虚拟桌面工具）
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)
            if w >= screen_w or h >= screen_h:
                return True

            pid = ctypes.wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            results.append({
                'hwnd': hwnd,
                'title': title,
                'x': rect.left,
                'y': rect.top,
                'w': w,
                'h': h,
                'pid': pid.value,
                'is_douyin': True,
                'is_iconic': bool(IsIconic(hwnd)),
                'matched_keywords': matched_keywords,
            })
        except Exception:
            pass
        return True

    EnumWindows(WNDENUMPROC(callback), 0)

    if not results:
        # 诊断：列出所有可见窗口标题，帮助用户识别抖音窗口
        logger.debug(f"窗口标题兜底搜索未匹配到抖音。关键字: {DOUYIN_WINDOW_KEYWORDS}")
        logger.debug(f"当前可见顶层窗口共 {len(all_visible_windows)} 个：")
        for hwnd, title in all_visible_windows:
            logger.debug(f"  hwnd={hwnd}, title={title!r}")

    # 优先选标题含中文"抖音"的窗口，避免含"Douyin"的资源管理器等被误识别
    best = None
    best_area = 0
    for win in results:
        if '抖音' in win.get('matched_keywords', []) and not win['is_iconic']:
            area = win['w'] * win['h']
            if area > best_area:
                best = win
                best_area = area

    # 没有中文"抖音"时，再考虑 Douyin/Aweme
    if best is None:
        for win in results:
            if not win['is_iconic']:
                area = win['w'] * win['h']
                if area > best_area:
                    best = win
                    best_area = area
    return best


def find_douyin_window(proc) -> Optional[Dict]:
    """根据进程找到抖音主窗口（窗口标题包含"抖音/Douyin/Aweme"关键字）"""
    try:
        target_pid = proc.pid
    except Exception:
        return None

    # 抖音客户端常以多进程方式运行（主+helper+渲染），主窗口在主进程
    # 所以还要遍历所有子进程
    candidate_pids = {target_pid}
    try:
        for child in proc.children(recursive=True):
            try:
                candidate_pids.add(child.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    # 收集所有候选窗口（标题未必含关键字，因为抖音 UI 可能放在独立渲染进程）
    all_candidates = []
    for pid in candidate_pids:
        windows = _enum_windows_for_pid(pid)
        for win in windows:
            if win['w'] < 300 or win['h'] < 300:
                continue
            all_candidates.append(win)

    if all_candidates:
        logger.debug(f"进程 {target_pid} 及其子进程共找到 {len(all_candidates)} 个候选窗口")
        for win in all_candidates:
            logger.debug(f"  pid={win.get('pid')}, title={win['title']!r}, "
                         f"rect=({win['x']},{win['y']},{win['w']}x{win['h']}), "
                         f"is_douyin={win['is_douyin']}, is_iconic={win['is_iconic']}")

    # 优先选标题含关键字的非最小化窗口
    best = None
    best_area = 0
    for win in all_candidates:
        if win['is_douyin'] and not win['is_iconic']:
            area = win['w'] * win['h']
            if area > best_area:
                best = win
                best_area = area

    # 兜底：选最大的非最小化窗口（兼容抖音独立渲染进程窗口标题不匹配的情况）
    if best is None:
        for win in all_candidates:
            if not win['is_iconic']:
                area = win['w'] * win['h']
                if area > best_area:
                    best = win
                    best_area = area

    if best:
        logger.debug(f"按进程找到抖音窗口: {best['title']} (pid={best.get('pid')})")
        return best

    # 最后兜底：按窗口标题全局搜索
    best = _find_douyin_window_by_title()
    if best:
        logger.debug(f"进程名匹配失败，通过窗口标题找到抖音窗口: {best['title']}")

    return best


def is_douyin_running() -> bool:
    """抖音是否在运行（进程名匹配 或 窗口标题匹配）"""
    proc = find_douyin_process()
    if proc is not None:
        logger.debug(f"抖音进程已找到: {proc.info['name']} (pid={proc.pid})")
        return True
    # 进程名没匹配上，尝试按窗口标题找
    win = _find_douyin_window_by_title()
    if win:
        logger.debug(f"通过窗口标题找到抖音: {win['title']} (pid={win.get('pid')})")
        return True
    logger.debug("抖音未运行（进程名和窗口标题均未匹配）")
    return False


def is_douyin_window_ready() -> bool:
    """窗口可见 + 非最小化（进程名或窗口标题任一匹配即可）"""
    # 先尝试进程名 → 窗口
    proc = find_douyin_process()
    if proc:
        win = find_douyin_window(proc)
        if win and win['w'] > 100 and win['h'] > 100:
            return True
    # 兜底：按窗口标题全局搜索
    win = _find_douyin_window_by_title()
    return win is not None and win['w'] > 100 and win['h'] > 100


def wait_for_douyin(timeout=60, require_window=True) -> bool:
    """等待抖音进程+窗口就绪"""
    start = time.time()
    while time.time() - start < timeout:
        if not is_douyin_running():
            time.sleep(2)
            continue
        if require_window and not is_douyin_window_ready():
            time.sleep(2)
            continue
        logger.info("检测到抖音进程已启动且窗口就绪")
        return True
    logger.warning(f"等待抖音启动超时 ({timeout}秒)")
    return False


def get_douyin_info() -> Optional[Dict]:
    """获取抖音进程+窗口详细信息，供UI展示和截图使用"""
    proc = find_douyin_process()

    # 进程名没匹配上时，尝试按窗口标题找
    if not proc:
        win = _find_douyin_window_by_title()
        if not win:
            return None
        # 通过窗口的 PID 反查进程
        try:
            proc = psutil.Process(win['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc = None
        if not proc:
            # 至少返回窗口信息
            return {
                'pid': win.get('pid', 0),
                'name': '(通过窗口标题检测)',
                'memory_mb': 0.0,
                'cpu_percent': 0.0,
                'create_time': None,
                'window': {
                    'title': win['title'],
                    'x': win['x'],
                    'y': win['y'],
                    'w': win['w'],
                    'h': win['h'],
                },
            }

    info = {
        'pid': proc.pid,
        'name': proc.name(),
        'memory_mb': 0.0,
        'cpu_percent': 0.0,
        'create_time': None,
        'window': None,
    }
    try:
        with proc.oneshot():
            info['memory_mb'] = proc.memory_info().rss / 1024 / 1024
            info['cpu_percent'] = proc.cpu_percent(interval=0)
            info['create_time'] = proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    win = find_douyin_window(proc)
    if win:
        info['window'] = {
            'title': win['title'],
            'x': win['x'],
            'y': win['y'],
            'w': win['w'],
            'h': win['h'],
        }
    return info


def get_douyin_screenshot_rect() -> Optional[tuple]:
    """返回抖音窗口的 (x, y, w, h)，用于后续pyautogui.screenshot(region=...)精准截图"""
    proc = find_douyin_process()
    if proc:
        win = find_douyin_window(proc)
        if win:
            return (win['x'], win['y'], win['w'], win['h'])
    # 兜底：按窗口标题搜索
    win = _find_douyin_window_by_title()
    if win:
        return (win['x'], win['y'], win['w'], win['h'])
    return None


def is_douyin_foreground() -> bool:
    """抖音窗口是否在前台（focused）"""
    fg = GetForegroundWindow()
    if not fg:
        return False
    fg_pid = ctypes.wintypes.DWORD()
    GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))

    proc = find_douyin_process()
    if proc and fg_pid.value == proc.pid:
        return True

    # 兜底：检查前台窗口标题是否含抖音关键字
    length = GetWindowTextLengthW(fg)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(fg, buf, length + 1)
        title = buf.value
        if any(kw.lower() in title.lower() for kw in DOUYIN_WINDOW_KEYWORDS):
            return True
    return False
