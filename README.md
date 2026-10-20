# Chronicle

A small local Python + Tkinter/ttk task timer **and, when the core is complete,
explicit absolute POL-R reconciliation**. SQLite is the sole replacement authority.

## Product authority and implementation status

| Owner | Scope |
| --- | --- |
| [Requirements](docs/TIMESHEET_REQUIREMENTS.md) | Selected behavior, delivered scope and Open decisions. |
| [Architecture](docs/ARCHITECTURE.md) | Tkinter/SQLite boundaries, transactions, exact units and worker lifecycle. |
| [Export/POL-R contract](docs/EXPORT_EVIDENCE_CONTRACT.md) | Frozen evidence and the single weekly quarter-hour allocation/confirmation contract. |
| [Roadmap](docs/ROADMAP.md) | Stages 0–6 and qualification gates. |
| [Design Notes](DESIGN_NOTES.md) | Retained unshipped JSONL implementation history. |
| [Testing strategy](docs/TESTING_STRATEGY.md) | Applicable evidence and platform limits. |
| [Decisions](docs/DECISIONS.md) | Approval chronology and supersessions. |
| [Repository instructions](AGENTS.md) / [Changelog](CHANGELOG.md) | Governance and sole cumulative change history. |

The shipped source route now runs `src/chronicle`. Stage 1A connects fresh
SQLite datasets, task/project creation and renaming, independent reassignment,
Start/Stop/atomic Switch, persisted active timers and audited active-start recovery.
Stage 2A adds Add timed work and Add date-only work for a selected task, with
callback-driven modal forms, immutable revision/deletion services and detached
history/revision readers. The Week starts selector persists any weekday.
Main shows own-task Today/This week; mini shows active or selected task Today.
One database worker supplies coordinated integer-microsecond accounting while Tk
continues events. Exact committed request retries precede stale checks; uncertain
acknowledgements retain the same request for reconciliation. Active-start correction
keeps its modal draft until a matching worker result: rejected inputs stay visible,
stale review requires reopening, and uncertain work offers exact Retry/Reconcile
and exceptional exit inside the editor. Queuing alone never closes it or means Saved.

Sleep and normal exit do not stop timers. Restart/crash restores committed active
identity/start. Impossible observations show unavailable values and a clock/start
warning; explicit correction never guesses DST or discards the timer. Unknown
storage outcomes are not reported as failed writes. Shutdown drains accepted work;
an idle unverified operation offers Retry/Reconcile or default-cancel exceptional
exit explaining possible commitment and loss of volatile retry inputs.

Stage 1A is independently accepted at `897aec2c0d57b6d4aa5c0c5109f55270a4bb1968`.
Stage 1B portable interruption/ownership and cleanup work is independently accepted
at `1e84a043c1c055aced9b8c4b000ef766bbf6d178`. Stage 1C simplifies the runtime to
standard sqlite3 DELETE/EXTRA and direct Python execution, retiring executable
build tooling. Stage 1 remains **In Progress** pending independent functional
adjudication, not complete MVP/pilot. Native Windows source/NTFS/Tk and actual
suspend/resume evidence remain deployment/pilot qualifications; they do not
permanently block later Stage 2 development.
Stage 0 was independently accepted at `a24aca706740b7e02cc1f856baa194042785bbcb`. Active work is
`feature/chronicle-rewrite`; the old feature branch/history is preserved.

## Run from source (repo root)

Use Python 3.11+ with built-in SQLite 3.37.0+ and Tcl/Tk. Check the actual modules,
then install the sole external runtime dependency in a permitted environment:

```powershell
python -c "import sys,sqlite3,tkinter; print(sys.version); print(sqlite3.sqlite_version); print(tkinter.TkVersion)"
python -m pip install --only-binary=:all: tzdata==2026.5
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh --timezone America/Chicago --create
```

Reopen the same dataset without creating it:

```powershell
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh
```

The root launcher supplies the src path; no editable install, wheel build or
compiler is required. The PowerShell helper accepts `-DataDir`, `-Timezone` and
`-Create`. No implicit data directory or legacy-runtime fallback exists.

## Data layout

An explicitly selected local directory contains `chronicle.sqlite3`,
`.chronicle.lock` and SQLite's temporary rollback journal during writes. Lock
existence is not ownership. A live OS-held lock excludes a second application owner. Create refuses
unknown nonempty or partial directories; open refuses unsupported datasets and
never creates a database accidentally. Nothing discovers/imports/deletes the old
`~/.task_timer_data` directory. Exact production paths/cutover remain Open.

SQLite is the standard Python `sqlite3` module, worker-owned and explicitly
transactional: **DELETE / synchronous=EXTRA (3) / foreign_keys=ON (1)**, with STRICT
tables requiring SQLite 3.37.0+. Startup verifies effective settings and records
Python/SQLite versions, source ID and compile options. The obsolete WAL-reset
version restriction is removed. Old development profiles refuse without automatic
conversion or deletion; no production SQLite migration is needed. Offline IANA
rules come from `tzdata==2026.5`; the dataset zone cannot be changed by this UI.

Do not copy a live database as a backup. Supported backup/restore and future
rewritten-data upgrades belong to Stage 4; unknown schemas refuse rather than
being reconstructed. See [RUNNING.md](RUNNING.md) for concise setup, optional venv,
source launch, troubleshooting and native Windows source validation. Initial pip
installation needs internet or an approved local wheel source and available IT
permission; ordinary Chronicle operation is offline and never installs packages.

## Selected core and sequence

Stage 2 is **In Progress**. Stage 2A connects genuine manual intervals and
endpoint-free date-only amounts to the worker and main/mini Actual. Date-only
H:MM work stays wholly on its declared date, including future dates. Timed entry
uses separate local dates/minutes and explicit repeated-time choices; its end
cannot exceed the accepted submission observation. Forms start with local dates
and blank clock/duration fields; validation retains drafts and uncertain outcomes
retain exact requests. No automatic overlap correction is performed.

Correction/deletion services preserve earlier revisions and entry UUIDs; unchanged
and comment-only edits write nothing. Task History reads include daily portions
with complete identities/endpoints, and revision details retain deleted work.
These are backend foundations: Stage 2B's modal History/inline editing and deletion
UI remain pending. Week start is configurable, initially Sunday. Main/mini and
Current week history reads use committed metadata, with no historical-work rewrite.
No Reset controls/counters or synthetic work are added.

Stage 3 must deliver frozen Timesheet Preview/Save/recovery **and core POL-R**:
full-task/week upward quarter rounding, deterministic daily distribution, immutable
absolute whole/checked/manual confirmation, Unknown versus zero, daily/weekly
reconciliation and required reminders. Exact Actual, displayed hundredths and
quarter units remain distinct. The single algorithm lives in the export contract;
there is no duplicate timer-display rounding implementation. External redistribution
and worked-day zero-entry rules need validation before affected official reporting.

Stages 4–5 stabilize and pilot the complete core; Stage 6 contains optional
allocations/conveniences. A timer-only foundation is not core signoff.

## Historical legacy implementation

`src/task_timer` and its meaningful tests remain unshipped engineering evidence.
The old source contains JSONL replay/snapshots, mixed History and frozen Timesheet,
legacy backup/export services and hierarchical conveniences. It is not imported by
the replacement or included in its package. Its bounded Phase 2 acceptance remains
historical, not SQLite qualification or a compatibility promise. Detailed former
source contracts remain in Design Notes; they are not current launcher instructions.

## Qualification

No executable bundle or builder is part of the supported workflow. Linux tests do
not establish native Windows/NTFS, actual suspend/resume, hardware power-loss or
release qualification. Final paths/cutover remain Open; the full core is not complete.
