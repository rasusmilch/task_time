# Building Chronicle for Windows (PyInstaller)

## Runtime and qualification boundary

The root launcher and `chronicle.spec` now select only `src/chronicle`, the Stage
1A SQLite timer. `task_timer` is excluded, not a fallback. Stage 1 remains In
Progress: native Windows source/onedir smoke and operational qualification are
pending. [Architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md) and
[testing strategy](docs/TESTING_STRATEGY.md) own the corresponding boundaries.

Python 3.11+ is the source floor. Verify the linked SQLite, not only Python:
STRICT needs 3.37+, but supported deployment requires the WAL-reset corruption fix
(3.51.3+ excluding withdrawn 3.52.0). The store checks that gate and effective
WAL/FULL/foreign keys. Linux development here uses Python 3.12.14, SQLite 3.53.1
and Tcl/Tk 9.0.4; those are exercised source versions, not a Windows version pin.
See [upstream changes](https://sqlite.org/changes.html) for the fix/release status.

`tzdata==2026.5` is the pinned runtime dependency; zone loading uses its resources
offline even when system TZPATH exists. The spec collects those resources and
uses PyInstaller's normal tkinter/Tcl/Tk hooks. Resource presence and launch must
still be verified on the Windows artifact. No network timezone lookup is used.

## Run from source

Use a disposable explicit local path, never the old default data directory:

```powershell
python -m pip install -e .
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh --timezone America/Chicago --create
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh
```

Alternatively `./scripts/run.ps1 -DataDir C:\Chronicle-test\fresh -Timezone
America/Chicago -Create`, then reopen without Create/Timezone. Missing data-dir
is a usage error. Unknown nonempty/partial datasets are refused, not repaired.
Production install paths, cutover and cleanup remain Open. No source/build command
imports or initializes `~/.task_timer_data`.

## Windows onedir build

Use a native Windows checkout with Python 3.11+ and PowerShell 5.1+/7:

```powershell
./scripts/build.ps1
```

The script creates a missing Windows venv, refuses an existing incompatible venv,
installs the project and `pyinstaller==6.22.3`, checks SQLite and builds the spec.
It refuses existing build/ or dist/ rather than deleting them. Inspect/move those
outputs explicitly first. There is no separate onefile/legacy build route.
PyInstaller 6.22.3 was installed/imported on Linux; that is not a native build test.
Transitive build locking, native SQLite/toolkit pins and reproducibility evidence
remain in the subsequent operational/Windows slice. There is no unconstrained
pip-upgrade step or invented claim of fully reproducible Windows output.

Distribute the full `dist\Chronicle\` directory when qualified. Smoke with a
separate fresh engineering directory:

```powershell
.\dist\Chronicle\Chronicle.exe --data-dir C:\Chronicle-test\packaged --timezone America/Chicago --create
```

Exercise duplicate-name tasks/projects, Start/Switch/Stop, mini, active restart,
explicit active-start correction, second-owner refusal, offline zones, close and
storage failures. Verify Tcl/Tk resources, actual SQLite source/profile and that
no old dataset is touched. Windows builds must run on Windows. Linux imports,
Tk/X11 tests and syntax checks are not NTFS, packaged or release qualification.
