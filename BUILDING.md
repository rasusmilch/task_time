# Building Task Timer for Windows (PyInstaller)

This repository includes a Windows-focused PyInstaller setup for internal distribution.

## Expected environment

- **OS for release builds:** Windows (build Windows executables on Windows)
- **Python:** 3.11+
- **PowerShell:** Windows PowerShell 5.1+ or PowerShell 7+

## Run from source (repo root)

You can launch Task Timer directly from the repository root without an editable install:

```powershell
python .\run_task_timer.py
```

Optional development install:

```powershell
python -m pip install -e .
```

## One-command build (recommended)

From the repository root in PowerShell:

```powershell
./scripts/build.ps1
```

What this script does:

1. Creates `.venv` if it does not exist.
2. Upgrades `pip`.
3. Installs project + `pyinstaller` in the virtual environment.
4. Removes prior `build/` and `dist/` directories.
5. Runs PyInstaller with `task_timer.spec`.

Default output:

- `dist\Task Timer\` (**onedir**, recommended for internal distribution)

Optional onefile output:

```powershell
./scripts/build.ps1 -OneFile
```

Onefile output:

- `dist\Task Timer.exe`

## Manual venv activation (optional)

If you prefer to activate and run commands yourself:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . pyinstaller
python -m PyInstaller --noconfirm --clean task_timer.spec
```

## Internal distribution guidance

- The default supported artifact is the full folder: **`dist\Task Timer\`**.
- Distribute that entire folder internally (zip/copy as a unit).
- End users should run: **`Task Timer.exe`** from inside that folder.
- For future releases, replacing the app folder does **not** delete user data, because data is stored outside the app directory.

## User data location (unchanged)

Task Timer continues to read/write user data in the per-user home directory:

- `%USERPROFILE%\.task_timer_data`

Do **not** attempt to bundle or ship that data directory in the executable package.
