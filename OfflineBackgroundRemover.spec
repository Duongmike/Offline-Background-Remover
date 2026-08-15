# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)
from pathlib import Path

from image_tool.version import (
    APP_EXECUTABLE_BASENAME,
    APP_EXECUTABLE_FILENAME,
    APP_NAME,
    APP_VERSION,
    WINDOWS_VERSION,
)


block_cipher = None

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=WINDOWS_VERSION,
        prodvers=WINDOWS_VERSION,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                "040904B0",
                [
                    StringStruct("CompanyName", "Không biết gì đừng nói"),
                    StringStruct("FileDescription", f"{APP_NAME} - Xóa nền AI và resize ảnh"),
                    StringStruct("FileVersion", APP_VERSION),
                    StringStruct("InternalName", APP_EXECUTABLE_BASENAME),
                    StringStruct("LegalCopyright", "Copyright 2026"),
                    StringStruct("OriginalFilename", APP_EXECUTABLE_FILENAME),
                    StringStruct("ProductName", APP_NAME),
                    StringStruct("ProductVersion", APP_VERSION),
                ],
            )
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

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
    name=APP_EXECUTABLE_BASENAME,
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
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_EXECUTABLE_BASENAME,
)
