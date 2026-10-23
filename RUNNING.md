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
  A definitively stopped worker cannot reconcile within that session: retain the
  uncertainty, explicitly exit, and reopen. Failed connection cleanup retains
  dataset ownership until an explicit cleanup retry succeeds.

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
Stage 3A preview/evidence and Stage 3B file Save/recovery are independently accepted.
Stage 3C confirmation is independently accepted for functional development under
the later Stage 3D GO instruction. Stage 3D reconciliation/reminders are connected
and independently accepted for functional development by the later Stage 4A GO
instruction. The later Stage 4B GO independently accepts Stage 4A backup/cold
restore. The later Stage 4C GO independently accepts Stage 4B portable reliability.
Stage 4C cold compatibility inspection is delivered for independent review, not
complete stabilization or native/pilot qualification.

## Backup and cold recovery

Close other modal views, then choose **Backup Chronicle**. Choose a new file outside
the dataset and click Create Backup. Opening/canceling writes nothing. Timers
continue; wait for **Backup verified** before treating the operation as complete.
Existing files are never overwritten. Failure retains the path/diagnostic; choose
another path or explicitly validate a possibly published image. No automatic
backup/retry or cleanup of final files occurs.

Validate without opening the application:

    python run_chronicle.py --verify-backup BACKUP_PATH

Restore into a directory that does not yet exist, with an existing local parent:

    python run_chronicle.py --restore-from BACKUP_PATH --data-dir NEW_DATA_DIR

Restore validates before reserving that directory, uses consistent SQLite staging,
and exits without Tk/worker construction. It refuses existing directories, including
empty ones. Do not add --create or --timezone. Then start a fresh normal session:

    python run_chronicle.py --data-dir NEW_DATA_DIR

The original and backup remain untouched. A clone retains the same dataset identity:
**do not operate original and restored copies as competing live work authorities**.
Active timers resume without a Stop; dismissal uses the restored date and normal
current-date evaluation. Registered report text/basis and confirmation evidence
survive exactly. External text files are not bundled; use Saved Reports explicitly
if a copy is missing. A partially reserved directory is not automatically removed
or repaired; choose another new directory after reviewing the diagnostic.

Use supported local-disk directories. Hard-link publication must be available;
there is no unsafe fallback, overwrite or in-place/live restore. These engineering
checks do not qualify Windows/NTFS, hostile concurrent changes or hardware power
loss. Native source recovery qualification remains required before pilot.

## Cold dataset inspection

Close other Chronicle sessions first. On trusted local storage, inspect an existing
dataset without opening the application:

    python run_chronicle.py --inspect-dataset DATA_DIR

This command creates no Tk root, worker, writable connection or lock file. Do not
combine it with --data-dir, --create, --timezone, --verify-backup or --restore-from.
It reports only compatibility and validation diagnostics, not task/work contents.
A permitted result describes this completed cold inspection, not durable READY
status or exclusion of future external writes. Ordinary startup still revalidates
the dataset and acquires its normal ownership lock.

| Exit | Classification / meaning |
| --- | --- |
| 0 | SUPPORTED_CURRENT: complete version-1 schema, integrity and evidence verified; ordinary current-version startup permitted. |
| 2 | OLDER_UNSUPPORTED / NEWER_UNSUPPORTED: trustworthy observed version marker differs; no automatic migration or downgrade. A lower marker does not authenticate a historical Chronicle schema. |
| 3 | FOREIGN_DATABASE / UNSUPPORTED_LAYOUT / UNSUPPORTED_PROFILE: wrong application identity, differing current-version DDL or unsupported SQLite format/profile. |
| 4 | UNSAFE_OR_UNAVAILABLE: safe identity/integrity or successful inspection/cleanup/reporting could not be established. |

Argument-parser errors also use exit 2 and print usage. Schema version 1 and the
application identity remain unchanged. No upgrade is currently available.

Missing/unreadable/unstable files, symlinks (including directory aliases), unsuitable
objects and explicit network paths refuse. WAL-format headers refuse before SQLite
can create shared-memory sidecars. Any outstanding journal/WAL/SHM sidecar makes
cold inspection unavailable; this is not proof of corruption. The inspector neither
recovers nor deletes it. For a valid DELETE-mode dataset interrupted before COMMIT,
ordinary startup acquires exclusive dataset ownership and lets SQLite recover its
committed image, then completely validates it before the application becomes ready.
Unsupported recovered schemas, evidence and profiles still refuse; recovery is not
an upgrade or repair. Uncommitted work is rolled back and committed timers/evidence
remain intact. Cold inspection can be repeated after successful ordinary recovery
and orderly shutdown.
Do not delete sidecars or change permissions to force inspection. Metadata/digest
checks are bounded observations, not reliable exclusion of another writer or
hostile-directory protection. Use Backup Chronicle for a consistent live image.

A future approved transition requires its own exact source/target definitions,
transformation and evidence-preservation tests. The selected default is cold
transformation into a new nonexistent directory with independent target validation;
the original stays untouched. No such transformation or migration engine exists now.

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
exit nor failure undoes evidence/files. Timers continue. Reconciliation and
calendar reminders are described below; Save does not alter either confirmation
or reminder dismissal.

## Explicit POL-R confirmation

Load a registered export in Saved Reports (or use one just registered), then choose
Review POL-R Confirmation. File availability is separate from source evidence.
The review shows frozen suggested amounts, current Confirmed or Unknown, prior
identities and stale conflicts. Every positive suggestion is initially checked,
including equal values; zero is initially unchecked. Click Select cells or Select
all positive suggestions, then Confirm checked. Empty selection is an error.
Each selected newer-differing conflict requires its own unchecked acknowledgement;
review the exact task/date, old identity/value and frozen proposal before choosing it.
Refresh review discards old consent. Defer / Review later writes nothing.

Manual POL-R Confirmation requires no report: choose a retained task UUID, type a
civil date, Review current, then enter absolute decimal hours in exact 0.25 increments
(e.g. 0.00, 1.25, 2.5). Confirm absolute amount replaces that task/day value; it does
not add a Delta. Unknown is not zero. Invalid input retains the draft. A changed
reviewed prior requires explicit Refresh review; an unverified commit locks the
submitted inputs and offers Retry/Reconcile or default-No exceptional application
exit. A new explicit equal-value confirmation still records new immutable evidence.

Confirmation History reads complete immutable selected cells by batch UUID. Immediate
task/day feedback separates Actual, current Suggested, Confirmed, Daily Delta,
suggested-entry gap and full-week exact upward adjustment. Optional calculation
failure is visible and does not fabricate numbers or hide the reviewed confirmation
prior. Confirmation records your entered POL-R values; it does not query or verify
POL-R. It never edits a report, stops a timer, submits externally or dismisses a
reminder. Employer/customer redistribution and worked-day zero-entry treatment
still require external validation before official reporting/pilot.
Current-week suggestions may change; Preview is not external submission or
employer/customer policy qualification.

## Reconciliation and reminders

Open Timesheet / POL-R, then Reconciliation. This week/Last week/Custom and
All/Selected task UUIDs are independent drafts. Typed dates and Calendar choices
need Apply / Refresh; the as-of label always identifies the applied observation.
Scroll the daily table horizontally for Actual, Suggested, Confirmed, signed
Delta/gap and status. Unknown is not zero. Copy Suggested copies the absolute
amount for the selected task/date; copying is not external submission.

Weekly summaries show complete seven-day targets, precise upward adjustment
(not extra Actual), known confirmed subtotals and coverage. Partial scope is not
a complete-week review. Equal weekly sums cannot hide opposing daily mismatches;
an explained nonzero Delta may still match the suggestion. Compare loaded report
with current reconciliation preserves the historical report, shows frozen/current
week conventions and source differences. Review saved report, source confirmation
and manual absolute confirmation use the existing interfaces. No read confirms work.

The main banner checks previous week on every application-used local date and
current week on local Monday/Friday, independently of the selected week start.
Open Timesheet chooses the outstanding period (previous week first). It does not
dismiss. Dismiss for today is explicit, persists across same-day restart and
suppresses both reminder categories only for that dataset-local date. Later work
that day does not undo dismissal; the next date is reevaluated without a cleanup
write. Recheck POL-R explicitly retries unavailable evaluation. Failure is not an
all-clear. Running timers continue through all views. Saving never dismisses or
confirms. External redistribution/zero-entry policy and native deployment still
need qualification.
