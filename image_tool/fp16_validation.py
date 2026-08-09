from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .backends import CUDA_PROVIDER, TENSORRT_PROVIDER, sha256_file
from .config import BackendConfig
from .image_ops import postprocess_u2net, preprocess_u2net
from .processing import bundled_model_directory


def _create_session(model_path: Path, providers: list[object], config: BackendConfig) -> object:
    """Create one temporary validation session with conservative 4 GB limits."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.log_severity_level = 3
    return ort.InferenceSession(str(model_path), sess_options=options, providers=providers)


def _run_mask(session: object, image: Image.Image) -> np.ndarray:
    """Run a validation session and return its final uint8 alpha channel."""
    tensor, _ = preprocess_u2net(image)
    input_name = getattr(session, "get_inputs")()[0].name
    raw = getattr(session, "run")(None, {input_name: tensor})[0]
    cutout, _ = postprocess_u2net(image, raw)
    try:
        return np.asarray(cutout.getchannel("A"), dtype=np.uint8).copy()
    finally:
        cutout.close()


def validate_fp16(model_path: Path, sample_paths: list[Path], max_alpha_mae: float = 1.0) -> dict[str, Any]:
    """Compare TensorRT FP16 alpha against CUDA FP32 and return a signed-off manifest."""
    import onnxruntime as ort

    available = set(ort.get_available_providers())
    missing = {TENSORRT_PROVIDER, CUDA_PROVIDER} - available
    if missing:
        raise RuntimeError(f"Không thể kiểm định FP16; thiếu provider: {', '.join(sorted(missing))}")
    if not sample_paths:
        raise ValueError("Cần ít nhất một ảnh kiểm định alpha đại diện.")
    config = BackendConfig()
    trt_options = {
        "trt_fp16_enable": True,
        "trt_max_workspace_size": config.tensorrt_workspace_bytes,
        "trt_engine_cache_enable": False,
    }
    cuda_options = {"gpu_mem_limit": config.gpu_memory_limit_bytes, "arena_extend_strategy": "kSameAsRequested"}
    fp16_session = _create_session(
        model_path,
        [(TENSORRT_PROVIDER, trt_options), (CUDA_PROVIDER, cuda_options)],
        config,
    )
    fp16_masks: list[np.ndarray] = []
    for sample in sample_paths:
        with Image.open(sample) as opened:
            image = opened.convert("RGB")
        try:
            fp16_masks.append(_run_mask(fp16_session, image))
        finally:
            image.close()
    del fp16_session
    gc.collect()

    fp32_session = _create_session(model_path, [(CUDA_PROVIDER, cuda_options)], config)
    absolute_errors: list[np.ndarray] = []
    for sample, fp16_mask in zip(sample_paths, fp16_masks):
        with Image.open(sample) as opened:
            image = opened.convert("RGB")
        try:
            fp32_mask = _run_mask(fp32_session, image)
        finally:
            image.close()
        absolute_errors.append(np.abs(fp16_mask.astype(np.int16) - fp32_mask.astype(np.int16)))
    del fp32_session
    gc.collect()
    alpha_mae = float(np.mean([np.mean(error) for error in absolute_errors]))
    alpha_max_error = int(max(np.max(error) for error in absolute_errors))
    return {
        "approved": alpha_mae <= max_alpha_mae,
        "model_sha256": sha256_file(model_path),
        "alpha_mae": alpha_mae,
        "alpha_max_error": alpha_max_error,
        "max_alpha_mae": max_alpha_mae,
        "sample_count": len(sample_paths),
        "reference": "CUDA FP32",
        "candidate": "TensorRT FP16 with CUDA fallback",
    }


def main() -> int:
    """Validate FP16 using representative images and persist a model-bound manifest."""
    parser = argparse.ArgumentParser(description="Kiểm định chất lượng alpha TensorRT FP16")
    parser.add_argument("samples", nargs="+", type=Path)
    parser.add_argument("--model", default="u2net", choices=("u2net", "u2netp"))
    parser.add_argument("--max-alpha-mae", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    model_path = bundled_model_directory() / f"{arguments.model}.onnx"
    try:
        report = validate_fp16(model_path, arguments.samples, arguments.max_alpha_mae)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Kiểm định FP16 không thể chạy: {exc}", file=sys.stderr)
        return 1
    output = arguments.output or model_path.with_suffix(".fp16-quality.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
