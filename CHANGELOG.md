# Changelog

All notable changes to this project will be documented in this file. Versions
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.0] - 2026-08-08

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

[Unreleased]: https://github.com/Duongmike/Offline-Background-Remover/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/Duongmike/Offline-Background-Remover/releases/tag/v1.5.0
