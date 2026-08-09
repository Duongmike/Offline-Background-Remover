from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .models import BatchOptions, BatchProgress, BatchResult, ResizeMode, ResizeOptions
from .processing import BatchImageService, discover_images


# SMELL: Đây là UI legacy trùng trách nhiệm với app_modern.py.
# Đề xuất refactor: xóa module này sau một chu kỳ tương thích; entry point hiện chỉ dùng app_modern.py.


class ImageToolApp(tk.Tk):
    """Small desktop UI for batch background removal and resizing."""

    RESIZE_LABELS = {
        "Không resize": ResizeMode.NONE,
        "Theo phần trăm": ResizeMode.PERCENT,
        "Vừa trong khung W × H": ResizeMode.EXACT,
        "Giới hạn cạnh dài": ResizeMode.MAX_SIDE,
    }
    MODELS = {
        "Cân bằng – u2net": "u2net",
        "Nhanh – u2netp": "u2netp",
        "Chi tiết – isnet-general-use": "isnet-general-use",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("Xóa nền & Resize ảnh hàng loạt")
        self.geometry("780x690")
        self.minsize(720, 620)

        self._service = BatchImageService()
        self._cancel_event = threading.Event()
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.remove_background_var = tk.BooleanVar(value=True)
        self.recursive_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.resize_mode_var = tk.StringVar(value="Không resize")
        self.percent_var = tk.StringVar(value="50")
        self.width_var = tk.StringVar(value="1024")
        self.height_var = tk.StringVar(value="1024")
        self.max_side_var = tk.StringVar(value="1024")
        self.keep_aspect_var = tk.BooleanVar(value=True)
        self.model_var = tk.StringVar(value="Cân bằng – u2net")
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.count_var = tk.StringVar(value="Chưa chọn folder")

        self._configure_style()
        self._build_ui()
        self._update_resize_fields()
        self.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#5f6368")
        style.configure("Run.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 9))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=20)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="Xóa nền & Resize ảnh hàng loạt", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            root,
            text="Chạy hoàn toàn trên máy. Ảnh gốc không bị chỉnh sửa.",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(2, 16))

        paths = ttk.LabelFrame(root, text="1. Folder ảnh", padding=12)
        paths.pack(fill=tk.X)
        paths.columnconfigure(1, weight=1)
        ttk.Label(paths, text="Đầu vào").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(paths, textvariable=self.input_var).grid(row=0, column=1, sticky=tk.EW, pady=4)
        ttk.Button(paths, text="Chọn…", command=self._choose_input).grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Label(paths, text="Đầu ra").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(paths, textvariable=self.output_var).grid(row=1, column=1, sticky=tk.EW, pady=4)
        ttk.Button(paths, text="Chọn…", command=self._choose_output).grid(row=1, column=2, padx=(8, 0), pady=4)
        ttk.Checkbutton(paths, text="Quét cả folder con", variable=self.recursive_var, command=self._refresh_count).grid(
            row=2, column=1, sticky=tk.W, pady=(6, 0)
        )
        ttk.Label(paths, textvariable=self.count_var, style="Hint.TLabel").grid(row=2, column=2, sticky=tk.E, pady=(6, 0))

        actions = ttk.LabelFrame(root, text="2. Chức năng", padding=12)
        actions.pack(fill=tk.X, pady=(12, 0))
        actions.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            actions,
            text="Xóa nền tự động",
            variable=self.remove_background_var,
            command=self._update_background_fields,
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(actions, text="Model").grid(row=0, column=1, sticky=tk.E, padx=(20, 8))
        self.model_combo = ttk.Combobox(
            actions,
            textvariable=self.model_var,
            values=tuple(self.MODELS),
            state="readonly",
            width=28,
        )
        self.model_combo.grid(row=0, column=2, sticky=tk.E)

        ttk.Label(actions, text="Resize").grid(row=1, column=0, sticky=tk.W, pady=(14, 0))
        self.resize_combo = ttk.Combobox(
            actions,
            textvariable=self.resize_mode_var,
            values=tuple(self.RESIZE_LABELS),
            state="readonly",
            width=28,
        )
        self.resize_combo.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=(20, 0), pady=(14, 0))
        self.resize_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_resize_fields())

        self.resize_fields = ttk.Frame(actions)
        self.resize_fields.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(12, 0))
        self.resize_fields.columnconfigure((1, 3), weight=1)

        self.percent_label = ttk.Label(self.resize_fields, text="Tỷ lệ (%)")
        self.percent_entry = ttk.Entry(self.resize_fields, textvariable=self.percent_var, width=12)
        self.width_label = ttk.Label(self.resize_fields, text="Rộng")
        self.width_entry = ttk.Entry(self.resize_fields, textvariable=self.width_var, width=12)
        self.height_label = ttk.Label(self.resize_fields, text="Cao")
        self.height_entry = ttk.Entry(self.resize_fields, textvariable=self.height_var, width=12)
        self.aspect_check = ttk.Checkbutton(self.resize_fields, text="Giữ tỷ lệ, không crop", variable=self.keep_aspect_var)
        self.max_side_label = ttk.Label(self.resize_fields, text="Cạnh dài tối đa (px)")
        self.max_side_entry = ttk.Entry(self.resize_fields, textvariable=self.max_side_var, width=12)

        options = ttk.Frame(root)
        options.pack(fill=tk.X, pady=(12, 0))
        ttk.Checkbutton(options, text="Ghi đè file đã có", variable=self.overwrite_var).pack(side=tk.LEFT)
        ttk.Label(options, text="Xóa nền luôn xuất PNG để giữ kênh trong suốt.", style="Hint.TLabel").pack(side=tk.RIGHT)

        progress_box = ttk.LabelFrame(root, text="3. Tiến trình", padding=12)
        progress_box.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.progress = ttk.Progressbar(progress_box, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)
        ttk.Label(progress_box, textvariable=self.status_var).pack(anchor=tk.W, pady=(7, 6))
        self.log = tk.Text(progress_box, height=8, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.log.pack(fill=tk.BOTH, expand=True)

        buttons = ttk.Frame(root)
        buttons.pack(fill=tk.X, pady=(14, 0))
        self.run_button = ttk.Button(buttons, text="Bắt đầu xử lý", style="Run.TButton", command=self._start)
        self.run_button.pack(side=tk.RIGHT)
        self.cancel_button = ttk.Button(buttons, text="Hủy", command=self._cancel, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.RIGHT, padx=(0, 8))

    def _choose_input(self) -> None:
        selected = filedialog.askdirectory(title="Chọn folder chứa ảnh")
        if not selected:
            return
        input_path = Path(selected)
        self.input_var.set(str(input_path))
        if not self.output_var.get().strip():
            self.output_var.set(str(input_path.parent / f"{input_path.name}_output"))
        self._refresh_count()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Chọn folder đầu ra", mustexist=False)
        if selected:
            self.output_var.set(selected)
            self._refresh_count()

    def _refresh_count(self) -> None:
        path = Path(self.input_var.get().strip())
        if not path.is_dir():
            self.count_var.set("Folder không hợp lệ")
            return
        excluded_text = self.output_var.get().strip()
        excluded = Path(excluded_text) if excluded_text else None
        count = len(discover_images(path, self.recursive_var.get(), excluded))
        self.count_var.set(f"{count} ảnh")

    def _update_background_fields(self) -> None:
        self.model_combo.configure(state="readonly" if self.remove_background_var.get() else tk.DISABLED)

    def _update_resize_fields(self) -> None:
        for widget in self.resize_fields.winfo_children():
            widget.grid_forget()

        mode = self.RESIZE_LABELS[self.resize_mode_var.get()]
        if mode == ResizeMode.PERCENT:
            self.percent_label.grid(row=0, column=0, sticky=tk.W)
            self.percent_entry.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        elif mode == ResizeMode.EXACT:
            self.width_label.grid(row=0, column=0, sticky=tk.W)
            self.width_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 18))
            self.height_label.grid(row=0, column=2, sticky=tk.W)
            self.height_entry.grid(row=0, column=3, sticky=tk.EW, padx=(8, 0))
            self.aspect_check.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        elif mode == ResizeMode.MAX_SIDE:
            self.max_side_label.grid(row=0, column=0, sticky=tk.W)
            self.max_side_entry.grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

    def _build_options(self) -> BatchOptions:
        def positive_int(value: str, label: str) -> int:
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"{label} phải là số nguyên.") from exc
            if parsed < 1:
                raise ValueError(f"{label} phải lớn hơn 0.")
            return parsed

        resize_mode = self.RESIZE_LABELS[self.resize_mode_var.get()]
        resize = ResizeOptions(
            mode=resize_mode,
            percent=positive_int(self.percent_var.get(), "Tỷ lệ"),
            width=positive_int(self.width_var.get(), "Chiều rộng"),
            height=positive_int(self.height_var.get(), "Chiều cao"),
            keep_aspect_ratio=self.keep_aspect_var.get(),
            max_side=positive_int(self.max_side_var.get(), "Cạnh dài"),
        )
        options = BatchOptions(
            input_directory=Path(self.input_var.get().strip()),
            output_directory=Path(self.output_var.get().strip()),
            remove_background=self.remove_background_var.get(),
            resize=resize,
            recursive=self.recursive_var.get(),
            overwrite=self.overwrite_var.get(),
            model_name=self.MODELS[self.model_var.get()],
        )
        options.validate()
        return options

    def _start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            options = self._build_options()
            image_count = len(discover_images(options.input_directory, options.recursive, options.output_directory))
            if image_count == 0:
                raise ValueError("Không tìm thấy ảnh hỗ trợ trong folder đầu vào.")
        except ValueError as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc), parent=self)
            return

        options.output_directory.mkdir(parents=True, exist_ok=True)
        self._cancel_event.clear()
        self.progress.configure(value=0)
        self._clear_log()
        self.status_var.set(f"Chuẩn bị xử lý {image_count} ảnh…")
        self.run_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)

        self._worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True)
        self._worker.start()

    def _run_worker(self, options: BatchOptions) -> None:
        try:
            result = self._service.process(
                options,
                self._cancel_event,
                lambda progress: self._events.put(("progress", progress)),
            )
            self._events.put(("done", result))
        except Exception as exc:
            self._events.put(("fatal", str(exc)))

    def _cancel(self) -> None:
        self._cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_var.set("Đang dừng sau ảnh hiện tại…")

    def _poll_events(self) -> None:
        try:
            while True:
                event_name, payload = self._events.get_nowait()
                if event_name == "progress":
                    self._show_progress(payload)  # type: ignore[arg-type]
                elif event_name == "done":
                    self._show_done(payload)  # type: ignore[arg-type]
                elif event_name == "fatal":
                    self._show_fatal(str(payload))
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_events)

    def _show_progress(self, progress: BatchProgress) -> None:
        percent = progress.completed * 100 / max(1, progress.total)
        self.progress.configure(value=percent)
        self.status_var.set(f"{progress.completed}/{progress.total} – {progress.source.name}")
        marker = "LỖI" if progress.error and "bỏ qua" not in progress.error else "OK"
        detail = f"[{marker}] {progress.source.name}"
        if progress.error:
            detail += f" — {progress.error}"
        self._append_log(detail)

    def _show_done(self, result: BatchResult) -> None:
        self._set_idle()
        if result.cancelled:
            self.status_var.set("Đã hủy theo yêu cầu.")
            return
        self.progress.configure(value=100)
        summary = f"Hoàn tất: {result.succeeded} thành công, {result.failed} lỗi, {result.skipped} bỏ qua."
        self.status_var.set(summary)
        messagebox.showinfo("Xử lý hoàn tất", summary, parent=self)

    def _show_fatal(self, error: str) -> None:
        self._set_idle()
        self.status_var.set("Không thể xử lý.")
        messagebox.showerror("Lỗi", error, parent=self)

    def _set_idle(self) -> None:
        self.run_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self._worker = None

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{text}\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def run() -> None:
    """Start the desktop application."""
    app = ImageToolApp()
    app.mainloop()
