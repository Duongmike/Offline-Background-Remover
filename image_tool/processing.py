from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event

from .backends import (
    CPU_PROVIDER,
    CUDA_PROVIDER,
    DIRECTML_PROVIDER,
    TENSORRT_PROVIDER,
    BackendEvent,
    InferenceBackendManager,
    backend_priority,
    detect_available_providers,
)
from .config import AppConfig
from .image_ops import calculate_resize_size, resize_image
from .models import (
    SUPPORTED_IMAGE_EXTENSIONS,
    BatchOptions,
    BatchProgress,
    BatchResult,
    SingleImageOptions,
)
from .pipeline import BoundedImagePipeline, PipelineItemResult, PipelineRequest


SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS


def bundled_model_directory() -> Path:
    """Return the offline model directory in source or PyInstaller mode."""
    environment_path = os.getenv("U2NET_HOME")
    if environment_path:
        return Path(environment_path)
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / "assets" / "models"


def select_execution_providers(available: Sequence[str] | None = None) -> list[str]:
    """Return available providers in TensorRT → CUDA → DirectML → CPU order."""
    provider_set = set(available) if available is not None else detect_available_providers()
    selected = [provider for provider in backend_priority() if provider in provider_set]
    return selected or [CPU_PROVIDER]


def describe_execution_backend() -> str:
    """Return a concise Vietnamese label for the best installed backend."""
    provider = select_execution_providers()[0]
    labels = {
        TENSORRT_PROVIDER: "GPU TensorRT",
        CUDA_PROVIDER: "GPU CUDA",
        DIRECTML_PROVIDER: "GPU DirectML",
        CPU_PROVIDER: "CPU tối ưu",
    }
    return labels.get(provider, provider)


def discover_images(input_directory: Path, recursive: bool, excluded_directory: Path | None = None) -> list[Path]:
    """Return a stable, sorted list of supported images."""
    iterator = input_directory.rglob("*") if recursive else input_directory.glob("*")
    excluded = excluded_directory.resolve() if excluded_directory else None
    images: list[Path] = []
    for path in iterator:
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if excluded is not None:
            try:
                path.resolve().relative_to(excluded)
                continue
            except ValueError:
                pass
        images.append(path)
    return sorted(images, key=lambda item: str(item).casefold())


class BatchImageService:
    """Application service that owns one backend manager and one bounded pipeline."""

    def __init__(
        self,
        config: AppConfig | None = None,
        model_directory: Path | None = None,
        backend_manager: InferenceBackendManager | None = None,
        on_backend_event: Callable[[BackendEvent], None] | None = None,
    ) -> None:
        self._config = config or AppConfig()
        self._backend_manager = backend_manager or InferenceBackendManager(
            model_directory or bundled_model_directory(),
            self._config.backend,
            on_event=on_backend_event,
        )
        self._pipeline = BoundedImagePipeline(self._backend_manager, self._config.pipeline)

    @property
    def active_provider(self) -> str:
        """Return the provider currently owning the one ONNX session."""
        return self._backend_manager.active_provider

    @property
    def pipeline(self) -> BoundedImagePipeline:
        """Expose read-only pipeline metrics for diagnostics and tests."""
        return self._pipeline

    def preload(self, model_name: str) -> str:
        """Load and warm the selected model without blocking the Tkinter thread."""
        provider = self.prepare_model(model_name)
        import numpy as np

        warmup = np.zeros((1, 3, 320, 320), dtype=np.float32)
        _, provider = self._backend_manager.infer(model_name, warmup)
        return provider

    def prepare_model(self, model_name: str) -> str:
        """Load the selected model without running warm inference."""
        return self._backend_manager.prepare(model_name)

    def process(
        self,
        options: BatchOptions,
        cancel_event: Event,
        on_progress: Callable[[BatchProgress], None],
    ) -> BatchResult:
        """Process a folder through the bounded pipeline and report progress."""
        options.validate()
        images = discover_images(options.input_directory, options.recursive, options.output_directory)
        destinations = self._build_destination_map(images, options)
        requests = [self._request(source, destinations[source], options) for source in images]
        return self._run_requests(requests, cancel_event, on_progress)

    def process_single(
        self,
        options: SingleImageOptions,
        cancel_event: Event,
        on_progress: Callable[[BatchProgress], None],
    ) -> BatchResult:
        """Process one image into the exact Save As destination."""
        options.validate()
        request = self._request(options.source_file, options.output_file, options)
        return self._run_requests([request], cancel_event, on_progress)

    def request_shutdown(self) -> None:
        """Request non-blocking shutdown for background preload and inference."""
        self._backend_manager.request_shutdown()

    def close(self) -> None:
        """Release the active ONNX session after workers have stopped."""
        self._backend_manager.close()

    def _run_requests(
        self,
        requests: Sequence[PipelineRequest],
        cancel_event: Event,
        on_progress: Callable[[BatchProgress], None],
    ) -> BatchResult:
        total = len(requests)
        succeeded = failed = skipped = completed = 0

        def handle(item: PipelineItemResult) -> None:
            nonlocal succeeded, failed, skipped, completed
            completed += 1
            if item.outcome == "ok":
                succeeded += 1
            elif item.outcome == "skip":
                skipped += 1
            else:
                failed += 1
            on_progress(
                BatchProgress(
                    completed,
                    total,
                    item.source,
                    item.destination,
                    item.error,
                    item.provider,
                    item.timings,
                )
            )

        cancelled = self._pipeline.run(requests, cancel_event, handle)
        return BatchResult(total, succeeded, failed, skipped, cancelled)

    @staticmethod
    def _request(
        source: Path,
        destination: Path,
        options: BatchOptions | SingleImageOptions,
    ) -> PipelineRequest:
        return PipelineRequest(
            source,
            destination,
            options.remove_background,
            options.resize,
            options.model_name,
            options.png_compression,
            options.overwrite,
            options.removal_mode,
            options.color_samples,
            options.color_key_config,
            options.manual_strokes,
        )

    @staticmethod
    def _build_destination_map(images: list[Path], options: BatchOptions) -> dict[Path, Path]:
        """Build unique destinations while preserving relative subfolders."""
        destinations: dict[Path, Path] = {}
        used: set[str] = set()
        for source in images:
            relative = source.relative_to(options.input_directory)
            destination = options.output_directory / relative
            if options.remove_background:
                destination = destination.with_suffix(".png")
            normalized = str(destination).casefold()
            if normalized in used:
                suffix_label = source.suffix.lower().lstrip(".") or "image"
                base_stem = destination.stem
                destination = destination.with_name(f"{base_stem}_{suffix_label}{destination.suffix}")
                counter = 2
                while str(destination).casefold() in used:
                    destination = destination.with_name(f"{base_stem}_{suffix_label}_{counter}{destination.suffix}")
                    counter += 1
            used.add(str(destination).casefold())
            destinations[source] = destination
        return destinations
