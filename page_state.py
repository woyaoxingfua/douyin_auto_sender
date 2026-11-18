# -*- coding: utf-8 -*-
"""页面状态检测（v7，对应 MaaFramework 的 recognition 层）。

核心思想：**先断言状态，再决定动作**（老项目最大毛病是"无法确认当前
打开的是不是消息页"——盲目 hover 私信入口，人在小窗里找全屏的按钮）。

状态定义（基于 2026-07-28 真实截图的 OCR 验证结果）：
  HOME          抖音首页：顶部导航有「消息」入口
  MESSAGE_LIST  消息列表页：有「搜索」框 + 会话列表（含 99+ 等）
  CHAT_OPEN     某个聊天会话已打开：有「退出会话」按钮
  UNKNOWN       无法判定（弹窗遮罩/加载中/别的页面）

全部检测跑在【窗口相对坐标】的截图上（WindowCapture.capture() 的返回），
ROI 也是窗口相对比例 —— 换屏幕、改窗口大小都不受影响。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 状态常量
HOME = "HOME"
MESSAGE_LIST = "MESSAGE_LIST"
CHAT_OPEN = "CHAT_OPEN"
UNKNOWN = "UNKNOWN"

# 窗口相对 ROI（x, y, w, h 比例）——用 07-28 截图反推的安全范围
ROI_TOP_NAV = (0.60, 0.00, 0.40, 0.09)    # 顶部导航条（消息/通知/投稿）
ROI_LIST_HEAD = (0.60, 0.00, 0.40, 0.20)  # 消息列表头部（搜索框附近）
ROI_CHAT_TOP = (0.62, 0.04, 0.36, 0.12)   # 聊天窗顶部（退出会话）


def _normalize(text: str) -> str:
    """归一化：去空白、全角转半角、小写（复用 ocr_service 的口径）。"""
    if not text:
        return ""
    out = []
    for ch in str(text):
        code = ord(ch)
        if code == 0x3000:
            continue
        if 0xFF01 <= code <= 0xFF5E:
            ch = chr(code - 0xFEE0)
        out.append(ch)
    return "".join(out).replace(" ", "").replace("\t", "").replace("\n", "").lower()


def _roi_crop(img, roi):
    """按窗口相对比例裁 ROI，返回子图。"""
    if not roi:
        return img
    W, H = img.size
    x = int(roi[0] * W)
    y = int(roi[1] * H)
    w = int(roi[2] * W)
    h = int(roi[3] * H)
    # 防御性 clamp
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return img.crop((x, y, x + w, y + h))


def _ocr_blocks(img, ocr_client):
    """跑一次 OCR，返回 [(归一化文本, bbox_center)，...]（img 相对坐标）。"""
    try:
        results = ocr_client.recognize_text_with_bbox(img, region=None)
    except Exception as e:
        logger.debug(f"OCR异常: {e}")
        return []
    blocks = []
    for item in results:
        norm = _normalize(item.get("words", ""))
        if norm:
            blocks.append((norm, item.get("center", (0, 0))))
    return blocks


def _find_text(blocks, keyword: str) -> Optional[tuple]:
    """在 OCR 块里找关键词（归一化子串匹配），返回中心坐标。"""
    target = _normalize(keyword)
    for norm, center in blocks:
        if target in norm:
            return center
    return None


class PageDetector:
    """页面状态检测器：一张截图 -> 状态 + 各锚点窗口坐标。

    用法：
        det = PageDetector(ocr_client)
        state, anchors = det.detect(img)
        if state == page_state.HOME:
            click anchors['sixin_entry']
    """

    # 判定规则（顺序即优先级）：
    #   CHAT_OPEN  : ROI 内出现「退出会话」
    #   MESSAGE_LIST: 「搜索」或列表特征（99+）且没有「退出会话」
    #   HOME       : 顶部导航有「消息」（且非上面两种）
    # 特征词故意用多候选（OCR 对同一 UI 偶发不同读法）

    CHAT_EXIT_WORDS = ["退出会话", "退出"]
    SEARCH_WORDS = ["搜索", "查找"]
    # 「消息 (99+)」/「消息」列表页标题特征 —— 必须出现在列表头部 ROI，
    # 用于区分"首页顶部搜索框"和"消息列表页搜索框"
    LIST_TITLE_WORDS = ["99+", "消息("]
    HOME_NAV_WORDS = ["消息", "私信"]

    def __init__(self, ocr_client, roi_top_nav=ROI_TOP_NAV,
                 roi_list_head=ROI_LIST_HEAD, roi_chat_top=ROI_CHAT_TOP):
        self.ocr = ocr_client
        self.roi_top_nav = roi_top_nav
        self.roi_list_head = roi_list_head
        self.roi_chat_top = roi_chat_top

    def detect(self, img):
        """识别页面状态。

        返回 (state, anchors)：
          state   : HOME / MESSAGE_LIST / CHAT_OPEN / UNKNOWN
          anchors : dict，各锚点的【窗口相对】坐标：
              sixin_entry   首页私信入口（HOME 时有）
              search_box    消息列表搜索框（MESSAGE_LIST 时有）
              chat_exit     聊天窗退出按钮（CHAT_OPEN 时有）

        判定依据（7-28 真实截图验证）：
          - 首页也有顶部搜索框，所以 MESSAGE_LIST 不能只看"搜索"，
            必须同时看到「消息 (99+)」这类会话列表标题；
          - 首页右上同样有"消息"字样，CHAT 判定要先于 HOME，
            且"退出"字样只认聊天窗顶部 ROI 内的出现。
        """
        anchors = {}
        if img is None:
            return UNKNOWN, anchors

        # 1) 消息列表头部：搜索框 + 列表标题（一次 OCR）
        head_img = _roi_crop(img, self.roi_list_head)
        head_blocks = _ocr_blocks(head_img, self.ocr)
        search_center = None
        for word in self.SEARCH_WORDS:
            search_center = _find_text(head_blocks, word)
            if search_center:
                anchors['search_box'] = self._roi_to_img_coords(search_center, self.roi_list_head, img)
                break
        has_list_title = any(_find_text(head_blocks, w) for w in self.LIST_TITLE_WORDS)

        # 2) 聊天窗顶部：退出按钮（仅当不在"纯首页"形态时才可信；
        #    首页消息浮层顶部没有"退出"，所以直接判定即可）
        chat_img = _roi_crop(img, self.roi_chat_top)
        chat_blocks = _ocr_blocks(chat_img, self.ocr)
        exit_center = None
        for word in self.CHAT_EXIT_WORDS:
            exit_center = _find_text(chat_blocks, word)
            if exit_center:
                anchors['chat_exit'] = self._roi_to_img_coords(exit_center, self.roi_chat_top, img)
                break

        # 3) 状态综合（优先级：CHAT > MESSAGE_LIST > HOME > UNKNOWN）
        if exit_center:
            return CHAT_OPEN, anchors
        if search_center and has_list_title:
            return MESSAGE_LIST, anchors

        # 4) 首页私信入口（顶部导航）
        nav_img = _roi_crop(img, self.roi_top_nav)
        nav_blocks = _ocr_blocks(nav_img, self.ocr)
        sixin_center = None
        for word in self.HOME_NAV_WORDS:
            sixin_center = _find_text(nav_blocks, word)
            if sixin_center:
                anchors['sixin_entry'] = self._roi_to_img_coords(sixin_center, self.roi_top_nav, img)
                break
        if sixin_center:
            return HOME, anchors

        return UNKNOWN, anchors

    @staticmethod
    def _roi_to_img_coords(center, roi, img):
        """ROI 子图内坐标 -> 整图（窗口）相对坐标。

        v6 的教训：crop 后 OCR 返回子图内坐标，必须加回 ROI 像素偏移，
        否则所有锚点都会聚到窗口左上角。
        """
        if not center:
            return None
        W, H = img.size
        return (int(center[0] + roi[0] * W), int(center[1] + roi[1] * H))
