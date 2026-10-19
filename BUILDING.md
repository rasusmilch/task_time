# Building Chronicle for Windows (PyInstaller)

## Current source versus selected rewrite

The commands below describe the inspected **legacy Tkinter/JSONL** scripts and
launcher. They do not build an implemented SQLite rewrite or establish Windows
qualification. [ARCHITECTURE.md](docs/ARCHITECTURE.md) owns the selected replacement;
[ROADMAP.md](docs/ROADMAP.md) starts early native Windows onedir smoke in Stage 1
and requires complete core POL-R before pilot. Preserve one replacement runtime,
not parallel legacy packaging or a Qt/PySide6 frontend.

The future package must verify its actual SQLite runtime, WAL/FULL profile,
foreign keys/constraints and supported backup/restore, and bundle offline IANA
timezone data. Existing metadata declares Python 3.11+, tkcalendar and tzlocal;
the current spec includes tkcalendar/tzlocal and does not establish tzdata bundling.
Exact rewrite runtime/toolkit pins and packaging changes require validation in
later authorized implementation, not assumptions in this document. No scripts,
dependencies or spec are changed here. Native Tk/SQLite/filesystem/package tests
remain separate from Linux source tests and syntax checks.

The replacement starts with fresh data. Exact selected release paths/cutover and
cleanup are Open; no old-data discovery/import or startup deletion is authorized.
Future upgrades must protect new-runtime data. This documentation neither moves
nor removes the existing data directory.

## Expected environment

- **OS for release builds:** Windows (build Windows executables on Windows)
- **Python:** 3.11+
- **PowerShell:** Windows PowerShell 5.1+ or PowerShell 7+

## Run from source (repo root)

You can launch Chronicle directly from the repository root without an editable install:

```powershell
python .\run_chronicle.py
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
5. Runs PyInstaller with `chronicle.spec`.

Default output:

- `dist\Chronicle\` (**onedir**, recommended for internal distribution)

Optional onefile output:

```powershell
./scripts/build.ps1 -OneFile
```

Onefile output:

- `dist\Chronicle.exe`

## Manual venv activation (optional)

If you prefer to activate and run commands yourself:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . pyinstaller
python -m PyInstaller --noconfirm --clean chronicle.spec
```

## Internal distribution guidance

- The default supported artifact is the full folder: **`dist\Chronicle\`**.
- Distribute that entire folder internally (zip/copy as a unit).
- End users should run: **`Chronicle.exe`** from inside that folder.
- Replacing the current app folder does **not** delete user data, because the
  current launcher stores data outside the app directory. This does not select
  replacement release paths or authorize deleting existing data.

## Current legacy user data location (unchanged)

Chronicle continues to read/write user data in the per-user home directory:

- `%USERPROFILE%\.task_timer_data`

Do **not** attempt to bundle or ship that data directory in the executable package.
