from __future__ import annotations

import ctypes
from datetime import datetime
from pathlib import Path
import queue
import shutil
import sys
import threading


_SELF_CHECK_MARKER: Path | None = None
if "--self-check" in sys.argv:
    marker_index = sys.argv.index("--self-check") + 1
    if marker_index < len(sys.argv):
        _SELF_CHECK_MARKER = Path(sys.argv[marker_index])
        _SELF_CHECK_MARKER.write_text("started\n", encoding="utf-8")

from fashion_mall import client_state
from fashion_mall import copy as copy_text
from fashion_mall.diagnostics import archive_recent_steps
from fashion_mall.paths import resolve_paths
from fashion_mall.ui_helpers import (
    calculate_ui_scale,
    drag_insertion_index,
    move_list_item,
)


_PATHS = resolve_paths(__file__, sys)
if not getattr(sys, "frozen", False):
    import runner
else:
    # 冻结进程统一延迟加载 runner；自检不加载 Maa 控制器，GUI 在 main 中加载。
    runner = None


APP_VERSION = _PATHS.version_path.read_text(encoding="utf-8").strip()
BASE_WINDOW_WIDTH = 780
BASE_WINDOW_HEIGHT = 620
MIN_WINDOW_WIDTH = 700
MIN_WINDOW_HEIGHT = 480
ERROR_HANDLING_NEXT_ACCOUNT = "切换到下一个账号继续"
ERROR_HANDLING_SKIP_TASK = "跳过该任务并继续执行"
ERROR_HANDLING_OPTIONS = (
    ERROR_HANDLING_NEXT_ACCOUNT,
    ERROR_HANDLING_SKIP_TASK,
)


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
        self.root.title(f"{copy_text.APP_NAME} v{APP_VERSION}")
        self.ui_scale = self._configure_display_scaling()
        self.root.geometry(self._centered_geometry(BASE_WINDOW_WIDTH, BASE_WINDOW_HEIGHT))
        self.root.minsize(self._px(MIN_WINDOW_WIDTH), self._px(MIN_WINDOW_HEIGHT))

        local_config = runner.load_local_config()
        account_configs = runner.load_account_configs(local_config)
        if not account_configs:
            account_configs = [
                {"account": "", "password": "", "server_number": 1, "active": True}
            ]
        self.initial_account_configs = account_configs
        self.account_rows: list[dict] = []
        self.account_widgets: list[tk.Widget] = []
        self.dragged_account_row: dict | None = None
        self.account_drag_start_y = 0
        self.account_drag_active = False
        self.account_drag_changed = False
        self.account_drag_enabled = True
        self.show_password = tk.BooleanVar(value=False)
        self.account_selection_summary = tk.StringVar(value="已选择 0/0 个账号")
        saved_error_handling = (
            ERROR_HANDLING_SKIP_TASK
            if runner.load_continue_on_task_error(local_config)
            else ERROR_HANDLING_NEXT_ACCOUNT
        )
        self.error_handling_mode = tk.StringVar(value=saved_error_handling)
        self.package_error_diagnostics = tk.BooleanVar(
            value=runner.load_package_error_diagnostics(local_config)
        )
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
        self._write_session_log("客户端已启动，会话日志已开启。")

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
        style = ttk.Style(self.root)
        style.configure(".", font=("Microsoft YaHei UI", 9))
        drag_border_width = max(1, round(2 * scale))
        style.configure("AccountTable.TFrame", background="#ffffff")
        style.configure(
            "AccountHeader.TFrame",
            background="#eef2f7",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "AccountHeader.TLabel",
            background="#eef2f7",
            foreground="#374151",
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="center",
        )
        style.configure(
            "AccountRow.TFrame",
            background="#ffffff",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Dragging.AccountRow.TFrame",
            borderwidth=drag_border_width,
            relief="solid",
        )
        style.configure(
            "AccountDragHandle.TLabel",
            background="#ffffff",
            foreground="#6b7280",
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="center",
        )
        style.configure(
            "Dragging.AccountDragHandle.TLabel",
            foreground="#2563eb",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.configure("AccountActive.TCheckbutton", background="#ffffff")
        style.configure(
            "AccountRemove.TButton",
            foreground="#b42318",
            padding=(4, 2),
        )
        style.configure(
            "AccountSummary.TLabel",
            foreground="#2563eb",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
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
        outer.rowconfigure(5, weight=1)

        ttk.Label(
            outer,
            text=f"{copy_text.APP_NAME} v{APP_VERSION}",
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
        ttk.Label(account_toolbar, text="拖动左侧序号调整顺序；仅执行勾选“本轮执行”的账号").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            account_toolbar,
            textvariable=self.account_selection_summary,
            style="AccountSummary.TLabel",
        ).grid(row=0, column=1, padx=(self._px(8), self._px(4)))
        show_button = ttk.Checkbutton(
            account_toolbar,
            text="显示密码",
            variable=self.show_password,
            command=self._toggle_password,
        )
        show_button.grid(row=0, column=2, padx=self._px(8))
        add_button = ttk.Button(
            account_toolbar,
            text="＋ 添加账号",
            command=self._add_account_row,
        )
        add_button.grid(row=0, column=3, sticky="e")
        self.account_widgets.extend((show_button, add_button))

        list_frame = ttk.Frame(accounts_frame, style="AccountTable.TFrame")
        list_frame.grid(row=1, column=0, sticky="ew")
        list_frame.columnconfigure(0, weight=1)
        account_header = ttk.Frame(
            list_frame,
            style="AccountHeader.TFrame",
            padding=(self._px(6), self._px(6)),
        )
        account_header.grid(row=0, column=0, sticky="ew")
        self.account_header = account_header
        account_header.columnconfigure(1, weight=3)
        account_header.columnconfigure(2, weight=3)
        header_labels = (
            "顺序",
            "账号",
            "密码",
            "目标区服",
            "培育档位",
            "本轮执行",
            "操作",
        )
        for column, label in enumerate(header_labels):
            ttk.Label(
                account_header,
                text=label,
                style="AccountHeader.TLabel",
            ).grid(
                row=0,
                column=column,
                sticky="ew",
                padx=self._px(3),
            )

        self.accounts_canvas = tk.Canvas(
            list_frame,
            height=self._px(150),
            background="#ffffff",
            borderwidth=0,
            highlightthickness=0,
        )
        self.accounts_canvas.grid(row=1, column=0, sticky="ew")
        accounts_scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.accounts_canvas.yview
        )
        accounts_scrollbar.grid(row=1, column=1, sticky="ns")
        self.accounts_canvas.configure(yscrollcommand=accounts_scrollbar.set)
        self.accounts_container = ttk.Frame(
            self.accounts_canvas,
            style="AccountTable.TFrame",
        )
        self.accounts_window = self.accounts_canvas.create_window(
            (0, 0), window=self.accounts_container, anchor="nw"
        )
        self.accounts_container.bind("<Configure>", self._refresh_accounts_scrollregion)
        self.accounts_canvas.bind("<Configure>", self._resize_accounts_container)
        for account_config in self.initial_account_configs:
            self._add_account_row(account_config)

        mode_frame = ttk.LabelFrame(outer, text="运行选项", padding=self._px(8))
        mode_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(self._px(12), 0),
        )
        ttk.Label(mode_frame, text="当遇到任务错误/异常时，").grid(
            row=0, column=0, sticky="w"
        )
        self.error_handling_mode_box = ttk.Combobox(
            mode_frame,
            textvariable=self.error_handling_mode,
            values=ERROR_HANDLING_OPTIONS,
            state="readonly",
            width=24,
        )
        self.error_handling_mode_box.grid(row=0, column=1, sticky="w")
        ttk.Label(mode_frame, text="。").grid(row=0, column=2, sticky="w")
        self.error_diagnostic_button = ttk.Checkbutton(
            mode_frame,
            text="保存错误现场：发生错误时，在 runtime/error-diagnostics 中生成错误诊断包",
            variable=self.package_error_diagnostics,
        )
        self.error_diagnostic_button.grid(
            row=1, column=0, columnspan=3, sticky="w"
        )
        self.account_widgets.extend(
            (
                self.error_handling_mode_box,
                self.error_diagnostic_button,
            )
        )

        controls = ttk.Frame(outer)
        controls.grid(
            row=3,
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
        self.stop_button = ttk.Button(controls, text="停止运行", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=self._px(6))
        self.clear_button = ttk.Button(controls, text="清除本地配置", command=self._clear_config)
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(self._px(6), 0))

        ttk.Label(outer, textvariable=self.status, foreground="#2563eb").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, self._px(8))
        )

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=self._px(8))
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            outer,
            text="账号、密码、目标区服和培育档位会保存到本地配置文件。",
            foreground="#666666",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(self._px(10), 0))

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

    def _sync_account_column_widths(self) -> None:
        """让独立表头与账号行使用同一组列宽，避免后续列发生横向错位。"""

        frames = [self.account_header, *(row["frame"] for row in self.account_rows)]
        for column in range(7):
            requested_width = max(
                (
                    widget.winfo_reqwidth()
                    for frame in frames
                    for widget in frame.grid_slaves(column=column)
                ),
                default=0,
            )
            for frame in frames:
                frame.columnconfigure(column, minsize=requested_width)

    def _update_account_selection_summary(self) -> None:
        total = len(self.account_rows)
        selected = sum(bool(row["active"].get()) for row in self.account_rows)
        self.account_selection_summary.set(f"已选择 {selected}/{total} 个账号")

    def _add_account_row(self, values: dict | None = None) -> None:
        values = values or {}
        row_frame = ttk.Frame(
            self.accounts_container,
            style="AccountRow.TFrame",
            padding=(self._px(6), self._px(5)),
        )
        row_frame.pack(fill="x", pady=(0, self._px(1)))
        row_frame.columnconfigure(1, weight=3)
        row_frame.columnconfigure(2, weight=3)

        account_var = tk.StringVar(value=str(values.get("account", "")))
        password_var = tk.StringVar(value=str(values.get("password", "")))
        server_var = tk.StringVar(value=str(values.get("server_number", 1)))
        selected_cultivation_levels = runner.normalize_cultivation_levels(
            values.get("cultivation_levels", values.get("cultivation_level"))
        )
        cultivation_level_vars = {
            level: tk.BooleanVar(value=level in selected_cultivation_levels)
            for level in runner.CULTIVATION_LEVELS
        }
        cultivation_summary_var = tk.StringVar()
        active_var = tk.BooleanVar(value=bool(values.get("active", True)))

        number_label = ttk.Label(
            row_frame,
            text=f"☰ {len(self.account_rows) + 1}",
            width=5,
            cursor="fleur",
            style="AccountDragHandle.TLabel",
        )
        number_label.grid(row=0, column=0, sticky="ew", padx=self._px(3))
        account_entry = ttk.Entry(row_frame, textvariable=account_var, width=18)
        account_entry.grid(row=0, column=1, sticky="ew", padx=self._px(3))
        password_entry = ttk.Entry(
            row_frame,
            textvariable=password_var,
            show="" if self.show_password.get() else "•",
            width=18,
        )
        password_entry.grid(row=0, column=2, sticky="ew", padx=self._px(3))
        server_entry = ttk.Spinbox(
            row_frame, from_=1, to=999, textvariable=server_var, width=6
        )
        server_entry.grid(row=0, column=3, sticky="ew", padx=self._px(3))
        cultivation_button = ttk.Menubutton(
            row_frame,
            textvariable=cultivation_summary_var,
            width=13,
        )
        cultivation_menu = tk.Menu(cultivation_button, tearoff=False)

        def update_cultivation_summary() -> None:
            abbreviations = {
                "入门培育": "入",
                "初级培育": "初",
                "中级培育": "中",
                "高级培育": "高",
            }
            selected = [
                level
                for level in runner.CULTIVATION_LEVELS
                if cultivation_level_vars[level].get()
            ]
            if len(selected) == len(runner.CULTIVATION_LEVELS):
                cultivation_summary_var.set("全部 4 项")
            elif selected:
                labels = "/".join(abbreviations[level] for level in selected)
                cultivation_summary_var.set(f"{labels}（{len(selected)}）")
            else:
                cultivation_summary_var.set("请选择")

        for level in runner.CULTIVATION_LEVELS:
            cultivation_menu.add_checkbutton(
                label=level,
                variable=cultivation_level_vars[level],
                command=update_cultivation_summary,
            )
        cultivation_button.configure(menu=cultivation_menu)
        update_cultivation_summary()
        cultivation_button.grid(row=0, column=4, sticky="ew", padx=self._px(3))
        active_button = ttk.Checkbutton(
            row_frame,
            variable=active_var,
            command=self._update_account_selection_summary,
            style="AccountActive.TCheckbutton",
        )
        active_button.grid(row=0, column=5, padx=self._px(3))
        remove_button = ttk.Button(
            row_frame,
            text="移除",
            width=5,
            style="AccountRemove.TButton",
            command=lambda frame=row_frame: self._remove_account_row(frame),
        )
        remove_button.grid(row=0, column=6, padx=(self._px(3), 0))

        row = {
            "frame": row_frame,
            "number_label": number_label,
            "account": account_var,
            "password": password_var,
            "server_number": server_var,
            "cultivation_levels": cultivation_level_vars,
            "active": active_var,
            "account_entry": account_entry,
            "password_entry": password_entry,
            "cultivation_button": cultivation_button,
        }
        self.account_rows.append(row)
        number_label.bind(
            "<ButtonPress-1>",
            lambda event, frame=row_frame: self._start_account_drag(frame, event),
        )
        number_label.bind("<B1-Motion>", self._drag_account_row)
        number_label.bind("<ButtonRelease-1>", self._end_account_drag)
        self.account_widgets.extend(
            (
                account_entry,
                password_entry,
                server_entry,
                cultivation_button,
                active_button,
                remove_button,
            )
        )
        self._update_account_selection_summary()
        self.root.after_idle(self._sync_account_column_widths)
        self.root.after_idle(self._scroll_accounts_to_bottom)

    def _scroll_accounts_to_bottom(self) -> None:
        self._refresh_accounts_scrollregion()
        self.accounts_canvas.yview_moveto(1.0)

    def _start_account_drag(self, frame: ttk.Frame, event=None):
        if not self.account_drag_enabled:
            return "break"
        self.dragged_account_row = next(
            (row for row in self.account_rows if row["frame"] is frame),
            None,
        )
        self.account_drag_start_y = event.y_root if event is not None else 0
        self.account_drag_active = False
        self.account_drag_changed = False
        return "break"

    def _set_account_drag_visual(self, row: dict, active: bool) -> None:
        row["frame"].configure(
            style="Dragging.AccountRow.TFrame" if active else "AccountRow.TFrame"
        )
        row["number_label"].configure(
            style=(
                "Dragging.AccountDragHandle.TLabel"
                if active
                else "AccountDragHandle.TLabel"
            ),
            cursor="fleur" if self.account_drag_enabled else "arrow",
        )

    def _auto_scroll_accounts(self, pointer_y: int) -> None:
        canvas_top = self.accounts_canvas.winfo_rooty()
        canvas_bottom = canvas_top + self.accounts_canvas.winfo_height()
        margin = self._px(24)
        if pointer_y < canvas_top + margin:
            self.accounts_canvas.yview_scroll(-1, "units")
            self.root.update_idletasks()
        elif pointer_y > canvas_bottom - margin:
            self.accounts_canvas.yview_scroll(1, "units")
            self.root.update_idletasks()

    def _drag_account_row(self, event):
        dragged_row = self.dragged_account_row
        if not self.account_drag_enabled or dragged_row is None:
            return "break"

        if not self.account_drag_active:
            if abs(event.y_root - self.account_drag_start_y) < self._px(6):
                return "break"
            self.account_drag_active = True
            self._set_account_drag_visual(dragged_row, True)

        self._auto_scroll_accounts(event.y_root)

        other_centers = [
            row["frame"].winfo_rooty() + row["frame"].winfo_height() // 2
            for row in self.account_rows
            if row is not dragged_row
        ]
        if not other_centers:
            return "break"
        target_index = drag_insertion_index(event.y_root, other_centers)
        if move_list_item(self.account_rows, dragged_row, target_index):
            self.account_drag_changed = True
            self._repack_account_rows()
        return "break"

    def _end_account_drag(self, _event=None):
        if self.dragged_account_row is not None:
            self._set_account_drag_visual(self.dragged_account_row, False)
            self.dragged_account_row = None
            if self.account_drag_changed:
                self._append_log("[账号队列] 执行顺序已调整；开始运行后将按当前顺序执行。")
        self.account_drag_changed = False
        self.account_drag_active = False
        return "break"

    def _repack_account_rows(self) -> None:
        for row in self.account_rows:
            row["frame"].pack_forget()
        for index, row in enumerate(self.account_rows, start=1):
            row["frame"].pack(fill="x", pady=(0, self._px(1)))
            row["number_label"].configure(text=f"☰ {index}")
        self._refresh_accounts_scrollregion()

    def _remove_account_row(self, frame: ttk.Frame) -> None:
        if len(self.account_rows) == 1:
            messagebox.showinfo("无法删除账号", "账号队列至少需要保留一个账号。", parent=self.root)
            return
        removed = next(row for row in self.account_rows if row["frame"] is frame)
        self.account_rows.remove(removed)
        for widget in frame.winfo_children():
            if widget in self.account_widgets:
                self.account_widgets.remove(widget)
        frame.destroy()
        for index, row in enumerate(self.account_rows, start=1):
            row["number_label"].configure(text=f"☰ {index}")
        self._update_account_selection_summary()
        self.root.after_idle(self._sync_account_column_widths)
        self.root.after_idle(self._refresh_accounts_scrollregion)

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
                raise RuntimeError(f"第 {index} 个账号的目标区服必须是整数。") from error
            accounts.append(
                {
                    "account": account,
                    "password": password,
                    "server_number": server_number,
                    "cultivation_levels": runner.validate_cultivation_levels(
                        [
                            level
                            for level in runner.CULTIVATION_LEVELS
                            if row["cultivation_levels"][level].get()
                        ]
                    ),
                    "active": bool(row["active"].get()),
                }
            )
        client_state.require_active_accounts(accounts)
        return accounts

    def _set_account_controls_state(self, state: str) -> None:
        self.account_drag_enabled = state == "normal"
        if not self.account_drag_enabled:
            if self.dragged_account_row is not None:
                self._set_account_drag_visual(self.dragged_account_row, False)
            self.dragged_account_row = None
            self.account_drag_active = False
            self.account_drag_changed = False
        for widget in self.account_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        self.error_handling_mode_box.configure(
            state="readonly" if state == "normal" else "disabled"
        )
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
        self.events.put((kind, copy_text.normalize_log_message(message)))

    def _report(self, message: str) -> None:
        normalized = copy_text.normalize_log_message(message)
        self._write_session_log(normalized)
        self._emit("log", normalized)

    def _start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        try:
            accounts = self._collect_accounts()
        except RuntimeError as error:
            messagebox.showerror("输入有误", str(error), parent=self.root)
            return

        error_handling_mode = self.error_handling_mode.get()
        continue_on_process_error = (
            error_handling_mode == ERROR_HANDLING_NEXT_ACCOUNT
        )
        continue_on_task_error = error_handling_mode == ERROR_HANDLING_SKIP_TASK

        try:
            runner.save_account_configs(
                accounts,
                continue_on_process_error=continue_on_process_error,
                package_error_diagnostics=bool(self.package_error_diagnostics.get()),
                continue_on_task_error=continue_on_task_error,
            )
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("配置保存失败", f"无法保存本地配置：{error}", parent=self.root)
            return

        active_accounts = client_state.require_active_accounts(accounts)
        package_error_diagnostics = bool(self.package_error_diagnostics.get())
        self.cancel_event = threading.Event()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._set_account_controls_state("disabled")
        self.status.set("正在运行")
        self._append_log(
            f"[运行] 已开始：共 {len(active_accounts)} 个已启用账号，正在查找 MuMu 模拟器……"
        )

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(
                active_accounts,
                self.cancel_event,
                continue_on_process_error,
                package_error_diagnostics,
                continue_on_task_error,
            ),
            daemon=True,
        )
        self.worker.start()

    def _clear_config(self) -> None:
        if not messagebox.askyesno(
            "清除本地配置",
            "确定删除本地保存的账号、密码、目标区服和培育档位吗？",
            parent=self.root,
        ):
            return
        try:
            runner.clear_local_config()
        except OSError as error:
            messagebox.showerror("配置清除失败", str(error), parent=self.root)
            return
        for row in list(self.account_rows):
            row["frame"].destroy()
        self.account_rows.clear()
        self.account_widgets = self.account_widgets[:2]
        self.account_widgets.extend(
            (
                self.error_handling_mode_box,
                self.error_diagnostic_button,
            )
        )
        self.error_handling_mode.set(ERROR_HANDLING_NEXT_ACCOUNT)
        self.package_error_diagnostics.set(True)
        self._add_account_row()
        self._append_log("[配置] 本地账号配置已清除。")

    def _run_worker(
        self,
        accounts: list[dict],
        cancel_event: threading.Event,
        continue_on_process_error: bool = False,
        package_error_diagnostics: bool = True,
        continue_on_task_error: bool = False,
    ) -> None:
        diagnostic_context = None
        diagnostic_attempted = False

        def package_current_error(error_message: str, *, force: bool = False):
            nonlocal diagnostic_attempted
            diagnostic_attempted = True
            if (not package_error_diagnostics and not force) or diagnostic_context is None:
                return None
            account_config, account_index, account_screenshot_dir = diagnostic_context
            try:
                archive_path = archive_recent_steps(
                    self.session_log_path,
                    account_screenshot_dir,
                    runner.RUNTIME_DIR / "error-diagnostics",
                    account_name=account_config["account"],
                    account_index=account_index,
                    error_message=error_message,
                )
            except Exception as archive_error:
                self._report(f"[错误诊断包] 生成失败：{archive_error}")
                return None
            self._report(
                f"[错误诊断包] 最近 5 步操作和截图已保存至：{archive_path}"
            )
            return archive_path

        try:
            total = len(accounts)
            recovered_error_count = 0
            recovered_task_error_count = 0
            for index, account_config in enumerate(accounts, start=1):
                account_screenshot_dir = self.debug_screenshot_dir / f"account-{index}"
                diagnostic_context = (
                    account_config,
                    index,
                    account_screenshot_dir,
                )
                diagnostic_attempted = False
                runner.ensure_not_cancelled(cancel_event)
                self._report(
                    client_state.progress_message(
                        index, total, account_config["server_number"]
                    )
                )
                try:
                    def handle_task_error(task_name: str, error: Exception):
                        nonlocal recovered_task_error_count
                        recovered_task_error_count += 1
                        return package_current_error(
                            f"业务任务“{task_name}”已跳过：{error}",
                            force=True,
                        )

                    completed = runner.run_automation(
                        account_config["account"],
                        account_config["password"],
                        server_number=account_config["server_number"],
                        cultivation_levels=account_config.get(
                            "cultivation_levels",
                            list(runner.DEFAULT_CULTIVATION_LEVELS),
                        ),
                        report=self._report,
                        cancel_event=cancel_event,
                        debug_screenshot_dir=account_screenshot_dir,
                        continue_on_task_error=continue_on_task_error,
                        on_task_error=handle_task_error,
                    )
                except runner.AutomationCancelled:
                    raise
                except Exception as error:
                    archive_path = package_current_error(str(error))
                    if not continue_on_process_error:
                        if archive_path is not None:
                            raise RuntimeError(
                            f"{error}\n错误诊断包：{archive_path}"
                            ) from error
                        raise
                    if not runner.close_game_after_process_error(self._report):
                        raise RuntimeError(
                            "运行错误后游戏未能确认关闭；为避免影响后续账号，账号队列已停止。"
                        ) from error
                    recovered_error_count += 1
                    self._report(
                        f"[任务恢复] 第 {index}/{total} 个账号已跳过，游戏已关闭。"
                    )
                    if index < total:
                        self._report("[账号队列] 即将重新打开游戏并执行下一个账号。")
                    continue
                if not completed:
                    incomplete_message = client_state.incomplete_message(index, total)
                    archive_path = package_current_error(incomplete_message)
                    if archive_path is not None:
                        incomplete_message += f"\n错误诊断包：{archive_path}"
                    self._emit("incomplete", incomplete_message)
                    return
                self._report(f"[账号队列] 第 {index}/{total} 个账号已完成，游戏已关闭。")
                if index < total:
                    self._report("[账号队列] 即将重新打开游戏并执行下一个账号。")
        except runner.AutomationCancelled as error:
            self._emit("cancelled", str(error))
        except Exception as error:
            archive_path = None
            if not diagnostic_attempted:
                archive_path = package_current_error(str(error))
            error_message = str(error)
            if archive_path is not None:
                error_message += f"\n错误诊断包：{archive_path}"
            self._emit("error", error_message)
        else:
            if recovered_error_count or recovered_task_error_count:
                diagnostic_summary = (
                    "并已生成错误诊断包。"
                    if package_error_diagnostics or recovered_task_error_count
                    else "。"
                )
                details = []
                if recovered_error_count:
                    details.append(f"{recovered_error_count} 个账号发生运行错误")
                if recovered_task_error_count:
                    details.append(f"{recovered_task_error_count} 个任务出错后已跳过")
                self._emit(
                    "done_with_errors",
                    f"[运行结束] 账号队列已结束，共处理 {len(accounts)} 个账号；"
                    f"其中 {'，'.join(details)}"
                    f"{diagnostic_summary}",
                )
            else:
                self._emit("done", f"[运行结束] 账号队列已完成，共执行 {len(accounts)} 个账号。")

    def _stop(self) -> None:
        if self.cancel_event is None:
            return
        self.cancel_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止")
        self._append_log("[运行] 已请求停止；当前识别动作完成后将安全退出。")

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
                elif kind == "done_with_errors":
                    self._finish("已完成（有错误）", message)
                elif kind == "cancelled":
                    self._finish("已停止", message)
                elif kind == "incomplete":
                    self._finish("未完全完成", message)
                    messagebox.showwarning("账号队列已停止", message, parent=self.root)
                elif kind == "error":
                    self._finish("运行失败", f"运行失败：{message}")
                    messagebox.showerror("运行失败", message, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _on_close(self) -> None:
        if self.closing:
            return
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno("确认退出", "任务仍在运行，确定停止运行并退出客户端吗？", parent=self.root):
                return
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.closing = True
            self.status.set("正在停止并关闭")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._append_log("[运行] 用户请求退出，等待当前识别动作完成。")
            self.root.after(100, self._wait_for_worker_then_close)
            return
        self._finish_close()

    def _wait_for_worker_then_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100, self._wait_for_worker_then_close)
            return
        self._finish_close()

    def _finish_close(self) -> None:
        self._write_session_log("客户端正常关闭，清理本次会话日志和调试截图。")
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
    global runner, tk, messagebox, ttk
    if "--self-check" in sys.argv:
        marker_path = _SELF_CHECK_MARKER
        if marker_path is None:
            marker_index = sys.argv.index("--self-check") + 1
            if marker_index < len(sys.argv):
                marker_path = Path(sys.argv[marker_index])
                marker_path.write_text("started\n", encoding="utf-8")
        if runner is not None:
            # 保持已导入 client 的调用方/单元测试可替换 runner 自检。
            runner.distribution_self_check()
        else:
            from fashion_mall.self_check import distribution_self_check

            distribution_self_check(_PATHS.version_path, _PATHS.ocr_dir)
        if marker_path is not None:
            marker_path.write_text("ok\n", encoding="utf-8")
        return
    if runner is None:
        import runner as runner_module

        runner = runner_module
    # 延迟加载 UI 依赖，使便携版的无界面自检不受 Tk 安装/显示环境影响。
    import tkinter as tk
    from tkinter import messagebox, ttk

    enable_windows_dpi_awareness()
    root = tk.Tk()
    FashionMallClient(root)
    root.mainloop()


if __name__ == "__main__":
    main()
