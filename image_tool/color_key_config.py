from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class ColorSample:
    """A robust background colour sample, optionally retaining its image-space seed."""

    rgb: tuple[int, int, int]
    position: tuple[int, int] | None = None

    def validate(self) -> None:
        """Raise ValueError when RGB or the optional seed position is invalid."""
        if len(self.rgb) != 3 or any(channel < 0 or channel > 255 for channel in self.rgb):
            raise ValueError("Mẫu màu nền phải chứa ba kênh RGB trong khoảng 0–255.")
        if self.position is not None and (self.position[0] < 0 or self.position[1] < 0):
            raise ValueError("Tọa độ mẫu màu nền không hợp lệ.")


@dataclass(frozen=True, slots=True)
class ColorKeyConfig:
    """Tunable, serializable parameters for the advanced colour-key pipeline."""

    color_similarity: float = 34.0
    edge_protection: float = 0.55
    edge_softness: float = 1.5
    spill_suppression: float = 0.35
    connected_to_border_only: bool = True
    hybrid_ai_foreground_threshold: int = 210
    hybrid_ai_protect_strength: float = 0.85
    coarse_max_side: int = 1600

    def validate(self) -> None:
        """Raise ValueError when a configuration could produce undefined processing."""
        if not 1.0 <= self.color_similarity <= 120.0:
            raise ValueError("Độ tương đồng màu phải nằm trong khoảng 1–120.")
        if not 0.0 <= self.edge_protection <= 1.0:
            raise ValueError("Bảo vệ cạnh phải nằm trong khoảng 0–1.")
        if not 0.0 <= self.edge_softness <= 12.0:
            raise ValueError("Độ mềm viền phải nằm trong khoảng 0–12.")
        if not 0.0 <= self.spill_suppression <= 1.0:
            raise ValueError("Khử ám màu phải nằm trong khoảng 0–1.")
        if not 0 <= self.hybrid_ai_foreground_threshold <= 255:
            raise ValueError("Ngưỡng bảo vệ foreground AI phải nằm trong khoảng 0–255.")
        if not 0.0 <= self.hybrid_ai_protect_strength <= 1.0 or self.coarse_max_side < 256:
            raise ValueError("Cấu hình hybrid không hợp lệ.")


RemovalMode = Literal["ai", "color_key", "hybrid"]
