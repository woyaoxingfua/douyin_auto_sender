"""Mini 悬浮状态窗

使用 tkinter 实现的 always-on-top 小窗口，用于在抖音前台运行时
在屏幕边角展示当前任务状态和滚动日志。

线程安全设计：
- tkinter 在独立线程中运行自己的 mainloop，所有 tkinter 调用都在该线程内完成
- 外部线程通过 queue.Queue 传递更新请求
- 恢复主窗口/停止任务的请求通过 threading.Event 传递给 DPG 后台线程
"""
import queue
import threading
import tkinter as tk


class MiniStatusWindow:
    """一个无边框、半透明、可拖拽的悬浮状态窗，含状态行 + 滚动日志。"""

    WIDTH = 260
    HEIGHT = 240
    MAX_LOG_LINES = 50

    def __init__(self):
        self._pending = queue.Queue()
        self.restore_requested = threading.Event()
        self.stop_requested = threading.Event()
        self._ready = threading.Event()
        self._tk_thread = threading.Thread(target=self._run_tk, daemon=True)
        self._tk_thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("MiniStatusWindow 初始化超时（tkinter 不可用？）")

    # ─── tkinter 线程 ───

    def _run_tk(self):
        """在独立线程中创建 tkinter 窗口并启动 mainloop。"""
        try:
            self._root = tk.Tk()
        except tk.TclError:
            self._ready.set()
            return
        self._root.withdraw()

        self.window = tk.Toplevel(self._root)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.attributes('-alpha', 0.90)
        self.window.resizable(False, False)
        self.window.configure(bg='#1a1a1a')

        self._drag_data = {"x": 0, "y": 0}
        self._log_lines = []
        self._build_ui()
        self._bind_drag()
        self._position_bottom_right()
        self.window.withdraw()

        self._ready.set()
        self._root.after(80, self._process_pending)
        self._root.mainloop()

    def _build_ui(self):
        frame = tk.Frame(self.window, bg='#1a1a1a', padx=10, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)

        # ── 顶部标题栏 + 关闭 ──
        header = tk.Frame(frame, bg='#1a1a1a')
        header.pack(fill=tk.X)

        title = tk.Label(header, text="抖音天气助手", fg='#f59e0b',
                         bg='#1a1a1a', font=('微软雅黑', 10, 'bold'))
        title.pack(side=tk.LEFT)

        # 关闭按钮用 Button+command（可靠，不依赖 bind）
        close_btn = tk.Button(header, text="×", fg='#888888', bg='#1a1a1a',
                              font=('微软雅黑', 10), bd=0, highlightthickness=0,
                              activebackground='#2a2a2a', activeforeground='#ffffff',
                              command=self.hide)
        close_btn.pack(side=tk.RIGHT)

        # ── 状态行 ──
        self.status_label = tk.Label(
            frame, text="就绪", fg='#4caf50', bg='#1a1a1a',
            font=('微软雅黑', 10, 'bold'), anchor='w'
        )
        self.status_label.pack(fill=tk.X, pady=(4, 0))

        # ── 数据行 ──
        self.info_label = tk.Label(
            frame, text="发送: 0  |  当前: -  |  下次: -",
            fg='#cccccc', bg='#1a1a1a', font=('微软雅黑', 8), anchor='w'
        )
        self.info_label.pack(fill=tk.X)

        # ── 日志区（滚动文本）──
        log_frame = tk.Frame(frame, bg='#0d0d0d', bd=1, relief='flat')
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.log_text = tk.Text(
            log_frame, height=6, bg='#0d0d0d', fg='#aaaaaa',
            font=('Consolas', 7), bd=0, wrap='word',
            state='disabled', relief='flat'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        log_scroll = tk.Scrollbar(log_frame, command=self.log_text.yview,
                                  bg='#1a1a1a', troughcolor='#0d0d0d')
        log_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        self.log_text.config(yscrollcommand=log_scroll.set)

        # ── 底部按钮栏：用 Button+command（最可靠）──
        btn_frame = tk.Frame(frame, bg='#1a1a1a')
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        self.stop_btn = tk.Button(
            btn_frame, text="停止", fg='#ef4444', bg='#1a1a1a',
            font=('微软雅黑', 8), bd=0, highlightthickness=0,
            activebackground='#2a2a2a', activeforeground='#ffffff',
            command=self._on_stop
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))

        restore_btn = tk.Button(
            btn_frame, text="恢复主窗口", fg='#4caf50', bg='#1a1a1a',
            font=('微软雅黑', 8), bd=0, highlightthickness=0,
            activebackground='#2a2a2a', activeforeground='#ffffff',
            command=self._on_restore
        )
        restore_btn.pack(side=tk.LEFT)

    def _bind_drag(self):
        """只对非 Button 控件绑定拖拽，避免干扰按钮点击。"""
        self._bind_drag_recursive(self.window)

    def _bind_drag_recursive(self, widget):
        """递归绑定拖拽，但跳过 Button 控件（Button 用 command 处理点击）。"""
        # 跳过 Button 类型
        if not isinstance(widget, tk.Button):
            widget.bind('<Button-1>', self._on_drag_start, add='+')
            widget.bind('<B1-Motion>', self._on_drag_motion, add='+')
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x_root - self.window.winfo_x()
        self._drag_data["y"] = event.y_root - self.window.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_data["x"]
        y = event.y_root - self._drag_data["y"]
        self.window.geometry(f"+{x}+{y}")

    def _position_bottom_right(self):
        screen_width = self._root.winfo_screenwidth()
        screen_height = self._root.winfo_screenheight()
        x = screen_width - self.WIDTH - 20
        y = screen_height - self.HEIGHT - 40
        self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _process_pending(self):
        """在 tkinter 线程中定期调用：处理队列中的待执行操作。"""
        while True:
            try:
                action, data = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                if action == 'update':
                    self._do_update(data)
                    self._do_show()
                elif action == 'log':
                    self._do_append_log(data)
                elif action == 'show':
                    self._do_show()
                elif action == 'hide':
                    self._do_hide()
                elif action == 'destroy':
                    self._root.quit()
                    return
            except tk.TclError:
                pass
        self._root.after(80, self._process_pending)

    def _do_update(self, data):
        self.status_label.config(text=data['status'], fg=data['status_color'] or '#4caf50')
        self.info_label.config(
            text=f"发送: {data['today_count']}  |  当前: {data['current_friend']}  |  下次: {data['countdown']}"
        )

    def _do_append_log(self, text):
        """追加一行日志到文本区，自动滚动到底部，限制行数。"""
        self._log_lines.append(text)
        if len(self._log_lines) > self.MAX_LOG_LINES:
            self._log_lines = self._log_lines[-self.MAX_LOG_LINES:]
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.insert(tk.END, '\n'.join(self._log_lines))
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def _do_show(self):
        self.window.deiconify()
        self.window.lift()
        self.window.attributes('-topmost', True)

    def _do_hide(self):
        self.window.withdraw()

    def _on_restore(self):
        """点击 [恢复主窗口] 时调用（在 tkinter 线程中）。"""
        self._do_hide()
        self.restore_requested.set()

    def _on_stop(self):
        """点击 [停止] 时调用（在 tkinter 线程中）。"""
        self.stop_requested.set()
        self.append_log("停止按钮已点击，等待任务响应...")

    # ─── 线程安全的公共接口（可在任意线程调用） ───

    def update_status(self, status, today_count=0, current_friend="-", countdown="-", status_color=None):
        """更新状态显示。线程安全。"""
        self._pending.put(('update', {
            'status': status,
            'today_count': today_count,
            'current_friend': current_friend,
            'countdown': countdown,
            'status_color': status_color,
        }))

    def append_log(self, text):
        """追加一行日志文本。线程安全。"""
        self._pending.put(('log', text))

    def show(self):
        self._pending.put(('show', None))

    def hide(self):
        self._pending.put(('hide', None))

    def destroy(self):
        self._pending.put(('destroy', None))

    def set_restore_callback(self, callback):
        """保留兼容。"""
        self._restore_callback = callback
