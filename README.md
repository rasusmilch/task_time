# Chronicle (tkinter)

A local-only Windows-friendly desktop task time tracker built with Python + tkinter.

## Product authority and implementation status

The [approved replacement/POL-R product contract](docs/TIMESHEET_REQUIREMENTS.md)
owns selected target behavior and its Open, Deferred and Unverified boundaries.
Selected functionality is not automatically implemented.

| Status | What it means here |
| --- | --- |
| Approved target | Replacement workflow, configurable weeks, decimal-hour reporting and separate Actual/Exported/Confirmed POL-R reconciliation with snapshot-first evidence are selected; consult the contract for complete behavior. |
| Staged service capability | Independent projects/tasks, date-only replay, fixed Sunday-start mixed accounting, exact and decimal text renderers, exact file-only saving, immutable export-snapshot registration/replay and verified materialization of frozen evidence are independently callable. |
| Production still pending | Production export integration, file-status/recovery UI, replacement UI, new date-only writers, POL-R confirmations/reconciliation, configurable weeks, weekly allocations and installation cutover are not active. |

Current production still uses legacy parent/subtask interfaces, synthetic manual
duration intervals, timestamp checkpoints and legacy submission markers. This
staging does not select a permanent parallel legacy interface.
`save_date_range_timesheet()` still creates an exact-format file only, without
export-event evidence or POL-R confirmation. Separate snapshot-first operations
now register frozen decimal evidence and materialize verified copies. They are
not combined or connected to the production UI; saving never confirms POL-R entry.

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

- Persistent tasks with start/stop/reset/delete/edit-time controls.
- Event-sourced storage with append-only JSONL logs.
- Archived immutable segments + manifest + derived snapshot.
- Crash-safe behavior: each state-changing action appends and flushes an event immediately.
- One-running-task rule: starting a task auto-stops the currently running task.
- Resets are logical cut lines for *current* totals (history is preserved).
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
**not enabled in production time entry or totals yet**; the existing duration UI
still uses its legacy representation. A separate read-only service API now derives
mixed daily/weekly totals over explicit local-date windows; it is not connected
to production readers or exports. No public dated-duration writer, historical
migration, or data-directory cutover is included. See
[mixed accounting](DESIGN_NOTES.md#mixed-date-window-accounting-service-only)
for selection semantics and the explicit legacy synthetic-duration boundary.

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
`get_timesheet_export_snapshot()` and `list_timesheet_export_snapshots()` return
detached committed evidence, retained across replay and later work changes.
Preparation writes nothing; registration creates no external report, confirmation,
checkpoint or reset. A preferred destination is frozen metadata, not file status.
Registration alone does not establish a successfully exported file. See
[snapshot registration](DESIGN_NOTES.md#immutable-export-snapshot-registration-staged).

`materialize_timesheet_export(export_id, destination=None)` verifies the journal,
then writes only the frozen report bytes to an explicit path or the snapshot's
preferred path. New files use complete staging and exclusive hard-link publication;
existing regular files are accepted only if every byte and SHA-256 match.
Conflicts and symlinks are refused. Success follows complete destination
verification, with no new events, recalculation or timer changes. Retries reuse
the same evidence; alternative paths never change it. Verification is current at
the check, not permanent file status. No status/recovery UI or automatic missing-file
recovery is implemented. See [materialization](DESIGN_NOTES.md#verified-export-materialization-staged).

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
integration and POL-R confirmations are not yet implemented.

Export is plain text and includes:

- Header with generation timestamp and timezone.
- Current day/week range (Sunday-start week).
- Source segments used for export.
- Overall totals and per-task totals (including notes).
- Detailed chronological event/interval history, including resets and corrections.

## Subtask Templates

Subtask Templates are reusable groups of subtask definitions. Applying a template copies those definitions into a parent task as real subtasks. The created subtasks are independent and can be edited, timed, reset, deleted, and exported like any other subtask.

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
