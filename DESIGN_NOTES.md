# Design Notes

## Architecture

The app uses an event-sourced model:

1. **Append-only active event log** (`active_events.jsonl`) as authoritative current segment.
2. **Archived immutable segments** under `archives/`.
3. **Manifest/index** (`log_manifest.json`) tracking segment sequence and metadata.
4. **Derived snapshot** (`state_snapshot.json`) for fast startup only.

The complete event stream across archived + active segments is the source of truth.

## Project/task service foundation

`AppState.projects` and `AppState.tasks` are separate UUID-keyed collections.
`ProjectState` stores only `project_id`, `name`, optional notes, and creation/update
timestamps. It has no intervals, timer state, reset boundary, or elapsed counters.
`TaskState.project_id` is optional; each task continues to own its intervals and
recorded time independently. Names are display labels, not identity or matching
keys, and duplicate project or task names do not merge records.

Implemented service operations:

- `create_project(name, notes="")`, `list_projects()`.
- `update_project(project_id, *, name=None, notes=None)` and
  `rename_project(project_id, name)`.
- `create_task(name, notes, tags=None, *, project_id=None)` creates an independent
  task, optionally assigned to an existing project.
- `assign_task_to_project(task_id, project_id)` assigns or moves just that task;
  `None` removes membership. `unassign_task_from_project(task_id)` is the explicit
  unassignment operation. Unchanged updates/membership are no-ops.

Project updates affect project metadata only. Membership changes preserve task
UUIDs, intervals, running starts, tags, notes, and all earlier event evidence.
There are no persisted project roll-up totals; derived project reporting remains
future work. Notes use the existing single-line, 160-character convention.

The existing event envelope and durable storage are reused:

| Event | Envelope `task_id` | Payload |
| --- | --- | --- |
| `project_created` | `__app__` | `project_id`, `name`, optional `notes` |
| `project_updated` | `__app__` | `project_id`, at least one of `name`/`notes` |
| `task_project_assigned` | task UUID | `project_id` (project UUID or `null`) |

New independent `task_created` events include `project_id` (possibly `null`) and
`parent_task_id: null`. Project/membership events and this new creation shape are
validated before append and again during replay: required fields, field types,
non-empty names, canonical creation UUIDs, ID collisions, and references must be
valid. Malformed events raise `ValueError`; they are not silently applied or
repaired. Legacy task events without `project_id` retain their existing replay
path. Snapshots include projects and membership, but are derived: startup and
explicit rebuild replay archived plus active events, preserving equal-timestamp
read order. Storage flush/fsync, rotation, and backup architecture are unchanged.

Task-only timer, manual-time, correction, reset, and deletion operations reject
project or unknown task IDs before mutation. Starting a task validates the target
before stopping valid running work. Bulk reset/delete selection validates all
requested IDs before touching any task. Valid task switching still enforces the
one-running-task rule. Historical corrections to existing deleted task records
retain the previous behavior; deleted tasks cannot be started or reassigned.

This foundation does not change the production UI, export calculations,
submission/checkpoint semantics, report rendering, templates, or launcher path.
Legacy `parent_task_id`, `create_subtask`, and `move_task` remain for the current
workflow; project assignment uses the separate operation above and does not
implicitly move legacy descendants. No migration or conversion events exist.

Fresh-start cutover will activate a separate data directory only after project
navigation and timesheet exports are usable. Until then the launcher still uses
`~/.task_timer_data`; it must not be used to experiment with the new service
operations on existing user data. A service initialized with an isolated empty
directory does not import tasks, submissions, projects, or templates from any
other directory. No external-system integration or task numbers are introduced.

## Event schema

Each event line is JSON with:

- `schema_version`
- `event_id`
- `timestamp_utc` (ISO-8601 with `Z`)
- `local_timezone`
- `task_id`
- `event_type`
- `payload`

Corrections are represented via explicit events:

- `manual_interval_added`
- `interval_edited`
- `interval_deleted`

## Reset semantics

`reset` creates a logical totals boundary (`last_reset_utc`) for each task:

- Current elapsed/day/week totals ignore prior intervals.
- Historical events remain visible in exports.

## Export + reset flow

- Export file is generated first.
- User is asked if timers should be reset.
- If **No**: only `exported` event is recorded.
- If **Yes**: `exported` plus `reset` events for all non-deleted tasks are recorded.

Default reset scope is all non-deleted tasks.

## Time handling

- Internal event timestamps are UTC-aware datetimes.
- Display/grouping uses local timezone from the running system.
- Day/week totals split intervals at local boundaries.
- Week start is Sunday.

## Durability

- Every state-changing action appends + flushes + fsyncs event log.
- Snapshot and manifest writes are atomic temp-write + replace.
- UI timer refresh never writes files.

## Backups

- Managed backups are stored under `~/.task_timer_data/backups` in GFS-style buckets:
  - `sons/`
  - `fathers/`
  - `grandfathers/`
- `backup_settings.json` is auto-created with defaults on first run and is user-editable from **File → Backup Settings**.
- Retention trims each bucket to configured keep counts after backup creation.
- Restore always takes a forced safety backup before data replacement.
- Other risky-operation safety backups are controlled by `auto_backup_before_risky_operations`.
- Optional app-start auto backups are controlled by:
  - `auto_backup_on_app_start`
  - `auto_backup_min_interval_minutes`

## Window snap behavior on Windows

Windows Aero Snap behavior is owned by the operating system. The app reduces accidental top-edge maximize by making the main and mini windows non-maximizable/non-resizable while keeping normal title bars and drag behavior. If a future version needs fully resizable main windows while still blocking only top-edge snap maximize, that will require deeper Win32 style handling or custom window chrome tradeoffs.

## Main window task list behavior

- The main Chronicle window displays tasks and subtasks with a `ttk.Treeview` hierarchy (parent rows with nested child rows).
- Main window actions (`Start/Stop`, `Reset`, `Delete`, `Edit Task`, `Edit Timeline`) operate on the currently selected task row.
- Tree interactions support quick toggles: double-click, `Enter`, and `Space` all trigger selected task `Start/Stop`.
- Parent expansion/collapse state is tracked during runtime and parents with running subtasks are automatically kept expanded.
