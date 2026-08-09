# Repository guidance for coding agents

## Project scope

Offline Background Remover is a privacy-first Windows desktop application built
with Python, Tkinter, Pillow, NumPy, OpenCV, and ONNX Runtime DirectML.

## Required checks

Run before proposing or committing changes:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Engineering constraints

- Keep the Tkinter main thread free of blocking I/O and inference.
- Preserve cancellation, bounded queues, atomic file writes, and backend fallback.
- Do not create more than one active ONNX session without measured justification.
- Close Pillow images and inference sessions deterministically.
- Avoid loading unnecessary full-resolution copies into memory.
- Never commit generated installers, build output, ONNX models, private images,
  credentials, or machine-specific absolute paths.
- Any performance claim must include reproducible benchmark parameters and
  hardware/provider information.

## Localization

- English is the source language for identifiers and developer documentation.
- User-facing UI must support English and Vietnamese once localization lands.
- Keep translations in a central resource instead of branching UI logic by
  language.
- Update both `README.md` and `README.vi.md` for user-facing workflow changes.

## Contributions

- Prefer small, test-backed changes with clear issue context.
- Preserve backwards compatibility unless the change is documented.
- Follow `CONTRIBUTING.md`, `SECURITY.md`, and third-party license notices.
