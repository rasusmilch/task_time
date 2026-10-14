# Chronicle approved export evidence and decimal-hour contract

## Authority and availability

This is the single authority for the **approved** technical
contract covering export snapshots, decimal representation, file materialization,
verification/recovery, POL-R confirmation events and batch integrity. The user
approved the architectural direction; ChatGPT selected the concrete contracts
below under that direction. Codex records them without selecting an alternative.

[TIMESHEET_REQUIREMENTS.md](TIMESHEET_REQUIREMENTS.md) owns product behavior;
[DECISIONS.md](DECISIONS.md) records provenance and rejection/supersession history;
[DESIGN_NOTES.md](../DESIGN_NOTES.md) describes current source;
[ROADMAP.md](ROADMAP.md) owns sequencing and gates; and
[TESTING_STRATEGY.md](TESTING_STRATEGY.md) owns validation applicability.

Current mixed accounting, exact HH:MM:SS rendering and safe file-only saving are
staged services. Pure decimal replacement rendering is also implemented/staged:
`build_decimal_timesheet_text()` and reusable `seconds_to_decimal_hundredths()`
apply the cell-rounding and displayed-rollup rules below without persistence.
The existing generation/save services still use the exact renderer. Export events,
confirmations, reconciliation and recovery workflows are not implemented. Approval
is not implementation or proof of Windows/NTFS compatibility or power-loss safety.

## One authoritative export snapshot

Use the existing append-only Chronicle event journal as the sole authoritative
persistent store for export evidence, with no second database. One export is an
immutable journal-backed snapshot and zero or more externally materialized copies
whose bytes can be verified against it. An external text file is a reproducible
representation, not independent timekeeping truth.

Regeneration uses the frozen snapshot without recalculating work. Later work,
corrections, renames, project moves or week-setting changes never modify it.
Frozen values are evidence, not another authoritative Actual counter. A valid
snapshot without a verified file is recoverable pending evidence, not a completed
export. This export snapshot is distinct from the existing rebuildable application
state snapshot.

## Export event identity and contents

Select `timesheet_export_snapshot_created`, using the existing event envelope:

```text
schema_version
event_id
timestamp_utc
local_timezone
task_id
event_type
payload
```

`task_id = "__app__"`; the envelope `event_id` is the stable export identity.
Use UUIDs consistent with existing journal validation conventions. Audit and
cutoff values are UTC-aware; work dates are ISO calendar dates. The payload must
preserve the following facts:

| Fact | Required frozen content |
| --- | --- |
| Date window | Inclusive start/end work dates. |
| Cutoff | One fixed UTC accounting cutoff. |
| Timezone | Report timezone identifier. |
| Week convention | Weekday 0–6, Monday = 0, Sunday = 6. |
| Scope | Complete or selected reporting scope. |
| Original request | Original selection parameters, including complete selection, task/project UUIDs and Unassigned inclusion. |
| Historical eligibility | Deleted-task inclusion policy. |
| Identity and labels | Task/project identities and relevant display information at export time, including original task names and project grouping. Duplicate names remain legal. |
| Task/day values | Records keyed by task UUID and work date, retaining full-precision accounting seconds and frozen integer decimal hundredths. |
| Report | Complete exact report text, encoded as UTF-8 for materialization. |
| Integrity | SHA-256 digest of the report's UTF-8 bytes. |
| Preferred destination | Original preferred output path, if selected. |

Generate structured cells and report text from the same calculation during one
preparation. Validate their consistency before registration. Exact text is
retained so future renderer changes cannot alter old report bytes; structured
cells are retained so confirmation never requires parsing a human-readable table.

## Decimal-hour representation

Replacement timesheets and POL-R-facing values use **exactly two decimal places**.
Retain full-precision Actual seconds without rounding. External cell values are
integer hundredths of an hour; one hundredth is 36 seconds:

```text
hundredths = ROUND_HALF_UP(actual_seconds / 36)
3.25 hours = 325 hundredths
```

Conversion is deterministic, without binary-float rounding artifacts at the
presentation boundary. Round each task/day cell once. Weekly, project and overall
displayed totals sum those already-rounded displayed task/day cells. Do not
independently round aggregate raw seconds to obtain displayed rollups. Visible
totals therefore reconcile with POL-R entry values, even when they differ from
independently rounded raw aggregates. Project subtotals remain informational and
non-additive; do not count them again in application totals.

| Actual amount | Display |
| --- | --- |
| 3 hours | 3.00 |
| 3 hours 15 minutes | 3.25 |
| 3 hours 20 minutes | 3.33 |
| 1 hour 30 minutes | 1.50 |
| 45 minutes | 0.75 |
| 1 minute | 0.02 |

Never add rounded export values back into Actual. Nonzero work rounding to 0.00
remains nonzero internally and must not automatically be confirmed as zero.
Legacy exporters retain their existing behavior during staging; the current
exact HH:MM:SS renderer is not changed merely by approving this contract.

## Snapshot-first creation and publication

Preserve this operation order:

1. Capture one fixed accounting cutoff.
2. Calculate the requested date-window Actual once.
3. Produce frozen structured task/day records.
4. Produce frozen decimal-hour report text.
5. Validate internal snapshot consistency.
6. Generate the stable export event identity.
7. Append and durably flush the immutable export event.
8. Verify authoritative event registration.
9. Only then begin external file publication.
10. Materialize the exact frozen text.
11. Verify external bytes against the snapshot.
12. Report successful export only after verification.

Do not publish when registration is absent or uncertain. File-first publication
followed by attempted evidence creation is rejected. Existing safe-publication
protections remain mandatory; a file/evidence disagreement is never successful
export.

## Materialization and byte verification

Require a valid committed snapshot. Use private same-directory temporary staging
and exact UTF-8 bytes from that snapshot. Complete the write, flush/fsync and close
before exclusive no-overwrite hard-link publication (`os.link`), preserving the
existing safe staging approach on supported filesystems. Then compare the complete
actual destination bytes with frozen UTF-8 content. SHA-256 is an additional
integrity check, not an alternative authority or substitute for the complete
byte comparison.

Never delete, truncate, replace or modify an existing destination to finish an
export. Matching existing bytes may be recognized as a valid materialized copy;
different bytes or a nonmatching file type are a conflict requiring a different
user-selected output path. Missing files may be retried. External modification
does not change the snapshot: an identical new copy may be written elsewhere.

Staging cleanup never targets the requested final destination. Preserve the
existing cleanup/error reporting and unsupported-filesystem protections; no
unsafe direct-write or overwrite fallback is authorized. Do not undo publication
to recover from staging cleanup failure.

Reverify the relevant file when displaying current materialization status or
relying on that file for export-based confirmation. Old verification is not proof
that a copy remains unchanged forever. No arbitrary hostile-directory immunity,
universal filesystem support or guaranteed power-loss durability is claimed.

## Derived pending and recovery outcomes

The snapshot is immutable; materialization status is derived by checking it and
the relevant selected output path. Do not persist an independent authoritative
“export completed” flag.

| Outcome | Meaning |
| --- | --- |
| PENDING | A valid committed snapshot exists, but no verified matching file has been established at the selected path. |
| READY | A valid snapshot exists and the selected external file has been verified to match its frozen contents. |
| MISSING | A previously selected external path no longer contains the expected file. |
| CONFLICT | The path exists but its bytes or file type do not match the snapshot. |
| UNVERIFIABLE | File status cannot safely be determined. |

Only READY is a successfully materialized export. Failed materialization leaves
the snapshot recoverable. Retry reuses its export identity and frozen contents;
it neither recalculates work nor creates another snapshot for the same operation.
Changing the retry output path does not modify the snapshot or its original
preferred path. A deliberate later new export is a new identity and frozen cutoff.
Clearly communicate a lack of verification for an earlier external copy.

## Journal interruption and export idempotency

Keep the export operation identity stable across retries. Before retrying ambiguous
registration, inspect the authoritative journal for that identity:

- A complete valid event exists: reuse it.
- It is demonstrably absent and the journal is healthy: registration may be
  retried with the original identity.
- The journal is malformed/partially written or registration cannot be established:
  fail closed; do not publish an external report.

Do not silently truncate/rewrite earlier valid records or create a second export
event merely because storage or derived-snapshot persistence returned an error.
If registration succeeded but the derived state snapshot failed, authoritative
journal replay takes precedence. Restart reconstructs valid pending evidence.
Exactly-once effective export identity is required: duplicate event identities
must not duplicate export evidence. This contract does not itself implement or
authorize unrelated general journal-recovery changes.

## Confirmation event structure

Select `polr_confirmation_batch_recorded` in the existing application-scoped
envelope with `task_id = "__app__"`. One operation produces one event containing
the whole validated batch; its envelope `event_id` identifies that batch.
Each cell records:

- Task UUID and ISO work date.
- Absolute nonnegative confirmed value in integer hundredths.
- Optional source export event identity.
- Expected prior confirmation event identity, or explicit absence when Unknown.
- Whether applicable stale-export replacement was expressly acknowledged.

The event timestamp is confirmation audit time. Unknown means absence of
confirmation evidence, never a numeric zero sentinel; explicit zero is valid.
Manual confirmation needs no export. Export-linked confirmation refers to a valid
frozen cell and proposes that cell's value, not current recalculated Actual.
Manual override is a separately explicit action.

## Whole-batch validation, concurrency and stale exports

Validate every selected entry before append. Reject invalid task identities or
dates, duplicate task/day keys, invalid/negative amounts, invalid export references,
inconsistent expected prior identities and unacknowledged stale-export conflicts.
A rejected batch neither appends a partial event nor partially changes effective
confirmation state. Commit the whole valid batch as one journal event.

Latest effective confirmation follows journal replay order. Earlier evidence
remains immutable. Each new confirmation replaces an absolute external cell
total; it adds no work. Optimistically check prior confirmation identity: if it
changes between UI proposal and commitment, reject the outdated proposal and
require refreshed review.

Compare source export creation with the latest effective confirmation for that
cell. If a newer confirmation differs from the proposed frozen value, require
explicit acknowledgement bound to the observed prior confirmation identity.
Acknowledging one conflict does not authorize unrelated replacements. Full-export
and checked-cell confirmation use the same rules. Do not auto-confirm displayed
0.00 cells; explicit zero remains possible. No batch changes timers, Actual
records or exported snapshots.

## Displayed reconciliation

For each task UUID and work date, render integer hundredths with two places:

| Field | Rule |
| --- | --- |
| Actual | Current recorded seconds converted to displayed hundredths; full precision remains in underlying accounting. |
| Confirmed | Latest effective confirmed hundredths, or Unknown. |
| Delta | Displayed Actual hundredths minus Confirmed hundredths when known; otherwise Unverified. |
| Enter in POL-R | Current displayed Actual hundredths, the complete replacement value. |

Do not calculate numeric Delta from Unknown. Zero Delta means agreement with
the latest user confirmation, not independent POL-R verification.

Mandatory decimal example: frozen export 3.00; more work 2.00; current Actual 5.00;
Confirmed 3.00; Delta +2.00; Enter 5.00. After confirming the external cell at 5.00,
Delta is 0.00. Negative correction: Actual 2.50; Confirmed 3.00; Delta -0.50;
Enter 2.50. These represent the already-approved 3:00 → 5:00 and 2:30 correction
cases without changing their underlying Actual-time semantics.

## Implementation boundaries and remaining decisions

Implement this contract through separately reviewed outcomes after independent
acceptance. Pure decimal-hour replacement rendering is implemented/staged as the
first focused outcome; independent GO review remains required before persistent
export-snapshot integration. The renderer creates no records or files. Export and
confirmation events, reconciliation, GUI/recovery controls, journal recovery,
migration and installation cutover remain unimplemented. Architectural
documentation does not activate them.

Do not reuse legacy submission markers/checkpoints as this POL-R model. Add no
second database, shadow authoritative export file or independently maintained
Delta counter. Allocation controls/recurrence/overrides and week-change behavior,
first-release allocation inclusion and installation/data cutover remain Open.
POL-R backend allocation administration remains Unverified. Windows/NTFS execution
requires actual platform validation; approval supplies no power-loss guarantee.
