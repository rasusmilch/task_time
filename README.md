# Chronicle (tkinter)

A local-only Windows-friendly desktop task time tracker built with Python + tkinter.

## Overview

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

The service now connects accounting and rendering through
`generate_date_range_timesheet()`. `save_date_range_timesheet()` optionally writes
the complete report to private same-directory staging, then atomically publishes
a caller-chosen **new** UTF-8 file with a no-overwrite hard link. Existing
destinations are protected, and cleanup never deletes the final path. Filesystems
without hard-link support fail clearly without a direct-write fallback. Both use
explicit inclusive work dates and a fixed aware cutoff;
neither submits time, creates checkpoints, resets counters, or changes timers.
These APIs remain separate from the production UI and legacy export workflow.
See the [service workflow](DESIGN_NOTES.md#date-range-timesheet-service-staged).

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
