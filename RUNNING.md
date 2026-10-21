# Running Chronicle from Python source

## Prerequisites

Use Python **3.11+** with its standard `sqlite3` and `tkinter/ttk` modules.
The actual linked SQLite must be **3.37.0+** for STRICT tables; a Python version
alone does not prove the SQLite version. Chronicle checks DELETE journaling,
EXTRA synchronous (3) and foreign keys (1) before application mutations.
No custom SQLite provider, compiler, administrator rights or executable build is
required for ordinary operation. Tcl/Tk must be included with the Python installation.

From the repository directory, check the chosen interpreter:

```powershell
python -c "import sys,sqlite3,tkinter; print(sys.version); print(sqlite3.sqlite_version); print(tkinter.TkVersion)"
```

Install the sole external runtime dependency into an environment you are permitted
to use. A virtual environment is recommended, but an editable project install is
not required. Optional setup: `python -m venv .venv`, then activate it or use its
Python executable directly (`.venv\Scripts\python.exe` on Windows,
`.venv/bin/python` on Linux).

```powershell
python -m pip install --only-binary=:all: tzdata==2026.5
```

Initial pip installation may need internet access or an approved local wheel
source. IT policy may restrict Python, pip or environment creation; these
instructions do not bypass those restrictions. Chronicle downloads nothing at
startup and operates offline once dependencies are installed.

## Create and reopen

Choose an explicit new, disposable local-disk directory for engineering use:

```powershell
python run_chronicle.py --data-dir PATH --timezone America/Chicago --create
```

Replace PATH with your chosen directory; quote paths containing spaces. Creation
requires a new or genuinely empty directory and an explicit IANA timezone.
Reopen that same dataset without `--create`:

```powershell
python run_chronicle.py --data-dir PATH
```

The launcher resolves `src/chronicle` directly. `chronicle.bootstrap.main` is the
single entry point; no project wheel or installation step is needed.
[scripts/run.ps1](scripts/run.ps1) is an optional thin convenience accepting
`-DataDir`, `-Timezone`, `-Create`; it neither builds nor installs dependencies.

Use writable local storage, not a network/cloud-sync directory. The dataset has
`chronicle.sqlite3`, `.chronicle.lock` and, during writes, a temporary SQLite
rollback journal. Do not delete lock/journal files or copy a live database as a
backup. A second owner refuses. Unknown, damaged or unsupported datasets refuse
without automatic recreation. Old development databases are disposable but are
never automatically converted or deleted. No production database migration or
installation/data-directory cutover is provided; final release paths remain Open.
The launcher never discovers or imports `~/.task_timer_data`.

## Troubleshooting and native Windows verification

- Missing `tkinter`/`_tkinter`: use an approved Python distribution with Tcl/Tk.
  An unavailable graphical display is also an environment error; check the desktop.
- SQLite too old: choose an approved Python installation whose **actual** built-in
  SQLite is at least 3.37.0. Chronicle does not install another driver or replace DLLs.
- Missing tzdata: install the pinned package above using the same interpreter.
  Invalid IANA keys are rejected; the dataset timezone is not editable in this UI.
- Ownership/busy/storage errors: preserve the dataset and original diagnostics;
  do not remove files or infer that an uncertain request failed. Use the existing
  exact-request Retry/Reconcile and explicit cleanup controls as appropriate.

Before real Windows deployment/pilot, record native Python, SQLite source/profile,
Tcl/Tk, offline zone loading and writable NTFS behavior. Exercise create/reopen,
second-owner refusal, persisted active timer, main/mini controls, active-start
correction, modal input/focus, exceptions and normal shutdown with disposable
paths. Actual suspend/resume needs native evidence too. Later core workflows need
their own validation when delivered. Linux SQLite/Xorg tests are engineering
evidence, not Windows/NTFS, hardware power-loss or release qualification.

Stage 1 functionality is independently accepted; unavailable Windows
source evidence is a deployment/pilot gate, not an executable-build prerequisite
or a permanent blocker to Stage 2 development. See [roadmap](docs/ROADMAP.md) and
[testing strategy](docs/TESTING_STRATEGY.md). Stage 2A is independently accepted;
Stage 2B/complete recording is independently accepted at `adc09ba0935e8718c4ad2101057af9c6022074cc`.
Stage 3A preview/evidence is independently accepted. Stage 3B file Save/recovery is
connected for independent review; Stage 3 remains incomplete.

## Manual work and week configuration

Select a task, then Add timed work or Add date-only work. Dates default to today
in the dataset timezone; enter actual clocks or a positive H:MM duration and Save.
Repeated local minutes need an explicit first/second occurrence; gaps reject.
Timed work cannot end after the accepted observation. Future date-only amounts
remain wholly on their declared dates. Cancel writes nothing. Validation/storage
errors retain drafts; an unverified Save retains exact retry inputs. Opening a
form does not stop an existing timer.

Week starts accepts Monday through Sunday (initially Sunday) and saves the choice
in this dataset. It changes containing-week totals, not work dates or amounts.
Stage 2A uses a revised fresh schema version 1: older development schema signatures
refuse without migration/recreation. Choose a new disposable directory explicitly;
never delete or overwrite an existing dataset as an automatic startup action.
Select a task and open Work History to browse Current week, inclusive Custom or
All. Custom typing/calendar choices need Apply; Refresh reloads the applied period.
Date reverses date groups only and is remembered for this running application.
Select a closed timed or date-only row to Edit the complete entry inline, or Delete
after reviewing its full date/range confirmation. Running rows cannot use those
actions. Details includes earlier revisions and Deleted entries. Save waits for
the worker result; unverified work retains exact Retry/Reconcile inputs. Close
History before using main/mini.

## Timesheet / POL-R Preview, Save and Saved Reports

Close History or another work form, then choose Timesheet / POL-R. Fresh openings
start This week/All tasks and require Preview. Last week uses the committed week
convention; Custom accepts inclusive dates or draft-only inline calendar choices.
Selected tasks uses explicit UUID rows (Ctrl/Shift selection), not names or
hierarchy. Retained deleted tasks remain available. Preview observes a running
timer without stopping it and shows Actual separately from suggested POL-R.
Full-week target/adjustment context includes dates outside a partial report.
Changed inputs require a fresh Preview even after changing back. Older output is
labeled previous. Save Timesheet opens an owned .txt destination dialog. Cancel
writes nothing. Registration must be verified before publication; an uncertain
registration retains the exact request for Retry/Reconcile and blocks ordinary
abandonment. A registered report can be retried or copied without recalculation.
Default Save protects existing files; Overwrite is offered only after a verified
regular-file content conflict, names the exact path and defaults to No. It permits
one replacement call. Active dataset paths/aliases are always protected.

Saved Reports lists frozen UUID/date/cutoff/scope/label context and loads exact stored
text, including after restart. Check File Status explicitly inspects the selected
path; READY is only that observation. A missing copy can be restored with Retry Save;
Save Copy As chooses a new destination without changing the original preferred path.
New Preview deliberately starts another identity. No automatic retry occurs.
Close discards an unsaved preview or completed view. A registered unfinished file
attempt requires default-No confirmation, then disposes the window; a small session
handoff retains its UUID/current path. Reopening starts fresh; Saved Reports recovers
the old report explicitly. Exit warns before losing volatile attempt context; neither
exit nor failure undoes evidence/files. Timers continue. Confirmed values and
reconciliation/reminders remain unavailable.
Current-week suggestions may change; Preview is not external submission or
employer/customer policy qualification.
