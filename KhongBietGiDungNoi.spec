# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata
from pathlib import Path


block_cipher = None

datas = [
    ("assets/app_icon_64.png", "assets"),
    ("assets/app_icon_256.png", "assets"),
    ("assets/app_icon.ico", "assets"),
    ("assets/models/u2net.onnx", "assets/models"),
    ("assets/models/u2netp.onnx", "assets/models"),
]
binaries = []
hiddenimports = [
    "onnxruntime.capi._pybind_state",
    "cv2",
]

for distribution in ("onnxruntime-directml", "numpy", "Pillow", "tkinterdnd2", "opencv-python-headless"):
    datas += copy_metadata(distribution)

for model_name in ("u2net", "u2netp"):
    manifest = Path(f"assets/models/{model_name}.fp16-quality.json")
    if manifest.is_file():
        datas.append((str(manifest), "assets/models"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "jupyter", "notebook"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KhongBietGiDungNoi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_icon.ico",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KhongBietGiDungNoi",
)
