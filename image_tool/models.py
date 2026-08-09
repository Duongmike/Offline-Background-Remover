from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .color_key_config import ColorKeyConfig, ColorSample, RemovalMode
from .manual_mask import MaskStroke


SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})


class ResizeMode(str, Enum):
    """Supported resize strategies."""

    NONE = "none"
    PERCENT = "percent"
    EXACT = "exact"
    MAX_SIDE = "max_side"


class PngCompressionMode(str, Enum):
    """PNG compression profiles; every profile preserves RGBA pixels exactly."""

    FAST = "fast"
    BALANCED = "balanced"
    SMALL = "small"


@dataclass(frozen=True, slots=True)
class ResizeOptions:
    """Immutable options describing one resize operation."""

    mode: ResizeMode = ResizeMode.NONE
    percent: int = 100
    width: int = 1024
    height: int = 1024
    keep_aspect_ratio: bool = True
    max_side: int = 1024

    def validate(self) -> None:
        """Raise ValueError when resize settings are invalid."""
        if self.mode == ResizeMode.PERCENT and not 1 <= self.percent <= 1000:
            raise ValueError("Phần trăm resize phải nằm trong khoảng 1–1000%.")
        if self.mode == ResizeMode.EXACT and (self.width < 1 or self.height < 1):
            raise ValueError("Chiều rộng và chiều cao phải lớn hơn 0.")
        if self.mode == ResizeMode.MAX_SIDE and self.max_side < 1:
            raise ValueError("Cạnh dài tối đa phải lớn hơn 0.")


@dataclass(frozen=True, slots=True)
class BatchOptions:
    """Configuration shared by every image in a batch."""

    input_directory: Path
    output_directory: Path
    remove_background: bool
    resize: ResizeOptions
    recursive: bool = True
    overwrite: bool = False
    model_name: str = "u2net"
    png_compression: PngCompressionMode = PngCompressionMode.FAST
    removal_mode: RemovalMode = "ai"
    color_samples: tuple[ColorSample, ...] = ()
    color_key_config: ColorKeyConfig = ColorKeyConfig()
    manual_strokes: tuple[MaskStroke, ...] = ()

    def validate(self) -> None:
        """Raise ValueError when the batch cannot safely run."""
        if not self.input_directory.is_dir():
            raise ValueError("Folder đầu vào không tồn tại.")
        if self.input_directory.resolve() == self.output_directory.resolve():
            raise ValueError("Folder đầu ra phải khác folder đầu vào để bảo vệ ảnh gốc.")
        if not self.remove_background and self.resize.mode == ResizeMode.NONE:
            raise ValueError("Hãy bật ít nhất một chức năng: xóa nền hoặc resize.")
        self.resize.validate()
        self.color_key_config.validate()
        if self.remove_background and self.removal_mode in {"color_key", "hybrid"} and not self.color_samples:
            raise ValueError("Chế độ theo màu cần ít nhất một mẫu màu nền.")


@dataclass(frozen=True, slots=True)
class SingleImageOptions:
    """Configuration for processing one image into an explicit output file."""

    source_file: Path
    output_file: Path
    remove_background: bool
    resize: ResizeOptions
    overwrite: bool = True
    model_name: str = "u2net"
    png_compression: PngCompressionMode = PngCompressionMode.FAST
    removal_mode: RemovalMode = "ai"
    color_samples: tuple[ColorSample, ...] = ()
    color_key_config: ColorKeyConfig = ColorKeyConfig()
    manual_strokes: tuple[MaskStroke, ...] = ()

    def validate(self) -> None:
        """Raise ValueError when a single-image operation is unsafe or invalid."""
        if not self.source_file.is_file():
            raise ValueError("Ảnh đầu vào không tồn tại.")
        if self.source_file.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError("Định dạng ảnh đầu vào chưa được hỗ trợ.")
        if self.output_file.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError("Định dạng file đầu ra chưa được hỗ trợ.")
        if self.remove_background and self.output_file.suffix.lower() != ".png":
            raise ValueError("Ảnh xóa nền phải được lưu ở định dạng PNG.")
        if self.source_file.resolve() == self.output_file.resolve():
            raise ValueError("Nơi lưu phải khác ảnh gốc để bảo vệ dữ liệu.")
        if not self.remove_background and self.resize.mode == ResizeMode.NONE:
            raise ValueError("Hãy bật ít nhất một chức năng: xóa nền hoặc resize.")
        self.resize.validate()
        self.color_key_config.validate()
        if self.remove_background and self.removal_mode in {"color_key", "hybrid"} and not self.color_samples:
            raise ValueError("Chế độ theo màu cần ít nhất một mẫu màu nền.")


@dataclass(frozen=True, slots=True)
class StageTimings:
    """Measured milliseconds spent in each image-processing stage."""

    decode_ms: float = 0.0
    preprocess_ms: float = 0.0
    inference_ms: float = 0.0
    postprocess_ms: float = 0.0
    encode_save_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        """Return the sum of all measured stages in milliseconds."""
        return self.decode_ms + self.preprocess_ms + self.inference_ms + self.postprocess_ms + self.encode_save_ms


@dataclass(frozen=True, slots=True)
class BatchProgress:
    """Progress snapshot emitted after processing one item."""

    completed: int
    total: int
    source: Path
    destination: Path | None
    error: str | None = None
    execution_provider: str | None = None
    timings: StageTimings | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Final statistics for a completed or cancelled batch."""

    total: int
    succeeded: int
    failed: int
    skipped: int
    cancelled: bool
