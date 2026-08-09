"""Repeatable 1.5.0 benchmark for advanced colour-key and hybrid processing."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from threading import Event

from PIL import Image

from .color_key import median_color_sample
from .color_key_config import ColorKeyConfig
from .models import ResizeOptions, SingleImageOptions
from .processing import BatchImageService


def _benchmark_samples(image: Image.Image) -> tuple:
    """Create the known lime-background seed for the supplied 1.5.0 benchmark image."""
    width, height = image.size
    return (median_color_sample(image, (width // 2, height // 2), 7),)


def benchmark(source: Path, output_directory: Path, model_name: str = "u2netp") -> dict[str, object]:
    """Measure cold/warm total processing and write colour-key and hybrid comparison PNGs."""
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh benchmark: {source}")
    output_directory.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        samples = _benchmark_samples(opened)
    config = ColorKeyConfig()
    service = BatchImageService()
    records: dict[str, object] = {"source": str(source), "outputs": {}, "runs": {}}
    try:
        for mode, name in (("color_key", "color_key_1.5.0.png"), ("hybrid", "hybrid_1.5.0.png")):
            destination = output_directory / name
            options = SingleImageOptions(source, destination, True, ResizeOptions(), model_name=model_name, removal_mode=mode, color_samples=samples, color_key_config=config)
            run_times: list[float] = []
            stage_records: list[dict[str, float]] = []
            for _ in range(2):
                started = time.perf_counter()
                progress = []
                result = service.process_single(options, Event(), progress.append)
                if result.failed or not result.succeeded:
                    raise RuntimeError(f"Benchmark {mode} không hoàn tất: {result}")
                run_times.append((time.perf_counter() - started) * 1000.0)
                timings = progress[-1].timings
                if timings is not None:
                    stage_records.append({"decode_ms": timings.decode_ms, "rgb_lab_hsv_ms": timings.preprocess_ms, "inference_ms": timings.inference_ms, "mask_refinement_ms": timings.postprocess_ms, "encode_png_ms": timings.encode_save_ms})
            records["runs"][mode] = {"cold_ms": run_times[0], "warm_ms": run_times[1], "stages": stage_records}
            records["outputs"][mode] = {"path": str(destination), "bytes": destination.stat().st_size}
        # Size sweep uses generated copies only; the real input and comparison outputs stay untouched.
        size_runs: dict[str, object] = {}
        with tempfile.TemporaryDirectory(prefix="color_key_benchmark_") as temporary:
            temporary_root = Path(temporary)
            with Image.open(source) as opened:
                for size in (512, 1024, 2048):
                    scaled = opened.convert("RGB")
                    try:
                        scaled.thumbnail((size, size), Image.Resampling.LANCZOS)
                        input_path = temporary_root / f"input_{size}.png"
                        scaled.save(input_path)
                    finally:
                        scaled.close()
                    destination = temporary_root / f"output_{size}.png"
                    progress = []
                    started = time.perf_counter()
                    result = service.process_single(
                        SingleImageOptions(input_path, destination, True, ResizeOptions(), removal_mode="color_key", color_samples=samples, color_key_config=config),
                        Event(),
                        progress.append,
                    )
                    if result.failed or not result.succeeded or progress[-1].timings is None:
                        raise RuntimeError(f"Benchmark {size}px không hoàn tất: {result}")
                    timings = progress[-1].timings
                    size_runs[str(size)] = {
                        "total_ms": (time.perf_counter() - started) * 1000.0,
                        "decode_ms": timings.decode_ms,
                        "rgb_lab_hsv_ms": timings.preprocess_ms,
                        "inference_ms": timings.inference_ms,
                        "mask_refinement_ms": timings.postprocess_ms,
                        "encode_png_ms": timings.encode_save_ms,
                        "png_bytes": destination.stat().st_size,
                    }
        records["size_sweep_color_key"] = size_runs
    finally:
        service.close()
    return records


def main() -> int:
    """Run the benchmark CLI and save JSON without touching source files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("benchmarks"))
    arguments = parser.parse_args()
    tracemalloc.start()
    report = benchmark(arguments.source, arguments.output)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report["python_tracemalloc_peak_mb"] = peak / (1024 * 1024)
    report_path = arguments.output / "color_key_1.5.0.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
