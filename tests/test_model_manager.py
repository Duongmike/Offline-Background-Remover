from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from image_tool.model_catalog import ModelArtifact
from image_tool.model_manager import ModelRepository


class ModelRepositoryTests(unittest.TestCase):
    @staticmethod
    def artifact(source: Path, payload: bytes) -> ModelArtifact:
        return ModelArtifact(
            model_id="fixture",
            filename="fixture.onnx",
            url=source.as_uri(),
            sha256=hashlib.sha256(payload).hexdigest(),
            expected_size=len(payload),
            display_key="model.u2netp",
            license_name="CC0-1.0",
            license_url="https://example.invalid/license",
        )

    def test_install_is_atomic_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"deterministic fake ONNX payload"
            source = root / "source.onnx"
            source.write_bytes(payload)
            repository = ModelRepository(root / "models")
            artifact = self.artifact(source, payload)
            progress = []
            installed = repository.install(artifact, on_progress=lambda received, total: progress.append((received, total)))
            self.assertEqual(payload, installed.read_bytes())
            self.assertEqual("installed", repository.inspect(artifact).state)
            self.assertTrue(progress)
            self.assertFalse(installed.with_suffix(".onnx.download").exists())

    def test_invalid_existing_model_is_detected_and_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"valid model"
            source = root / "source.onnx"
            source.write_bytes(payload)
            repository = ModelRepository(root / "models")
            artifact = self.artifact(source, payload)
            destination = repository.path_for(artifact)
            destination.parent.mkdir()
            destination.write_bytes(b"corrupt")
            self.assertEqual("invalid", repository.inspect(artifact).state)
            repository.install(artifact)
            self.assertEqual("installed", repository.inspect(artifact).state)


if __name__ == "__main__":
    unittest.main()
