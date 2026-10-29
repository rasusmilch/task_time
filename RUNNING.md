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

## Ordinary startup and first-run setup

From the repository directory, launch without flags:

```powershell
python run_chronicle.py
# Optional Windows convenience (same workflow and interpreter selection):
.\scripts\run.ps1
```

**Welcome to Chronicle** explains local storage and shows the proposed dataset
folder. Choose/enter another absolute local folder if needed. Select a readable
timezone and click **Create and Open** to confirm both; **Advanced / Other** accepts
an explicit offline IANA zone for other regions. A trusted exact Windows timezone
key can suggest a choice; otherwise choose one yourself. Existing datasets retain
their stored timezone. **Open Existing Dataset** chooses a dataset directory, not
a backup import. **Cancel** writes no settings/data and starts no database worker.

Windows suggests `%LOCALAPPDATA%\Chronicle\Data`; Linux uses
`$XDG_DATA_HOME/Chronicle/Data` or `$HOME/.local/share/Chronicle/Data`; macOS uses
`$HOME/Library/Application Support/Chronicle/Data`. Unsuitable/unavailable local
storage requires explicit selection. These are opt-in source-mode conveniences,
not final installation paths or legacy cutover. Displaying setup creates nothing.
Creation accepts only a new or genuinely empty folder, with the existing worker/
SQLite exclusive-creation and race guards. Network paths and existing symlink/
reparse redirection refuse; choose trusted local storage, outside cloud sync.

A bounded `launcher-selection.json` beside the suggested `Data` folder stores
only format version 1 and the absolute selected dataset directory. It is separate
from SQLite facts. It is written only after worker readiness and never by explicit
CLI/recovery commands. Missing preferences permit discovery only at this new
source-mode default: an apparent database opens normally; absent/empty folders
show setup; other content refuses implicit creation. No legacy paths are searched.

Subsequent zero-argument launches open the remembered dataset through ordinary
ownership, complete validation and native hot-journal recovery. Missing, busy,
damaged or unsupported datasets show diagnostics and require explicit action;
a failed open never creates replacement data. Corrupt, unsupported, linked or
unreadable selection records are retained, not silently overwritten. Explicit
selection can still open a healthy dataset; a persistent warning explains if its
location cannot be remembered. An unchanged valid reviewed record alone may be
replaced after readiness; publication is staged/synced/verified and an absent
record is published exclusively. These are trusted-local-storage protections,
not atomic compare-and-replace against hostile filesystem changes.

Setup and the application share one Tk root/mainloop. No worker starts until an
accepted create/open choice (including remembered/default existing discovery).
Controls wait for startup and cleanup; **Retry cleanup** retains existing ownership
until the original worker closes safely. Cancel after an accepted operation waits
for its completion rather than interrupting SQLite. A remembering failure does
not close or undo the successfully opened dataset.

Native Windows first-run/timezone suggestion, chooser/focus and reopen validation
of this new flow remain required. Earlier unattended Windows qualification is
historical supporting evidence, not execution of this startup UI. Stage 4 remains
IN PROGRESS and Stage 5 is NOT STARTED.

## Explicit engineering creation and reopening

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

B1 creates schema 2 only: task parentage has at most three levels under a project
or Unassigned, new recording is leaf-only, and historical parent work remains
retained. The current grouped main/mini interface creates project-scoped roots;
service-level nested development fixtures await the full nested UI and native
qualification. C1 supplies Archive and Archived Items; C2 adds unused-only Delete.
No template or branch-move GUI command is delivered.

The launcher resolves `src/chronicle` directly. `chronicle.bootstrap.main` is the
single entry point; no project wheel or installation step is needed.
[scripts/run.ps1](scripts/run.ps1) is an optional thin convenience accepting
optional `-DataDir`, `-Timezone`, `-Create`; it neither builds nor installs dependencies.
Explicit CLI preserves its former meanings and does not update launcher selection.
`--create` still requires `--data-dir` and `--timezone`; `--timezone` alone refuses.
Recovery/inspection remain headless and never enter setup. Existing supported
explicit directory aliases retain their previous CLI semantics; setup selection
uses the stricter no-redirection admission described above.

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
Stage 4C cold compatibility inspection, protected refusal and bounded owned
SQLite-native rollback recovery are independently accepted for functional
development. Stage 4 remains IN PROGRESS; Stage 5 is NOT STARTED. Native Windows/NTFS
qualification, including operator modal/focus, backup/restore and hot-journal recovery,
and actual suspend/resume remain outstanding. External reporting policy and
installation/cutover approval remain open.

## Bounded Windows qualification collector

From the reviewed, clean repository, use the installed Python environment and an
approved existing local NTFS output parent outside the repository, Chronicle data
and cloud-synchronized folders:

```powershell
.\scripts\qualify_windows.ps1 -Scope MetadataProbe -OutputParent 'C:\Qualification evidence'
```

The default scope is MetadataProbe. No source/path editing, package installation,
fetch, reset or execution-policy change is performed. If policy blocks the script,
stop and report it. Do not bypass policy. Optional `-Repo`, `-Python` and
`-ExpectedRevision` select existing source/interpreter and an expected commit prefix.
By default it finds this script's repository, `.venv\Scripts\python.exe` or installed
`python`, and reserves a new unique directory below the temporary directory. Passing
an output parent approves only the newly reserved child, not existing contents.
Store execution aliases, source/output aliases, network paths and repository/data overlap
refuse. Missing prerequisites produce BLOCKED evidence when a safe output directory
can be reserved; an unsafe/unavailable output parent cannot receive a receipt.

| Scope | Unattended work |
| --- | --- |
| MetadataProbe | Only new disposable files: raw stat/lstat/fstat JSONL, readonly/writable handle observations, fsync/close, hard-link identity and same-size mutation with restored mtime. No Chronicle dataset is opened. |
| Critical | Probe plus the frozen observation-contract tests and named profile/reopen, report publication/reuse/conflict/reinspection, minimal backup/restore and genuine hot-journal cases. |
| Storage | Probe plus explicitly listed source-runtime, schema/services/worker/bootstrap, ownership/lifecycle, interruption, compatibility, backup/restore and protected-report functions. |
| Extended | Storage plus listed pure time/accounting, manual/revision/history-reader/week/allocation cases and exactly two audited Backup callback tests. It is not the full repository suite or the supervised operator workflow. |

The exact frozen function lists and fixture allowlist live in
[scripts/qualification_pytest.py](scripts/qualification_pytest.py). Collection checks
each node's fixture closure, including indirect/dynamic dependencies. The generated
manifest records every collected rewrite exclusion as NOT RUN with its reason;
legacy source-level cases are separately listed as not collected. A name lacking
`real_tk` is no safety argument. Extended's chooser callback locally doubles its
owned file chooser to cancel; its failure/retry callback requests no native dialog.
Neither is native operator-input evidence. Other GUI/operator cases remain deferred.

The display updates at least once per second, with current node, setup/call/teardown,
selected/completed node counts, final node outcomes, elapsed time and event age.
Text heartbeats appear every ten seconds. Progress is indeterminate until collection
completes; percentages use completed nodes only. Setup/teardown errors classify the
node as error, rather than adding another completed node. Raw pytest reports, exit
status and real JUnit remain separate evidence. Critical/Storage/Extended only
report PASS when the final selection manifest, unique node completions, phase
outcomes and actual pytest JUnit cases agree. Missing, truncated, unrelated or
unmappable XML/manifest evidence yields EVIDENCE_INCOMPLETE even when pytest exits
zero. Parametrized nodes count individually; legitimate multiple setup/teardown
error details do not multiply completed nodes. MetadataProbe expects no JUnit and
reports OBSERVED, never a Windows compatibility PASS. Its mutation observations
include the open descriptor and a fresh read-only descriptor after close/reopen.

Defaults are 90 seconds for collection/prerequisites/probe, 120 seconds per whole
node and 900 seconds for the pytest phase. The genuine-spill recovery family alone
has an explicit 240-second node allowance. `-CollectionSeconds`, `-TestSeconds` and
`-PhaseSeconds` permit reviewed, recorded changes for legitimately longer work;
limits never extend automatically. A 30-second lack of pytest events warns while
heartbeats continue. Cancellation requests cooperative collector cleanup, then bounds
forced cleanup. ZIP generation is bounded to 60 seconds when Python is available.

Pytest is created suspended with a creation-time kill-on-close Job Object attribute,
then membership is checked before resume; inability to establish containment blocks
execution. Only its designated standard handles are inherited. Timeouts terminate
only that owned job, including descendants. Raw stdout/stderr drain independently.
Live console mirroring is bounded/truncated under large output so progress can
continue; complete original bytes remain in stdout.log/stderr.log, with truncation
reported separately. Launcher log streams close before the ZIP is generated.
Unexpected Tk construction or toolkit dialogs obstruct instead of receiving an
answer. Callback roots are allowed only for the two audited nodes; dialogs still
require their local doubles. Owned visible windows outside those permissions also
obstruct. External OS/security processes cannot be universally detected: an unknown
obstruction is bounded by the watchdog and never clicked or automatically approved.
No Defender/ACL/trust/security policy is changed.

The console reports a unique evidence directory and one ZIP beside it. Keep the ZIP
for manual upload; nothing uploads automatically. It contains source/collector
identities, environment/profile observations, manifests/deferred cases, arguments,
flushed events, both logs, real JUnit or explicit missing/partial status, timeout/
cleanup diagnostics, probe files and final summaries. Hidden artifacts are included;
reparse links are recorded as omitted, not traversed. Unexpected root/child
enumeration errors fail archiving instead of silently omitting evidence.
`archive-members.json` and other new receipt names are exclusively created: an
existing file, directory, hard link or reparse object is a conflict, never something
to overwrite. Updates to final records use their reserved handles.

`collector-result.json` retains the immutable raw collector/test outcome and
actual process/pytest exits. `summary.json` and `launcher-result.json` report the
separate overall and archive-delivery outcome. Directory receipts remain
pessimistic during archiving; the ZIP serializes the intended completed receipts,
and directory completion is installed only after archive closure/acknowledgement.
`archive-completion.json`, when present, is explicitly proposed receipt content,
not proof of delivery. A failed or timed-out archive, failed status finalization
or uncertain cleanup produces a nonzero launcher result; a completed underlying
test run remains visible in the raw record. An unacknowledged/partial ZIP is not
claimed as delivered. If storage prevents diagnostic/final-status writes, the
console reports that limitation and exits unsuccessfully; retained records may
then be incomplete and must not be treated as successful delivery.

ZIP failure leaves the directory and diagnostics intact. No failed archive is
overwritten or silently retried through another builder. Crash fixture databases/journals are diagnostic artifacts,
not verified backups. A failed pre-Python launch uses a .NET ZIP fallback.

PowerShell 5.1/7 quoting, visible progress, NTFS observations, native dialog guarding
and Windows Job Object containment remain UNVERIFIED until actual native execution.
Portable helper tests and static inspection do not establish Windows qualification.
The prior standalone metadata probe remains a fallback until this scope is natively
verified. The collector and bounded evidence-safety repair are independently
accepted for limited native MetadataProbe use only; Critical/Storage/Extended are
implemented scopes, not authorization to execute them. Monday's MetadataProbe
remains the next native qualification action. Do not proceed automatically to
broader scopes, operator qualification, suspend/resume or pilot. See
[acceptance provenance](docs/DECISIONS.md#stage-4c-and-portable-tooling-acceptance).

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
| 0 | SUPPORTED_CURRENT: complete version-2 schema, integrity and evidence verified; ordinary current-version startup permitted. |
| 2 | OLDER_UNSUPPORTED / NEWER_UNSUPPORTED: trustworthy observed version marker differs; no automatic migration or downgrade. A lower marker does not authenticate a historical Chronicle schema. |
| 3 | FOREIGN_DATABASE / UNSUPPORTED_LAYOUT / UNSUPPORTED_PROFILE: wrong application identity, differing current-version DDL or unsupported SQLite format/profile. |
| 4 | UNSAFE_OR_UNAVAILABLE: safe identity/integrity or successful inspection/cleanup/reporting could not be established. |

Argument-parser errors also use exit 2 and print usage. Only exact fresh schema 2
with application ID 0x4348524E is supported. Version 1 refuses; no migration,
downgrade or automatic replacement is available. A failed remembered v1 open
retains its selection and all prior data; choose a different new/empty directory
explicitly to create v2. Never use --create on retained data.

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

B1's supported image is exact fresh schema 2. These commands preserve and validate
its task parentage, archive metadata, direct work and protected evidence, with no
migration, backward-compatible mode or automatic conversion of version-1 datasets.
Existing files remain protected; choose a different new/empty folder explicitly
for fresh v2 creation. Branch movement, lifecycle actions, nested management UI
and templates remain pending separate approval. Do not delete journals or old databases
to bypass refusal. Any hypothetical future data-preserving transformation would
require separate source/target and safety approval; no such engine exists now.
See the [target boundary](docs/TIMESHEET_REQUIREMENTS.md#approved-hierarchy-target-and-fresh-data-boundary).

## Archive and Archived Items

Select a real project/task in main, then **Archive**. Review the node UUID and
affected descendant count in the default-No confirmation. Cancel writes nothing.
A containing running timer blocks Archive; Stop explicitly first if intended.
Archive preserves work, membership and reporting evidence. Only the selected
explicit flag/current accepted UTC archive instant changes; descendants inherit
visibility and retain any independently archived state.

**Archived Items** opens one modeless expandable tree, including empty archived
projects, full three-level branches and independent task branches with original
ancestor context. It cannot record new time. **Today / This Week** uses the same
coordinated report as main. Sort by **Name — A to Z / Z to A** or **Date Archived —
Newest first / Oldest first** (newest default), retaining selection and expansion.
Dates display in the dataset timezone with UTC offset; sorting uses actual UTC.

**Unarchive selected** clears only an explicitly archived selected node. For
inherited-only rows it is disabled and the hiding ancestor is explained. Independent
archived children stay hidden after parent Unarchive. **Work History** opens the
existing direct-task modal, including permitted retained work corrections/deleted
revisions. Close History before further management/main/mini actions. Pending or
uncertain operations retain the owner's exact Request even if Archived Items is
closed; Archive/Unarchive uses the existing Retry/Reconcile controls. C2 Delete
has the distinct no-retry uncertainty boundary below.
Full nested active-tree management and templates remain later packages. Native
Windows focus/topmost/input qualification of this changed interface remains pending.

## Delete unused projects and task branches

Select a real project/task in main or Archived Items, then **Delete**. No prior
Archive is required; virtual Unassigned is not deletable. The owned preview reads
the complete selected hierarchy and administrative closure on the worker. Review
name/UUID, every task, removal counts, eligibility and refusal reasons. Protected
work (including deleted revisions), active timers/corrections, frozen zero/scope/
basis/project references, confirmations or unresolved survivor dependencies refuse
the entire scope. Use Archive for history-bearing items; no automatic Archive occurs.

For an eligible review, read **Delete permanently removes this unused structure.
It cannot be undone.** Type exactly **DELETE**, then click **Delete**. Cancel or
incorrect text writes nothing. The service rechecks the complete original review
inside one transaction; stale scope/version/dependencies refuse and require **New
preview**, with a new confirmation. No rows hide before authoritative completion.
Only unused entity rows and proven exclusively owned administrative requests are
removed. Work, frozen reports, confirmations, unrelated records and backups remain.
No Trash, retained deleted identity, deletion ledger or secure-byte-erasure exists.
A reused name creates a fresh UUID through ordinary creation.

Delete writes no persistent receipt. If acknowledgement is uncertain, **do not
retry**. **Inspect current state / Inspect Delete state** may show PRESENT or ABSENT;
this establishes current presence only, never historical success. Further mutation
is blocked. Choose **Exit and reopen**, confirm the default-No warning explicitly,
then make a fresh selection/review/typed confirmation if a new Delete is still
appropriate. Ordinary Retry/Reconcile never resubmits Delete. Failed connection
cleanup retains dataset ownership and uses the established explicit shutdown
cleanup retry. No unresolved-delete journal is created. Native Windows UI/NTFS
qualification remains separate; Stage 4 is IN PROGRESS and Stage 5 NOT STARTED.

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
Stages 1–3 originally used fresh schema 1. B1 now supports exact fresh schema 2:
version-1 datasets and older development schema signatures
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
hierarchy. Schema-2 archived/parent identities remain reportable; they do
not change the Archive/Unarchive controls or authorize irreversible Delete. Preview
observes a running timer without stopping it and shows Actual separately from
suggested POL-R.
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
