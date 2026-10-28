# Chronicle

A small local Python + Tkinter/ttk task timer with **explicit absolute POL-R
reconciliation**. SQLite is the sole replacement authority.

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
Stage 2B connects Work History for the selected task: Current week/Custom/All,
draft-only inline calendars, session date direction, complete-entry inline editing,
confirmed deletion and immutable revision/deleted-entry details. One modal owner
blocks main/mini input while timers and worker delivery continue.
Timesheet / POL-R opens one modal preview/save workflow: This week/Last week/Custom,
All or explicit task UUIDs (including deleted tasks), draft-only calendars and
explicit Preview/Refresh. Actual HH:MM/decimal and suggested quarter-hour amounts
are separate, with complete-week target/adjustment context for partial views.
Preview writes no evidence or files. Save freezes the chosen original destination,
registers the reviewed candidate, then publishes and verifies its exact bytes.
Retry Save, Save Copy As, Check File Status and Saved Reports reuse registered
evidence. Conflicting regular files require separate default-No Overwrite consent;
ordinary Save never overwrites. The same modal window provides Review POL-R
Confirmation, Manual POL-R Confirmation and Confirmation History. Explicit checked
source cells use frozen suggestions, positive-only defaults include already-equal
values, zero requires explicit choice, and selected stale conflicts need individual
acknowledgement. Confirmed amounts are absolute quarter counts, separate from Actual.
Unknown is distinct from confirmed zero. Reconciliation shows current task/day
Actual, Suggested and Confirmed, signed Delta/gap, coverage and full-week summaries.
Partial Custom views retain complete-week rounding context. Compare a loaded report
without rewriting it; Copy Suggested copies the absolute quarter amount, not Delta.
The main banner checks previous week every used local day and current week Monday/
Friday. Open Timesheet navigates to reconciliation; explicit Dismiss for today
survives same-day restart and changes no work or confirmation. Recheck POL-R is
available after read failures. No external POL-R verification is claimed.
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
build tooling. Stage 1 functionality is independently accepted, not complete
MVP/pilot. Stage 2A is independently accepted at
`7bc1bce2894fd5d4ccddbcedfd7ae0f4e7c1323f`. Native Windows source/NTFS/Tk and actual
suspend/resume evidence remain deployment/pilot qualifications; they do not
permanently block later Stage 2 development.
Stage 0 was independently accepted at `a24aca706740b7e02cc1f856baa194042785bbcb`. Active work is
`feature/chronicle-rewrite`; the old feature branch/history is preserved.

## Approved hierarchy target — not yet implemented

The later approved target restores tree-oriented main/mini controls and supports
Project → Task → Subtask → Sub-subtask, leaf-only new time, reversible archive,
soft deletion/controlled restore and reusable nested templates. Individual remains
direct task Actual; Cumulative adds descendants exactly once for presentation.
POL-R stays task/day based; neither rollups nor project grouping add work or change
frozen evidence. Current source still has flat tasks and its existing main/mini
controls; no hierarchy/lifecycle/template workflow is delivered by this design.

Approved lifecycle defaults make Unassigned a virtual group with the same depth,
New Task without selection an Unassigned root, and hiding inherited from selected
node archive/deletion while independent descendant states survive. Restore needs
eligible ancestry; effectively archived branches cannot move. Templates are
soft-deleted/restorable with unique active trim/casefold names; task duplicates
remain valid. Keep Mini Open defaults Off/session-local; Show Main retains mini
only when On, and mini never takes focus/grabs from modals. Sort A-Z is initially
session-local.

Separate Permanent Delete is selected only through Deleted Items for unused
soft-deleted projects/tasks and eligible complete branches. Any historical work,
frozen/reporting/confirmation dependency or protected descendant blocks it.
Eligible deletion requires dependency preview, warning, typed confirmation and
transactional recheck. The proposed administrative-receipt/tombstone boundary
needs independent review before implementation; there is no automatic purge or
secure-erasure promise, and existing backups/copies remain unchanged.

Implementation will start with a distinctly identified fresh SQLite schema and
fresh data, **without v1 migration, compatibility mode or legacy import**. Old files
remain protected and may refuse; nothing automatically deletes or recreates them.
Exact DDL is proposed for separate review. See
[selected behavior](docs/TIMESHEET_REQUIREMENTS.md#approved-hierarchy-target-and-fresh-data-boundary),
[proposed foundation](docs/ARCHITECTURE.md#proposed-fresh-hierarchy-foundation) and
[bounded packages A–F](docs/ROADMAP.md#hierarchy-target--bounded-packages-a-f).
Stage 4 remains IN PROGRESS, Stage 5 NOT STARTED; native qualification, external
reporting and installation/cutover gates remain separate.

## Run from source (repo root)

Use Python 3.11+ with built-in SQLite 3.37.0+ and Tcl/Tk. Check the actual modules,
then install the sole external runtime dependency in a permitted environment:

```powershell
python -c "import sys,sqlite3,tkinter; print(sys.version); print(sqlite3.sqlite_version); print(tkinter.TkVersion)"
python -m pip install --only-binary=:all: tzdata==2026.5
python run_chronicle.py
# Optional Windows convenience:
.\scripts\run.ps1
```

First launch offers **Welcome to Chronicle**: choose a local dataset folder and a
readable timezone, then **Create and Open**, or choose **Open Existing Dataset**.
Nothing is created by displaying or canceling setup. Later zero-argument launches
open the remembered dataset normally, never implicitly recreating missing data.
Windows suggests `%LOCALAPPDATA%\Chronicle\Data` for explicit source-mode opt-in;
it is not an installation/cutover decision. See [startup details](RUNNING.md#ordinary-startup-and-first-run-setup)
for preference safety, Advanced / Other zones and refusal behavior.

Advanced engineering creation remains explicit:

```powershell
python run_chronicle.py --data-dir C:\Chronicle-test\fresh --timezone America/Chicago --create
```

Reopen the same dataset without creating it:

```powershell
python .\run_chronicle.py --data-dir C:\Chronicle-test\fresh
```

The root launcher supplies the src path; no editable install, wheel build or
compiler is required. The PowerShell helper accepts `-DataDir`, `-Timezone` and
`-Create`, and accepts no arguments for the same setup/reopen workflow. Explicit
CLI paths do not change the remembered selection. No legacy-runtime fallback or
legacy-data discovery exists. Native first-run GUI qualification remains required.

## Data layout

The selected local dataset directory contains `chronicle.sqlite3`,
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

Backup Chronicle creates a consistent worker-owned SQLite image at an explicit
new external path. Independent schema/evidence/full-integrity and final-byte
verification are required; existing files are never overwritten. Verify with
`python run_chronicle.py --verify-backup BACKUP_PATH`; cold restore with
`python run_chronicle.py --restore-from BACKUP_PATH --data-dir NEW_DATA_DIR`, then
launch normally with that directory. Restore does not start Tk and accepts only
a previously nonexistent directory. Original data remains untouched; do not run
original/clone as competing authorities. No live-file copying or in-place restore.
Stage 4A is independently accepted under the later Stage 4B GO instruction;
Stage 4B portable reliability is independently accepted under the later Stage 4C
GO. Stage 4C adds `python run_chronicle.py --inspect-dataset DATA_DIR`: close other
sessions first. This cold read-only command classifies current/unsupported versions,
layout, foreign identity, profile and unsafe/unavailable data without creating a
lock or starting Tk/worker. Healthy current data passes complete independent
validation; all other cases refuse ordinary startup. Schema remains version 1,
with no automatic upgrade, downgrade or repair. Stage 4C inspection, protected
refusal and bounded owned SQLite-native rollback recovery are independently
accepted for functional development.
Any hypothetical future data-preserving transformation needs separate approval;
the hierarchy target instead starts fresh, with no migration. Unknown schemas
refuse rather than being reconstructed. See [RUNNING.md](RUNNING.md) for concise setup, optional venv,
source launch, troubleshooting and native Windows source validation. Initial pip
installation needs internet or an approved local wheel source and available IT
permission; ordinary Chronicle operation is offline and never installs packages.

## Selected core and sequence

Stage 2 recording is **independently accepted** at
`adc09ba0935e8718c4ad2101057af9c6022074cc` under the later Stage 3A approval.
Stage 2A connects genuine manual intervals and
endpoint-free date-only amounts to the worker and main/mini Actual. Date-only
H:MM work stays wholly on its declared date, including future dates. Timed entry
uses separate local dates/minutes and explicit repeated-time choices; its end
cannot exceed the accepted submission observation. Forms start with local dates
and blank clock/duration fields; validation retains drafts and uncertain outcomes
retain exact requests. No automatic overlap correction is performed.

Correction/deletion services preserve earlier revisions and entry UUIDs; unchanged
and comment-only edits write nothing. Task History reads include daily portions
with complete identities/endpoints, and revision details retain deleted work.
Stage 2B connects those services through modal Work History with inline editing,
whole-entry Delete confirmation and read-only revision/deletion navigation.
Applied periods, unapplied Custom drafts and session sorting survive verified
edits; stale/unverified results retain their reviewed draft/exact request.
Stage 2 functional acceptance does not complete core POL-R. Week start is
configurable, initially Sunday. Main/mini and
Current week history reads use committed metadata, with no historical-work rewrite.
No Reset controls/counters or synthetic work are added.

Stage 3 is functionally accepted under the later explicit Stage 4A GO instruction.
Stage 4A backup/cold restore is independently accepted by the later Stage 4B approval.
Stage 4B portable operational qualification is independently accepted by the later
Stage 4C GO. Stage 4C is independently accepted for functional development;
Stage 4 remains IN PROGRESS and Stage 5 is NOT STARTED. Unit A's provisional
filesystem compatibility repair is accepted for portable development. Unit B's
collector and evidence-safety repair are accepted for limited native MetadataProbe
use; Windows qualification is not complete. The accepted integration coverage
audit found no material missing portable cross-boundary coverage and warrants no
new portable integration test. See [acceptance provenance](docs/DECISIONS.md#stage-4c-and-portable-tooling-acceptance).
Stage 3A connected frozen Preview, exact weekly suggestions
and immutable SQLite registration/recovery are independently accepted at
`d1e775c33982f109337ec237e3c78e8dc7b56f2e`. Stage 3B protected file Save/status and
Saved Reports recovery are independently accepted at
`76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`. Stage 3C is independently accepted for functional development under the later
Stage 3D GO instruction. Later Stage 4A approval records Stage 3 functional
acceptance, not release or pilot qualification. Registration stores
the reviewed labels, full-week basis, scoped cells
and exact UTF-8 text/digest atomically with its request receipt; later work cannot
rewrite them. Registered reports remain recoverable after restart without a retained
window, current Actual or a later renderer. File status is freshly inspected, never
persisted; alternate copy paths do not rewrite the original destination.
Three new SQLite tables retain immutable absolute batches/cells and latest current
references. Exact requests, complete frozen source coverage and selected reviewed
priors are transactionally validated; uncertain commits reconcile the same Request.
Confirmation never changes work, exports or files. Current reconciliation and
weekly summaries are derived reads. Dismissal stores only one nullable local date
in metadata through the existing atomic Request/receipt boundary; reads and ticks
never persist reconciliation truth.
Exact Actual, displayed hundredths and quarter units remain distinct. The single algorithm lives in the export contract;
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
