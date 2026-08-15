# Changelog

All notable changes to this project will be documented in this file. Versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.3] - 2026-08-15

### Changed

- Rename the packaged application to `OfflineBackgroundRemover.exe` and the
  installer to `OfflineBackgroundRemover_Setup_<version>.exe`.
- Keep upgrade compatibility by removing the legacy executable during install.

## [1.5.2] - 2026-08-09

### Fixed

- Localize the application name in the header, window title, and completion
  dialog when switching between English and Vietnamese.

## [1.5.1] - 2026-08-09

### Fixed

- Generate installer SHA256 checksums with the packaged Python runtime instead
  of relying on a Windows PowerShell cmdlet unavailable on `windows-2025` runners.
- Write `SHA256SUMS.txt` atomically and fail the build when checksum generation
  cannot complete.

## [1.5.0] - 2026-08-09

### Added

- Advanced colour-key removal with multiple samples and connected-background
  detection.
- Hybrid U²-Net and colour-key removal.
- Manual keep/remove mask brushes with compact undo and redo commands.
- Benchmark coverage for colour-key and hybrid processing.
- Reproducible tagged GitHub release automation with installer and checksum
  verification before publishing.
- Complete English and Vietnamese UI localization with persisted language
  selection and legacy-settings migration.
- Non-blocking Model Manager with SHA256 verification and atomic repair downloads.
- Licensed synthetic alpha-regression fixtures, MAE/SAD/IoU/F1 evaluator, and CI
  quality gate.

### Changed

- Improved bounded processing, backend fallback reporting, and offline packaging.
- Centralized application identity, benchmark, executable, installer, and
  checksum versioning in one canonical module.
- Kept AI mode compact by showing colour sampling and mask controls only for
  colour-key and hybrid removal.

[Unreleased]: https://github.com/Duongmike/Offline-Background-Remover/compare/v1.5.3...HEAD
[1.5.3]: https://github.com/Duongmike/Offline-Background-Remover/compare/v1.5.2...v1.5.3
[1.5.2]: https://github.com/Duongmike/Offline-Background-Remover/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/Duongmike/Offline-Background-Remover/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/Duongmike/Offline-Background-Remover/releases/tag/v1.5.0
