from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import os
import traceback

from PIL import Image, ImageDraw

from .models import BatchOptions, ResizeMode, ResizeOptions
from .processing import BatchImageService


def run_self_test(require_gpu: bool = False) -> int:
    """Run a packaged end-to-end AI and resize smoke test; return a process exit code."""
    diagnostics: list[str] = []
    service: BatchImageService | None = None
    try:
        with TemporaryDirectory(prefix="tach_nen_pro_") as temporary:
            root = Path(temporary)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()

            source = Image.new("RGB", (128, 128), "white")
            ImageDraw.Draw(source).ellipse((24, 14, 104, 114), fill="#2563EB")
            source.save(input_directory / "self_test.png")
            source.close()

            options = BatchOptions(
                input_directory=input_directory,
                output_directory=output_directory,
                remove_background=True,
                resize=ResizeOptions(mode=ResizeMode.PERCENT, percent=50),
                model_name="u2netp",
            )
            service = BatchImageService()
            result = service.process(
                options,
                Event(),
                lambda progress: diagnostics.append(progress.error or "OK"),
            )
            output = output_directory / "self_test.png"
            if result.succeeded != 1 or not output.exists():
                _write_diagnostics(diagnostics or [f"Result: {result}"])
                return 2
            if require_gpu and service.active_provider not in {
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "DmlExecutionProvider",
            }:
                _write_diagnostics([f"GPU required, active provider: {service.active_provider}"])
                return 5

            with Image.open(output) as processed:
                if processed.mode != "RGBA" or processed.size != (64, 64):
                    _write_diagnostics([f"Output: mode={processed.mode}, size={processed.size}"])
                    return 3
                alpha_minimum, alpha_maximum = processed.getchannel("A").getextrema()
                if alpha_minimum >= alpha_maximum:
                    _write_diagnostics([f"Alpha: {alpha_minimum}, {alpha_maximum}"])
                    return 4
            metrics = service.pipeline.last_metrics
            if metrics.max_inflight_images > 4 or max(
                metrics.max_decode_queue,
                metrics.max_inference_queue,
                metrics.max_encode_queue,
            ) > 2:
                _write_diagnostics([f"Pipeline limits exceeded: {metrics}"])
                return 6
        _clear_diagnostics()
        return 0
    except Exception:
        _write_diagnostics([traceback.format_exc()])
        return 1
    finally:
        if service is not None:
            service.close()


def _write_diagnostics(lines: list[str]) -> None:
    """Write self-test diagnostics to the OS temp directory when validation fails."""
    try:
        path = Path(os.getenv("TEMP", Path.home())) / "KhongBietGiDungNoi-self-test.log"
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass


def _clear_diagnostics() -> None:
    """Remove a stale diagnostics file after a successful self-test."""
    try:
        path = Path(os.getenv("TEMP", Path.home())) / "KhongBietGiDungNoi-self-test.log"
        path.unlink(missing_ok=True)
    except OSError:
        pass
