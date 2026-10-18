# Chronicle (tkinter)

A local-only Windows-friendly desktop task time tracker built with Python + tkinter.

## Product authority and implementation status

The [approved replacement/POL-R product contract](docs/TIMESHEET_REQUIREMENTS.md)
owns selected target behavior and its Open, Deferred and Unverified boundaries.
Selected functionality is not automatically implemented.

| Status | What it means here |
| --- | --- |
| Approved target | Replacement workflow, configurable weeks, decimal-hour reporting and separate Actual/Exported/Confirmed POL-R reconciliation with snapshot-first evidence are selected; consult the contract for complete behavior. |
| Staged service capability | Independent projects/tasks, date-only replay, closed timed-correction preparation/registration, exact and decimal text renderers, exact file-only saving, export-snapshot registration/replay, verified materialization, read-only file status, confirmation-batch preparation/registration/replay, frozen-export proposal/selection preparation and daily POL-R reconciliation calculation are staged. |
| Connected calendar Actual | Main own-task Today/This week and mini Today use mixed accounting at one cutoff; application totals include retained deleted work. Failed calculations remain visibly unavailable until a successful refresh. Exports remain interval-only. |
| Connected read-only history | Main-panel and recursive task-editor Work History commands share the modal browser, originating-parent return and session-only sorting. Replacement editing remains pending. |
| Standalone frozen preview and Save | TimesheetPreviewFrame offers explicit This week/Last week/Custom preparation, independent All/Selected task scope including deleted work, and exact read-only frozen text. Draft changes/failures invalidate readiness. TimesheetSaveFrame composes locked same-event registration/materialization retries and protected explicit destinations, with a separate confirmed Overwrite action for stable regular-file content conflicts. Production routing and general recovery UI remain pending. |
| Production still pending | Production export integration, file-status/recovery UI, remaining replacement editing UI, new date-only writers, POL-R confirmation/reconciliation UI and weekly reconciliation summaries, configurable weeks, weekly allocations and installation cutover are not active. |

[Phase 2's bounded evidence and daily-reconciliation service gate](docs/ROADMAP.md#phase-2--pol-r-evidence-and-reconciliation)
is independently accepted as Complete under serialized dataset ownership;
capabilities remain staged and production/release qualification remains pending.

Current production retains parent/subtask interfaces, timestamp checkpoints and
legacy submission markers, alongside the read-only Work History replacement.
Retained mutation/accounting services still handle synthetic duration records;
Work History refuses applicable synthetic work rather than adapting it. There
is no parallel legacy history interface.
`save_date_range_timesheet()` still creates an exact-format file only, without
export-event evidence or POL-R confirmation. Separate snapshot-first operations
now register frozen decimal evidence and materialize verified copies. They are
combined only in the standalone component below, not connected to the production
UI; saving never confirms POL-R entry.
A [standalone timesheet preview](DESIGN_NOTES.md#frozen-timesheet-preview-standalone)
now prepares an unregistered frozen candidate without writes. It does not replace
shipped export routes or unblock dated writers. A
[standalone Save/retry component](DESIGN_NOTES.md#standalone-frozen-export-saveretry)
now composes that preview with the existing verified services; it adds no production
route or restart recovery UI.

See [repository instructions](AGENTS.md), [current technical design](DESIGN_NOTES.md)
and the [canonical changelog](CHANGELOG.md) for their respective authority scopes.
The [development roadmap](docs/ROADMAP.md) owns sequencing, dependencies and phase
completion gates.
The [testing strategy](docs/TESTING_STRATEGY.md) defines validation applicability,
evidence expectations and release-qualification boundaries.
The [decision history](docs/DECISIONS.md) preserves historical rationale,
provenance and supersessions.
The [export evidence contract](docs/EXPORT_EVIDENCE_CONTRACT.md) owns approved
decimal-hour, snapshot, file verification/recovery and confirmation semantics.

## Overview

The following describes the current production application.

- Persistent tasks with start/stop/delete/task-edit controls and read-only Work History.
- Event-sourced storage with append-only JSONL logs.
- Archived immutable segments + manifest + derived snapshot.
- Crash-safe behavior: each state-changing action appends and flushes an event immediately.
- One-running-task rule: starting a task auto-stops the currently running task.
- Task Reset commands and export-completion Reset choices are removed. Retained
  backend reset evidence and interval-only export clipping remain unchanged.
- Main task rows show own Today/This week Actual; mini-mode shows Today from the
  same observation. Application totals include deleted-task work. Failures show
  — inline and retain Start/Stop with normal refresh recovery.
- Export to human-readable text with totals and audit history.

## Project/task foundation (service only)

The service now keeps projects and tasks as separate domain objects. Projects
have UUIDs, names, notes, and creation/update timestamps; they cannot own time
intervals or operate timers. Tasks retain their own UUIDs and intervals, and can
optionally belong to a project. Unassigned tasks and duplicate task names are
valid. Assignment, reassignment, and project renaming never transfer or reset
recorded time.

This is a staged foundation: project navigation and production daily timesheet
export controls are **not available yet**. The existing UI, hierarchical exports,
submission markers, and launcher data path remain in use. Legacy task hierarchy
is retained for that existing workflow; no historical conversion is performed.

The eventual fresh-start project workflow will use a **separate data directory**
once it is usable. This change does not activate that directory, import historical
data, or migrate `~/.task_timer_data`. Service tests use isolated temporary data
directories. See [Design Notes](DESIGN_NOTES.md#projecttask-service-foundation)
for the implemented APIs and event contract.

The replay foundation also supports `DatedDurationRecord`: a separate task-owned
work date and duration amount with audit timestamps and append-only corrections
and deletion. These records have no start/stop timestamps. This support is
not enabled in production time entry yet. The legacy duration-entry UI has been
removed; replacement duration-entry UI remains pending. The read-only mixed
accounting API now supplies main/mini calendar Actual over explicit local-date
windows. Exports/submission readers remain interval-only, so dated writer
activation remains blocked on their separate integration. No public dated-duration
writer, historical migration, or data-directory cutover is included. See
[mixed accounting](DESIGN_NOTES.md#mixed-date-window-accounting)
for selection semantics and the explicit legacy synthetic-duration boundary.

`get_task_work_history()` separately returns detached mixed history for one task:
linked local-day interval segments and whole date-only amounts, with explicit
cutoff, inclusive dates or All history, and deterministic date/within-day ordering.
It ignores legacy resets and preserves underlying entry identity without writes.
See the [history service contract](DESIGN_NOTES.md#mixed-work-history-service).

The standalone [WorkHistoryFrame](DESIGN_NOTES.md#mixed-work-history-table)
renders supplied rows in their exact order, with minute clocks, endpoint dates and
repeated-hour offsets, completed-minute durations and ↔ linked-portion markers.
Selection highlights related visible portions without work mutations. Full precise
row metadata stays detached behind temporary widget handles; rendering errors are
visible rather than silently presenting incomplete results. It loads no services,
settings or clocks; the modal browser composes it for read-only history access.

The standalone [WorkHistoryBrowserFrame](DESIGN_NOTES.md#single-task-history-browser)
connects the reader/table with Current week, Custom and All periods, typed dates
and calendar pickers, Apply and explicit Refresh. It retains unapplied drafts and
last-successful period/as-of information on failure. Date-header sorting stably
reorders existing results without loading newer records or advancing the cutoff;
direction remains in memory. The caller supplies a clock and week start (initially
Sunday); this is not the configurable-week setting.
The [Selected replacement history](docs/TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history)
starts each application session newest-first and remembers successful direction
changes across subsequent task/dataset history openings only in that session.
The application-owned handoff adds no settings or preference files. The
[owned modal history window](DESIGN_NOTES.md#owned-modal-history-window)
now connects Work History in the main selected-task panel and recursive task
editors through one owner, preserving timers, session direction and origin drafts.
It rejects duplicate requests without refreshing or changing the original task,
validates the originating parent and safely returns grab/focus. Launch errors
appear inline at their origin with Tk diagnostics; browser load errors remain
inside the browser. This read-only replacement removes the old timeline UI and
its editing tools without compatibility fallbacks. Unsupported synthetic work
fails visibly; no migration or user-file/data-directory cutover occurs.
Replacement segment editing, creation/deletion, missed-stop tools and audit
remain pending. Task Reset controls and both export Reset branches are removed;
backend reset APIs, persisted evidence and interval-only exports are unchanged.
Main/mini calendar Actual is connected separately; production POL-R presentation
and remaining active-reader integration stay pending.

Pure [timed-input validation](DESIGN_NOTES.md#replacement-timed-input-validation-staged)
separately resolves minute-only clock inputs with independent start/end dates,
explicit repeated-time occurrences, nonexistent-time rejection and UTC elapsed
ordering. Replacement entry/editing/display is Selected as minute-only; this
module activates no editor, writer or display changes and alters no recorded
precision or billing-rounding rule. Existing production time helpers remain active.

The standalone staged [TimedIntervalInputFrame](DESIGN_NOTES.md#timed-interval-input-form-staged)
provides separate date/time fields, explicit occurrence choices with UTC offsets
and inline validation through those APIs. It supplies no saving or record access;
production record-editor integration and writer activation remain pending.
The old timeline input dialog is removed; the standalone form is not routed.

Separate staged [timed-correction APIs](DESIGN_NOTES.md#timed-interval-corrections-staged)
prepare and register one effective closed genuine interval replacement. Unchanged
saves write nothing; changed endpoints preserve the other endpoint's precision,
comments are optional, and stale priors reject. Frozen identities support verified
journal recovery/reuse without rolling back newer work or confirmations. Results
distinguish registered evidence from projection/snapshot failures. These services
are now consumed by a [standalone correction dialog](DESIGN_NOTES.md#standalone-timed-interval-correction-dialog-staged).
It authoritatively loads one closed record, preserves unchanged precision behind
minute controls, retains stale drafts and distinguishes unverified registration
from recorded corrections with refresh warnings. Retries keep the same event;
production correction routing remains pending; legacy mutation services are unchanged.

`build_timesheet_text()` separately renders those accounting results as a
plain-text timesheet with independent task rows, dated daily columns and weekly
totals grouped by current project. Project subtotals are informational and
non-additive; selected project subsets are labeled accordingly. Seconds and
fractional seconds are preserved. Scope and timezone labels come from the
accounting result; optional caller assertions must match. Full task names wrap
in bordered tables without truncation, and calendar-edge slots are explicitly
marked when no date can be represented. Bidirectional formatting controls use
reversible visible ASCII escapes; useful Unicode such as ZWJ/ZWNJ remains intact.
This renderer is independently callable and
**not wired into production export menus**. See the
[renderer contract](DESIGN_NOTES.md#independent-task-timesheet-renderer-staged)
for authoritative metadata, wrapping and partial-week behavior.

`build_decimal_timesheet_text()` is a separate pure replacement renderer using
the same accounting result and safe layout. It displays two-place decimal hours:
`seconds_to_decimal_hundredths()` rounds each task/day once with decimal
ROUND_HALF_UP, then displayed rollups sum integer hundredths. Three tasks with
60 seconds each display `0.02` each and total `0.06`, while Actual remains
180 seconds. Nonzero work may display `0.00` without changing its recorded amount.
See the [decimal renderer](DESIGN_NOTES.md#decimal-hour-timesheet-renderer-staged).
No snapshot evidence, file output or production integration is added by rendering.

The service now connects accounting and rendering through
`generate_date_range_timesheet()`, which continues using the exact renderer.
`save_date_range_timesheet()` optionally writes
the complete report to private same-directory staging, then atomically publishes
a caller-chosen **new** UTF-8 file with a no-overwrite hard link. Existing
destinations are protected, and cleanup never deletes the final path. Filesystems
without hard-link support fail clearly without a direct-write fallback. Both use
explicit inclusive work dates and a fixed aware cutoff;
neither submits time, creates checkpoints, resets counters, or changes timers.
These APIs remain separate from the production UI and legacy export workflow.
See the [service workflow](DESIGN_NOTES.md#date-range-timesheet-service-staged).

The separate `prepare_timesheet_export_snapshot()` freezes one calculation as
decimal text, task/day seconds and hundredths, original labels/request/metadata,
and a SHA-256 digest. `register_prepared_timesheet_export()` durably registers
that candidate in the existing journal with stable, idempotent export identity.
Recovery and exact-identity reuse require successful journal synchronization,
complete evidence revalidation and installation before return; readable bytes alone
are insufficient after failed flushing.
`get_timesheet_export_snapshot()` and `list_timesheet_export_snapshots()` return
detached committed evidence, retained across replay and later work changes.
Preparation writes nothing; registration creates no external report, confirmation,
checkpoint or reset. A preferred destination is frozen metadata, not file status.
Registration alone does not establish a successfully exported file. See
[snapshot registration](DESIGN_NOTES.md#immutable-export-snapshot-registration-staged).

`materialize_timesheet_export(export_id, destination=None, *, overwrite=False)` verifies the journal,
then writes only the frozen report bytes to an explicit path or the snapshot's
preferred path. New files use complete staging and exclusive hard-link publication;
matching regular files are reused only after full byte/SHA-256 verification.
Ordinary Save/Retry refuses conflicts. Explicit confirmed Overwrite may replace a
fully inspected stable regular-file conflict using owned staging and `os.replace`,
with a target identity/metadata recheck; dataset-tree paths and resolved aliases
are protected. Symlinks and uncertain inspections cannot authorize replacement.
This is bounded checking, not atomic compare-and-replace or concurrency safety. Success follows complete destination
verification, with no new events, recalculation or timer changes. Retries reuse
the same evidence; alternative paths never change it. Verification is current at
the check, not permanent file status. No general status/recovery UI or automatic missing-file
recovery is implemented. See [materialization](DESIGN_NOTES.md#verified-export-materialization-staged).

`evaluate_timesheet_export_file_status(export_id, destination=None)` strictly
validates registered evidence and returns PENDING, READY, MISSING, CONFLICT or
UNVERIFIABLE for the explicit destination or frozen preference. It performs no
writes and retains no status or alternative path. Every check is current; absence
does not establish whether publication previously occurred. See [file-status evaluation](DESIGN_NOTES.md#export-file-status-evaluation-staged).

Strict immutable POL-R batch validation/replay now derives latest absolute
task/day confirmations in memory. `get_effective_polr_confirmations()` returns
detached evidence-derived values; Unknown differs from confirmed zero.
`prepare_polr_confirmation_batch(cells, *, batch_id=None)` freezes explicit reviewed
cells without writes; `register_prepared_polr_confirmation_batch(prepared_event)`
validates current priors and durably registers the immutable batch. Exact retry
synchronizes journal files before reuse without reapplying old amounts. These
service APIs require serialized dataset ownership and never increase Actual.
Confirmation dialogs and production integration remain absent. See [confirmation replay](DESIGN_NOTES.md#immutable-pol-r-confirmation-replay-staged).

`propose_export_polr_confirmation(export_id)` returns frozen export cells with
reviewed prior identities and stale-conflict flags. The separate
`prepare_export_polr_confirmation_batch()` validates explicit selection and
cell-specific acknowledgements, defaulting to positive proposals without selecting
zero automatically. It prepares an event without registration; callers explicitly
register and retry that exact event. These APIs review journal evidence, not report
file readiness. Acknowledgement dialogs and production integration remain pending.
See [proposal preparation](DESIGN_NOTES.md#export-confirmation-proposals-and-selected-preparation-staged).

`calculate_polr_reconciliation()` takes the same dates, fixed cutoff and selection
arguments as `calculate_date_window()`. It returns detached raw `actual` and daily
`cells` containing Actual/Confirmed/Delta/Enter hundredths and batch identity.
Unknown Confirmed/Delta are `None`; confirmed zero stays distinct. Enter is the
absolute Actual replacement amount. Each call strictly validates journal evidence
without writes or cache refresh. Reconciliation UI, weekly summaries and production
integration remain pending. See [daily calculation](DESIGN_NOTES.md#daily-pol-r-reconciliation-calculation-staged).

## Run from source (repo root)

From the repository root, run:

```powershell
python .\run_chronicle.py
```

This works directly with the `src/` layout and does **not** require setting `PYTHONPATH`.

Optional for development workflows:

```powershell
python -m pip install -e .
```

After an editable install, module execution also works:

```bash
python -m task_timer.main
```

PowerShell helper (uses `.venv\Scripts\python.exe` when present):

```powershell
./scripts/run.ps1
```

## Data layout

By default data is stored in `~/.task_timer_data`:

- `active_events.jsonl`: append-only active segment.
- `archives/*.jsonl`: immutable sealed segments.
- `state_snapshot.json`: derived state for fast startup.
- `log_manifest.json`: segment index/metadata.
- `subtask_templates.json`: reusable subtask template definitions.
- `backup_settings.json`: tunable GFS backup retention values.
- `backups/sons|fathers|grandfathers`: managed zip backups.

Journal initialization is allowed only for a nonexistent data path or a genuinely
empty directory. A nonempty directory missing `active_events.jsonl` or
`log_manifest.json` is refused without replacement files or changes to surviving
data. Existing empty journals remain valid. Strict loading checks journal contents
separately; startup does not recover missing files from snapshots or backups.
Backup restoration is explicit. See [storage behavior](DESIGN_NOTES.md#architecture).

Default backup settings:

- `son_keep_count: 14`
- `father_keep_count: 8`
- `grandfather_keep_count: 12`
- `auto_backup_before_risky_operations: true`
- `auto_backup_on_app_start: false`
- `auto_backup_min_interval_minutes: 60`

`backup_settings.json` is created automatically on first app start (or first backup manager use) and is written as human-readable JSON.

Backup settings can be edited in-app via **File → Backup Settings**.

## Backup behavior

- **Manual backup** (`File → Create Backup Now`) always creates a backup immediately.
- Backups include `subtask_templates.json`, so template definitions are captured with normal task data.
- **Retention** runs after backup creation and keeps only the configured counts:
  - sons: newest N son backups
  - fathers: newest N father backups
  - grandfathers: newest N grandfather backups
- **Risky-operation safety backups**:
  - Restore always creates a safety backup first (forced).
  - Other risky operations obey `auto_backup_before_risky_operations`:
    - checkpoint reopen/void
    - export
    - manual interval edit/delete
    - rebuild snapshot from journal
- **Restore** restores subtask templates from the selected backup, including `subtask_templates.json`.
- **Automatic backup on app start**:
  - Controlled by `auto_backup_on_app_start`.
  - Creates a son backup with reason `automatic backup on app start`.
  - Respects `auto_backup_min_interval_minutes` using the newest managed backup timestamp.

## Rotation and archives

- Active log rotates when size/event thresholds are reached.
- Rotation seals current active segment into `archives/` and records metadata in manifest.
- Archived segments are never rewritten.
- Full rebuild scans archives + active segment.

## Export format

This describes the active legacy exporter. The selected replacement workflow is
owned by the [product contract](docs/TIMESHEET_REQUIREMENTS.md). Separate export
evidence registration and verified materialization are staged; production export
integration and POL-R confirmation UI are not yet implemented.

Export is plain text and includes:

- Header with generation timestamp and timezone.
- Current day/week range (Sunday-start week).
- Source segments used for export.
- Overall totals and per-task totals (including notes).
- Detailed chronological event/interval history, including resets and corrections.

## Subtask Templates

Subtask Templates are reusable groups of subtask definitions. Applying a template copies those definitions into a parent task as real subtasks. The created subtasks are independent and can be edited, timed, deleted, and exported like any other subtask.

- Manage templates in **Tools → Manage Subtask Templates**.
- Templates are definitions only; they are not timed/running work items by themselves.
- Applying a template creates real subtasks under the selected parent task.
- Editing or deleting a template does not change existing subtasks that were already created from it.
- Duplicate subtask names are skipped when applying templates to avoid duplicate child tasks under the same parent.
- Template item order is preserved when creating subtasks.
- Templates are included in backups and restored with backup restore.

## Assumptions / limitations

- Notes are single-line and capped at **160 characters**.
- UI is intentionally utilitarian.
- This is a local desktop app; no network/cloud/account features.

## Windows executable packaging

For internal Windows executable packaging with PyInstaller (default `onedir` output), see [`BUILDING.md`](BUILDING.md).

Distribution guidance: ship the entire `dist\Chronicle\` folder and run `Chronicle.exe` from that folder. User data remains external in `~/.task_timer_data`.
