from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image

from .color_key import remove_by_advanced_color_key
from .color_key_config import ColorKeyConfig, ColorSample, RemovalMode
from .image_ops import postprocess_u2net
from .manual_mask import MaskStroke, apply_manual_strokes


@dataclass(frozen=True, slots=True)
class RemovalContext:
    """UI-independent data needed by all background-removal strategies."""

    samples: tuple[ColorSample, ...] = ()
    color_config: ColorKeyConfig = ColorKeyConfig()
    manual_strokes: tuple[MaskStroke, ...] = ()


class IBackgroundRemovalStrategy(Protocol):
    """Contract separating UI, AI inference and colour-key implementations."""

    requires_ai: bool

    def remove(self, image: Image.Image, raw_ai_output: np.ndarray | None, context: RemovalContext) -> tuple[Image.Image, float]:
        """Return an RGBA result and post-processing duration in milliseconds."""


class AIBackgroundRemovalStrategy:
    """Unchanged U²-Net background-removal backend from the 1.4.0 pipeline."""

    requires_ai = True

    def remove(self, image: Image.Image, raw_ai_output: np.ndarray | None, context: RemovalContext) -> tuple[Image.Image, float]:
        """Apply the existing U²-Net alpha, then optional manual corrections."""
        if raw_ai_output is None:
            raise ValueError("AI mode cần kết quả inference U²-Net.")
        result, elapsed = postprocess_u2net(image, raw_ai_output)
        if context.manual_strokes:
            values = np.asarray(result, dtype=np.uint8).copy()
            values[:, :, 3] = apply_manual_strokes(values[:, :, 3], context.manual_strokes)
            result.close()
            result = Image.fromarray(values, "RGBA")
        return result, elapsed


class AdvancedColorKeyStrategy:
    """Conservative connected colour-key implementation for difficult gradients and greens."""

    requires_ai = False

    def remove(self, image: Image.Image, raw_ai_output: np.ndarray | None, context: RemovalContext) -> tuple[Image.Image, float]:
        """Remove only colour-compatible background connected to border/explicit seeds."""
        result, stages = remove_by_advanced_color_key(image, context.samples, context.color_config, context.manual_strokes)
        return result, sum(stages.values())


class HybridBackgroundRemovalStrategy:
    """AI foreground prior plus connected colour background evidence."""

    requires_ai = True

    def remove(self, image: Image.Image, raw_ai_output: np.ndarray | None, context: RemovalContext) -> tuple[Image.Image, float]:
        """Protect confident AI foreground while removing strongly connected background colour."""
        if raw_ai_output is None:
            raise ValueError("Hybrid mode cần kết quả inference U²-Net.")
        ai_image, ai_time = postprocess_u2net(image, raw_ai_output)
        try:
            ai_alpha = np.asarray(ai_image.getchannel("A"), dtype=np.uint8).copy()
        finally:
            ai_image.close()
        result, stages = remove_by_advanced_color_key(image, context.samples, context.color_config, context.manual_strokes, ai_alpha)
        return result, ai_time + sum(stages.values())


def create_removal_strategy(mode: RemovalMode) -> IBackgroundRemovalStrategy:
    """Create the requested removal strategy without exposing implementation to UI."""
    if mode == "color_key":
        return AdvancedColorKeyStrategy()
    if mode == "hybrid":
        return HybridBackgroundRemovalStrategy()
    return AIBackgroundRemovalStrategy()
