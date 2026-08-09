from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from image_tool.version import APP_VERSION
from scripts.verify_release import validate_release_tag, verify_release_artifacts


class ReleaseValidationTests(unittest.TestCase):
    def test_release_tag_must_match_canonical_version(self) -> None:
        validate_release_tag(f"v{APP_VERSION}")
        for invalid_tag in (APP_VERSION, "latest", "v1.2", "v999.0.0"):
            with self.subTest(tag=invalid_tag), self.assertRaises(ValueError):
                validate_release_tag(invalid_tag)

    def test_release_artifacts_accept_matching_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            release_directory = Path(temporary_directory)
            installer = release_directory / f"KhongBietGiDungNoi_Setup_{APP_VERSION}.exe"
            installer.write_bytes(b"synthetic installer fixture")
            digest = hashlib.sha256(installer.read_bytes()).hexdigest().upper()
            checksum_file = release_directory / "SHA256SUMS.txt"
            checksum_file.write_text(f"{digest}  {installer.name}\n", encoding="ascii")

            actual_installer, actual_checksum = verify_release_artifacts(release_directory)

            self.assertEqual(installer, actual_installer)
            self.assertEqual(checksum_file, actual_checksum)

    def test_release_artifacts_reject_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            release_directory = Path(temporary_directory)
            installer = release_directory / f"KhongBietGiDungNoi_Setup_{APP_VERSION}.exe"
            installer.write_bytes(b"synthetic installer fixture")
            (release_directory / "SHA256SUMS.txt").write_text(
                f"{'0' * 64}  {installer.name}\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                verify_release_artifacts(release_directory)


if __name__ == "__main__":
    unittest.main()
