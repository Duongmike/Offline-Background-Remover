from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .models import PngCompressionMode, ResizeOptions


PNG_COMPRESSION_LEVELS: dict[PngCompressionMode, int] = {
    PngCompressionMode.FAST: 1,
    PngCompressionMode.BALANCED: 6,
    PngCompressionMode.SMALL: 9,
}


def decode_image(source: Path) -> tuple[Image.Image, float]:
    """Decode one Unicode-safe image path and return the image plus elapsed ms."""
    started = time.perf_counter()
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
    return image, (time.perf_counter() - started) * 1000.0


def preprocess_u2net(image: Image.Image) -> tuple[np.ndarray, float]:
    """Create the normalized NCHW float32 tensor expected by U²-Net."""
    started = time.perf_counter()
    rgb = image.convert("RGB")
    try:
        resized = rgb.resize((320, 320), Image.Resampling.LANCZOS)
    finally:
        rgb.close()
    try:
        values = np.asarray(resized, dtype=np.float32).copy()
    finally:
        resized.close()
    maximum = max(float(np.max(values)), 1e-6)
    values /= maximum
    values -= np.asarray((0.485, 0.456, 0.406), dtype=np.float32)
    values /= np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
    tensor = np.ascontiguousarray(values.transpose((2, 0, 1))[None, ...], dtype=np.float32)
    return tensor, (time.perf_counter() - started) * 1000.0


def postprocess_u2net(image: Image.Image, raw_output: np.ndarray) -> tuple[Image.Image, float]:
    """Convert raw U²-Net output into an RGBA cutout equivalent to rembg."""
    started = time.perf_counter()
    if raw_output.ndim < 3:
        raise RuntimeError(f"Output AI sai kích thước: {raw_output.shape}")
    prediction = raw_output[:, 0, :, :] if raw_output.ndim == 4 else raw_output
    prediction = np.squeeze(prediction).astype(np.float32, copy=False)
    minimum = float(np.nanmin(prediction))
    maximum = float(np.nanmax(prediction))
    span = maximum - minimum
    if not np.isfinite(span) or span <= 1e-8:
        normalized = np.zeros_like(prediction, dtype=np.float32)
    else:
        normalized = np.clip((prediction - minimum) / span, 0.0, 1.0)
    mask = Image.fromarray((normalized * 255.0).astype(np.uint8), mode="L")
    try:
        resized_mask = mask.resize(image.size, Image.Resampling.LANCZOS)
    finally:
        mask.close()
    try:
        empty = Image.new("RGBA", image.size, 0)
        try:
            cutout = Image.composite(image, empty, resized_mask)
        finally:
            empty.close()
    finally:
        resized_mask.close()
    if cutout.mode == "RGBA":
        result = cutout
    else:
        result = cutout.convert("RGBA")
        cutout.close()
    return result, (time.perf_counter() - started) * 1000.0


def calculate_resize_size(original: tuple[int, int], options: ResizeOptions) -> tuple[int, int]:
    """Calculate output dimensions without allocating image data."""
    from .models import ResizeMode

    width, height = original
    if options.mode == ResizeMode.NONE:
        return original
    if options.mode == ResizeMode.PERCENT:
        scale = options.percent / 100.0
        return max(1, round(width * scale)), max(1, round(height * scale))
    if options.mode == ResizeMode.MAX_SIDE:
        if max(width, height) <= options.max_side:
            return original
        scale = options.max_side / max(width, height)
        return max(1, round(width * scale)), max(1, round(height * scale))
    if not options.keep_aspect_ratio:
        return options.width, options.height
    scale = min(options.width / width, options.height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def resize_image(image: Image.Image, options: ResizeOptions) -> Image.Image:
    """Resize an image using high-quality Lanczos resampling."""
    target_size = calculate_resize_size(image.size, options)
    if target_size == image.size:
        return image
    resized = image.resize(target_size, Image.Resampling.LANCZOS)
    image.close()
    return resized


def atomic_save_image(image: Image.Image, destination: Path, png_mode: PngCompressionMode) -> float:
    """Encode to a temporary file and atomically replace the destination."""
    started = time.perf_counter()
    destination.parent.mkdir(parents=True, exist_ok=True)
    suffix = destination.suffix.lower()
    save_options: dict[str, object] = {}
    output = image
    if suffix in {".jpg", ".jpeg"}:
        if image.mode not in {"RGB", "L"}:
            output = image.convert("RGB")
        save_options.update(quality=95, optimize=False)
    elif suffix == ".png":
        save_options["compress_level"] = PNG_COMPRESSION_LEVELS[png_mode]
    elif suffix == ".webp":
        save_options.update(quality=95, method=2 if png_mode == PngCompressionMode.FAST else 4)

    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.{thread_id()}.processing{destination.suffix}")
    try:
        output.save(temporary, **save_options)
        os.replace(temporary, destination)
    finally:
        if output is not image:
            output.close()
        if temporary.exists():
            temporary.unlink()
    return (time.perf_counter() - started) * 1000.0


def thread_id() -> int:
    """Return a compact thread identifier for collision-free temporary names."""
    import threading

    return threading.get_ident()
