# Changelog

This is Chronicle's sole canonical historical project-change record.
Unreleased changes describe cumulative material effects, not individual tasks,
receipts or commits. No release or production activation is implied below.

## Unreleased

### Staged service capability

- Separate non-time-bearing project containers from independent UUID-based tasks,
  with optional membership and reassignment that preserves recorded work.
- Represent date-only manual durations separately from real intervals, with
  append-only effective-state correction/deletion replay and rebuildable snapshots.
- Derive mixed historical task/day/week actuals from intervals and dated durations,
  including local-day/DST splitting and informational project/Unassigned totals.
  Current weekly calculations use Sunday starts; project subtotals are not
  additional work.
- Provide read-only independent-task timesheet rendering and date-range generation
  with precise durations, explicit selection scope, Unicode-safe escaping and
  wrapping, and bounded calendar-week layout.
- Publish complete UTF-8 timesheet files through same-directory staging and atomic
  no-overwrite hard links on supporting filesystems. Cleanup is restricted to
  staging; saved files do not create submission or checkpoint records.

These services are independently callable but not fully connected to the
production application workflow. Legacy UI/export paths remain active during
staging; new production date-only duration writers and release cutover are inactive.
POL-R confirmations, immutable export-event registration, configurable week
starts and weekly allocation management are not implemented.

### Documentation and governance

- Establish [repository operating instructions](AGENTS.md) and the
  [approved replacement/POL-R product contract](docs/TIMESHEET_REQUIREMENTS.md),
  distinguishing selected targets, inspected implementation, Open decisions,
  deferred work and unverified external behavior.
- Reconcile overview and technical status with those owners. Documenting approved
  future behavior does not represent shipped application functionality.
