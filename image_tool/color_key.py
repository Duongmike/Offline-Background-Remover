from __future__ import annotations

import time

import numpy as np
from PIL import Image

from .color_key_config import ColorKeyConfig, ColorSample
from .manual_mask import MaskStroke, apply_manual_strokes

try:
    import cv2
except ImportError:  # Tests and source mode remain usable without the optional accelerator.
    cv2 = None  # type: ignore[assignment]


def preview_to_original(point: tuple[int, int], displayed_size: tuple[int, int], image_size: tuple[int, int]) -> tuple[int, int]:
    """Map a click in the actually displayed preview rectangle to original pixels."""
    display_width, display_height = displayed_size
    image_width, image_height = image_size
    if min(display_width, display_height, image_width, image_height) < 1:
        raise ValueError("Kích thước preview hoặc ảnh gốc không hợp lệ.")
    x = min(image_width - 1, max(0, int(point[0] * image_width / display_width)))
    y = min(image_height - 1, max(0, int(point[1] * image_height / display_height)))
    return x, y


def hsv_hue_circular_distance(first: float, second: float) -> float:
    """Return normalized circular hue distance, including the 0°/360° wrap-around."""
    difference = abs((first % 360.0) - (second % 360.0))
    return min(difference, 360.0 - difference) / 180.0


def median_color_sample(image: Image.Image, point: tuple[int, int], kernel_size: int = 5) -> ColorSample:
    """Sample a 5×5/7×7 median RGB patch at original resolution."""
    if kernel_size not in {5, 7}:
        raise ValueError("Vùng lấy mẫu màu phải là 5×5 hoặc 7×7.")
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    x, y = point
    if not (0 <= x < rgb.shape[1] and 0 <= y < rgb.shape[0]):
        raise ValueError("Điểm lấy mẫu nằm ngoài ảnh gốc.")
    radius = kernel_size // 2
    patch = rgb[max(0, y - radius) : min(rgb.shape[0], y + radius + 1), max(0, x - radius) : min(rgb.shape[1], x + radius + 1)]
    median = np.median(patch.reshape(-1, 3), axis=0).astype(np.uint8)
    return ColorSample((int(median[0]), int(median[1]), int(median[2])), (x, y))


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    if cv2 is None:
        # A stable fallback in HSV-like cylindrical space; OpenCV is installed in release dependencies.
        values = rgb.astype(np.float32) / 255.0
        maximum = values.max(axis=2)
        minimum = values.min(axis=2)
        chroma = maximum - minimum
        hue = np.zeros_like(maximum)
        nonzero = chroma > 1e-6
        red = (maximum == values[:, :, 0]) & nonzero
        green = (maximum == values[:, :, 1]) & nonzero
        blue = (maximum == values[:, :, 2]) & nonzero
        hue[red] = ((values[:, :, 1][red] - values[:, :, 2][red]) / chroma[red]) % 6.0
        hue[green] = (values[:, :, 2][green] - values[:, :, 0][green]) / chroma[green] + 2.0
        hue[blue] = (values[:, :, 0][blue] - values[:, :, 1][blue]) / chroma[blue] + 4.0
        return np.dstack((maximum * 100.0, chroma * 100.0 * np.cos(hue), chroma * 100.0 * np.sin(hue)))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def color_probability(rgb: np.ndarray, samples: tuple[ColorSample, ...], config: ColorKeyConfig) -> np.ndarray:
    """Return a continuous 0..1 background probability using multi-sample Lab distance."""
    config.validate()
    if not samples:
        raise ValueError("Hãy chọn ít nhất một mẫu màu nền.")
    for sample in samples:
        sample.validate()
    lab = _rgb_to_lab(rgb)
    sample_rgb = np.asarray([sample.rgb for sample in samples], dtype=np.uint8).reshape((-1, 1, 3))
    sample_lab = _rgb_to_lab(sample_rgb).reshape((-1, 3))
    distance = np.full(lab.shape[:2], np.inf, dtype=np.float32)
    for value in sample_lab:
        delta = lab - value
        distance = np.minimum(distance, np.sqrt(np.sum(delta * delta, axis=2)))
    low = config.color_similarity * 0.55
    high = config.color_similarity * 1.25
    normalized = np.clip((distance - low) / max(1e-6, high - low), 0.0, 1.0)
    return (1.0 - normalized * normalized * (3.0 - 2.0 * normalized)).astype(np.float32)


def _edge_barrier(rgb: np.ndarray, config: ColorKeyConfig) -> np.ndarray:
    if cv2 is None:
        gradient = np.max(np.abs(np.diff(rgb.astype(np.int16), axis=0, prepend=rgb[:1])), axis=2)
        return gradient > (22.0 + (1.0 - config.edge_protection) * 60.0)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    low = int(45 + (1.0 - config.edge_protection) * 50)
    edges = cv2.Canny(gray, low, low * 2, L2gradient=True)
    radius = max(1, int(round(1 + config.edge_protection * 2)))
    return cv2.dilate(edges, np.ones((radius, radius), np.uint8), iterations=1).astype(bool)


def connected_background(probability: np.ndarray, edge_barrier: np.ndarray, samples: tuple[ColorSample, ...], config: ColorKeyConfig) -> np.ndarray:
    """Keep only colour-compatible components touching a border or explicit colour seed."""
    candidate = (probability >= 0.5) & ~edge_barrier
    if not config.connected_to_border_only:
        return candidate
    height, width = candidate.shape
    if cv2 is None:
        # Conservative fallback: only border candidate pixels; never removes isolated foreground.
        result = np.zeros_like(candidate)
        result[0, :] = candidate[0, :]
        result[-1, :] |= candidate[-1, :]
        result[:, 0] |= candidate[:, 0]
        result[:, -1] |= candidate[:, -1]
        return result
    labels_count, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    if labels_count <= 1:
        return candidate
    connected_labels = np.unique(np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1])))
    for sample in samples:
        if sample.position is None:
            continue
        x, y = sample.position
        if 0 <= x < width and 0 <= y < height and candidate[y, x]:
            connected_labels = np.append(connected_labels, labels[y, x])
    return np.isin(labels, connected_labels) & candidate


def refine_alpha(rgb: np.ndarray, probability: np.ndarray, connected: np.ndarray, config: ColorKeyConfig, ai_alpha: np.ndarray | None = None) -> np.ndarray:
    """Create edge-aware soft alpha and protect confident AI foreground in hybrid mode."""
    background = probability * connected.astype(np.float32)
    if ai_alpha is not None:
        ai_foreground = ai_alpha.astype(np.float32) / 255.0
        protected = ai_foreground >= (config.hybrid_ai_foreground_threshold / 255.0)
        background[protected] *= 1.0 - config.hybrid_ai_protect_strength
        # Ambiguous regions preserve soft evidence from both methods.
        background = np.maximum(background, (1.0 - ai_foreground) * connected * 0.35)
    if cv2 is not None and config.edge_softness > 0.0:
        sigma = max(0.1, config.edge_softness)
        background = cv2.GaussianBlur(background, (0, 0), sigmaX=sigma, sigmaY=sigma)
        background *= connected.astype(np.float32)
    return np.clip((1.0 - background) * 255.0, 0, 255).astype(np.uint8)


def suppress_green_spill(rgb: np.ndarray, alpha: np.ndarray, amount: float) -> np.ndarray:
    """Reduce green spill only in semi-transparent pixels, preserving opaque green objects."""
    result = rgb.copy()
    if amount <= 0.0:
        return result
    edge = (alpha > 0) & (alpha < 254)
    green_excess = np.maximum(0.0, result[:, :, 1].astype(np.float32) - np.maximum(result[:, :, 0], result[:, :, 2]))
    reduction = (green_excess * amount * (1.0 - alpha.astype(np.float32) / 255.0)).astype(np.uint8)
    result[:, :, 1][edge] = np.maximum(0, result[:, :, 1][edge].astype(np.int16) - reduction[edge].astype(np.int16)).astype(np.uint8)
    return result


def remove_by_advanced_color_key(image: Image.Image, samples: tuple[ColorSample, ...], config: ColorKeyConfig, manual_strokes: tuple[MaskStroke, ...] = (), ai_alpha: np.ndarray | None = None) -> tuple[Image.Image, dict[str, float]]:
    """Run Lab probability, edge-aware connected propagation, alpha refinement and spill control."""
    started = time.perf_counter()
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    probability_started = time.perf_counter()
    probability = color_probability(rgb, samples, config)
    probability_ms = (time.perf_counter() - probability_started) * 1000.0
    edge_started = time.perf_counter()
    edges = _edge_barrier(rgb, config)
    edge_ms = (time.perf_counter() - edge_started) * 1000.0
    connected_started = time.perf_counter()
    connected = connected_background(probability, edges, samples, config)
    connected_ms = (time.perf_counter() - connected_started) * 1000.0
    alpha = refine_alpha(rgb, probability, connected, config, ai_alpha)
    alpha = apply_manual_strokes(alpha, manual_strokes)
    result = np.dstack((suppress_green_spill(rgb, alpha, config.spill_suppression), alpha))
    return Image.fromarray(result, "RGBA"), {
        "color_probability_ms": probability_ms,
        "edge_detection_ms": edge_ms,
        "connected_propagation_ms": connected_ms,
        "mask_refinement_ms": (time.perf_counter() - started) * 1000.0 - probability_ms - edge_ms - connected_ms,
    }
