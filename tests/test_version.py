from __future__ import annotations

import re
import unittest
from pathlib import Path

from image_tool.version import APP_VERSION, WINDOWS_VERSION, _parse_windows_version


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    def test_version_is_release_semver(self) -> None:
        self.assertRegex(APP_VERSION, re.compile(r"^\d+\.\d+\.\d+$"))
        expected = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)
        self.assertEqual(expected, WINDOWS_VERSION)

    def test_windows_version_rejects_invalid_values(self) -> None:
        invalid_versions = ("1.2", "1.2.3.4", "1.2.beta", "1.2.-1", "65536.0.0")
        for version in invalid_versions:
            with self.subTest(version=version), self.assertRaises(ValueError):
                _parse_windows_version(version)

    def test_version_consumers_do_not_duplicate_literal(self) -> None:
        consumer_suffixes = {".bat", ".iss", ".ps1", ".py", ".spec", ".yaml", ".yml"}
        excluded_roots = {".git", ".venv", "build", "dist", "release"}
        canonical_path = PROJECT_ROOT / "image_tool" / "version.py"

        for path in PROJECT_ROOT.rglob("*"):
            if (
                not path.is_file()
                or path.suffix.lower() not in consumer_suffixes
                or path == canonical_path
                or path.relative_to(PROJECT_ROOT).parts[0] in excluded_roots
            ):
                continue
            with self.subTest(path=path.relative_to(PROJECT_ROOT)):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn(APP_VERSION, content)

    def test_python_consumers_import_canonical_version(self) -> None:
        for relative_path in (
            "image_tool/app_modern.py",
            "image_tool/benchmark.py",
            "image_tool/color_key_benchmark.py",
        ):
            with self.subTest(path=relative_path):
                content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("from .version import APP_VERSION", content)

    def test_packaging_reads_canonical_version(self) -> None:
        spec = (PROJECT_ROOT / "KhongBietGiDungNoi.spec").read_text(encoding="utf-8")
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        build_script = (PROJECT_ROOT / "build_installer.bat").read_text(encoding="utf-8")

        self.assertIn("from image_tool.version import APP_VERSION, WINDOWS_VERSION", spec)
        self.assertIn('GetEnv("APP_VERSION")', installer)
        self.assertIn("-m image_tool.version", build_script)
        self.assertIn('set "APP_VERSION="', build_script)
        self.assertIn("SHA256SUMS.txt", build_script)


if __name__ == "__main__":
    unittest.main()
