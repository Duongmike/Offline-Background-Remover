"""Atomic JSON settings persistence with legacy-location migration."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


def default_settings_path() -> Path:
    """Return the per-user application settings path."""
    base = Path(os.getenv("APPDATA", Path.home()))
    return base / "KhongBietGiDungNoi" / "settings.json"


class JsonSettingsRepository:
    """Load and atomically save non-sensitive application settings."""

    def __init__(self, path: Path | None = None, legacy_path: Path | None = None) -> None:
        self.path = path or default_settings_path()
        base = Path(os.getenv("APPDATA", Path.home()))
        self.legacy_path = legacy_path or base / "TachNenPro" / "settings.json"

    def load(self) -> dict[str, Any]:
        """Return settings from the current or legacy path, or an empty mapping."""
        for candidate in (self.path, self.legacy_path):
            try:
                value = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, ValueError, TypeError):
                continue
        return {}

    def save(self, values: Mapping[str, object]) -> None:
        """Write settings through a same-directory temporary file and atomic replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(dict(values), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
