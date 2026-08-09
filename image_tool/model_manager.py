"""Model installation, verification, and repair outside the Tk main thread."""
from __future__ import annotations

import hashlib
import os
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .model_catalog import ModelArtifact


CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60


class ModelOperationCancelled(RuntimeError):
    """Raised when a model download is cancelled safely."""


@dataclass(frozen=True, slots=True)
class ModelStatus:
    """Verified state for one artifact in a model repository."""

    state: str
    size: int
    actual_sha256: str | None = None


def sha256_file(path: Path, cancel_event: threading.Event | None = None) -> str:
    """Return a file digest without retaining model-sized buffers in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            if cancel_event is not None and cancel_event.is_set():
                raise ModelOperationCancelled("Model operation was cancelled.")
            digest.update(chunk)
    return digest.hexdigest()


class ModelRepository:
    """Own checksummed model files in one explicit directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._operation_lock = threading.Lock()

    def path_for(self, artifact: ModelArtifact) -> Path:
        """Return the local destination for one catalog entry."""
        return self.directory / artifact.filename

    def inspect(self, artifact: ModelArtifact, cancel_event: threading.Event | None = None) -> ModelStatus:
        """Hash one installed model and report missing, valid, or invalid state."""
        path = self.path_for(artifact)
        if not path.is_file():
            return ModelStatus("missing", 0)
        size = path.stat().st_size
        digest = sha256_file(path, cancel_event)
        state = "installed" if digest == artifact.sha256 else "invalid"
        return ModelStatus(state, size, digest)

    def install(
        self,
        artifact: ModelArtifact,
        cancel_event: threading.Event | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        """Download and atomically install one artifact after SHA256 verification."""
        cancel = cancel_event or threading.Event()
        with self._operation_lock:
            current = self.inspect(artifact, cancel)
            destination = self.path_for(artifact)
            if current.state == "installed":
                return destination
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(
                f".{destination.name}.{os.getpid()}.{threading.get_ident()}.download"
            )
            request = urllib.request.Request(
                artifact.url,
                headers={"User-Agent": "Offline-Background-Remover/1.5 model-manager"},
            )
            received = 0
            try:
                with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, temporary.open("wb") as output:
                    length_header = response.headers.get("Content-Length")
                    total = int(length_header) if length_header and length_header.isdigit() else None
                    while True:
                        if cancel.is_set():
                            raise ModelOperationCancelled("Model download was cancelled.")
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        received += len(chunk)
                        if on_progress is not None:
                            on_progress(received, total)
                    output.flush()
                    os.fsync(output.fileno())
                if sha256_file(temporary, cancel) != artifact.sha256:
                    raise ValueError(f"SHA256 mismatch for {artifact.filename}")
                os.replace(temporary, destination)
                return destination
            finally:
                temporary.unlink(missing_ok=True)
