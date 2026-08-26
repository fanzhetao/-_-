from __future__ import annotations

import ctypes
from datetime import datetime
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import runner


APP_VERSION = (runner.BUNDLE_DIR / "VERSION").read_text(encoding="utf-8").strip()
BASE_WINDOW_WIDTH = 780
BASE_WINDOW_HEIGHT = 620
MIN_WINDOW_WIDTH = 700
MIN_WINDOW_HEIGHT = 480


def move_list_item(items: list, item, target_index: int) -> bool:
    """按对象身份移动列表项；返回顺序是否发生变化。"""
    current_index = next(
        (index for index, candidate in enumerate(items) if candidate is item),
        None,
    )
    if current_index is None or not items:
        return False
    target_index = max(0, min(int(target_index), len(items) - 1))
    if current_index == target_index:
        return False
    items.pop(current_index)
    items.insert(target_index, item)
    return True


def calculate_ui_scale(screen_width: int, screen_height: int, dpi: float) -> float:
    dpi_scale = max(dpi, 96.0) / 96.0
    resolution_scale = min(max(screen_width, 1) / 1920.0, max(screen_height, 1) / 1080.0)
    return max(1.0, min(2.0, max(dpi_scale, resolution_scale)))


def enable_windows_dpi_awareness() -> None:
    """让 Tk 在 1080p、2K、4K 和混合 DPI 显示器上保持清晰。"""
    if sys.platform != "win32":
        return

    try:
        # Windows 10 1703+：Per-Monitor v2，随窗口所在显示器使用正确 DPI。
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass

    try:
        # Windows 8.1+ 回退。
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class FashionMallClient:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"时尚百货城自动化 v{APP_VERSION}")
        self.ui_scale = self._configure_display_scaling()
        self.root.geometry(self._centered_geometry(BASE_WINDOW_WIDTH, BASE_WINDOW_HEIGHT))
        self.root.minsize(self._px(MIN_WINDOW_WIDTH), self._px(MIN_WINDOW_HEIGHT))

        account_configs = runner.load_account_configs()
        if not account_configs:
            account_configs = [
                {"account": "", "password": "", "server_number": 1, "active": True}
            ]
        self.initial_account_configs = account_configs
        self.account_rows: list[dict] = []
        self.account_widgets: list[tk.Widget] = []
        self.dragged_account_row: dict | None = None
        self.account_drag_changed = False
        self.account_drag_enabled = True
        self.show_password = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="就绪")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.cancel_event: threading.Event | None = None
        self.worker: threading.Thread | None = None
        self.closing = False
        self.log_file_lock = threading.Lock()
        log_dir = runner.RUNTIME_DIR / "debug"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.session_log_path = log_dir / f"session-{timestamp}.log"
        self.debug_screenshot_dir = log_dir / f"screenshots-{timestamp}"
        self._write_session_log("客户端已启动，会话诊断日志已开启。")

        self._build_ui()
        self._append_log(
            f"诊断日志：{self.session_log_path}",
            persist=False,
        )
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_display_scaling(self) -> float:
        self.root.update_idletasks()
        screen_width = max(self.root.winfo_screenwidth(), 1)
        screen_height = max(self.root.winfo_screenheight(), 1)
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except (tk.TclError, ValueError):
            dpi = 96.0

        # 即使 Windows 缩放被手动设为 100%，高分屏也不会显示成一个很小的窗口。
        scale = calculate_ui_scale(screen_width, screen_height, dpi)
        self.root.tk.call("tk", "scaling", (96.0 / 72.0) * scale)
        ttk.Style(self.root).configure(".", font=("Microsoft YaHei UI", 9))
        return scale

    def _px(self, value: int) -> int:
        return max(1, round(value * self.ui_scale))

    def _centered_geometry(self, width: int, height: int) -> str:
        scaled_width = min(self._px(width), round(self.root.winfo_screenwidth() * 0.9))
        scaled_height = min(self._px(height), round(self.root.winfo_screenheight() * 0.9))
        left = max(0, (self.root.winfo_screenwidth() - scaled_width) // 2)
        top = max(0, (self.root.winfo_screenheight() - scaled_height) // 2)
        return f"{scaled_width}x{scaled_height}+{left}+{top}"

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=self._px(20))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(4, weight=1)

        ttk.Label(
            outer,
            text=f"时尚百货城自动化 v{APP_VERSION}",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, self._px(18))
        )

        accounts_frame = ttk.LabelFrame(outer, text="账号队列", padding=self._px(8))
        accounts_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        accounts_frame.columnconfigure(0, weight=1)

        account_toolbar = ttk.Frame(accounts_frame)
        account_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, self._px(6)))
        account_toolbar.columnconfigure(0, weight=1)
        ttk.Label(account_toolbar, text="按顺序执行所有勾选“使用”的账号").grid(
            row=0, column=0, sticky="w"
        )
        show_button = ttk.Checkbutton(
            account_toolbar,
            text="显示密码",
            variable=self.show_password,
            command=self._toggle_password,
        )
        show_button.grid(row=0, column=1, padx=self._px(8))
        add_button = ttk.Button(
            account_toolbar,
            text="＋ 添加账号",
            command=self._add_account_row,
        )
        add_button.grid(row=0, column=2, sticky="e")
        self.account_widgets.extend((show_button, add_button))

        list_frame = ttk.Frame(accounts_frame)
        list_frame.grid(row=1, column=0, sticky="ew")
        list_frame.columnconfigure(0, weight=1)
        self.accounts_canvas = tk.Canvas(
            list_frame,
            height=self._px(150),
            highlightthickness=0,
        )
        self.accounts_canvas.grid(row=0, column=0, sticky="ew")
        accounts_scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.accounts_canvas.yview
        )
        accounts_scrollbar.grid(row=0, column=1, sticky="ns")
        self.accounts_canvas.configure(yscrollcommand=accounts_scrollbar.set)
        self.accounts_container = ttk.Frame(self.accounts_canvas)
        self.accounts_window = self.accounts_canvas.create_window(
            (0, 0), window=self.accounts_container, anchor="nw"
        )
        self.accounts_container.bind("<Configure>", self._refresh_accounts_scrollregion)
        self.accounts_canvas.bind("<Configure>", self._resize_accounts_container)
        account_header = ttk.Frame(self.accounts_container)
        account_header.pack(fill="x", pady=(0, self._px(2)))
        account_header.columnconfigure(1, weight=3)
        account_header.columnconfigure(2, weight=3)
        ttk.Label(account_header, text="顺序", width=5).grid(row=0, column=0)
        ttk.Label(account_header, text="游戏账号").grid(row=0, column=1, sticky="w", padx=self._px(3))
        ttk.Label(account_header, text="游戏密码").grid(row=0, column=2, sticky="w", padx=self._px(3))
        ttk.Label(account_header, text="区号", width=6).grid(row=0, column=3, padx=self._px(3))
        ttk.Label(account_header, text="培育档位", width=10).grid(row=0, column=4, padx=self._px(3))
        ttk.Label(account_header, text="启用", width=5).grid(row=0, column=5, padx=self._px(3))
        ttk.Label(account_header, text="操作", width=5).grid(row=0, column=6)
        for account_config in self.initial_account_configs:
            self._add_account_row(account_config)

        controls = ttk.Frame(outer)
        controls.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(self._px(14), self._px(10)),
        )
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)
        self.start_button = ttk.Button(controls, text="开始运行", command=self._start)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, self._px(6)))
        self.stop_button = ttk.Button(controls, text="停止", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=self._px(6))
        self.clear_button = ttk.Button(controls, text="清除本地配置", command=self._clear_config)
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(self._px(6), 0))

        ttk.Label(outer, textvariable=self.status, foreground="#2563eb").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(0, self._px(8))
        )

        log_frame = ttk.LabelFrame(outer, text="运行状态", padding=self._px(8))
        log_frame.grid(row=4, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            outer,
            text="账号、密码、区号和培育档位会保存在 runtime/config/client_config.json。",
            foreground="#666666",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(self._px(10), 0))

        self.account_rows[0]["account_entry"].focus_set()
        self.root.bind("<Return>", lambda _event: self._start())

    def _toggle_password(self) -> None:
        show = "" if self.show_password.get() else "•"
        for row in self.account_rows:
            row["password_entry"].configure(show=show)

    def _refresh_accounts_scrollregion(self, _event=None) -> None:
        self.accounts_canvas.configure(scrollregion=self.accounts_canvas.bbox("all"))

    def _resize_accounts_container(self, event) -> None:
        self.accounts_canvas.itemconfigure(self.accounts_window, width=event.width)

    def _add_account_row(self, values: dict | None = None) -> None:
        values = values or {}
        row_frame = ttk.Frame(self.accounts_container)
        row_frame.pack(fill="x", pady=self._px(3))
        row_frame.columnconfigure(1, weight=3)
        row_frame.columnconfigure(2, weight=3)

        account_var = tk.StringVar(value=str(values.get("account", "")))
        password_var = tk.StringVar(value=str(values.get("password", "")))
        server_var = tk.StringVar(value=str(values.get("server_number", 1)))
        cultivation_level_var = tk.StringVar(
            value=runner.normalize_cultivation_level(values.get("cultivation_level"))
        )
        active_var = tk.BooleanVar(value=bool(values.get("active", True)))

        number_label = ttk.Label(
            row_frame,
            text=f"↕ {len(self.account_rows) + 1}",
            width=5,
            cursor="fleur",
        )
        number_label.grid(row=0, column=0, padx=(0, self._px(4)))
        account_entry = ttk.Entry(row_frame, textvariable=account_var)
        account_entry.grid(row=0, column=1, sticky="ew", padx=self._px(3))
        password_entry = ttk.Entry(
            row_frame,
            textvariable=password_var,
            show="" if self.show_password.get() else "•",
        )
        password_entry.grid(row=0, column=2, sticky="ew", padx=self._px(3))
        server_entry = ttk.Spinbox(
            row_frame, from_=1, to=999, textvariable=server_var, width=6
        )
        server_entry.grid(row=0, column=3, padx=self._px(3))
        cultivation_level_box = ttk.Combobox(
            row_frame,
            textvariable=cultivation_level_var,
            values=runner.CULTIVATION_LEVELS,
            state="readonly",
            width=9,
        )
        cultivation_level_box.grid(row=0, column=4, padx=self._px(3))
        active_button = ttk.Checkbutton(row_frame, text="使用", variable=active_var)
        active_button.grid(row=0, column=5, padx=self._px(3))
        remove_button = ttk.Button(
            row_frame,
            text="删除",
            width=5,
            command=lambda frame=row_frame: self._remove_account_row(frame),
        )
        remove_button.grid(row=0, column=6, padx=(self._px(3), 0))

        row = {
            "frame": row_frame,
            "number_label": number_label,
            "account": account_var,
            "password": password_var,
            "server_number": server_var,
            "cultivation_level": cultivation_level_var,
            "active": active_var,
            "account_entry": account_entry,
            "password_entry": password_entry,
            "cultivation_level_box": cultivation_level_box,
        }
        self.account_rows.append(row)
        number_label.bind(
            "<ButtonPress-1>",
            lambda _event, frame=row_frame: self._start_account_drag(frame),
        )
        number_label.bind("<B1-Motion>", self._drag_account_row)
        number_label.bind("<ButtonRelease-1>", self._end_account_drag)
        self.account_widgets.extend(
            (
                account_entry,
                password_entry,
                server_entry,
                cultivation_level_box,
                active_button,
                remove_button,
            )
        )
        self.root.after_idle(self._scroll_accounts_to_bottom)

    def _scroll_accounts_to_bottom(self) -> None:
        self._refresh_accounts_scrollregion()
        self.accounts_canvas.yview_moveto(1.0)

    def _start_account_drag(self, frame: ttk.Frame):
        if not self.account_drag_enabled:
            return "break"
        self.dragged_account_row = next(
            (row for row in self.account_rows if row["frame"] is frame),
            None,
        )
        self.account_drag_changed = False
        return "break"

    def _drag_account_row(self, event):
        dragged_row = self.dragged_account_row
        if not self.account_drag_enabled or dragged_row is None:
            return "break"

        centers = [
            row["frame"].winfo_rooty() + row["frame"].winfo_height() // 2
            for row in self.account_rows
        ]
        if not centers:
            return "break"
        target_index = min(
            range(len(centers)),
            key=lambda index: abs(event.y_root - centers[index]),
        )
        if move_list_item(self.account_rows, dragged_row, target_index):
            self.account_drag_changed = True
            self._repack_account_rows()
        return "break"

    def _end_account_drag(self, _event=None):
        if self.dragged_account_row is not None:
            self.dragged_account_row = None
            if self.account_drag_changed:
                self._append_log("账号执行顺序已调整；点击开始后将按当前顺序执行。")
        self.account_drag_changed = False
        return "break"

    def _repack_account_rows(self) -> None:
        for row in self.account_rows:
            row["frame"].pack_forget()
        for index, row in enumerate(self.account_rows, start=1):
            row["frame"].pack(fill="x", pady=self._px(3))
            row["number_label"].configure(text=f"↕ {index}")
        self._refresh_accounts_scrollregion()

    def _remove_account_row(self, frame: ttk.Frame) -> None:
        if len(self.account_rows) == 1:
            messagebox.showinfo("至少保留一个账号", "账号列表中至少需要保留一行。", parent=self.root)
            return
        removed = next(row for row in self.account_rows if row["frame"] is frame)
        self.account_rows.remove(removed)
        for widget in frame.winfo_children():
            if widget in self.account_widgets:
                self.account_widgets.remove(widget)
        frame.destroy()
        for index, row in enumerate(self.account_rows, start=1):
            row["number_label"].configure(text=f"↕ {index}")

    def _collect_accounts(self) -> list[dict]:
        accounts = []
        for index, row in enumerate(self.account_rows, start=1):
            account = row["account"].get().strip()
            password = row["password"].get()
            try:
                server_number = int(row["server_number"].get().strip())
                runner.validate_credential(account, f"第 {index} 个账号")
                runner.validate_credential(password, f"第 {index} 个密码")
                runner.validate_server_number(server_number)
            except ValueError as error:
                raise RuntimeError(f"第 {index} 个账号的区号必须是整数。") from error
            accounts.append(
                {
                    "account": account,
                    "password": password,
                    "server_number": server_number,
                    "cultivation_level": runner.validate_cultivation_level(
                        row["cultivation_level"].get()
                    ),
                    "active": bool(row["active"].get()),
                }
            )
        if not any(item["active"] for item in accounts):
            raise RuntimeError("请至少勾选一个要使用的账号。")
        return accounts

    def _set_account_controls_state(self, state: str) -> None:
        self.account_drag_enabled = state == "normal"
        if not self.account_drag_enabled:
            self.dragged_account_row = None
            self.account_drag_changed = False
        for widget in self.account_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        if state == "normal":
            for row in self.account_rows:
                row["cultivation_level_box"].configure(state="readonly")
        for row in self.account_rows:
            row["number_label"].configure(
                cursor="fleur" if self.account_drag_enabled else "arrow"
            )

    def _write_session_log(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        line = f"{timestamp} {message.rstrip()}\n"
        try:
            with self.log_file_lock:
                with self.session_log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(line)
        except OSError:
            # 诊断日志失败不能中断自动化主流程。
            pass

    def _append_log(self, message: str, *, persist: bool = True) -> None:
        if persist:
            self._write_session_log(message)
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _emit(self, kind: str, message: str) -> None:
        self.events.put((kind, message))

    def _report(self, message: str) -> None:
        self._write_session_log(message)
        self._emit("log", message)

    def _start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        try:
            accounts = self._collect_accounts()
        except RuntimeError as error:
            messagebox.showerror("输入有误", str(error), parent=self.root)
            return

        try:
            runner.save_account_configs(accounts)
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("保存失败", f"无法写入本地配置：{error}", parent=self.root)
            return

        active_accounts = [item for item in accounts if item["active"]]
        self.cancel_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._set_account_controls_state("disabled")
        self.status.set("正在运行")
        self._append_log(
            f"开始运行，共有 {len(active_accounts)} 个已启用账号，正在查找 MuMu 模拟器……"
        )

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(active_accounts, self.cancel_event),
            daemon=True,
        )
        self.worker.start()

    def _clear_config(self) -> None:
        if not messagebox.askyesno(
            "清除本地配置",
            "确定删除本地保存的账号、密码、区号和培育档位吗？",
            parent=self.root,
        ):
            return
        try:
            runner.clear_local_config()
        except OSError as error:
            messagebox.showerror("删除失败", str(error), parent=self.root)
            return
        for row in list(self.account_rows):
            row["frame"].destroy()
        self.account_rows.clear()
        self.account_widgets = self.account_widgets[:2]
        self._add_account_row()
        self._append_log("本地账号配置已删除。")

    def _run_worker(
        self,
        accounts: list[dict],
        cancel_event: threading.Event,
    ) -> None:
        try:
            total = len(accounts)
            for index, account_config in enumerate(accounts, start=1):
                runner.ensure_not_cancelled(cancel_event)
                self._report(
                    f"[账号队列] 开始执行第 {index}/{total} 个账号（{account_config['server_number']} 区）"
                )
                completed = runner.run_automation(
                    account_config["account"],
                    account_config["password"],
                    server_number=account_config["server_number"],
                    cultivation_level=account_config.get(
                        "cultivation_level", runner.DEFAULT_CULTIVATION_LEVEL
                    ),
                    report=self._report,
                    cancel_event=cancel_event,
                    debug_screenshot_dir=self.debug_screenshot_dir / f"account-{index}",
                )
                if not completed:
                    self._emit(
                        "incomplete",
                        f"第 {index}/{total} 个账号未能完成“领取 100 活跃礼包并关闭游戏”的完整条件，账号队列已停止。",
                    )
                    return
                self._report(f"[账号队列] 第 {index}/{total} 个账号已完成，游戏已关闭")
                if index < total:
                    self._report("[账号队列] 即将重新打开游戏并执行下一个账号")
        except runner.AutomationCancelled as error:
            self._emit("cancelled", str(error))
        except Exception as error:
            self._emit("error", str(error))
        else:
            self._emit("done", f"账号队列已完成，共执行 {len(accounts)} 个账号。")

    def _stop(self) -> None:
        if self.cancel_event is None:
            return
        self.cancel_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止")
        self._append_log("已请求停止；当前识别动作结束后将退出。")

    def _finish(self, status: str, message: str) -> None:
        self.status.set(status)
        self._append_log(message)
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._set_account_controls_state("normal")
        self.cancel_event = None

    def _drain_events(self) -> None:
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "log":
                    self._append_log(message, persist=False)
                elif kind == "done":
                    self._finish("已完成", message)
                elif kind == "cancelled":
                    self._finish("已停止", message)
                elif kind == "incomplete":
                    self._finish("未完全完成", message)
                    messagebox.showwarning("账号队列已停止", message, parent=self.root)
                elif kind == "error":
                    self._finish("运行失败", f"执行失败：{message}")
                    messagebox.showerror("运行失败", message, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _on_close(self) -> None:
        if self.closing:
            return
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("确认退出", "任务仍在运行，确定停止并退出吗？", parent=self.root):
                return
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.closing = True
            self.status.set("正在停止并关闭")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._append_log("用户关闭程序，等待当前识别动作结束。")
            self.root.after(100, self._wait_for_worker_then_close)
            return
        self._finish_close()

    def _wait_for_worker_then_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100, self._wait_for_worker_then_close)
            return
        self._finish_close()

    def _finish_close(self) -> None:
        self._write_session_log("客户端正常关闭，删除本次会话日志和全部调试截图。")
        log_dir = runner.RUNTIME_DIR / "debug"
        for screenshot_dir in log_dir.glob("screenshots-*"):
            if screenshot_dir.is_dir():
                shutil.rmtree(screenshot_dir, ignore_errors=True)
        try:
            self.session_log_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.root.destroy()


def main() -> None:
    if "--self-check" in sys.argv:
        runner.distribution_self_check()
        marker_index = sys.argv.index("--self-check") + 1
        if marker_index < len(sys.argv):
            Path(sys.argv[marker_index]).write_text("ok\n", encoding="utf-8")
        return
    enable_windows_dpi_awareness()
    root = tk.Tk()
    FashionMallClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
