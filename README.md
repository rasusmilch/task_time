# Task Timer (tkinter)

A local-only Windows-friendly desktop task time tracker built with Python + tkinter.

## Overview

- Persistent tasks with start/stop/reset/delete/edit-time controls.
- Event-sourced storage with append-only JSONL logs.
- Archived immutable segments + manifest + derived snapshot.
- Crash-safe behavior: each state-changing action appends and flushes an event immediately.
- One-running-task rule: starting a task auto-stops the currently running task.
- Resets are logical cut lines for *current* totals (history is preserved).
- Export to human-readable text with totals and audit history.

## Run from source (repo root)

From the repository root, run:

```powershell
python .\run_task_timer.py
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

## Assumptions / limitations

- Notes are single-line and capped at **160 characters**.
- UI is intentionally utilitarian.
- This is a local desktop app; no network/cloud/account features.

## Windows executable packaging

For internal Windows executable packaging with PyInstaller (default `onedir` output), see [`BUILDING.md`](BUILDING.md).

Distribution guidance: ship the entire `dist\Task Timer\` folder and run `Task Timer.exe` from that folder. User data remains external in `~/.task_timer_data`.
