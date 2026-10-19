# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Chronicle (Windows onedir default)."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

try:
    repo_root = Path(SPECPATH).resolve()
except NameError:
    repo_root = Path.cwd().resolve()

# Keep analysis focused on project sources under src/.
a = Analysis(
    [str(repo_root / "run_chronicle.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=collect_data_files("tzdata"),
    hiddenimports=["chronicle.bootstrap"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["__pycache__", "task_timer"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Windowed desktop app: no console window.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Chronicle",
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
    icon=None,  # Set to a .ico path when an app icon is available.
)

# Keep default artifact as onedir for internal distribution.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Chronicle",
)
