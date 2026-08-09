"""Download the AI models required by Offline Background Remover."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


CHUNK_SIZE = 1024 * 1024
DEFAULT_MODEL_DIRECTORY = Path(__file__).resolve().parent.parent / "assets" / "models"


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """Describe one immutable model artifact and its expected digest."""

    name: str
    url: str
    sha256: str


MODELS = {
    "u2net": ModelArtifact(
        name="u2net.onnx",
        url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
        sha256="8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491",
    ),
    "u2netp": ModelArtifact(
        name="u2netp.onnx",
        url="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        sha256="309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8",
    ),
}


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download_model(artifact: ModelArtifact, destination: Path) -> None:
    """Download and atomically install one model after checksum validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256_file(destination) == artifact.sha256:
        print(f"[OK] {artifact.name} already exists and is valid.")
        return

    temporary_path = destination.with_suffix(destination.suffix + ".download")
    try:
        print(f"[DOWNLOAD] {artifact.name}")
        urllib.request.urlretrieve(artifact.url, temporary_path)
        actual_digest = sha256_file(temporary_path)
        if actual_digest != artifact.sha256:
            raise ValueError(
                f"SHA256 mismatch for {artifact.name}: expected {artifact.sha256}, "
                f"received {actual_digest}"
            )
        os.replace(temporary_path, destination)
        print(f"[OK] Installed {destination}")
    finally:
        temporary_path.unlink(missing_ok=True)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options for reproducible setup and CI usage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        choices=sorted(MODELS),
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
    selected_models = arguments.model or list(MODELS)
    try:
        for model_name in selected_models:
            artifact = MODELS[model_name]
            download_model(artifact, arguments.output / artifact.name)
    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
