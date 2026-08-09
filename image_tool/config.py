from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import PngCompressionMode


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Resource limits and cache settings shared by ONNX backends."""

    gpu_memory_limit_bytes: int = 3 * 1024 * 1024 * 1024
    tensorrt_workspace_bytes: int = 1536 * 1024 * 1024
    cpu_threads: int = min(6, max(1, os.cpu_count() or 1))
    enable_tensorrt_fp16: bool = True
    fp16_quality_manifest: Path | None = None
    tensorrt_cache_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Bounded pipeline settings that cap full-resolution images in memory."""

    decode_workers: int = 2
    encode_workers: int = 2
    queue_capacity: int = 2
    max_inflight_images: int = 4

    def validate(self) -> None:
        """Raise ValueError when a pipeline limit is unsafe or invalid."""
        if self.decode_workers < 1 or self.encode_workers < 1:
            raise ValueError("Số worker decode/encode phải lớn hơn 0.")
        if self.queue_capacity < 1:
            raise ValueError("Giới hạn queue phải lớn hơn 0.")
        if self.max_inflight_images < 1:
            raise ValueError("Giới hạn ảnh trong bộ nhớ phải lớn hơn 0.")


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application defaults kept outside UI and processing implementations."""

    preload_model: bool = True
    png_compression: PngCompressionMode = PngCompressionMode.FAST
    backend: BackendConfig = BackendConfig()
    pipeline: PipelineConfig = PipelineConfig()
