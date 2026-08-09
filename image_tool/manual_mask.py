from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw


@dataclass(frozen=True, slots=True)
class MaskStroke:
    """One compact image-space manual correction stroke; no RGBA snapshot is stored."""

    points: tuple[tuple[int, int], ...]
    radius: int
    mode: str

    def validate(self) -> None:
        """Validate a stroke before it is admitted to the bounded history."""
        if self.mode not in {"keep", "remove"} or self.radius < 1 or not self.points:
            raise ValueError("Nét cọ chỉnh mask không hợp lệ.")


@dataclass(slots=True)
class ManualMaskEditor:
    """Bounded undo/redo command history for original-resolution manual mask edits."""

    max_history: int = 20
    _strokes: list[MaskStroke] = field(default_factory=list)
    _redo: list[MaskStroke] = field(default_factory=list)

    @property
    def strokes(self) -> tuple[MaskStroke, ...]:
        """Return immutable strokes suitable for passing to worker threads."""
        return tuple(self._strokes)

    def add_stroke(self, stroke: MaskStroke) -> None:
        """Append one stroke and discard redo commands without allocating full masks."""
        stroke.validate()
        self._strokes.append(stroke)
        if len(self._strokes) > self.max_history:
            self._strokes.pop(0)
        self._redo.clear()

    def undo(self) -> bool:
        """Undo one stroke, returning False when there is no command to undo."""
        if not self._strokes:
            return False
        self._redo.append(self._strokes.pop())
        return True

    def redo(self) -> bool:
        """Redo one stroke, returning False when there is no command to redo."""
        if not self._redo:
            return False
        self._strokes.append(self._redo.pop())
        return True


def apply_manual_strokes(alpha: np.ndarray, strokes: tuple[MaskStroke, ...]) -> np.ndarray:
    """Apply keep/remove strokes to alpha at original image resolution."""
    if alpha.ndim != 2 or alpha.dtype != np.uint8:
        raise ValueError("Manual mask yêu cầu alpha uint8 hai chiều.")
    if not strokes:
        return alpha
    result = Image.fromarray(alpha.copy(), "L")
    try:
        draw = ImageDraw.Draw(result)
        for stroke in strokes:
            stroke.validate()
            fill = 255 if stroke.mode == "keep" else 0
            points = stroke.points
            if len(points) == 1:
                x, y = points[0]
                draw.ellipse((x - stroke.radius, y - stroke.radius, x + stroke.radius, y + stroke.radius), fill=fill)
            else:
                draw.line(points, fill=fill, width=stroke.radius * 2, joint="curve")
                for x, y in (points[0], points[-1]):
                    draw.ellipse((x - stroke.radius, y - stroke.radius, x + stroke.radius, y + stroke.radius), fill=fill)
        return np.asarray(result, dtype=np.uint8).copy()
    finally:
        result.close()
