# AI models

Model binaries are intentionally excluded from Git history because the full
U²-Net artifact is larger than GitHub's regular file limit.

Download both verified models from the repository root:

```powershell
.venv\Scripts\python.exe scripts\download_models.py
```

Download only the lightweight model used by CI:

```powershell
python scripts/download_models.py --model u2netp
```

The downloader uses the upstream assets published by
[`danielgatis/rembg`](https://github.com/danielgatis/rembg) and rejects files
whose SHA256 digest does not match the pinned value. See
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) for attribution.
