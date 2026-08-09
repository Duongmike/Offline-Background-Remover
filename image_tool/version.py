"""Application identity shared by the UI, packaging, and release tooling."""
from __future__ import annotations


APP_NAME = "Xóa Nền AI Offline"
APP_VERSION = "1.5.0"


def _parse_windows_version(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"APP_VERSION must use MAJOR.MINOR.PATCH: {version!r}")
    components = tuple(int(part) for part in parts)
    if any(component > 65_535 for component in components):
        raise ValueError(f"APP_VERSION components must fit Windows version fields: {version!r}")
    return components[0], components[1], components[2], 0


WINDOWS_VERSION = _parse_windows_version(APP_VERSION)


def main() -> int:
    """Print the canonical version for build and release scripts."""
    print(APP_VERSION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
