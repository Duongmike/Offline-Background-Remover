from __future__ import annotations

import argparse
import ctypes
import json
import platform
import random
import statistics
import subprocess
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .models import PngCompressionMode, ResizeOptions, SingleImageOptions, StageTimings
from .processing import BatchImageService, bundled_model_directory


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_rss_mb() -> float | None:
    """Return current process working-set MB on Windows."""
    if platform.system() != "Windows":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return counters.WorkingSetSize / (1024.0 * 1024.0)


def gpu_memory_used_mb() -> float | None:
    """Return total first-NVIDIA-GPU memory usage when nvidia-smi is available."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return float(output.splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class ResourceSampler:
    """Low-frequency RAM/VRAM sampler used only by the benchmark command."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True, name="benchmark-resource-sampler")
        self.ram_samples: list[float] = []
        self.vram_samples: list[float] = []

    def __enter__(self) -> ResourceSampler:
        """Start background sampling."""
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        """Stop background sampling and wait for the sampler."""
        self._stop.set()
        self._thread.join()

    def _sample(self) -> None:
        while not self._stop.is_set():
            ram = process_rss_mb()
            vram = gpu_memory_used_mb()
            if ram is not None:
                self.ram_samples.append(ram)
            if vram is not None:
                self.vram_samples.append(vram)
            self._stop.wait(0.05)


def create_benchmark_image(path: Path, size: int) -> None:
    """Create a deterministic image with gradients and a foreground shape."""
    axis = np.linspace(0, 255, size, dtype=np.uint8)
    pixels = np.empty((size, size, 3), dtype=np.uint8)
    pixels[:, :, 0] = axis[None, :]
    pixels[:, :, 1] = axis[:, None]
    pixels[:, :, 2] = (
        (axis[None, :].astype(np.uint16) + axis[:, None].astype(np.uint16)) // 2
    ).astype(np.uint8)
    image = Image.fromarray(pixels, "RGB")
    ImageDraw.Draw(image).ellipse((size // 5, size // 8, size * 4 // 5, size * 7 // 8), fill=(35, 105, 225))
    image.save(path, format="PNG", compress_level=6)
    image.close()


def timings_to_dict(timings: StageTimings) -> dict[str, float]:
    """Serialize one stage timing record."""
    return {
        "decode_ms": timings.decode_ms,
        "preprocess_ms": timings.preprocess_ms,
        "inference_ms": timings.inference_ms,
        "postprocess_ms": timings.postprocess_ms,
        "encode_save_ms": timings.encode_save_ms,
        "stage_total_ms": timings.total_ms,
    }


def median_timings(records: list[dict[str, float]]) -> dict[str, float]:
    """Return per-field medians for repeated warm runs."""
    return {key: statistics.median(record[key] for record in records) for key in records[0]}


def benchmark_runtime(model_name: str, repeats: int = 3) -> dict[str, Any]:
    """Benchmark model load, cold/warm stages, RAM, VRAM, and PNG profiles."""
    import onnxruntime as ort

    service = BatchImageService()
    report: dict[str, Any] = {
        "app_version": "1.4.0",
        "model": model_name,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "onnxruntime": ort.__version__,
            "available_providers": ort.get_available_providers(),
            "model_directory": str(bundled_model_directory()),
            "ram_initial_mb": process_rss_mb(),
            "vram_initial_mb": gpu_memory_used_mb(),
        },
        "sizes": {},
        "png_profiles": {},
    }
    with tempfile.TemporaryDirectory(prefix="kbgn_benchmark_") as temporary:
        root = Path(temporary)
        sources: dict[int, Path] = {}
        for size in (512, 1024, 2048):
            source = root / f"input_{size}.png"
            create_benchmark_image(source, size)
            sources[size] = source

        with ResourceSampler() as sampler:
            started = time.perf_counter()
            provider = service.prepare_model(model_name)
            load_ms = (time.perf_counter() - started) * 1000.0
            ram_after_load = process_rss_mb()
            vram_after_load = gpu_memory_used_mb()

            cold_progress = []
            started = time.perf_counter()
            cold_result = service.process_single(
                SingleImageOptions(
                    sources[512],
                    root / "cold_512.png",
                    True,
                    ResizeOptions(),
                    model_name=model_name,
                    png_compression=PngCompressionMode.FAST,
                ),
                threading.Event(),
                cold_progress.append,
            )
            cold_wall_ms = (time.perf_counter() - started) * 1000.0
            if cold_result.succeeded != 1 or not cold_progress[0].timings:
                raise RuntimeError(f"Cold benchmark thất bại: {cold_progress}")

            report["cold_start"] = {
                "provider": provider,
                "model_load_ms": load_ms,
                "first_image_wall_ms": cold_wall_ms,
                "ready_to_first_output_ms": load_ms + cold_wall_ms,
                "stages": timings_to_dict(cold_progress[0].timings),
                "ram_after_load_mb": ram_after_load,
                "vram_after_load_mb": vram_after_load,
            }

            for size, source in sources.items():
                records: list[dict[str, float]] = []
                wall_times: list[float] = []
                for repeat in range(repeats):
                    progress = []
                    started = time.perf_counter()
                    result = service.process_single(
                        SingleImageOptions(
                            source,
                            root / f"warm_{size}_{repeat}.png",
                            True,
                            ResizeOptions(),
                            model_name=model_name,
                            png_compression=PngCompressionMode.FAST,
                        ),
                        threading.Event(),
                        progress.append,
                    )
                    wall_times.append((time.perf_counter() - started) * 1000.0)
                    if result.succeeded != 1 or not progress[0].timings:
                        raise RuntimeError(f"Warm benchmark {size}px thất bại: {progress}")
                    records.append(timings_to_dict(progress[0].timings))
                values = median_timings(records)
                values["wall_ms"] = statistics.median(wall_times)
                report["sizes"][str(size)] = values

        report["resources"] = {
            "ram_peak_mb": max(sampler.ram_samples) if sampler.ram_samples else None,
            "vram_peak_mb": max(sampler.vram_samples) if sampler.vram_samples else None,
            "pipeline_high_water": {
                "decode_queue": service.pipeline.last_metrics.max_decode_queue,
                "inference_queue": service.pipeline.last_metrics.max_inference_queue,
                "encode_queue": service.pipeline.last_metrics.max_encode_queue,
                "inflight_images": service.pipeline.last_metrics.max_inflight_images,
            },
        }

        rgba = Image.open(sources[2048]).convert("RGBA")
        alpha = Image.fromarray(np.tile(np.linspace(0, 255, 2048, dtype=np.uint8), (2048, 1)), "L")
        rgba.putalpha(alpha)
        alpha.close()
        try:
            from .image_ops import atomic_save_image

            profile_times = {mode: [] for mode in PngCompressionMode}
            profile_sizes = {mode: [] for mode in PngCompressionMode}
            profile_alpha_exact = {mode: True for mode in PngCompressionMode}
            order = list(PngCompressionMode) * repeats
            random.Random(140).shuffle(order)
            expected_alpha = np.asarray(rgba.getchannel("A"))
            for index, mode in enumerate(order):
                output = root / f"profile_{mode.value}_{index}.png"
                profile_times[mode].append(atomic_save_image(rgba, output, mode))
                profile_sizes[mode].append(output.stat().st_size)
                with Image.open(output) as decoded:
                    profile_alpha_exact[mode] &= np.array_equal(expected_alpha, np.asarray(decoded.getchannel("A")))
            for mode in PngCompressionMode:
                report["png_profiles"][mode.value] = {
                    "median_ms": statistics.median(profile_times[mode]),
                    "median_bytes": statistics.median(profile_sizes[mode]),
                    "alpha_exact": profile_alpha_exact[mode],
                }
        finally:
            rgba.close()
    service.close()
    return report


def main() -> int:
    """Run the command-line benchmark and optionally persist JSON output."""
    parser = argparse.ArgumentParser(description="Benchmark pipeline xóa nền 1.4.0")
    parser.add_argument("--model", default="u2net", choices=("u2net", "u2netp"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = benchmark_runtime(arguments.model, max(1, arguments.repeats))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
