from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageOps, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseTk = TkinterDnD.Tk
except ImportError:  # The app remains usable without optional drag-and-drop support.
    DND_FILES = None
    BaseTk = tk.Tk

from .models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    BatchOptions,
    BatchProgress,
    BatchResult,
    PngCompressionMode,
    ResizeMode,
    ResizeOptions,
    SingleImageOptions,
)
from .backends import BackendEvent
from .color_key import color_probability, median_color_sample, preview_to_original
from .color_key_config import ColorKeyConfig, ColorSample
from .manual_mask import ManualMaskEditor, MaskStroke
from .processing import BatchImageService, describe_execution_backend, discover_images


APP_NAME = "Không biết gì đừng nói"
APP_VERSION = "1.5.0"


def resource_path(relative: str) -> Path:
    """Return a resource path in source mode or in a PyInstaller bundle."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / relative


def configure_runtime() -> None:
    """Configure bundled AI models and Windows DPI behavior before creating UI."""
    model_directory = resource_path("assets/models")
    if model_directory.is_dir():
        os.environ["U2NET_HOME"] = str(model_directory)

    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class KhongBietGiDungNoiApp(BaseTk):
    """Production-oriented Vietnamese desktop UI for local batch image processing."""

    COLORS = {
        "navy": "#081A33",
        "navy_light": "#12355D",
        "blue": "#2563EB",
        "blue_hover": "#1D4ED8",
        "cyan": "#22D3EE",
        "purple": "#8B5CF6",
        "surface": "#FFFFFF",
        "canvas": "#F3F6FA",
        "border": "#DCE4EE",
        "text": "#132238",
        "muted": "#64748B",
        "success": "#059669",
        "warning": "#D97706",
        "danger": "#DC2626",
    }

    RESIZE_LABELS = {
        "Không thay đổi kích thước": ResizeMode.NONE,
        "Theo phần trăm": ResizeMode.PERCENT,
        "Vừa trong khung W × H": ResizeMode.EXACT,
        "Giới hạn cạnh dài": ResizeMode.MAX_SIDE,
    }

    MODELS = {
        "Chất lượng cao · U²-Net": "u2net",
        "Tốc độ nhanh · U²-Net Lite": "u2netp",
    }

    REMOVAL_MODES = {
        "AI tự động": "ai",
        "Theo màu nâng cao": "color_key",
        "Hybrid AI + màu": "hybrid",
    }

    INPUT_MODES = {
        "Một ảnh": "single",
        "Cả folder": "folder",
    }

    PNG_MODES = {
        "Nhanh · lossless": PngCompressionMode.FAST,
        "Cân bằng": PngCompressionMode.BALANCED,
        "File nhỏ": PngCompressionMode.SMALL,
    }

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} — Xóa nền & Resize ảnh")
        self.geometry("980x1020")
        self.minsize(900, 720)
        self.configure(bg=self.COLORS["canvas"])

        self._cancel_event = threading.Event()
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._service = BatchImageService(on_backend_event=lambda event: self._events.put(("backend", event)))
        self._worker: threading.Thread | None = None
        self._preload_worker: threading.Thread | None = None
        self._closing = False
        self._count_after_id: str | None = None
        self._preview_after_id: str | None = None
        self._preview_generation = {"source": 0, "result": 0}
        self._preview_photos: dict[str, ImageTk.PhotoImage] = {}
        self._source_preview_bitmap: Image.Image | None = None
        self._preview_display: dict[str, tuple[int, int, int, int, tuple[int, int]]] = {}
        self._color_samples: list[ColorSample] = []
        self._manual_editor = ManualMaskEditor(max_history=20)
        self._active_stroke_points: list[tuple[int, int]] = []
        self._overlay_after_id: str | None = None
        self._last_output_directory: Path | None = None
        self._last_output_file: Path | None = None
        self._last_processing_error: str | None = None
        self._execution_backend = describe_execution_backend()
        self._reported_provider: str | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.input_mode_var = tk.StringVar(value="Cả folder")
        self.source_label_var = tk.StringVar(value="Folder đầu vào")
        self.choose_input_text_var = tk.StringVar(value="Chọn folder")
        self.output_hint_var = tk.StringVar(value="")
        self.remove_background_var = tk.BooleanVar(value=True)
        self.recursive_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.resize_mode_var = tk.StringVar(value="Không thay đổi kích thước")
        self.percent_var = tk.StringVar(value="50")
        self.width_var = tk.StringVar(value="1024")
        self.height_var = tk.StringVar(value="1024")
        self.max_side_var = tk.StringVar(value="1024")
        self.keep_aspect_var = tk.BooleanVar(value=True)
        self.model_var = tk.StringVar(value="Chất lượng cao · U²-Net")
        self.removal_mode_var = tk.StringVar(value="AI tự động")
        self.eyedropper_var = tk.BooleanVar(value=False)
        self.overlay_var = tk.BooleanVar(value=True)
        self.brush_mode_var = tk.StringVar(value="keep")
        self.brush_size_var = tk.IntVar(value=18)
        self.color_similarity_var = tk.DoubleVar(value=34.0)
        self.edge_softness_var = tk.DoubleVar(value=1.5)
        self.edge_protection_var = tk.DoubleVar(value=0.55)
        self.spill_suppression_var = tk.DoubleVar(value=0.35)
        self.connected_border_var = tk.BooleanVar(value=True)
        self.preload_var = tk.BooleanVar(value=True)
        self.png_mode_var = tk.StringVar(value="Nhanh · lossless")
        self.status_var = tk.StringVar(value="Sẵn sàng xử lý")
        self.count_var = tk.StringVar(value="0 ảnh")
        self.progress_detail_var = tk.StringVar(value="Chọn folder ảnh để bắt đầu")
        self.runtime_var = tk.StringVar(value=f"{self._execution_backend} · CPU fallback · Không upload ảnh")
        self.source_preview_meta_var = tk.StringVar(value="Chưa chọn ảnh")
        self.result_preview_meta_var = tk.StringVar(value="Chưa xử lý")

        self._configure_icon()
        self._configure_styles()
        self._build_ui()
        self.input_var.trace_add("write", self._on_input_changed)
        self.output_var.trace_add("write", lambda *_args: self._schedule_count_refresh())
        for variable in (self.color_similarity_var, self.edge_softness_var, self.edge_protection_var, self.spill_suppression_var):
            variable.trace_add("write", self._schedule_overlay_refresh)
        self._load_settings()
        self._update_input_mode()
        self._update_resize_fields()
        self._update_background_fields()
        self._center_window()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_events)
        self.after(350, self._start_preload)

    def _configure_icon(self) -> None:
        icon_png = resource_path("assets/app_icon_64.png")
        icon_ico = resource_path("assets/app_icon.ico")
        try:
            if icon_ico.exists():
                self.iconbitmap(default=str(icon_ico))
            if icon_png.exists():
                self._window_icon = tk.PhotoImage(file=str(icon_png))
                self.iconphoto(True, self._window_icon)
        except tk.TclError:
            self._window_icon = None

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("App.TFrame", background=self.COLORS["canvas"])
        style.configure("Card.TFrame", background=self.COLORS["surface"], relief="flat")
        style.configure("Card.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["text"], font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 11))
        style.configure("Muted.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Count.TLabel", background="#E8F0FF", foreground=self.COLORS["blue"], font=("Segoe UI Semibold", 10), padding=(10, 4))
        style.configure("Status.TLabel", background=self.COLORS["canvas"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 10))
        style.configure("Footer.TLabel", background=self.COLORS["canvas"], foreground=self.COLORS["muted"], font=("Segoe UI", 8))

        style.configure("TEntry", fieldbackground="#F8FAFC", foreground=self.COLORS["text"], bordercolor=self.COLORS["border"], padding=8)
        style.map("TEntry", bordercolor=[("focus", self.COLORS["blue"])])
        style.configure("TCombobox", fieldbackground="#F8FAFC", background="#F8FAFC", foreground=self.COLORS["text"], padding=7)
        style.map("TCombobox", bordercolor=[("focus", self.COLORS["blue"])])
        style.configure("TCheckbutton", background=self.COLORS["surface"], foreground=self.COLORS["text"], font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", self.COLORS["surface"])])
        style.configure("TRadiobutton", background=self.COLORS["surface"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 9))
        style.map("TRadiobutton", background=[("active", self.COLORS["surface"])])

        style.configure("Accent.TButton", background=self.COLORS["blue"], foreground="white", borderwidth=0, padding=(22, 11), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", self.COLORS["blue_hover"]), ("disabled", "#A8BCE8")])
        style.configure("Secondary.TButton", background="#EAF0F8", foreground=self.COLORS["text"], borderwidth=0, padding=(14, 9), font=("Segoe UI Semibold", 9))
        style.map("Secondary.TButton", background=[("active", "#DCE7F4")])
        style.configure("Danger.TButton", background="#FEE2E2", foreground=self.COLORS["danger"], borderwidth=0, padding=(16, 10), font=("Segoe UI Semibold", 9))
        style.map("Danger.TButton", background=[("active", "#FECACA")])

        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#DCE7F5", background=self.COLORS["blue"], bordercolor="#DCE7F5", lightcolor=self.COLORS["cyan"], darkcolor=self.COLORS["blue"], thickness=9)

    def _build_ui(self) -> None:
        self._build_header()

        scroll_host = tk.Frame(self, bg=self.COLORS["canvas"], highlightthickness=0)
        scroll_host.pack(fill=tk.BOTH, expand=True)
        self._content_canvas = tk.Canvas(scroll_host, bg=self.COLORS["canvas"], highlightthickness=0)
        content_scrollbar = ttk.Scrollbar(scroll_host, orient=tk.VERTICAL, command=self._content_canvas.yview)
        self._content_canvas.configure(yscrollcommand=content_scrollbar.set)
        self._content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        content = ttk.Frame(self._content_canvas, style="App.TFrame", padding=(24, 18, 24, 12))
        self._content_window = self._content_canvas.create_window((0, 0), window=content, anchor=tk.NW)
        content.bind(
            "<Configure>",
            lambda _event: self._content_canvas.configure(scrollregion=self._content_canvas.bbox("all")),
        )
        self._content_canvas.bind(
            "<Configure>",
            lambda event: self._content_canvas.itemconfigure(self._content_window, width=event.width),
        )
        self.bind("<MouseWheel>", self._on_mousewheel)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(2, weight=1)

        self._build_paths_card(content)
        self._build_actions_card(content)
        self._build_progress_card(content)
        self._build_footer(content)

    def _on_mousewheel(self, event: tk.Event) -> str:
        direction = -1 if event.delta > 0 else 1
        self._content_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _build_header(self) -> None:
        header = tk.Canvas(self, height=92, bg=self.COLORS["navy"], highlightthickness=0)
        self._header_canvas = header
        header.pack(fill=tk.X)
        header.create_rectangle(0, 0, 980, 92, fill=self.COLORS["navy"], outline="")
        header.create_oval(770, -110, 1030, 150, fill=self.COLORS["navy_light"], outline="")
        header.create_oval(860, -40, 1010, 110, fill="#143D6B", outline="")

        icon_path = resource_path("assets/app_icon_64.png")
        if icon_path.exists():
            try:
                self._header_icon = tk.PhotoImage(file=str(icon_path))
                header.create_image(30, 14, image=self._header_icon, anchor=tk.NW)
            except tk.TclError:
                self._header_icon = None

        header.create_text(108, 30, text="KHÔNG BIẾT GÌ ĐỪNG NÓI", fill="white", font=("Segoe UI Semibold", 18), anchor=tk.W)
        header.create_text(108, 58, text="Xóa nền AI & resize một ảnh hoặc hàng loạt — nhanh, riêng tư, chạy local", fill="#BDD5F4", font=("Segoe UI", 10), anchor=tk.W)
        header.create_text(935, 26, text=f"v{APP_VERSION}", fill="#C7D8EE", font=("Segoe UI Semibold", 9), anchor=tk.E)
        self._backend_header_item = header.create_text(935, 52, text=self._execution_backend.upper(), fill=self.COLORS["cyan"], font=("Segoe UI Semibold", 9), anchor=tk.E)

    def _build_paths_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 12))
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="01  NGUỒN ẢNH", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(card, textvariable=self.count_var, style="Count.TLabel").grid(row=0, column=2, sticky=tk.E)

        mode_controls = ttk.Frame(card, style="Card.TFrame")
        mode_controls.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(12, 4))
        for label in self.INPUT_MODES:
            ttk.Radiobutton(
                mode_controls,
                text=label,
                value=label,
                variable=self.input_mode_var,
                command=self._update_input_mode,
            ).pack(side=tk.LEFT, padx=(0, 20))

        self.source_label = ttk.Label(card, textvariable=self.source_label_var, style="Card.TLabel")
        self.source_label.grid(row=2, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        self.input_entry = ttk.Entry(card, textvariable=self.input_var)
        self.input_entry.grid(row=2, column=1, sticky=tk.EW, pady=6)
        self.choose_input_button = ttk.Button(
            card,
            textvariable=self.choose_input_text_var,
            style="Secondary.TButton",
            command=self._choose_input,
        )
        self.choose_input_button.grid(row=2, column=2, padx=(10, 0), pady=6)

        self.output_label = ttk.Label(card, text="Folder đầu ra", style="Card.TLabel")
        self.output_label.grid(row=3, column=0, sticky=tk.W, padx=(0, 12), pady=6)
        self.output_entry = ttk.Entry(card, textvariable=self.output_var)
        self.output_entry.grid(row=3, column=1, sticky=tk.EW, pady=6)
        self.choose_output_button = ttk.Button(card, text="Chọn folder", style="Secondary.TButton", command=self._choose_output)
        self.choose_output_button.grid(row=3, column=2, padx=(10, 0), pady=6)

        self.single_output_hint = ttk.Label(card, textvariable=self.output_hint_var, style="Muted.TLabel")

        self.folder_controls = ttk.Frame(card, style="Card.TFrame")
        self.folder_controls.grid(row=4, column=1, columnspan=2, sticky=tk.EW, pady=(8, 0))
        ttk.Checkbutton(self.folder_controls, text="Bao gồm folder con", variable=self.recursive_var, command=self._refresh_count).pack(side=tk.LEFT)
        ttk.Checkbutton(self.folder_controls, text="Ghi đè file đã tồn tại", variable=self.overwrite_var).pack(side=tk.LEFT, padx=(22, 0))
        ttk.Label(self.folder_controls, text="Ảnh gốc luôn được giữ nguyên", style="Muted.TLabel").pack(side=tk.RIGHT)

        if DND_FILES is not None:
            self.input_entry.drop_target_register(DND_FILES)
            self.input_entry.dnd_bind("<<Drop>>", self._on_drop)

    def _build_actions_card(self, parent: ttk.Frame) -> None:
        background_card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        background_card.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 6), pady=(0, 12))
        background_card.columnconfigure(0, weight=1)

        ttk.Label(background_card, text="02  XÓA NỀN AI", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(background_card, text="Bật xóa nền tự động", variable=self.remove_background_var, command=self._update_background_fields).grid(row=1, column=0, sticky=tk.W, pady=(14, 10))
        ttk.Label(background_card, text="Phương pháp", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W)
        self.removal_combo = ttk.Combobox(background_card, textvariable=self.removal_mode_var, values=tuple(self.REMOVAL_MODES), state="readonly")
        self.removal_combo.grid(row=3, column=0, sticky=tk.EW, pady=(6, 8))
        self.removal_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_background_fields())
        ttk.Label(background_card, text="Mô hình xử lý", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W)
        self.model_combo = ttk.Combobox(background_card, textvariable=self.model_var, values=tuple(self.MODELS), state="readonly")
        self.model_combo.grid(row=5, column=0, sticky=tk.EW, pady=(6, 8))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)
        ttk.Label(background_card, text="AI: U²-Net. Màu nâng cao chỉ xóa nền liên thông,\nưu tiên không làm mất lá/cọng/vật thể xanh.", style="Muted.TLabel", justify=tk.LEFT).grid(row=6, column=0, sticky=tk.W)
        self.color_controls = ttk.Frame(background_card, style="Card.TFrame")
        self.color_controls.grid(row=7, column=0, sticky=tk.EW, pady=(10, 0))
        self.color_controls.columnconfigure(0, weight=1)
        ttk.Button(self.color_controls, text="Chọn màu nền", style="Secondary.TButton", command=self._toggle_eyedropper).grid(row=0, column=0, sticky=tk.W)
        ttk.Button(self.color_controls, text="Xóa mẫu", style="Secondary.TButton", command=self._clear_color_samples).grid(row=0, column=1, sticky=tk.E)
        self.samples_var = tk.StringVar(value="Chưa có mẫu màu · Chọn ảnh đơn rồi bấm Chọn màu nền")
        ttk.Label(self.color_controls, textvariable=self.samples_var, style="Muted.TLabel", wraplength=350).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 6))
        self._add_color_slider(self.color_controls, "Độ tương đồng màu", self.color_similarity_var, 8, 80, 2)
        self._add_color_slider(self.color_controls, "Độ mềm viền", self.edge_softness_var, 0, 6, 3)
        self._add_color_slider(self.color_controls, "Bảo vệ cạnh", self.edge_protection_var, 0, 1, 4)
        self._add_color_slider(self.color_controls, "Khử ám màu", self.spill_suppression_var, 0, 1, 5)
        ttk.Checkbutton(self.color_controls, text="Chỉ xóa vùng liên thông với biên", variable=self.connected_border_var, command=self._schedule_overlay_refresh).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))
        ttk.Checkbutton(self.color_controls, text="Hiện overlay mask đỏ/xanh", variable=self.overlay_var, command=self._schedule_overlay_refresh).grid(row=7, column=0, columnspan=2, sticky=tk.W)
        brush_row = ttk.Frame(self.color_controls, style="Card.TFrame")
        brush_row.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        ttk.Radiobutton(brush_row, text="Giữ lại", variable=self.brush_mode_var, value="keep").pack(side=tk.LEFT)
        ttk.Radiobutton(brush_row, text="Xóa thêm", variable=self.brush_mode_var, value="remove").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Scale(brush_row, from_=4, to=80, variable=self.brush_size_var, orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        action_row = ttk.Frame(self.color_controls, style="Card.TFrame")
        action_row.grid(row=9, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        ttk.Button(action_row, text="Undo", style="Secondary.TButton", command=self._undo_manual).pack(side=tk.LEFT)
        ttk.Button(action_row, text="Redo", style="Secondary.TButton", command=self._redo_manual).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_row, text="Tự nhận diện lại", style="Secondary.TButton", command=self._schedule_overlay_refresh).pack(side=tk.RIGHT)
        ttk.Checkbutton(
            background_card,
            text="Chuẩn bị AI trong nền khi mở app",
            variable=self.preload_var,
            command=self._on_preload_changed,
        ).grid(row=8, column=0, sticky=tk.W, pady=(10, 0))

        resize_card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        resize_card.grid(row=1, column=1, sticky=tk.NSEW, padx=(6, 0), pady=(0, 12))
        resize_card.columnconfigure(0, weight=1)
        ttk.Label(resize_card, text="03  RESIZE ẢNH", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        self.resize_combo = ttk.Combobox(resize_card, textvariable=self.resize_mode_var, values=tuple(self.RESIZE_LABELS), state="readonly")
        self.resize_combo.grid(row=1, column=0, sticky=tk.EW, pady=(14, 10))
        self.resize_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_resize_fields())

        self.resize_fields = ttk.Frame(resize_card, style="Card.TFrame")
        self.resize_fields.grid(row=2, column=0, sticky=tk.EW)
        self.resize_fields.columnconfigure(1, weight=1)
        self.resize_fields.columnconfigure(3, weight=1)

        self.percent_label = ttk.Label(self.resize_fields, text="Tỷ lệ (%)", style="Card.TLabel")
        self.percent_entry = ttk.Entry(self.resize_fields, textvariable=self.percent_var, width=10)
        self.width_label = ttk.Label(self.resize_fields, text="Rộng", style="Card.TLabel")
        self.width_entry = ttk.Entry(self.resize_fields, textvariable=self.width_var, width=10)
        self.height_label = ttk.Label(self.resize_fields, text="Cao", style="Card.TLabel")
        self.height_entry = ttk.Entry(self.resize_fields, textvariable=self.height_var, width=10)
        self.aspect_check = ttk.Checkbutton(self.resize_fields, text="Giữ tỷ lệ, không crop", variable=self.keep_aspect_var)
        self.max_side_label = ttk.Label(self.resize_fields, text="Cạnh dài tối đa (px)", style="Card.TLabel")
        self.max_side_entry = ttk.Entry(self.resize_fields, textvariable=self.max_side_var, width=12)
        self.resize_hint = ttk.Label(resize_card, text="Lanczos chất lượng cao · Không upscale ở chế độ cạnh dài", style="Muted.TLabel")
        self.resize_hint.grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Label(resize_card, text="Nén PNG", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W, pady=(10, 4))
        self.png_mode_combo = ttk.Combobox(
            resize_card,
            textvariable=self.png_mode_var,
            values=tuple(self.PNG_MODES),
            state="readonly",
        )
        self.png_mode_combo.grid(row=5, column=0, sticky=tk.EW)

    def _build_progress_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.grid(row=2, column=0, columnspan=2, sticky=tk.NSEW)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(3, minsize=78, weight=1)

        title_row = ttk.Frame(card, style="Card.TFrame")
        title_row.grid(row=0, column=0, sticky=tk.EW)
        ttk.Label(title_row, text="04  TIẾN TRÌNH", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_row, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(card, style="Blue.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.progress.grid(row=1, column=0, sticky=tk.EW, pady=(12, 6))
        ttk.Label(card, textvariable=self.progress_detail_var, style="Muted.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(0, 8))

        self.preview_frame = ttk.Frame(card, style="Card.TFrame")
        self.preview_frame.grid(row=3, column=0, sticky=tk.NSEW)
        self.preview_frame.columnconfigure(0, weight=1, uniform="preview")
        self.preview_frame.columnconfigure(1, weight=1, uniform="preview")
        self._build_preview_panel(self.preview_frame, 0, "source", "ẢNH GỐC", self.source_preview_meta_var)
        self._build_preview_panel(self.preview_frame, 1, "result", "KẾT QUẢ", self.result_preview_meta_var)

        self.log_frame = tk.Frame(card, bg="#0B1628", highlightthickness=0)
        self.log_frame.grid(row=3, column=0, sticky=tk.NSEW)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(self.log_frame, height=4, state=tk.DISABLED, wrap=tk.NONE, bg="#0B1628", fg="#C9D8EC", insertbackground="white", borderwidth=0, padx=12, pady=10, font=("Cascadia Mono", 9))
        self.log.grid(row=0, column=0, sticky=tk.NSEW)
        log_scroll = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.tag_configure("ok", foreground="#75E6B4")
        self.log.tag_configure("skip", foreground="#FBBF72")
        self.log.tag_configure("error", foreground="#FDA4AF")
        self.log.tag_configure("info", foreground="#9CC8FF")

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.grid(row=4, column=0, sticky=tk.EW, pady=(12, 0))
        self.open_output_button = ttk.Button(buttons, text="Mở folder kết quả", style="Secondary.TButton", command=self._open_output, state=tk.DISABLED)
        self.open_output_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(buttons, text="Dừng xử lý", style="Danger.TButton", command=self._cancel, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.run_button = ttk.Button(buttons, text="BẮT ĐẦU XỬ LÝ", style="Accent.TButton", command=self._start)
        self.run_button.pack(side=tk.RIGHT)

    def _build_preview_panel(
        self,
        parent: ttk.Frame,
        column: int,
        kind: str,
        title: str,
        metadata_var: tk.StringVar,
    ) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=(0, 0, 6 if column == 0 else 0, 0))
        panel.grid(row=0, column=column, sticky=tk.NSEW, padx=(0, 6) if column == 0 else (6, 0))
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text=title, style="Section.TLabel").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))

        canvas = tk.Canvas(
            panel,
            width=400,
            height=180,
            bg="#EEF2F7",
            highlightbackground=self.COLORS["border"],
            highlightthickness=1,
        )
        canvas.grid(row=1, column=0, sticky=tk.EW)
        self._draw_checkerboard(canvas, 400, 180)
        canvas.create_text(200, 90, text="Chưa có ảnh", fill=self.COLORS["muted"], font=("Segoe UI", 10), tags="preview_content")
        setattr(self, f"{kind}_preview_canvas", canvas)
        if kind == "source":
            canvas.bind("<ButtonPress-1>", self._on_source_canvas_down)
            canvas.bind("<B1-Motion>", self._on_source_canvas_move)
            canvas.bind("<ButtonRelease-1>", self._on_source_canvas_up)
        ttk.Label(panel, textvariable=metadata_var, style="Muted.TLabel").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))

    @staticmethod
    def _draw_checkerboard(canvas: tk.Canvas, width: int, height: int) -> None:
        cell_size = 12
        colors = ("#FFFFFF", "#E6EAF0")
        for y in range(0, height, cell_size):
            for x in range(0, width, cell_size):
                color = colors[((x // cell_size) + (y // cell_size)) % 2]
                canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill=color, outline="", tags="checker")

    @staticmethod
    def _add_color_slider(parent: ttk.Frame, label: str, variable: tk.DoubleVar, start: float, end: float, row: int) -> None:
        """Create one light-weight Tk slider; expensive preview work is debounced elsewhere."""
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky=tk.W, pady=(4, 0))
        ttk.Scale(parent, from_=start, to=end, variable=variable, orient=tk.HORIZONTAL).grid(row=row, column=1, sticky=tk.EW, padx=(8, 0), pady=(4, 0))

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent, style="App.TFrame")
        footer.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(9, 0))
        ttk.Label(footer, text="PNG · JPG · WEBP · BMP · TIFF", style="Footer.TLabel").pack(side=tk.LEFT)
        ttk.Label(footer, textvariable=self.runtime_var, style="Footer.TLabel").pack(side=tk.RIGHT)

    def _choose_input(self) -> None:
        if self._is_single_mode():
            selected = filedialog.askopenfilename(
                title="Chọn một ảnh",
                filetypes=self._image_filetypes(),
            )
        else:
            selected = filedialog.askdirectory(title="Chọn folder chứa ảnh")
        if not selected:
            return
        input_path = Path(selected)
        self.input_var.set(str(input_path))
        current_output = self.output_var.get().strip()
        if input_path.is_dir() and (not current_output or not Path(current_output).is_absolute()):
            self.output_var.set(str(input_path.parent / f"{input_path.name}_ket_qua"))
        self._refresh_count()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(title="Chọn folder lưu kết quả", mustexist=False)
        if selected:
            self.output_var.set(selected)

    def _on_input_changed(self, *_args: object) -> None:
        self._schedule_count_refresh()
        self._schedule_source_preview()

    def _schedule_source_preview(self) -> None:
        self._preview_generation["source"] += 1
        self._preview_generation["result"] += 1
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None
        self._set_preview_placeholder("result", "Chưa xử lý", "Chưa xử lý")

        if not self._is_single_mode():
            return
        source = Path(self.input_var.get().strip())
        if not source.is_file() or source.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            self._set_preview_placeholder("source", "Chọn hoặc kéo thả một ảnh", "Chưa chọn ảnh")
            return
        generation = self._preview_generation["source"]
        self._set_preview_placeholder("source", "Đang tải preview…", source.name)
        self._preview_after_id = self.after(220, lambda: self._start_preview_loader("source", source, generation))

    def _request_result_preview(self, result: Path) -> None:
        self._preview_generation["result"] += 1
        generation = self._preview_generation["result"]
        self._set_preview_placeholder("result", "Đang tạo preview…", result.name)
        self._start_preview_loader("result", result, generation)

    def _start_preview_loader(self, kind: str, path: Path, generation: int) -> None:
        if kind == "source":
            self._preview_after_id = None
        thread = threading.Thread(
            target=self._load_preview_worker,
            args=(kind, path, generation),
            daemon=True,
            name=f"{kind}-preview-loader",
        )
        thread.start()

    def _load_preview_worker(self, kind: str, path: Path, generation: int) -> None:
        preview: Image.Image | None = None
        try:
            file_size = path.stat().st_size
            with Image.open(path) as opened:
                oriented = ImageOps.exif_transpose(opened)
                original_size = oriented.size
                oriented.thumbnail((384, 164), Image.Resampling.LANCZOS)
                preview = oriented.convert("RGBA")
                if oriented is not opened:
                    oriented.close()
            payload = (kind, generation, path, preview, original_size, file_size, None)
        except Exception as exc:
            if preview is not None:
                preview.close()
            payload = (kind, generation, path, None, None, None, str(exc))
        self._events.put(("preview", payload))

    def _show_preview(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 7:
            return
        kind, generation, path, preview, original_size, file_size, error = payload
        if kind not in self._preview_generation or generation != self._preview_generation[kind]:
            if isinstance(preview, Image.Image):
                preview.close()
            return
        if error or not isinstance(preview, Image.Image):
            self._set_preview_placeholder(str(kind), "Không thể đọc preview", "File ảnh không hợp lệ")
            return

        canvas: tk.Canvas = getattr(self, f"{kind}_preview_canvas")
        if kind == "source":
            if self._source_preview_bitmap is not None:
                self._source_preview_bitmap.close()
            self._source_preview_bitmap = preview.copy()
        photo = ImageTk.PhotoImage(preview)
        preview.close()
        self._preview_photos[str(kind)] = photo
        canvas.delete("preview_content")
        canvas.create_image(200, 90, image=photo, anchor=tk.CENTER, tags="preview_content")
        width, height = original_size
        self._preview_display[str(kind)] = (200 - photo.width() // 2, 90 - photo.height() // 2, photo.width(), photo.height(), original_size)
        suffix = path.suffix.upper().lstrip(".").replace("JPG", "JPEG")
        metadata = f"{width:,} × {height:,} px · {suffix} · {self._format_file_size(file_size)}".replace(",", ".")
        metadata_var: tk.StringVar = getattr(self, f"{kind}_preview_meta_var")
        metadata_var.set(metadata)
        if kind == "source":
            self._schedule_overlay_refresh()

    def _set_preview_placeholder(self, kind: str, text: str, metadata: str) -> None:
        canvas: tk.Canvas | None = getattr(self, f"{kind}_preview_canvas", None)
        if canvas is None:
            return
        self._preview_photos.pop(kind, None)
        canvas.delete("preview_content")
        canvas.create_text(200, 90, text=text, fill=self.COLORS["muted"], font=("Segoe UI", 10), tags="preview_content")
        metadata_var: tk.StringVar = getattr(self, f"{kind}_preview_meta_var")
        metadata_var.set(metadata)

    def _toggle_eyedropper(self) -> None:
        """Enable/disable image-space background colour sampling on the source preview."""
        if not self._is_single_mode() or not Path(self.input_var.get().strip()).is_file():
            messagebox.showinfo("Chọn màu nền", "Hãy chuyển sang Một ảnh và chọn ảnh trước khi lấy mẫu màu nền.", parent=self)
            return
        enabled = not self.eyedropper_var.get()
        self.eyedropper_var.set(enabled)
        self.progress_detail_var.set("Click lên preview ảnh gốc để lấy mẫu median 5×5." if enabled else "Đã tắt chọn màu nền.")

    def _clear_color_samples(self) -> None:
        """Clear selected background samples without modifying the source image."""
        self._color_samples.clear()
        self.samples_var.set("Chưa có mẫu màu")
        self._schedule_overlay_refresh()

    def _color_config(self) -> ColorKeyConfig:
        """Build validated colour-key settings outside of the image algorithm module."""
        config = ColorKeyConfig(
            color_similarity=float(self.color_similarity_var.get()),
            edge_protection=float(self.edge_protection_var.get()),
            edge_softness=float(self.edge_softness_var.get()),
            spill_suppression=float(self.spill_suppression_var.get()),
            connected_to_border_only=self.connected_border_var.get(),
        )
        config.validate()
        return config

    def _map_source_event(self, event: tk.Event) -> tuple[int, int] | None:
        display = self._preview_display.get("source")
        if display is None:
            return None
        left, top, width, height, original_size = display
        if not (left <= event.x < left + width and top <= event.y < top + height):
            return None
        return preview_to_original((event.x - left, event.y - top), (width, height), original_size)

    def _on_source_canvas_down(self, event: tk.Event) -> None:
        """Start eyedropper sampling or an original-resolution manual stroke."""
        point = self._map_source_event(event)
        if point is None:
            return
        if self.eyedropper_var.get():
            source = Path(self.input_var.get().strip())
            threading.Thread(target=self._sample_color_worker, args=(source, point), daemon=True, name="color-sample-worker").start()
            return
        self._active_stroke_points = [point]

    def _on_source_canvas_move(self, event: tk.Event) -> None:
        """Append a sparse image-space point while the manual brush is dragged."""
        if not self._active_stroke_points:
            return
        point = self._map_source_event(event)
        if point is not None and point != self._active_stroke_points[-1]:
            self._active_stroke_points.append(point)

    def _on_source_canvas_up(self, event: tk.Event) -> None:
        """Commit one bounded manual mask command after the brush is released."""
        if not self._active_stroke_points:
            return
        point = self._map_source_event(event)
        if point is not None and point != self._active_stroke_points[-1]:
            self._active_stroke_points.append(point)
        stroke = MaskStroke(tuple(self._active_stroke_points), max(1, int(self.brush_size_var.get())), self.brush_mode_var.get())
        self._active_stroke_points = []
        try:
            self._manual_editor.add_stroke(stroke)
            self._schedule_overlay_refresh()
        except ValueError as exc:
            self._append_log(f"MASK     {exc}", "error")

    def _sample_color_worker(self, source: Path, point: tuple[int, int]) -> None:
        """Read only the source image in a worker and return a robust 5×5 sample to Tk."""
        try:
            with Image.open(source) as opened:
                sample = median_color_sample(ImageOps.exif_transpose(opened), point, 5)
            self._events.put(("color_sample", sample))
        except Exception as exc:
            self._events.put(("color_sample_error", str(exc)))

    def _schedule_overlay_refresh(self, *_args: object) -> None:
        """Debounce preview-mask work so sliders never re-run processing per mouse pixel."""
        if self._overlay_after_id is not None:
            self.after_cancel(self._overlay_after_id)
        self._overlay_after_id = self.after(180, self._start_overlay_worker)

    def _start_overlay_worker(self) -> None:
        """Run the small preview overlay calculation off the Tk event loop."""
        self._overlay_after_id = None
        if not self.overlay_var.get() or self._source_preview_bitmap is None or not self._color_samples:
            return
        try:
            image = self._source_preview_bitmap.copy()
            samples = tuple(self._color_samples)
            config = self._color_config()
        except (ValueError, tk.TclError):
            return
        threading.Thread(target=self._overlay_worker, args=(image, samples, config), daemon=True, name="mask-preview-worker").start()

    def _overlay_worker(self, preview: Image.Image, samples: tuple[ColorSample, ...], config: ColorKeyConfig) -> None:
        """Generate a red/green probability overlay for the compact preview only."""
        try:
            values = np.asarray(preview.convert("RGB"), dtype=np.uint8)
            probability = color_probability(values, samples, config)
            overlay = values.copy()
            overlay[:, :, 0] = np.maximum(overlay[:, :, 0], (probability * 220).astype(np.uint8))
            overlay[:, :, 1] = np.maximum(overlay[:, :, 1], ((1.0 - probability) * 180).astype(np.uint8))
            self._events.put(("mask_overlay", Image.fromarray(overlay, "RGB")))
        except Exception as exc:
            self._events.put(("mask_overlay_error", str(exc)))
        finally:
            preview.close()

    def _show_mask_overlay(self, image: Image.Image) -> None:
        """Display a worker-produced overlay without changing the original preview data."""
        photo = ImageTk.PhotoImage(image)
        image.close()
        self._preview_photos["source"] = photo
        canvas = self.source_preview_canvas
        canvas.delete("preview_content")
        canvas.create_image(200, 90, image=photo, anchor=tk.CENTER, tags="preview_content")

    def _undo_manual(self) -> None:
        """Undo one compact brush command."""
        if self._manual_editor.undo():
            self._schedule_overlay_refresh()

    def _redo_manual(self) -> None:
        """Redo one compact brush command."""
        if self._manual_editor.redo():
            self._schedule_overlay_refresh()

    @staticmethod
    def _format_file_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _update_input_mode(self) -> None:
        single_mode = self._is_single_mode()
        self.source_label_var.set("Ảnh đầu vào" if single_mode else "Folder đầu vào")
        self.choose_input_text_var.set("Chọn ảnh" if single_mode else "Chọn folder")
        self.run_button.configure(text="LƯU ẢNH…" if single_mode else "BẮT ĐẦU XỬ LÝ")
        self.open_output_button.configure(text="Mở vị trí ảnh" if single_mode else "Mở folder kết quả")

        if single_mode:
            self.log_frame.grid_remove()
            self.preview_frame.grid()
            self.output_label.grid_remove()
            self.output_entry.grid_remove()
            self.choose_output_button.grid_remove()
            self.folder_controls.grid_remove()
            self.output_hint_var.set("Kéo thả ảnh vào ô trên hoặc chọn ảnh · Nơi lưu sẽ được hỏi khi bấm LƯU ẢNH")
            self.single_output_hint.grid(row=3, column=1, columnspan=2, sticky=tk.W, pady=(5, 8))
            self.progress_detail_var.set("Chọn hoặc kéo thả một ảnh để bắt đầu")
            self._schedule_source_preview()
        else:
            self.preview_frame.grid_remove()
            self.log_frame.grid()
            self._preview_generation["source"] += 1
            self._preview_generation["result"] += 1
            self.single_output_hint.grid_remove()
            self.output_label.grid()
            self.output_entry.grid()
            self.choose_output_button.grid()
            self.folder_controls.grid()
            self.output_hint_var.set("")
            self.progress_detail_var.set("Chọn folder ảnh để bắt đầu")
        self._refresh_count()

    def _on_drop(self, event: object) -> str:
        data = getattr(event, "data", "")
        dropped = self.tk.splitlist(data)
        if len(dropped) != 1:
            messagebox.showwarning("Chỉ chọn một nguồn", "Hãy kéo thả đúng một ảnh hoặc một folder.", parent=self)
            return "break"

        path = Path(dropped[0])
        if path.is_dir():
            self.input_mode_var.set("Cả folder")
            self.input_var.set(str(path))
            current_output = self.output_var.get().strip()
            if not current_output or not Path(current_output).is_absolute():
                self.output_var.set(str(path.parent / f"{path.name}_ket_qua"))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            self.input_mode_var.set("Một ảnh")
            self.input_var.set(str(path))
        else:
            messagebox.showerror("File không được hỗ trợ", "Hãy thả file PNG, JPG, WEBP, BMP hoặc TIFF.", parent=self)
            return "break"

        self._update_input_mode()
        return "break"

    def _is_single_mode(self) -> bool:
        return self.INPUT_MODES.get(self.input_mode_var.get()) == "single"

    @staticmethod
    def _image_filetypes() -> list[tuple[str, str]]:
        return [
            ("Ảnh được hỗ trợ", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
            ("Tất cả file", "*.*"),
        ]

    def _schedule_count_refresh(self) -> None:
        if self._count_after_id is not None:
            self.after_cancel(self._count_after_id)
        self._count_after_id = self.after(350, self._refresh_count)

    def _refresh_count(self) -> None:
        self._count_after_id = None
        input_path = Path(self.input_var.get().strip())
        if self._is_single_mode():
            is_supported = input_path.is_file() and input_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
            self.count_var.set("1 ảnh" if is_supported else "Chưa chọn ảnh")
            return
        if not input_path.is_dir():
            self.count_var.set("0 ảnh")
            return
        output_text = self.output_var.get().strip()
        excluded = Path(output_text) if output_text else None
        try:
            count = len(discover_images(input_path, self.recursive_var.get(), excluded))
            self.count_var.set(f"{count:,} ảnh".replace(",", "."))
        except OSError:
            self.count_var.set("Không thể đọc")

    def _update_background_fields(self) -> None:
        enabled = self.remove_background_var.get()
        self.model_combo.configure(state="readonly" if enabled else tk.DISABLED)
        self.removal_combo.configure(state="readonly" if enabled else tk.DISABLED)
        mode = self.REMOVAL_MODES[self.removal_mode_var.get()]
        color_state = tk.NORMAL if enabled and mode in {"color_key", "hybrid"} else tk.DISABLED
        for widget in self.color_controls.winfo_children():
            try:
                widget.configure(state=color_state)
            except tk.TclError:
                pass

    def _on_model_changed(self, _event: object | None = None) -> None:
        """Warm the newly selected model when background preload is enabled."""
        if self.preload_var.get() and self.remove_background_var.get() and self.REMOVAL_MODES[self.removal_mode_var.get()] != "color_key":
            self._start_preload()

    def _on_preload_changed(self) -> None:
        """Start optional background warm-up without blocking Tkinter."""
        if self.preload_var.get():
            self._start_preload()
        self._save_settings()

    def _start_preload(self) -> None:
        """Start a daemon warm-up worker while keeping all UI controls responsive."""
        if self._closing or not self.preload_var.get() or not self.remove_background_var.get() or self.REMOVAL_MODES[self.removal_mode_var.get()] == "color_key":
            return
        if self._worker is not None and self._worker.is_alive():
            return
        if self._preload_worker is not None and self._preload_worker.is_alive():
            return
        model_name = self.MODELS[self.model_var.get()]
        self.status_var.set("Đang chuẩn bị AI")
        self.progress_detail_var.set("Đang preload và warm-up model trong nền · Bạn vẫn có thể thao tác")

        def preload_worker() -> None:
            try:
                provider = self._service.preload(model_name)
                self._events.put(("preload_done", provider))
            except Exception as exc:
                self._events.put(("preload_error", str(exc)))

        self._preload_worker = threading.Thread(target=preload_worker, daemon=True, name="ai-preload-worker")
        self._preload_worker.start()

    def _update_resize_fields(self) -> None:
        for widget in self.resize_fields.winfo_children():
            widget.grid_forget()

        mode = self.RESIZE_LABELS[self.resize_mode_var.get()]
        if mode == ResizeMode.PERCENT:
            self.percent_label.grid(row=0, column=0, sticky=tk.W)
            self.percent_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))
        elif mode == ResizeMode.EXACT:
            self.width_label.grid(row=0, column=0, sticky=tk.W)
            self.width_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 14))
            self.height_label.grid(row=0, column=2, sticky=tk.W)
            self.height_entry.grid(row=0, column=3, sticky=tk.EW, padx=(8, 0))
            self.aspect_check.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        elif mode == ResizeMode.MAX_SIDE:
            self.max_side_label.grid(row=0, column=0, sticky=tk.W)
            self.max_side_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))

    def _build_options(self) -> BatchOptions:
        resize = self._build_resize_options()
        input_text = self.input_var.get().strip()
        output_text = self.output_var.get().strip()
        if not input_text:
            raise ValueError("Hãy chọn folder đầu vào.")
        if not output_text:
            raise ValueError("Hãy chọn folder đầu ra.")

        options = BatchOptions(
            input_directory=Path(input_text),
            output_directory=Path(output_text),
            remove_background=self.remove_background_var.get(),
            resize=resize,
            recursive=self.recursive_var.get(),
            overwrite=self.overwrite_var.get(),
            model_name=self.MODELS[self.model_var.get()],
            png_compression=self.PNG_MODES[self.png_mode_var.get()],
            removal_mode=self.REMOVAL_MODES[self.removal_mode_var.get()],
            color_samples=tuple(self._color_samples),
            color_key_config=self._color_config(),
            manual_strokes=self._manual_editor.strokes,
        )
        options.validate()
        return options

    def _build_resize_options(self) -> ResizeOptions:
        def positive_int(value: str, label: str) -> int:
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError(f"{label} phải là số nguyên.") from exc
            if parsed < 1:
                raise ValueError(f"{label} phải lớn hơn 0.")
            return parsed

        resize_mode = self.RESIZE_LABELS[self.resize_mode_var.get()]
        return ResizeOptions(
            mode=resize_mode,
            percent=positive_int(self.percent_var.get(), "Tỷ lệ") if resize_mode == ResizeMode.PERCENT else 100,
            width=positive_int(self.width_var.get(), "Chiều rộng") if resize_mode == ResizeMode.EXACT else 1024,
            height=positive_int(self.height_var.get(), "Chiều cao") if resize_mode == ResizeMode.EXACT else 1024,
            keep_aspect_ratio=self.keep_aspect_var.get(),
            max_side=positive_int(self.max_side_var.get(), "Cạnh dài") if resize_mode == ResizeMode.MAX_SIDE else 1024,
        )

    def _build_single_options(self, output_file: Path, resize: ResizeOptions) -> SingleImageOptions:
        options = SingleImageOptions(
            source_file=Path(self.input_var.get().strip()),
            output_file=output_file,
            remove_background=self.remove_background_var.get(),
            resize=resize,
            overwrite=True,
            model_name=self.MODELS[self.model_var.get()],
            png_compression=self.PNG_MODES[self.png_mode_var.get()],
            removal_mode=self.REMOVAL_MODES[self.removal_mode_var.get()],
            color_samples=tuple(self._color_samples),
            color_key_config=self._color_config(),
            manual_strokes=self._manual_editor.strokes,
        )
        options.validate()
        return options

    def _choose_single_destination(self, source: Path) -> Path | None:
        remove_background = self.remove_background_var.get()
        suffix = ".png" if remove_background else source.suffix.lower()
        action_label = "tach_nen" if remove_background else "da_xu_ly"
        selected = filedialog.asksaveasfilename(
            title="Chọn nơi lưu ảnh kết quả",
            initialdir=str(source.parent),
            initialfile=f"{source.stem}_{action_label}{suffix}",
            defaultextension=suffix,
            filetypes=[("Ảnh PNG", "*.png")] if remove_background else self._image_filetypes(),
            confirmoverwrite=True,
        )
        if not selected:
            return None
        destination = Path(selected)
        return destination

    def _start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            if self._is_single_mode():
                source = Path(self.input_var.get().strip())
                if not source.is_file() or source.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                    raise ValueError("Hãy chọn một ảnh PNG, JPG, WEBP, BMP hoặc TIFF.")
                resize = self._build_resize_options()
                if not self.remove_background_var.get() and resize.mode == ResizeMode.NONE:
                    raise ValueError("Hãy bật ít nhất một chức năng: xóa nền hoặc resize.")
                destination = self._choose_single_destination(source)
                if destination is None:
                    return
                options: BatchOptions | SingleImageOptions = self._build_single_options(destination, resize)
                image_count = 1
            else:
                options = self._build_options()
                image_count = len(discover_images(options.input_directory, options.recursive, options.output_directory))
                if image_count == 0:
                    raise ValueError("Không tìm thấy ảnh được hỗ trợ trong folder đầu vào.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cấu hình chưa hợp lệ", str(exc), parent=self)
            return

        try:
            output_directory = options.output_file.parent if isinstance(options, SingleImageOptions) else options.output_directory
            output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Không thể tạo folder", f"Không thể tạo folder đầu ra:\n{exc}", parent=self)
            return

        self._last_output_file = options.output_file if isinstance(options, SingleImageOptions) else None
        self._last_output_directory = output_directory
        self._cancel_event.clear()
        self.progress.configure(value=0)
        self._clear_log()
        self._reported_provider = None
        self._last_processing_error = None
        if isinstance(options, SingleImageOptions):
            self._preview_generation["result"] += 1
            self._set_preview_placeholder("result", "Đang chờ xử lý…", options.output_file.name)
        source_summary = "Đã chọn 1 ảnh" if isinstance(options, SingleImageOptions) else f"Đã tìm thấy {image_count} ảnh"
        self._append_log(f"{source_summary} · Engine: {self._execution_backend}", "info")
        if options.remove_background:
            self.progress_detail_var.set(f"Đang nạp mô hình AI vào {self._execution_backend}…")
        else:
            self.progress_detail_var.set("Đang chuẩn bị bộ xử lý resize…")
        self.status_var.set("Đang xử lý")
        self.run_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.open_output_button.configure(state=tk.DISABLED)
        self._save_settings()

        self._worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True, name="image-processing-worker")
        self._worker.start()

    def _run_worker(self, options: BatchOptions | SingleImageOptions) -> None:
        try:
            on_progress = lambda progress: self._events.put(("progress", progress))
            if isinstance(options, SingleImageOptions):
                result = self._service.process_single(options, self._cancel_event, on_progress)
            else:
                result = self._service.process(options, self._cancel_event, on_progress)
            self._events.put(("done", result))
        except Exception as exc:
            self._events.put(("fatal", str(exc)))

    def _cancel(self) -> None:
        self._cancel_event.set()
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_var.set("Đang dừng")
        self.progress_detail_var.set("Tool sẽ dừng an toàn sau ảnh đang xử lý…")

    def _poll_events(self) -> None:
        try:
            while True:
                event_name, payload = self._events.get_nowait()
                if event_name == "progress" and isinstance(payload, BatchProgress):
                    self._show_progress(payload)
                elif event_name == "done" and isinstance(payload, BatchResult):
                    self._show_done(payload)
                elif event_name == "fatal":
                    self._show_fatal(str(payload))
                elif event_name == "preview":
                    self._show_preview(payload)
                elif event_name == "color_sample" and isinstance(payload, ColorSample):
                    self._color_samples.append(payload)
                    labels = ", ".join(f"#{sample.rgb[0]:02X}{sample.rgb[1]:02X}{sample.rgb[2]:02X}" for sample in self._color_samples[-5:])
                    self.samples_var.set(f"{len(self._color_samples)} mẫu: {labels}")
                    self.eyedropper_var.set(False)
                    self._schedule_overlay_refresh()
                elif event_name == "color_sample_error":
                    self._append_log(f"MÀU      {payload}", "error")
                elif event_name == "mask_overlay" and isinstance(payload, Image.Image):
                    self._show_mask_overlay(payload)
                elif event_name == "mask_overlay_error":
                    self._append_log(f"OVERLAY  {payload}", "skip")
                elif event_name == "backend" and isinstance(payload, BackendEvent):
                    self._show_backend_event(payload)
                elif event_name == "preload_done":
                    self._preload_worker = None
                    self._update_actual_provider(str(payload))
                    if self._worker is None:
                        self.status_var.set("AI đã sẵn sàng")
                        self.progress_detail_var.set("Model đã warm-up · Ảnh đầu tiên không phải chờ nạp model")
                elif event_name == "preload_error":
                    self._preload_worker = None
                    if not self._closing:
                        self.status_var.set("Sẵn sàng xử lý")
                        self.progress_detail_var.set("Preload chưa thành công · App sẽ tự fallback khi xử lý")
                        self._append_log(f"PRELOAD  {payload}", "skip")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_events)

    def _show_progress(self, progress: BatchProgress) -> None:
        self._update_actual_provider(progress.execution_provider)
        percent = progress.completed * 100 / max(1, progress.total)
        self.progress.configure(value=percent)
        self.progress_detail_var.set(f"{progress.completed}/{progress.total} · {progress.source.name}")
        if progress.error and "bỏ qua" in progress.error.casefold():
            self._append_log(f"BỎ QUA  {progress.source.name} — {progress.error}", "skip")
        elif progress.error:
            self._last_processing_error = progress.error
            self._append_log(f"LỖI     {progress.source.name} — {progress.error}", "error")
            if self._last_output_file is not None and progress.destination == self._last_output_file:
                self._set_preview_placeholder("result", "Xử lý không thành công", progress.error)
        else:
            self._append_log(f"XONG     {progress.source.name}", "ok")
            if self._last_output_file is not None and progress.destination == self._last_output_file:
                self._request_result_preview(progress.destination)

    def _update_actual_provider(self, provider: str | None) -> None:
        if not provider or provider == self._reported_provider:
            return
        self._reported_provider = provider
        labels = {
            "TensorrtExecutionProvider": "GPU TensorRT / CUDA FP16",
            "CUDAExecutionProvider": "GPU CUDA",
            "DmlExecutionProvider": "GPU DirectML",
            "CPUExecutionProvider": "CPU fallback",
        }
        label = labels.get(provider, provider)
        self.runtime_var.set(f"{label} · Không upload ảnh")
        self._header_canvas.itemconfigure(self._backend_header_item, text=label.upper())
        if provider == "CPUExecutionProvider" and self._execution_backend.startswith("GPU"):
            self._append_log("GPU không tương thích trong phiên này · Đã tự chuyển sang CPU an toàn", "skip")
        else:
            self._append_log(f"Provider thực tế: {label}", "info")

    def _show_backend_event(self, event: BackendEvent) -> None:
        """Mirror backend activation and fallback details into the Vietnamese UI log."""
        tag = "skip" if event.level == "warning" else "info"
        self._append_log(f"AI       {event.message}", tag)
        if event.provider:
            self._update_actual_provider(event.provider)

    def _show_done(self, result: BatchResult) -> None:
        self._set_idle()
        if result.cancelled:
            self.open_output_button.configure(state=tk.NORMAL if result.succeeded else tk.DISABLED)
            self.status_var.set("Đã dừng")
            self.progress_detail_var.set(f"Đã xử lý {result.succeeded}/{result.total} ảnh trước khi dừng")
            self._append_log("Phiên xử lý đã được dừng an toàn.", "skip")
            return

        self.progress.configure(value=100)
        self.open_output_button.configure(state=tk.NORMAL if result.succeeded else tk.DISABLED)
        self.status_var.set("Hoàn tất")
        summary = f"{result.succeeded} thành công · {result.failed} lỗi · {result.skipped} bỏ qua"
        self.progress_detail_var.set(summary)
        self._append_log(f"HOÀN TẤT  {summary}", "info")
        if result.succeeded == 0:
            detail = f"\n\nChi tiết: {self._last_processing_error}" if self._last_processing_error else ""
            messagebox.showerror("Xử lý không thành công", f"Không tạo được ảnh kết quả.\n\n{summary}{detail}", parent=self)
            return
        saved_at = self._last_output_file or self._last_output_directory
        messagebox.showinfo("Xử lý hoàn tất", f"{APP_NAME} đã xử lý xong.\n\n{summary}\n\nKết quả được lưu tại:\n{saved_at}", parent=self)

    def _show_fatal(self, error: str) -> None:
        self._set_idle()
        self.status_var.set("Có lỗi")
        self.progress_detail_var.set("Không thể hoàn thành phiên xử lý")
        self._append_log(f"LỖI HỆ THỐNG  {error}", "error")
        if self._last_output_file is not None:
            self._set_preview_placeholder("result", "Xử lý không thành công", error)
        messagebox.showerror("Không thể xử lý", error, parent=self)

    def _set_idle(self) -> None:
        self.run_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self._worker = None

    def _open_output(self) -> None:
        if self._last_output_file is not None and self._last_output_file.exists() and sys.platform == "win32":
            subprocess.Popen(["explorer.exe", f"/select,{self._last_output_file}"])
            return
        directory = self._last_output_directory or Path(self.output_var.get().strip())
        if not directory.is_dir():
            messagebox.showwarning("Folder không tồn tại", "Chưa có folder kết quả để mở.", parent=self)
            return
        if sys.platform == "win32":
            os.startfile(directory)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])

    def _clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _append_log(self, text: str, tag: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, f"{timestamp}  {text}\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _settings_path(self) -> Path:
        base = Path(os.getenv("APPDATA", Path.home()))
        return base / "KhongBietGiDungNoi" / "settings.json"

    def _load_settings(self) -> None:
        path = self._settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            legacy_path = Path(os.getenv("APPDATA", Path.home())) / "TachNenPro" / "settings.json"
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                return

        self.input_var.set(str(data.get("input", "")))
        self.output_var.set(str(data.get("output", "")))
        if data.get("input_mode") in self.INPUT_MODES:
            self.input_mode_var.set(data["input_mode"])
        self.remove_background_var.set(bool(data.get("remove_background", True)))
        self.recursive_var.set(bool(data.get("recursive", True)))
        self.overwrite_var.set(bool(data.get("overwrite", False)))
        if data.get("resize_mode") in self.RESIZE_LABELS:
            self.resize_mode_var.set(data["resize_mode"])
        if data.get("model") in self.MODELS:
            self.model_var.set(data["model"])
        self.preload_var.set(bool(data.get("preload_model", True)))
        if data.get("png_mode") in self.PNG_MODES:
            self.png_mode_var.set(data["png_mode"])
        for variable, key in ((self.percent_var, "percent"), (self.width_var, "width"), (self.height_var, "height"), (self.max_side_var, "max_side")):
            if key in data:
                variable.set(str(data[key]))
        self.keep_aspect_var.set(bool(data.get("keep_aspect", True)))
        self._refresh_count()

    def _save_settings(self) -> None:
        data = {
            "input": self.input_var.get(),
            "output": self.output_var.get(),
            "input_mode": self.input_mode_var.get(),
            "remove_background": self.remove_background_var.get(),
            "recursive": self.recursive_var.get(),
            "overwrite": self.overwrite_var.get(),
            "resize_mode": self.resize_mode_var.get(),
            "model": self.model_var.get(),
            "preload_model": self.preload_var.get(),
            "png_mode": self.png_mode_var.get(),
            "percent": self.percent_var.get(),
            "width": self.width_var.get(),
            "height": self.height_var.get(),
            "max_side": self.max_side_var.get(),
            "keep_aspect": self.keep_aspect_var.get(),
        }
        path = self._settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            if hasattr(self, "log"):
                self._append_log(f"CẤU HÌNH Không thể lưu thiết lập: {exc}", "skip")

    def _on_close(self) -> None:
        if self._closing:
            return
        if self._worker is not None and self._worker.is_alive():
            should_close = messagebox.askyesno("Đang xử lý", "Một phiên xử lý đang chạy. Bạn có muốn dừng và thoát?", parent=self)
            if not should_close:
                return
            self._cancel_event.set()
        self._closing = True
        self._service.request_shutdown()
        self._save_settings()
        self.status_var.set("Đang đóng an toàn")
        self.after(50, self._finish_close)

    def _finish_close(self) -> None:
        """Destroy Tk only after processing and preload workers release native resources."""
        worker_alive = self._worker is not None and self._worker.is_alive()
        preload_alive = self._preload_worker is not None and self._preload_worker.is_alive()
        if worker_alive or preload_alive:
            self.after(100, self._finish_close)
            return
        self._service.close()
        self.destroy()

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")


def run() -> None:
    """Configure and start the packaged desktop application."""
    configure_runtime()
    app = KhongBietGiDungNoiApp()
    app.mainloop()


def run_ui_smoke_test() -> int:
    """Create the real Tk UI, allow startup callbacks, then close it safely."""
    app = KhongBietGiDungNoiApp()
    app.after(1500, app._on_close)
    app.mainloop()
    return 0
