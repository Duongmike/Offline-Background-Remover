from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .backends import InferenceBackendManager
from .config import PipelineConfig
from .image_ops import atomic_save_image, decode_image, preprocess_u2net, resize_image
from .color_key_config import ColorKeyConfig, ColorSample, RemovalMode
from .manual_mask import MaskStroke
from .models import PngCompressionMode, ResizeOptions, StageTimings
from .removal_strategies import RemovalContext, create_removal_strategy


_SENTINEL = object()
_PIPELINE_DONE = object()


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    """One source/destination pair flowing through the bounded pipeline."""

    source: Path
    destination: Path
    remove_background: bool
    resize: ResizeOptions
    model_name: str
    png_compression: PngCompressionMode
    overwrite: bool
    removal_mode: RemovalMode = "ai"
    color_samples: tuple[ColorSample, ...] = ()
    color_key_config: ColorKeyConfig = ColorKeyConfig()
    manual_strokes: tuple[MaskStroke, ...] = ()


@dataclass(slots=True)
class PreparedImage:
    """Decoded full-resolution image and optional compact AI input tensor."""

    request: PipelineRequest
    image: Image.Image
    tensor: np.ndarray | None
    decode_ms: float
    preprocess_ms: float


@dataclass(slots=True)
class InferredImage:
    """Prepared item with optional raw mask output from the single GPU stage."""

    prepared: PreparedImage
    raw_output: np.ndarray | None
    inference_ms: float
    provider: str | None


@dataclass(frozen=True, slots=True)
class PipelineItemResult:
    """Completed, skipped, or failed item emitted to the application service."""

    source: Path
    destination: Path
    outcome: str
    error: str | None = None
    provider: str | None = None
    timings: StageTimings | None = None


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    """High-water marks proving queue and memory back-pressure limits."""

    max_decode_queue: int
    max_inference_queue: int
    max_encode_queue: int
    max_inflight_images: int


class _MetricsTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.decode_queue = 0
        self.inference_queue = 0
        self.encode_queue = 0
        self.inflight = 0
        self.max_inflight = 0

    def observe_queue(self, stage: str, size: int) -> None:
        """Record one bounded queue high-water observation."""
        with self._lock:
            if stage == "decode":
                self.decode_queue = max(self.decode_queue, size)
            elif stage == "inference":
                self.inference_queue = max(self.inference_queue, size)
            else:
                self.encode_queue = max(self.encode_queue, size)

    def add_inflight(self) -> None:
        """Increment the number of full-resolution items currently in memory."""
        with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)

    def remove_inflight(self) -> None:
        """Decrement the number of full-resolution items currently in memory."""
        with self._lock:
            self.inflight = max(0, self.inflight - 1)

    def snapshot(self) -> PipelineMetrics:
        """Return an immutable metrics snapshot."""
        with self._lock:
            return PipelineMetrics(self.decode_queue, self.inference_queue, self.encode_queue, self.max_inflight)


class BoundedImagePipeline:
    """Bounded CPU → single inference → CPU pipeline with cancellation and back-pressure."""

    def __init__(self, backend_manager: InferenceBackendManager, config: PipelineConfig | None = None) -> None:
        self._backend_manager = backend_manager
        self._config = config or PipelineConfig()
        self._config.validate()
        self._last_metrics = PipelineMetrics(0, 0, 0, 0)

    @property
    def last_metrics(self) -> PipelineMetrics:
        """Return queue high-water marks from the latest run."""
        return self._last_metrics

    def run(
        self,
        requests: Sequence[PipelineRequest],
        cancel_event: threading.Event,
        on_item: Callable[[PipelineItemResult], None],
    ) -> bool:
        """Process requests and return True when cancellation stopped submission."""
        if not requests:
            self._last_metrics = PipelineMetrics(0, 0, 0, 0)
            return cancel_event.is_set()

        capacity = self._config.queue_capacity
        decode_queue: queue.Queue[object] = queue.Queue(maxsize=capacity)
        inference_queue: queue.Queue[object] = queue.Queue(maxsize=capacity)
        encode_queue: queue.Queue[object] = queue.Queue(maxsize=capacity)
        result_queue: queue.Queue[object] = queue.Queue()
        inflight = threading.BoundedSemaphore(self._config.max_inflight_images)
        metrics = _MetricsTracker()
        decoder_lock = threading.Lock()
        encoder_lock = threading.Lock()
        decoders_remaining = self._config.decode_workers
        encoders_remaining = self._config.encode_workers

        def finish_inflight() -> None:
            metrics.remove_inflight()
            inflight.release()

        def put_bounded(target: queue.Queue[object], item: object, stage: str) -> None:
            while True:
                try:
                    target.put(item, timeout=0.1)
                    metrics.observe_queue(stage, target.qsize())
                    return
                except queue.Full:
                    continue

        def feeder() -> None:
            try:
                for request in requests:
                    if cancel_event.is_set():
                        break
                    if request.destination.exists() and not request.overwrite:
                        result_queue.put(PipelineItemResult(request.source, request.destination, "skip", "Đã tồn tại – bỏ qua"))
                        continue
                    while not cancel_event.is_set():
                        if inflight.acquire(timeout=0.1):
                            metrics.add_inflight()
                            put_bounded(decode_queue, request, "decode")
                            break
            finally:
                for _ in range(self._config.decode_workers):
                    put_bounded(decode_queue, _SENTINEL, "decode")

        def decode_worker() -> None:
            nonlocal decoders_remaining
            while True:
                item = decode_queue.get()
                try:
                    if item is _SENTINEL:
                        break
                    assert isinstance(item, PipelineRequest)
                    if cancel_event.is_set():
                        finish_inflight()
                        continue
                    image: Image.Image | None = None
                    try:
                        image, decode_ms = decode_image(item.source)
                        tensor: np.ndarray | None = None
                        preprocess_ms = 0.0
                        strategy = create_removal_strategy(item.removal_mode)
                        if item.remove_background and strategy.requires_ai:
                            tensor, preprocess_ms = preprocess_u2net(image)
                        put_bounded(inference_queue, PreparedImage(item, image, tensor, decode_ms, preprocess_ms), "inference")
                        image = None
                    except Exception as exc:
                        if image is not None:
                            image.close()
                        result_queue.put(PipelineItemResult(item.source, item.destination, "error", f"Decode/tiền xử lý: {exc}"))
                        finish_inflight()
                finally:
                    decode_queue.task_done()
            with decoder_lock:
                decoders_remaining -= 1
                if decoders_remaining == 0:
                    put_bounded(inference_queue, _SENTINEL, "inference")

        def inference_worker() -> None:
            while True:
                item = inference_queue.get()
                try:
                    if item is _SENTINEL:
                        break
                    assert isinstance(item, PreparedImage)
                    if cancel_event.is_set():
                        item.image.close()
                        finish_inflight()
                        continue
                    try:
                        raw_output: np.ndarray | None = None
                        provider: str | None = None
                        inference_ms = 0.0
                        if item.tensor is not None:
                            started = time.perf_counter()
                            raw_output, provider = self._backend_manager.infer(item.request.model_name, item.tensor)
                            inference_ms = (time.perf_counter() - started) * 1000.0
                        put_bounded(encode_queue, InferredImage(item, raw_output, inference_ms, provider), "encode")
                    except Exception as exc:
                        item.image.close()
                        result_queue.put(PipelineItemResult(item.request.source, item.request.destination, "error", f"AI inference: {exc}"))
                        finish_inflight()
                finally:
                    inference_queue.task_done()
            for _ in range(self._config.encode_workers):
                put_bounded(encode_queue, _SENTINEL, "encode")

        def encode_worker() -> None:
            nonlocal encoders_remaining
            while True:
                item = encode_queue.get()
                try:
                    if item is _SENTINEL:
                        break
                    assert isinstance(item, InferredImage)
                    prepared = item.prepared
                    if cancel_event.is_set():
                        prepared.image.close()
                        finish_inflight()
                        continue
                    image = prepared.image
                    postprocess_ms = 0.0
                    try:
                        if prepared.request.remove_background:
                            strategy = create_removal_strategy(prepared.request.removal_mode)
                            context = RemovalContext(
                                prepared.request.color_samples,
                                prepared.request.color_key_config,
                                prepared.request.manual_strokes,
                            )
                            processed, postprocess_ms = strategy.remove(image, item.raw_output, context)
                            image.close()
                            image = processed
                        image = resize_image(image, prepared.request.resize)
                        encode_ms = atomic_save_image(image, prepared.request.destination, prepared.request.png_compression)
                        timings = StageTimings(
                            prepared.decode_ms,
                            prepared.preprocess_ms,
                            item.inference_ms,
                            postprocess_ms,
                            encode_ms,
                        )
                        result_queue.put(PipelineItemResult(prepared.request.source, prepared.request.destination, "ok", provider=item.provider, timings=timings))
                    except Exception as exc:
                        result_queue.put(PipelineItemResult(prepared.request.source, prepared.request.destination, "error", f"Hậu xử lý/lưu file: {exc}", item.provider))
                    finally:
                        image.close()
                        finish_inflight()
                finally:
                    encode_queue.task_done()
            with encoder_lock:
                encoders_remaining -= 1
                if encoders_remaining == 0:
                    result_queue.put(_PIPELINE_DONE)

        threads = [threading.Thread(target=feeder, daemon=True, name="pipeline-feeder")]
        threads.extend(threading.Thread(target=decode_worker, daemon=True, name=f"pipeline-decode-{index}") for index in range(self._config.decode_workers))
        threads.append(threading.Thread(target=inference_worker, daemon=True, name="pipeline-inference"))
        threads.extend(threading.Thread(target=encode_worker, daemon=True, name=f"pipeline-encode-{index}") for index in range(self._config.encode_workers))
        for thread in threads:
            thread.start()

        while True:
            result = result_queue.get()
            if result is _PIPELINE_DONE:
                break
            if isinstance(result, PipelineItemResult):
                on_item(result)
        for thread in threads:
            thread.join()
        self._last_metrics = metrics.snapshot()
        return cancel_event.is_set()
