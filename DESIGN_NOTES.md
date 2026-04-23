# Design Notes

## Architecture

The app uses an event-sourced model:

1. **Append-only active event log** (`active_events.jsonl`) as authoritative current segment.
2. **Archived immutable segments** under `archives/`.
3. **Manifest/index** (`log_manifest.json`) tracking segment sequence and metadata.
4. **Derived snapshot** (`state_snapshot.json`) for fast startup only.

The complete event stream across archived + active segments is the source of truth.

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
