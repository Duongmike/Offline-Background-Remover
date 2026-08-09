"""Validate release tags and generated installer checksums."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

from image_tool.version import APP_VERSION


RELEASE_TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
INSTALLER_PREFIX = "KhongBietGiDungNoi_Setup_"


def _installer_path(release_directory: Path) -> Path:
    return release_directory / f"{INSTALLER_PREFIX}{APP_VERSION}.exe"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release_tag(tag: str) -> None:
    """Raise ValueError unless *tag* is the canonical release tag."""
    if not RELEASE_TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"Release tag must use vMAJOR.MINOR.PATCH: {tag!r}")
    expected = f"v{APP_VERSION}"
    if tag != expected:
        raise ValueError(f"Release tag {tag!r} does not match APP_VERSION {APP_VERSION!r}")


def write_release_checksum(release_directory: Path) -> tuple[Path, Path]:
    """Atomically write the canonical installer's portable SHA256SUMS entry."""
    installer = _installer_path(release_directory)
    checksum_file = release_directory / "SHA256SUMS.txt"
    if not installer.is_file() or installer.stat().st_size == 0:
        raise ValueError(f"Missing or empty installer: {installer}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="ascii",
            newline="\n",
            dir=release_directory,
            prefix=".SHA256SUMS.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(f"{_sha256_file(installer).upper()}  {installer.name}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, checksum_file)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return installer, checksum_file


def verify_release_artifacts(release_directory: Path) -> tuple[Path, Path]:
    """Verify the canonical installer and SHA256SUMS file in a release directory."""
    installer = _installer_path(release_directory)
    checksum_file = release_directory / "SHA256SUMS.txt"
    if not installer.is_file() or installer.stat().st_size == 0:
        raise ValueError(f"Missing or empty installer: {installer}")
    if not checksum_file.is_file():
        raise ValueError(f"Missing checksum file: {checksum_file}")

    lines = [line.strip() for line in checksum_file.read_text(encoding="ascii").splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("SHA256SUMS.txt must contain exactly one non-empty entry")
    parts = lines[0].split(maxsplit=1)
    if len(parts) != 2 or parts[1].lstrip("*") != installer.name:
        raise ValueError(f"Checksum entry must target {installer.name!r}")
    expected_digest = parts[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise ValueError("Checksum entry does not contain a valid SHA256 digest")

    if _sha256_file(installer) != expected_digest:
        raise ValueError(f"SHA256 mismatch for {installer.name}")
    return installer, checksum_file


def main(argv: list[str] | None = None) -> int:
    """Run requested release validations and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Validate a Git tag against APP_VERSION")
    parser.add_argument("--write-checksum", type=Path, help="Atomically generate SHA256SUMS.txt for an installer")
    parser.add_argument("--release-dir", type=Path, help="Verify installer and SHA256SUMS.txt")
    arguments = parser.parse_args(argv)
    if arguments.tag is None and arguments.write_checksum is None and arguments.release_dir is None:
        parser.error("at least one of --tag, --write-checksum, or --release-dir is required")

    try:
        if arguments.tag is not None:
            validate_release_tag(arguments.tag)
            print(f"Validated release tag: {arguments.tag}")
        if arguments.write_checksum is not None:
            installer, checksum_file = write_release_checksum(arguments.write_checksum)
            print(f"Wrote release checksum: {checksum_file.name} for {installer.name}")
        if arguments.release_dir is not None:
            installer, checksum_file = verify_release_artifacts(arguments.release_dir)
            print(f"Verified release artifacts: {installer.name}, {checksum_file.name}")
    except (OSError, ValueError) as exc:
        print(f"Release validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
