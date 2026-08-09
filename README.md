# Xóa Nền AI Offline

[![CI](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml/badge.svg)](https://github.com/Duongmike/Offline-Background-Remover/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.11](https://img.shields.io/badge/Python-3.10%E2%80%933.11-blue.svg)](https://www.python.org/)

**English** · [Tiếng Việt](README.vi.md)

Xóa Nền AI Offline is a Windows desktop application for AI background removal,
advanced colour-keying, batch processing, and image resizing. Images stay on
the local machine; the application does not upload them to a remote service.

> **Project status:** actively developed. The current application UI is in
> Vietnamese; English localization is on the roadmap. Public APIs and UI details
> may change before the first stable release.

![Offline Background Remover user interface](ui_preview.png)

## Highlights

- Process one image or a complete directory while preserving subdirectories.
- Remove backgrounds with U²-Net, advanced colour-keying, or a hybrid strategy.
- Use multiple background samples, a mask overlay, and keep/remove brushes with
  20-step undo and redo.
- Keep the default AI layout compact; colour controls expand only for advanced
  colour-key and hybrid modes, with a visible swatch beside each sampled hex value.
- Resize by percentage, exact bounding box, or longest edge.
- Keep the Tkinter UI responsive with background warm-up, cancellation, bounded
  queues, and atomic file replacement.
- Prefer TensorRT/CUDA, CUDA, DirectML, then CPU, with explicit fallback events.
- Run fully offline after the verified models have been installed.

## Architecture

```text
Desktop UI
    │
    ▼
BatchImageService
    │
    ├── AI removal ───────────┐
    ├── Advanced colour-key ──┼──► bounded pipeline ─► atomic PNG output
    └── Hybrid removal ───────┘
             │
             ▼
InferenceBackendManager
    └── TensorRT/CUDA → CUDA → DirectML → CPU
```

The pipeline keeps at most four full-resolution images in flight and owns only
one ONNX session at a time. GPU inference is serialized to avoid multiplying
model or VRAM usage.

## Run from source

Requirements:

- Windows 10 or newer, 64-bit
- Python 3.10 or 3.11, 64-bit
- Internet access during the first setup only, for dependencies and AI models

```powershell
git clone https://github.com/Duongmike/Offline-Background-Remover.git
cd Offline-Background-Remover
setup.bat
run.bat
```

`setup.bat` creates `.venv`, installs the constrained runtime dependencies, downloads
the U²-Net models, and verifies their SHA256 digests. Subsequent processing is
offline.

## Test

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The test suite covers resizing, Unicode paths, atomic output, cancellation,
bounded queues, inference-provider fallback, PNG alpha preservation, advanced
colour-keying, manual mask commands, and legacy-backend equivalence.

## Build the Windows installer

Install [Inno Setup 6](https://jrsoftware.org/isinfo.php), then run:

```powershell
build.bat
build_installer.bat
```

Generated applications and installers stay outside Git history. Published
binaries belong in [GitHub Releases](https://github.com/Duongmike/Offline-Background-Remover/releases)
with their SHA256 checksum.

Maintainers can run the Release workflow manually as a build-only dry run. A
tag matching `vMAJOR.MINOR.PATCH` publishes only after the tag matches the
canonical application version, all tests pass, and the packaged self-test, UI
smoke test, installer build, and checksum verification succeed.

## Benchmark

The checked-in benchmark report documents the machine, providers, cold/warm
runs, stage timings, and PNG trade-offs. The project does not claim quality
percentages without a labelled ground-truth dataset.

```powershell
.venv\Scripts\python.exe -m image_tool.benchmark --model u2net --repeats 3 --output benchmarks\after_local.json
```

See [the benchmark report](benchmarks/BENCHMARK_REPORT_1.4.0.md).

## Roadmap

- [ ] English and Vietnamese localization with persisted language selection
- [x] Reproducible tagged release workflow
- [ ] Larger labelled image-quality regression dataset
- [ ] More GPU and hardware benchmark coverage
- [ ] Contributor-friendly plugin points for removal backends

Roadmap items are tracked as GitHub issues so contributors can discuss scope
before implementation.

## Contributing and security

Bug reports, documentation improvements, tests, translations, benchmarks, and
focused pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before
starting a change. Please report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).

## License and model attribution

The application source is released under the [MIT License](LICENSE). Models and
third-party packages retain their respective licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
