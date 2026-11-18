# -*- coding: utf-8 -*-
"""MaaFramework 风格的任务流水线引擎（v7）。

学 Maa 的核心执行模型（docs/en_us/3.1-PipelineProtocol.md）：

  节点生命周期：进入 -> 截图 -> 顺序探测 next 列表 -> 命中则执行其 action
  -> 进入命中节点的 next；整轮未命中且超时 -> 走 on_error 恢复链。

对本项目的映射：
  recognition  -> PageDetector.detect()（页面级状态断言）
               -> OCR 关键词定位（元素级，如找好友名/发送按钮）
  action       -> Click / InputText / PressKey / DoNothing（等待稳定）
  next         -> 候选状态节点列表（顺序探测）
  on_error     -> 恢复路由（如"找不到发送按钮 -> 先断言在聊天页"）

与 Maa JSON 声明式配置不同，这里用 Python 类定义节点（类型安全、可断点），
但执行语义保持一致：**每一步先识别确认，再动手；识别不到不硬点**。
"""
import logging
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineContext:
    """流水线共享上下文（各节点读写）。"""

    def __init__(self):
        self.data: Dict = {}
        self.history: List[str] = []          # 已执行节点名（诊断用）
        self.current_node: Optional[str] = None

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)


class PipelineNode:
    """单个流水线节点。

    子类实现：
      recognize(ctx) -> Optional[dict]
          返回 None = 未命中（继续探测 next 列表里的其他节点）；
          返回 anchors dict = 命中，anchors 会传给 action。
      action(ctx, anchors) -> bool
          返回 True = 动作成功，进入本节点 next；
          返回 False / 抛异常 = 进入本节点 on_error。
    """

    name = "base"

    def __init__(self, timeout: float = 10.0, post_delay: float = 0.5):
        self.timeout = timeout          # 作为"next 候选"被探测的总时限
        self.post_delay = post_delay    # action 后的稳定等待
        self.next: List["PipelineNode"] = []
        self.on_error: List["PipelineNode"] = []

    def recognize(self, ctx: PipelineContext) -> Optional[Dict]:
        raise NotImplementedError

    def action(self, ctx: PipelineContext, anchors: Dict) -> bool:
        return True

    def __repr__(self):
        return f"<Node:{self.name}>"


class PipelineEngine:
    """顺序探测执行器（Maa 语义：next 轮询直到超时/命中，命中即执行 action）。

    用法：
        engine = PipelineEngine(stop_check=...)
        ctx = engine.run(entry_node)
    """

    MAX_STEPS = 200          # 死循环保险丝
    POLL_INTERVAL = 0.4      # next 未命中时的轮询间隔
    RECOVER_TIMEOUT = 3.0    # on_error 恢复链的探测时限

    def __init__(self, stop_check: Optional[Callable[[], bool]] = None,
                 progress_cb: Optional[Callable] = None):
        self.stop_check = stop_check or (lambda: False)
        self.progress_cb = progress_cb

    def _report(self, **kw):
        if self.progress_cb:
            try:
                self.progress_cb(**kw)
            except Exception:
                pass

    def run(self, entry: PipelineNode, ctx: Optional[PipelineContext] = None) -> PipelineContext:
        """从 entry 起执行流水线，返回上下文（含完整 history）。"""
        ctx = ctx or PipelineContext()
        steps = 0

        # 0) 等待入口节点命中（轮询）
        hit = self._wait_hit([entry], entry.timeout, ctx)
        if hit is None:
            if self.stop_check():
                ctx.set("stopped", True)
            else:
                logger.error(f"✗ 入口节点 {entry.name} 识别超时，终止")
                ctx.set("failed_node", entry.name)
            return ctx

        # 1) 主循环：命中 -> 执行 action -> 探测 next -> 超时走 on_error
        while hit is not None:
            if self.stop_check():
                logger.info(f"⏹ 流水线收到停止请求，中断于 {ctx.current_node}")
                ctx.set("stopped", True)
                return ctx
            steps += 1
            if steps > self.MAX_STEPS:
                logger.error(f"流水线步数超限({self.MAX_STEPS})，疑似死循环，强制终止")
                ctx.set("loop_guard", True)
                return ctx

            node, anchors = hit
            ctx.current_node = node.name
            ctx.history.append(node.name)
            self._report(stage="node", node=node.name)

            if self._act(ctx, node, anchors):
                if not node.next:
                    logger.info(f"✓ 流水线完成于节点 {node.name}")
                    ctx.set("finished_node", node.name)
                    return ctx
                # next 顺序探测（Maa: Sequential Detection，命中即执行不回环）
                hit = self._wait_hit(node.next, node.timeout, ctx)
                if hit is None:
                    if self.stop_check():
                        ctx.set("stopped", True)
                        return ctx
                    hit = self._recover_hit(node, ctx)
                    if hit is None:
                        return ctx
            else:
                # action 失败 -> on_error 恢复链
                hit = self._recover_hit(node, ctx)
                if hit is None:
                    return ctx

        return ctx

    def _act(self, ctx: PipelineContext, node: PipelineNode, anchors: Dict) -> bool:
        """执行节点动作并做 post_delay 稳定等待。"""
        try:
            ok = node.action(ctx, anchors)
        except Exception as e:
            logger.error(f"节点 {node.name} action 异常: {e}")
            ok = False
        time.sleep(node.post_delay)
        if not ok:
            logger.warning(f"节点 {node.name} 动作失败")
        return ok

    def _wait_hit(self, candidates: List[PipelineNode], timeout: float,
                  ctx: PipelineContext):
        """轮询 candidates 直到某节点 recognize 命中或超时。

        返回 (node, anchors) 或 None；单轮内按序探测（Maa: Sequential Detection）。
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.stop_check():
                return None
            for node in candidates:
                try:
                    anchors = node.recognize(ctx)
                    if anchors is not None:
                        return (node, anchors)
                except Exception as e:
                    logger.debug(f"探测 {node.name} 异常: {e}")
            time.sleep(self.POLL_INTERVAL)
        return None

    def _recover_hit(self, node: PipelineNode, ctx: PipelineContext):
        """on_error 恢复链探测（短超时轮询）。

        命中返回 (node, anchors)；无恢复链或未命中则标记 failed_node 返回 None。
        """
        if not node.on_error:
            logger.error(f"✗ 节点 {node.name} 失败且无恢复路由，终止")
            ctx.set("failed_node", node.name)
            return None
        logger.warning(f"节点 {node.name} 失败/超时，进入恢复链: "
                       f"{[n.name for n in node.on_error]}")
        hit = self._wait_hit(node.on_error, self.RECOVER_TIMEOUT, ctx)
        if hit is None:
            logger.error(f"✗ 节点 {node.name} 恢复链未命中，终止")
            ctx.set("failed_node", node.name)
            return None
        return hit
