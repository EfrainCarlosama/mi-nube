# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

root = Path(SPECPATH)
datas = [
    (str(root / "src" / "mi_nube" / "assets" / "update_public_key.pem"), "mi_nube/assets"),
    (str(root / "build" / "runtime_config.json"), "mi_nube/assets"),
]

a = Analysis(
    [str(root / "src" / "mi_nube" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MiNube",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.getenv("MI_NUBE_BUILD_CONSOLE") == "1",
    icon=str(root / "assets" / "mi_nube.ico"),
    version=str(root / "packaging" / "windows_version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MiNube",
)
