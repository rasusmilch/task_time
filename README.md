# Chronicle

A small local Python + Tkinter/ttk application for task-time recording **and
explicit absolute POL-R reconciliation**. The selected clean rewrite uses
transactional SQLite. Confirmation, reconciliation, summaries and reminders are
core requirements before pilot; optional allocations are separate.

## Product authority and implementation status

| Owner | Scope |
| --- | --- |
| [Requirements](docs/TIMESHEET_REQUIREMENTS.md) | Selected product behavior, core/optional scope and Open decisions. |
| [Target architecture](docs/ARCHITECTURE.md) | Single Tkinter/SQLite technical owner: exact units, relational records/revisions, atomic requests, worker/Tk lifecycle. |
| [Export/POL-R contract](docs/EXPORT_EVIDENCE_CONTRACT.md) | Frozen reports, rounding, protective publication/confirmed overwrite and absolute confirmations. |
| [Roadmap](docs/ROADMAP.md) | Active rewrite Stages 0–6 and gates. |
| [Design Notes](DESIGN_NOTES.md) | Actual legacy Tkinter/JSONL source and limitations, not rewrite instructions. |
| [Testing strategy](docs/TESTING_STRATEGY.md) | Proportional evidence and platform/release limitations. |
| [Decisions](docs/DECISIONS.md) | Historical approvals and explicit supersessions. |
| [Repository instructions](AGENTS.md) / [Changelog](CHANGELOG.md) | Governance and sole cumulative change history. |

**Selected is not implemented.** No SQLite runtime, worker bridge or inline History
editor is delivered by the documentation change. Tkinter is final, not a frontend
pending Qt/PySide6. The rewrite has no migration/import/old-schema/API or parallel
runtime requirement. Existing user files stay protected; exact release paths,
installation/cutover and cleanup remain Open.

## Selected core and sequence

- Independent UUID tasks, optional non-time-bearing projects, Start/Stop/atomic
  Switch and persisted active timer; own Today/This week plus mini Today.
- Genuine intervals and endpoint-free dated amounts, stable work-entry revisions,
  correction/deletion details, exact local-day accounting, configurable week start
  (Sunday initially), mixed History and inline whole-entry editing.
- Explicit frozen This week/Last week/Custom preview, independent task selection
  including retained deleted work, exact saved bytes and same-report recovery.
- Whole/checked/manual absolute POL-R confirmation, explicit zero versus Unknown,
  stale-prior rejection, daily Actual/Confirmed/Delta/Enter, weekly summaries and
  required reminders. Save never confirms, resets timers or dismisses reminders.

Mandatory: Actual 5.00, Confirmed 3.00 → Delta +2.00, Enter 5.00. Confirm 5.00 →
Delta 0.00. Correct Actual to 2.50 against 3.00 → Delta -0.50, Enter 2.50, with old
exports/confirmations unchanged. Unknown gives Unverified Delta; Enter is whole
current Actual. Displayed hundredths round task/day once; rollups sum cells.

Stage 1 is a working timer **engineering slice, not complete MVP/pilot**. Stage 2
completes recording/History; Stage 3 completes frozen Timesheet **and POL-R**;
Stage 4 stabilizes; Stage 5 pilots the complete reporting-week workflow. Stage 6
is optional allocations/conveniences, never deferred core reconciliation.
After independent architecture acceptance, next runtime work is a bounded Stage 1
read-only implementation plan, then separately approved execution on an authorized
branch from the accepted architecture commit. This task creates no such branch.

## Current legacy implementation

The commands and layout below run/build the **existing JSONL application**.
Source still has synchronous services, authoritative event logs/manifests and
replayed Python state with derived JSON snapshots. It does not use SQLite or the
selected worker architecture. Its inspected capabilities are:

- Main/mini mixed calendar Actual using one observation; own task Today/This week
  and retained deleted work in application totals, with visible calculation errors.
- Read-only modal Work History from main and recursive task editors, explicit
  periods/Refresh, local sorting remembered for the session and safe modal return.
- Production modal frozen Timesheet Preview/Save/retry and confirmed Overwrite,
  with same-component unfinished-attempt retention only within the session.
- Staged project/task/date-only replay, pure minute/DST inputs, standalone closed
  correction dialog, decimal reports, frozen export evidence, absolute confirmation
  services and read-only daily reconciliation. Production correction/date-only
  entry, POL-R UI, weekly reminders and selectable weeks remain absent.
- No shipped Reset or old full/selected export UI; independent legacy backend
  reset/checkpoint/submission/export readers remain, not compatibility promises.

The old **Phase 2 bounded service gate was independently accepted Complete** for
JSONL serialized ownership; see [historical scope](docs/ROADMAP.md#historical-jsonl-evidence--not-rewrite-completion).
It completes no SQLite stage. Existing tests establish semantic/current-runtime
evidence only, not a complete replacement, worker safety or Windows qualification.

The legacy duration-entry UI has been removed; replacement manual work entry
remains pending. Date-only replay/accounting already supplies main/mini and frozen
Timesheet, but production dated writers stay inactive under the active-reader/UI
gate. Current float-second storage, replacement interval IDs, constructor waits,
monthly reminders and widget-retained retries are **not target mechanisms**.
The rewrite uses integer microseconds, stable revisions, SQLite request receipts,
callback-driven presentation, inline editing and saved-report recovery independent
of a widget. Recursive metadata-editor History routing is superseded as target
navigation; current source is unchanged by this documentation.

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
    - backend checkpoint reopen/void and legacy export APIs (no shipped UI routes)
    - manual interval edit/delete
    - rebuild snapshot from journal
  - Frozen Timesheet preview/Save does not call legacy pre-export backup hooks.
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

## Timesheet and export format

Toolbar **Timesheet**, File **Timesheet…**, the reminder banner and the close-reminder
choice open one application-owned modal window. Timers continue while main/mini
input is blocked. Explicit Preview resolves This week, Last week or Custom and
All or independently selected task UUIDs, including deleted work. The scrollable
report is the complete frozen decimal-hour text; changing drafts requires a fresh
preview. Save registers that exact evidence before verified file publication.
Retry preserves identity; Overwrite requires a separate one-call confirmation.

Closing before a Save attempt discards the preview. Closing an unsuccessful Save
requires confirmation and retains the same hidden instance for session resumption;
reopening does not retry automatically. Completion permits a fresh next opening.
Exit warns before losing unfinished session resumption, without undoing evidence
or files. Save never submits, confirms POL-R, resets/stops timers, deletes tasks
or marks reminders handled. Explicit Dismiss remains available. Current monthly
reminder visibility remains temporary; approved weekly reconciliation scheduling
and POL-R presentation are pending.

Independent legacy backend exporters and their audit/checkpoint/submission
representations remain available to service callers, without a parallel shipped
export interface or compatibility promise. See the
[technical contract](docs/EXPORT_EVIDENCE_CONTRACT.md) and
[owned Timesheet](DESIGN_NOTES.md#application-owned-modal-timesheet).

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
