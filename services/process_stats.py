# -*- coding: utf-8 -*-
"""进程统计（v7 精简版：去掉报警线程，只做按需采样）。

v6 的 process_monitor 自带常驻报警线程 + 阈值回调，实际 UI 只是每隔几秒
拉一次数字 —— 重写为无状态的按需采样，UI 想要多久拉一次自己定。
"""
import os
from typing import Dict

import psutil


def get_process_stats() -> Dict:
    """主进程 + 子进程聚合统计（内存/CPU/线程数/子进程明细）。"""
    try:
        main = psutil.Process(os.getpid())
        tree = [main] + main.children(recursive=True)
        total_mem = 0.0
        total_cpu = 0.0
        children_info = []
        for p in tree:
            try:
                with p.oneshot():
                    m = p.memory_info().rss / 1024 / 1024
                    c = p.cpu_percent(interval=0)
                    total_mem += m
                    total_cpu += c
                    children_info.append({
                        'pid': p.pid,
                        'name': p.name(),
                        'memory_mb': m,
                        'cpu_percent': c,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return {
            'main_pid': main.pid,
            'total_memory_mb': total_mem,
            'total_cpu_percent': total_cpu,
            'child_count': len(tree) - 1,
            'thread_count': main.num_threads(),
            'children': children_info,
        }
    except Exception as e:
        return {
            'main_pid': os.getpid(),
            'total_memory_mb': 0.0,
            'total_cpu_percent': 0.0,
            'child_count': 0,
            'thread_count': 0,
            'children': [],
            'error': str(e),
        }
