# Contributing

Thank you for helping improve Offline Background Remover. Documentation,
translations, reproducible bug reports, tests, benchmarks, and focused code
changes are welcome.

## Before starting

1. Search existing issues and pull requests.
2. Open an issue before a large architectural or UI change.
3. Keep each pull request focused on one problem.
4. Do not commit model files, generated binaries, private images, or benchmark
   inputs that you do not have permission to redistribute.

## Development setup

Use Windows with 64-bit Python 3.10 or 3.11:

```powershell
setup.bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To download only the lightweight model used by integration tests:

```powershell
.venv\Scripts\python.exe scripts\download_models.py --model u2netp
```

## Release version

Update the release identity and version only in `image_tool/version.py`. The
application, PyInstaller metadata, benchmark artifacts, Inno Setup installer,
and checksum generation derive their release metadata from that module.

## Pull-request checklist

- Add or update tests for observable behaviour changes.
- Run the full unit-test command locally.
- Keep UI work off the Tkinter main thread when it can block.
- Preserve bounded queues, cancellation, atomic output, and backend fallback.
- Update both `README.md` and `README.vi.md` when user-facing instructions change.
- Add both English and Vietnamese strings when modifying localized UI text.
- Document performance claims with reproducible measurements and hardware data.
- Confirm that no generated binary, AI model, secret, or personal input image is
  included in the diff.

## Commit messages

Use short imperative messages, preferably with a conventional prefix:

```text
feat: add persisted language selection
fix: preserve alpha during exact resize
docs: explain DirectML fallback
test: cover cancellation during encoding
```

By contributing, you agree that your contribution is licensed under the MIT
License used by this repository.
