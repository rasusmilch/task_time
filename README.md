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

The shipped source/build route now runs `src/chronicle`. Stage 1A connects fresh
SQLite datasets, task/project creation and renaming, independent reassignment,
Start/Stop/atomic Switch, persisted active timers and audited active-start recovery.
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
Stage 1B adds killed-process transaction/reopen tests, separate-process ownership,
startup/cleanup diagnostics and controlled Windows build inputs. Failed startup
cleanup remains worker-owned until closure; cleanup-only shutdown cannot resume
normal mutations. Stage 1 remains **In Progress**, not complete MVP/pilot: native
Windows source/NTFS/Tk/onedir and actual suspend/resume qualification are pending.
Stage 0 was independently accepted at `a24aca706740b7e02cc1f856baa194042785bbcb`. Active work is
`feature/chronicle-rewrite`; the old feature branch/history is preserved.

## Run from source (repo root)

Install the declared dependency into a supported Python 3.11+ environment:

```powershell
python -m pip install -e .
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh --timezone America/Chicago --create
```

Reopen the same dataset without creating it:

```powershell
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh
```

The root launcher supplies the src path. Module execution is `python -m chronicle`
after installation. The PowerShell helper accepts `-DataDir`, `-Timezone` and
`-Create`. No implicit data directory or legacy-runtime fallback exists.

## Data layout

An explicitly selected local directory contains `chronicle.sqlite3`, SQLite's
WAL/SHM sidecars when applicable, and `.chronicle.lock`. Lock existence is not
ownership. A live OS-held lock excludes a second application owner. Create refuses
unknown nonempty or partial directories; open refuses unsupported datasets and
never creates a database accidentally. Nothing discovers/imports/deletes the old
`~/.task_timer_data` directory. Exact production paths/cutover remain Open.

SQLite is worker-owned, explicit-transaction, WAL/FULL/foreign-key/STRICT. Runtime
checks require both STRICT support and a build containing the WAL-reset fix:
3.51.3 or later, excluding withdrawn 3.52.0. The available operational tests exercise
Python 3.12.14 / SQLite 3.53.1 on Linux, not native Windows qualification or universal
power-loss safety. Offline IANA rules come from pinned bundled `tzdata`; the dataset zone cannot be changed by this UI.

Do not copy only the main file of a live WAL database as a backup. Supported backup,
restore and upgrade workflows belong to later operational/stabilization work;
Stage 1A refuses unknown schema versions rather than attempting upgrades.

## Selected core and sequence

Stage 2 adds genuine manual intervals and endpoint-free dated amounts, immutable
correction/deletion revisions, mixed History with inline whole-entry editing and
configurable weeks. None is exposed by this timer slice. Sunday is initially used,
not a permanent week policy. No Reset controls/counters or synthetic work are added.

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

## Windows executable packaging

See [BUILDING.md](BUILDING.md) for the aligned replacement onedir route and explicit
engineering data arguments. Native Windows/NTFS, PowerShell, packaged execution,
power-loss and release qualification are not established by Linux tests.
