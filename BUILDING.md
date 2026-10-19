# Building Chronicle for Windows (PyInstaller)

## Runtime and qualification boundary

The sole source/build route selects `src/chronicle`, not the retained `task_timer`
package. Stage 1A is accepted for its bounded connected timer scope. Stage 1B
adds portable interruption, ownership, startup/cleanup and controlled-build-input
engineering. **Native Windows source, NTFS, PowerShell and packaged qualification
remain unverified. Stage 1 remains In Progress.** See [architecture](docs/ARCHITECTURE.md),
[roadmap](docs/ROADMAP.md) and [testing strategy](docs/TESTING_STRATEGY.md).

The source floor is Python 3.11. The candidate build input set targets native
Windows x64 CPython 3.11–3.15, constrained by PyInstaller's actual wheel metadata.
That range is not a list of qualified interpreter builds. The linked SQLite must
contain the WAL-reset fix: **3.51.3+ excluding withdrawn 3.52.0**, distinct from the
STRICT feature floor 3.37. An ordinary Windows Python may fail this gate; select
an interpreter whose actual linked build passes, rather than weakening the gate
or swapping in an unapproved SQLite library. No native interpreter combination is
qualified by the Linux evidence. See [upstream changes](https://sqlite.org/changes.html).

The available Linux environment exercises Python 3.12.14 / SQLite 3.53.1 /
Tcl/Tk 9.0.4. Process kills and injected errors are bounded experiments, not all
power-loss or filesystem failures. Simulated sleep gaps are not actual suspend/resume.

## Controlled inputs and safe build

Use a fresh native Windows checkout, PowerShell 5.1+/7 and an explicitly selected
supported x64 CPython executable. Do not reuse a user dataset or production folder.

```powershell
./scripts/build.ps1 -Python 'C:\path to supported Python\python.exe'
```

If `.venv` already exists, the script verifies its actual prefix, architecture,
Python/SQLite runtime and package inventory before installing anything. An
incompatible environment or unrelated packages are refused; preserve them and use
a fresh checkout. An explicit invalid interpreter never silently falls back.
Existing `build/` or `dist/` is refused before installation, without deleting it.
A partial failed build is likewise preserved for inspection; use a new isolated
checkout for another attempt. Run one builder per checkout.

[requirements/windows-build.lock](requirements/windows-build.lock) freezes actual
PyPI wheel versions and SHA-256 hashes, including Windows-specific dependencies:

| Input | Version |
| --- | --- |
| PyInstaller | 6.22.3 |
| pyinstaller-hooks-contrib | 2026.8 |
| altgraph | 0.17.5 |
| packaging | 26.3 |
| pefile | 2024.8.26 |
| pywin32-ctypes | 0.2.3 |
| setuptools | 84.0.0 |
| wheel | 0.48.0 |
| pip | 25.0.1 |
| tzdata | 2026.5 |

These artifacts were resolved/downloaded for Windows x64 and rechecked with pip
hash enforcement on Linux. That is artifact-input evidence, not Windows execution.
The script uses this exact dependency installation form, only in the checked venv:

```powershell
& .\.venv\Scripts\python.exe -I -B -m pip --isolated install --no-user --require-hashes --only-binary=:all: -r .\requirements\windows-build.lock
```

Pip checks dependency consistency; the preflight verifies exact installed versions
and rejects uncontrolled extras. The spec analyzes this checkout's `src/` directly,
so no application install/build step can prepopulate its work directory. UPX,
`--clean`, overwrite confirmation bypass and global installs are not used. Native
command failures are checked immediately and terminate the script nonzero.

`build/environment.json` is exclusive build provenance, not application state. It
records Python/build/architecture, linked SQLite source ID/compile options, Tcl and
linked Tk version, dependency versions, lock/source hashes and SQLite binary hashes.
A Windows operator must separately record the loaded Tk patchlevel and actual
packaged runtime. The resulting artifact is `dist\Chronicle\Chronicle.exe`; distribute
the whole onedir directory. Controlled inputs do not promise identical binary bytes
across machines. `chronicle.spec` collects offline tzdata and uses the normal Tk hooks;
actual resource usability still requires the native smoke below.

## Native source and packaged qualification procedure — pending

These are commands and acceptance observations for a later native run, **not an
executed Windows transcript**. Record Windows version, local filesystem/NTFS,
PowerShell, Python architecture/build, SQLite source/profile and Tcl/Tk patchlevels.
First parse the script with PowerShell's parser; any errors fail before execution:

```powershell
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\scripts\build.ps1), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { throw ($errors | Out-String) }
./scripts/build.ps1 -Python 'C:\path to supported Python\python.exe'
```

Pass: every command succeeds, environment/provenance is recorded, the onedir exe
exists, and no unrelated output/data was removed. Also run negative build cases:
unsupported SQLite, incompatible `.venv`, failed installation/preflight/PyInstaller,
existing outputs, and checkout paths with spaces/Unicode. Each must fail nonzero
and preserve existing files. Native `$LASTEXITCODE` behavior is not established by
Linux static tests.

Use two different new engineering datasets (never old defaults):

```powershell
$Lab = Join-Path $env:TEMP ('Chronicle qualification ' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Lab | Out-Null
& .\.venv\Scripts\python.exe -B .\run_chronicle.py --data-dir (Join-Path $Lab 'source Ω') --timezone America/Chicago --create
& .\.venv\Scripts\python.exe -B .\run_chronicle.py --data-dir (Join-Path $Lab 'source Ω')
& .\dist\Chronicle\Chronicle.exe --data-dir (Join-Path $Lab 'packaged Ω') --timezone America/Chicago --create
& .\dist\Chronicle\Chronicle.exe --data-dir (Join-Path $Lab 'packaged Ω')
```

For source and packaged GUI, exercise and record:

1. Duplicate-name tasks, project create/rename, assignment/unassignment. UUIDs stay
   independent. Start A, Switch B, Stop B; one exact shared Switch instant, conserved
   Today/This week, one active timer, no extra work or receipts from refresh.
2. Main/mini interaction, normal Close while active, reopen with the same UUID/start.
   In a disposable process only, terminate after an acknowledged Start, then reopen;
   no synthetic Stop/new Start. A second process is refused while ownership is live,
   succeeds after normal/crashed-owner closure, and leaves unknown nonempty targets
   untouched. Exercise ordinary native directory aliases/junctions and NTFS permissions;
   unsupported alias privileges are a narrowly reported limitation, not a whole-suite pass.
3. Active-start correction: invalid gap, explicit repeated-hour choice, preserved
   rejected draft, valid correction, immutable original/prior/new audit, exact retry
   and default-cancel exceptional exit under injected uncertainty. Main/mini stay
   blocked under the editor grab; queue/result delivery and timers continue.
4. Actual suspend/resume while active, plus midnight/week/DST observations where
   practicable. Time remains continuous until explicit Stop/Switch. Report controlled
   clock-gap tests separately from a real suspend/resume experiment.
5. Startup refusal/error presentation for partial, corrupt, future-schema,
   permission-denied and unknown directories. Cleanup failure retains ownership and
   offers explicit retry; never reports success before connection closure.

Run the portable tests on that supported Windows source interpreter too:

```powershell
& .\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -o addopts='' tests/rewrite/
```

Pytest is deliberately absent from the controlled packaging environment. Use a
separate test venv with declared test extras for this command; do not contaminate
the build venv and then call that an identical controlled build. The command above
uses that test checkout's `.venv`. Linux-only XTest cases skip on Windows; obtain
native mouse/keyboard evidence through the real GUI procedure instead.

For the real onedir executable, launch a copied complete bundle from an unrelated
working directory, offline, without repository/PYTHONPATH/venv access. A clean
Windows machine without a separately installed Python is the independence test;
removing Python from PATH alone is weaker evidence. Verify actual loaded module
paths (for example with a native module inspector) are inside the bundle, compare
`_sqlite3.pyd`/SQLite DLL hashes with build provenance, and record the executable's
SQLite version shown in its UI. Verify actual WAL/FULL/FK settings and STRICT checks
in the disposable dataset and offline Chicago zone behavior. A build-machine version
check alone is insufficient. Retain any missing packaged source/runtime evidence
as an open gate.

```powershell
& .\.venv\Scripts\pyi-archive_viewer.exe -l -r .\dist\Chronicle\Chronicle.exe
```

Inspect the actual archive/resources for Chronicle, Tk and tzdata and the absence
of `task_timer`/legacy settings/writers. The archive listing alone is not desktop
qualification. A diagnostic/console runner is not the real windowed artifact.
No network service is required at application runtime.

## Remaining boundaries

There is one onedir route, no compatibility runtime or automatic production path.
Fresh paths/cutover stay Open. Stage 4 owns supported SQLite backup/restore/schema
upgrade workflows; never copy only a live WAL database main file as a backup.
Stage 2 recording/History and Stage 3 core Timesheet/POL-R remain unimplemented.
Independent review plus missing native evidence is required before Stage 1 Complete;
this engineering work is not product/release qualification.
