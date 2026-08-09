"""Download the AI models required by Offline Background Remover."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from image_tool.model_catalog import MODEL_CATALOG, ModelArtifact
from image_tool.model_manager import ModelRepository

DEFAULT_MODEL_DIRECTORY = Path(__file__).resolve().parent.parent / "assets" / "models"


def download_model(artifact: ModelArtifact, destination: Path) -> None:
    """Download and atomically install one model after checksum validation."""
    repository = ModelRepository(destination.parent)
    if repository.inspect(artifact).state == "installed":
        print(f"[OK] {artifact.filename} already exists and is valid.")
        return
    print(f"[DOWNLOAD] {artifact.filename}")
    repository.install(artifact)
    print(f"[OK] Installed {destination}")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options for reproducible setup and CI usage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        choices=sorted(MODEL_CATALOG),
        help="Download only the selected model. Repeat for multiple models.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_MODEL_DIRECTORY,
        help="Target model directory.",
    )
    return parser.parse_args()


def main() -> int:
    """Download selected models and return a process exit code."""
    arguments = parse_arguments()
    selected_models = arguments.model or list(MODEL_CATALOG)
    try:
        for model_name in selected_models:
            artifact = MODEL_CATALOG[model_name]
            download_model(artifact, arguments.output / artifact.filename)
    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
