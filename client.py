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


BASE_WINDOW_WIDTH = 640
BASE_WINDOW_HEIGHT = 560
MIN_WINDOW_WIDTH = 560
MIN_WINDOW_HEIGHT = 480


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
        self.root.title("时尚百货城自动化")
        self.ui_scale = self._configure_display_scaling()
        self.root.geometry(self._centered_geometry(BASE_WINDOW_WIDTH, BASE_WINDOW_HEIGHT))
        self.root.minsize(self._px(MIN_WINDOW_WIDTH), self._px(MIN_WINDOW_HEIGHT))

        config = runner.load_local_config()
        self.account = tk.StringVar(value=str(config.get("account", "")))
        self.password = tk.StringVar(value=str(config.get("password", "")))
        self.server_number = tk.StringVar(value=str(config.get("server_number", 1)))
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
        outer.rowconfigure(6, weight=1)

        ttk.Label(outer, text="时尚百货城自动化", font=("Microsoft YaHei UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, self._px(18))
        )

        ttk.Label(outer, text="游戏账号").grid(
            row=1, column=0, sticky="w", padx=(0, self._px(12)), pady=self._px(6)
        )
        self.account_entry = ttk.Entry(outer, textvariable=self.account)
        self.account_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=self._px(6))

        ttk.Label(outer, text="游戏密码").grid(
            row=2, column=0, sticky="w", padx=(0, self._px(12)), pady=self._px(6)
        )
        self.password_entry = ttk.Entry(outer, textvariable=self.password, show="•")
        self.password_entry.grid(row=2, column=1, sticky="ew", pady=self._px(6))
        ttk.Checkbutton(
            outer,
            text="显示",
            variable=self.show_password,
            command=self._toggle_password,
        ).grid(row=2, column=2, sticky="e", padx=(self._px(10), 0))

        ttk.Label(outer, text="目标区号").grid(
            row=3, column=0, sticky="w", padx=(0, self._px(12)), pady=self._px(6)
        )
        self.server_entry = ttk.Spinbox(
            outer,
            from_=1,
            to=999,
            textvariable=self.server_number,
            width=12,
        )
        self.server_entry.grid(row=3, column=1, columnspan=2, sticky="w", pady=self._px(6))

        controls = ttk.Frame(outer)
        controls.grid(
            row=4,
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
            row=5, column=0, columnspan=3, sticky="w", pady=(0, self._px(8))
        )

        log_frame = ttk.LabelFrame(outer, text="运行状态", padding=self._px(8))
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            outer,
            text="账号、密码和区号会明文保存在 runtime/config/client_config.json。",
            foreground="#666666",
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(self._px(10), 0))

        self.account_entry.focus_set()
        self.root.bind("<Return>", lambda _event: self._start())

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "•")

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

        config = runner.load_local_config()
        account = self.account.get().strip() or str(config.get("account", "")).strip()
        password = self.password.get() or str(config.get("password", ""))
        try:
            server_value = self.server_number.get().strip() or str(config.get("server_number", 1))
            server_number = int(server_value)
            runner.validate_credential(account, "账号")
            runner.validate_credential(password, "密码")
            runner.validate_server_number(server_number)
        except (RuntimeError, ValueError) as error:
            if isinstance(error, ValueError):
                error = RuntimeError("区号必须是整数。")
            messagebox.showerror("输入有误", str(error), parent=self.root)
            return

        try:
            runner.save_local_config(account, password, server_number)
        except OSError as error:
            messagebox.showerror("保存失败", f"无法写入本地配置：{error}", parent=self.root)
            return

        self.account.set(account)
        self.server_number.set(str(server_number))
        self.password.set("")
        self.show_password.set(False)
        self._toggle_password()
        self.cancel_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("正在运行")
        self._append_log("开始运行，正在查找 MuMu 模拟器……")

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(account, password, server_number, self.cancel_event),
            daemon=True,
        )
        self.worker.start()

    def _clear_config(self) -> None:
        if not messagebox.askyesno(
            "清除本地配置",
            "确定删除本地保存的账号、密码和区号吗？",
            parent=self.root,
        ):
            return
        try:
            runner.clear_local_config()
        except OSError as error:
            messagebox.showerror("删除失败", str(error), parent=self.root)
            return
        self.account.set("")
        self.password.set("")
        self.server_number.set("1")
        self._append_log("本地账号配置已删除。")

    def _run_worker(
        self,
        account: str,
        password: str,
        server_number: int,
        cancel_event: threading.Event,
    ) -> None:
        try:
            runner.run_automation(
                account,
                password,
                server_number=server_number,
                report=self._report,
                cancel_event=cancel_event,
                debug_screenshot_dir=self.debug_screenshot_dir,
            )
        except runner.AutomationCancelled as error:
            self._emit("cancelled", str(error))
        except Exception as error:
            self._emit("error", str(error))
        else:
            self._emit("done", "自动化流程已完成。")
        finally:
            password = ""

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
