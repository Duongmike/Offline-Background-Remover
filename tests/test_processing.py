from __future__ import annotations

import gc
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from threading import Event

import numpy as np
from PIL import Image

from image_tool.backends import (
    CPU_PROVIDER,
    CUDA_PROVIDER,
    DIRECTML_PROVIDER,
    TENSORRT_PROVIDER,
    IInferenceBackend,
    InferenceBackendManager,
)
from image_tool.config import AppConfig, PipelineConfig
from image_tool.image_ops import atomic_save_image, calculate_resize_size
from image_tool.models import (
    BatchOptions,
    PngCompressionMode,
    ResizeMode,
    ResizeOptions,
    SingleImageOptions,
)
from image_tool.processing import BatchImageService, discover_images, select_execution_providers


class FakeBackendManager:
    """Small deterministic backend used to test pipeline behavior without model IO."""

    def __init__(self, inference_delay: float = 0.0) -> None:
        self.active_provider = CPU_PROVIDER
        self.inference_delay = inference_delay
        self.calls = 0

    def prepare(self, _model_name: str) -> str:
        """Return the fake provider without allocating a session."""
        return self.active_provider

    def infer(self, _model_name: str, _tensor: np.ndarray) -> tuple[np.ndarray, str]:
        """Return a stable soft mask after an optional test delay."""
        self.calls += 1
        if self.inference_delay:
            time.sleep(self.inference_delay)
        axis = np.linspace(-1.0, 1.0, 320, dtype=np.float32)
        x, y = np.meshgrid(axis, axis)
        mask = 1.0 - np.clip(np.sqrt(x * x + y * y), 0.0, 1.0)
        return mask[None, None, :, :], self.active_provider

    def request_shutdown(self) -> None:
        """No-op shutdown signal for tests."""

    def close(self) -> None:
        """No-op close for tests."""


class FakeInferenceBackend(IInferenceBackend):
    """Controllable backend used to validate selection, fallback, and reuse."""

    def __init__(self, provider: str, fail_load: bool = False, fail_infer: bool = False) -> None:
        self._provider = provider
        self.fail_load = fail_load
        self.fail_infer = fail_infer
        self.load_count = 0
        self.close_count = 0

    @property
    def display_name(self) -> str:
        """Return a test label."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Return the configured test provider."""
        return self._provider

    def is_available(self, available_providers: set[str]) -> bool:
        """Return whether this fake provider is listed."""
        return self._provider in available_providers

    def load(self, _model_path: Path) -> None:
        """Count loads and optionally fail."""
        self.load_count += 1
        if self.fail_load:
            raise RuntimeError("load failure")

    def infer(self, _input_tensor: np.ndarray) -> np.ndarray:
        """Return a fake output or raise an inference failure."""
        if self.fail_infer:
            raise RuntimeError("infer failure")
        return np.ones((1, 1, 2, 2), dtype=np.float32)

    def close(self) -> None:
        """Count resource releases."""
        self.close_count += 1


class ResizeTests(unittest.TestCase):
    def test_percent_resize(self) -> None:
        options = ResizeOptions(mode=ResizeMode.PERCENT, percent=50)
        self.assertEqual((400, 300), calculate_resize_size((800, 600), options))

    def test_exact_resize_keeps_aspect(self) -> None:
        options = ResizeOptions(mode=ResizeMode.EXACT, width=500, height=500, keep_aspect_ratio=True)
        self.assertEqual((500, 250), calculate_resize_size((1000, 500), options))

    def test_max_side_does_not_upscale(self) -> None:
        options = ResizeOptions(mode=ResizeMode.MAX_SIDE, max_side=1024)
        self.assertEqual((640, 480), calculate_resize_size((640, 480), options))


class BackendTests(unittest.TestCase):
    def test_provider_selection_uses_required_priority(self) -> None:
        available = [CPU_PROVIDER, DIRECTML_PROVIDER, CUDA_PROVIDER, TENSORRT_PROVIDER]
        self.assertEqual([TENSORRT_PROVIDER, CUDA_PROVIDER, DIRECTML_PROVIDER, CPU_PROVIDER], select_execution_providers(available))

    def test_load_falls_back_from_tensorrt_to_cuda(self) -> None:
        trt = FakeInferenceBackend(TENSORRT_PROVIDER, fail_load=True)
        cuda = FakeInferenceBackend(CUDA_PROVIDER)
        events = []
        manager = InferenceBackendManager(
            Path("."),
            available_providers={TENSORRT_PROVIDER, CUDA_PROVIDER},
            factories=[lambda: trt, lambda: cuda],
            on_event=events.append,
        )
        self.assertEqual(CUDA_PROVIDER, manager.prepare("unused"))
        self.assertEqual(1, trt.load_count)
        self.assertEqual(1, cuda.load_count)
        self.assertTrue(any("fallback" in event.message or "backend tiếp theo" in event.message for event in events))

    def test_inference_failure_falls_back_safely(self) -> None:
        trt = FakeInferenceBackend(TENSORRT_PROVIDER, fail_infer=True)
        cuda = FakeInferenceBackend(CUDA_PROVIDER)
        manager = InferenceBackendManager(
            Path("."),
            available_providers={TENSORRT_PROVIDER, CUDA_PROVIDER},
            factories=[lambda: trt, lambda: cuda],
        )
        output, provider = manager.infer("unused", np.zeros((1, 3, 2, 2), dtype=np.float32))
        self.assertEqual(CUDA_PROVIDER, provider)
        self.assertEqual((1, 1, 2, 2), output.shape)
        self.assertGreaterEqual(trt.close_count, 1)

    def test_tensor_and_cuda_failures_continue_to_directml(self) -> None:
        trt = FakeInferenceBackend(TENSORRT_PROVIDER, fail_load=True)
        cuda = FakeInferenceBackend(CUDA_PROVIDER, fail_load=True)
        directml = FakeInferenceBackend(DIRECTML_PROVIDER)
        manager = InferenceBackendManager(
            Path("."),
            available_providers={TENSORRT_PROVIDER, CUDA_PROVIDER, DIRECTML_PROVIDER},
            factories=[lambda: trt, lambda: cuda, lambda: directml],
        )
        self.assertEqual(DIRECTML_PROVIDER, manager.prepare("unused"))
        self.assertEqual(1, trt.load_count)
        self.assertEqual(1, cuda.load_count)
        self.assertEqual(1, directml.load_count)

    def test_prepare_reuses_exactly_one_session(self) -> None:
        cpu = FakeInferenceBackend(CPU_PROVIDER)
        manager = InferenceBackendManager(
            Path("."),
            available_providers={CPU_PROVIDER},
            factories=[lambda: cpu],
        )
        manager.prepare("unused")
        manager.prepare("unused")
        manager.infer("unused", np.zeros((1, 3, 2, 2), dtype=np.float32))
        self.assertEqual(1, cpu.load_count)


class BatchTests(unittest.TestCase):
    def make_service(self, delay: float = 0.0, max_inflight: int = 4) -> BatchImageService:
        """Create a service with deterministic inference and small queue limits."""
        config = AppConfig(pipeline=PipelineConfig(2, 2, 2, max_inflight))
        return BatchImageService(config=config, backend_manager=FakeBackendManager(delay))  # type: ignore[arg-type]

    def test_single_image_writes_unicode_path_and_png_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "ảnh gốc.jpg"
            destination = root / "nơi lưu" / "kết quả.png"
            Image.new("RGB", (40, 20), "red").save(source)
            options = SingleImageOptions(source, destination, True, ResizeOptions(mode=ResizeMode.PERCENT, percent=50))
            progress = []
            result = self.make_service().process_single(options, Event(), progress.append)
            self.assertEqual(1, result.succeeded)
            self.assertEqual(destination, progress[0].destination)
            with Image.open(destination) as processed:
                self.assertEqual((20, 10), processed.size)
                self.assertEqual("RGBA", processed.mode)
                self.assertLess(processed.getchannel("A").getextrema()[0], processed.getchannel("A").getextrema()[1])

    def test_single_image_rejects_overwriting_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.png"
            Image.new("RGB", (10, 10), "blue").save(source)
            options = SingleImageOptions(source, source, True, ResizeOptions())
            with self.assertRaisesRegex(ValueError, "khác ảnh gốc"):
                options.validate()

    def test_discovery_and_output_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            nested = input_dir / "nested"
            output_dir = input_dir / "generated"
            nested.mkdir(parents=True)
            output_dir.mkdir()
            Image.new("RGB", (20, 10), "red").save(input_dir / "one.jpg")
            Image.new("RGB", (10, 20), "blue").save(nested / "two.png")
            Image.new("RGB", (5, 5), "green").save(output_dir / "ignored.png")
            self.assertEqual(2, len(discover_images(input_dir, True, output_dir)))
            options = BatchOptions(input_dir, output_dir, True, ResizeOptions(mode=ResizeMode.PERCENT, percent=50))
            result = self.make_service().process(options, Event(), lambda _progress: None)
            self.assertEqual(2, result.succeeded)
            self.assertTrue((output_dir / "one.png").exists())
            self.assertTrue((output_dir / "nested" / "two.png").exists())

    def test_pipeline_never_exceeds_queue_or_inflight_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            for index in range(12):
                Image.new("RGB", (256, 256), (index * 10, 40, 80)).save(input_dir / f"image_{index}.png")
            service = self.make_service(delay=0.01, max_inflight=3)
            result = service.process(BatchOptions(input_dir, output_dir, True, ResizeOptions()), Event(), lambda _progress: None)
            metrics = service.pipeline.last_metrics
            self.assertEqual(12, result.succeeded)
            self.assertLessEqual(metrics.max_inflight_images, 3)
            self.assertLessEqual(metrics.max_decode_queue, 2)
            self.assertLessEqual(metrics.max_inference_queue, 2)
            self.assertLessEqual(metrics.max_encode_queue, 2)

    def test_batch_cancellation_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            for index in range(20):
                Image.new("RGB", (256, 256), "blue").save(input_dir / f"image_{index}.png")
            service = self.make_service(delay=0.05, max_inflight=3)
            cancel = Event()
            holder = []
            worker = threading.Thread(
                target=lambda: holder.append(service.process(BatchOptions(input_dir, output_dir, True, ResizeOptions()), cancel, lambda _p: None))
            )
            worker.start()
            time.sleep(0.08)
            cancel.set()
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
            self.assertTrue(holder[0].cancelled)
            self.assertFalse(any(output_dir.rglob("*.processing.png")))

    def test_png_profiles_preserve_alpha_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rgba = np.zeros((64, 64, 4), dtype=np.uint8)
            rgba[:, :, :3] = (20, 100, 220)
            rgba[:, :, 3] = np.arange(64, dtype=np.uint8)[None, :] * 4
            image = Image.fromarray(rgba, "RGBA")
            try:
                for mode in PngCompressionMode:
                    path = root / f"{mode.value}.png"
                    atomic_save_image(image, path, mode)
                    with Image.open(path) as decoded:
                        self.assertTrue(np.array_equal(rgba[:, :, 3], np.asarray(decoded.getchannel("A"))))
            finally:
                image.close()

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            Image.new("RGB", (16, 16), "red").save(input_dir / "same.png")
            existing = output_dir / "same.png"
            Image.new("RGBA", (7, 7), "green").save(existing)
            result = self.make_service().process(BatchOptions(input_dir, output_dir, True, ResizeOptions()), Event(), lambda _p: None)
            self.assertEqual(1, result.skipped)
            with Image.open(existing) as output:
                self.assertEqual((7, 7), output.size)


class BackendEquivalenceTests(unittest.TestCase):
    def test_new_backend_alpha_is_near_legacy_rembg(self) -> None:
        try:
            from rembg import new_session, remove
        except ImportError as exc:
            self.skipTest(f"rembg unavailable: {exc}")
        from image_tool.image_ops import postprocess_u2net, preprocess_u2net
        from image_tool.processing import bundled_model_directory
        import onnxruntime as ort

        model_dir = bundled_model_directory()
        os.environ["U2NET_HOME"] = str(model_dir)
        providers = [DIRECTML_PROVIDER] if DIRECTML_PROVIDER in ort.get_available_providers() else [CPU_PROVIDER]
        image = Image.new("RGB", (128, 96), "white")
        pixels = np.asarray(image).copy()
        pixels[15:85, 32:100] = (30, 100, 220)
        image.close()
        source = Image.fromarray(pixels, "RGB")
        legacy_session = new_session("u2netp", providers=providers)
        legacy = remove(source, session=legacy_session).convert("RGBA")
        del legacy_session
        gc.collect()

        config = AppConfig()
        manager = InferenceBackendManager(model_dir, config.backend, available_providers=set(providers))
        tensor, _ = preprocess_u2net(source)
        raw, _ = manager.infer("u2netp", tensor)
        modern, _ = postprocess_u2net(source, raw)
        manager.close()
        legacy_alpha = np.asarray(legacy.getchannel("A"), dtype=np.int16)
        modern_alpha = np.asarray(modern.getchannel("A"), dtype=np.int16)
        mae = float(np.mean(np.abs(legacy_alpha - modern_alpha)))
        legacy.close()
        modern.close()
        source.close()
        self.assertLessEqual(mae, 1.0)


if __name__ == "__main__":
    unittest.main()
