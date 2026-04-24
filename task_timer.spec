# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Task Timer (Windows onedir default)."""

from pathlib import Path

repo_root = Path(__file__).resolve().parent

# Keep analysis focused on project sources under src/.
a = Analysis(
    [str(repo_root / "run_task_timer.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["__pycache__"],
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
    name="Task Timer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="Task Timer",
)
