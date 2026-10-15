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
The existing generation/save services still use the exact renderer. Separate
export-snapshot preparation, durable registration, detached lookup and journal
replay are implemented/staged; registration publishes no external report file.
Verified materialization from committed evidence is also staged: exact-byte/digest
checking, matching-file reuse and exclusive no-overwrite publication are available
through a separate service operation. Standalone read-only destination-relative
file-status evaluation is also implemented/staged. Strict immutable confirmation
batch validation/replay, detached preparation and dedicated durable registration
with an in-memory effective projection are staged. Confirmation UI, reconciliation,
automatic missing-file recovery and general file-status/recovery UI are not implemented.
Approval is not proof of Windows/NTFS
compatibility or power-loss safety. See the
[current registration mechanism](../DESIGN_NOTES.md#immutable-export-snapshot-registration-staged)
and [materialization](../DESIGN_NOTES.md#verified-export-materialization-staged).

## One authoritative export snapshot

Use the existing append-only Chronicle event journal as the sole authoritative
persistent store for export evidence, with no second database. One export is an
immutable journal-backed snapshot and zero or more externally materialized copies
whose bytes can be verified against it. An external text file is a reproducible
representation, not independent timekeeping truth.

Regeneration uses the frozen snapshot without recalculating work. Later work,
corrections, renames, project moves or week-setting changes never modify it.
Frozen values are evidence, not another authoritative Actual counter. A valid
snapshot without a currently verified file remains recoverable registered
evidence. That broad concept is distinct from the specific PENDING status below.
This export snapshot is distinct from the existing rebuildable application state
snapshot.

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

These five Selected outcomes define current-observation status evaluation. The
standalone service evaluator is implemented/staged; general status/recovery UI
is not implemented. One immutable journal-backed export may have zero or more
independently verifiable external copies. Status is derived
for the particular destination evaluated, not stored as a global lifecycle
attribute of the export identity.

First establish a valid committed snapshot through authoritative journal
validation. Missing, malformed, conflicting or otherwise unverifiable journal
evidence must fail closed, not become PENDING, MISSING or another file-status
result. Existing journal integrity requirements remain binding.

Evaluate an explicit destination when supplied; otherwise use the snapshot's
immutable `preferred_destination`, if present. An alternative destination does
not modify the snapshot. If neither destination is available, derive PENDING.

| Outcome | Meaning |
| --- | --- |
| PENDING | A valid committed snapshot exists, but neither an explicit destination nor an original preferred destination is available for evaluation. This does not assert that file creation was attempted. |
| READY | A valid committed snapshot exists and the selected destination currently contains a suitable regular file whose complete bytes match the frozen UTF-8 report and whose SHA-256 agrees with the frozen digest. Verification succeeded for this destination at the time of the check. |
| MISSING | A valid committed snapshot exists and a destination is selected, but no file currently exists there. This establishes no publication history. |
| CONFLICT | The selected destination exists but its bytes differ, its digest disagrees, or its object type is unsuitable. Directories, symlinks (including dangling links) and other unsuitable objects are not matching report files. |
| UNVERIFIABLE | A destination is selected, but current contents or file status cannot safely be established, for example because of access failure, interrupted verification or other inspection uncertainty. |

Only READY establishes a currently verified copy at the evaluated destination.
It is not permanent proof that the file remains unchanged; an unreadable file
cannot be READY merely because an earlier check succeeded. Every current-status
check reevaluates the selected destination.

After restart, reconstruct the export from the journal and reevaluate the
destination selected under the same rules. Registration alone proves no earlier
publication. A previously used alternative destination is not automatically
remembered merely because it was verified in an earlier session.

An absent selected file may never have been created, may reflect failed
publication, or may have been published and subsequently deleted. These histories
are intentionally indistinguishable from the same current observable state.
MISSING does not prove previous publication or deletion.

Recoverable registered evidence is broader than uppercase PENDING. MISSING,
CONFLICT and UNVERIFIABLE can still retain valid immutable evidence for safe
retry or materialization elsewhere. Retry reuses the export identity and frozen
contents without recalculation, overwrite or another snapshot for the same
operation. Matching-file reuse and complete byte/digest verification remain
required. Changing the output path never changes the snapshot or its original
preferred path, and no file outcome implies POL-R confirmation. A deliberate
later new export is a new identity and frozen cutoff.

The journal and current filesystem inspection suffice for this observable-state
model. Do not add a persisted completion flag, publication-history event,
external-file registry, second authoritative database, durable READY/MISSING
state machine, stored file-status cache, separate recovery ledger or automatic
file-recovery subsystem. Historical publication tracking would require a
separately approved product requirement; it is not authorized by these outcomes.

## Journal interruption and export idempotency

Current initialization creates journal files only for nonexistent or genuinely
empty data directories. Nonempty datasets missing an authoritative root journal
component are refused before replacement or other initialization writes. Surviving
export evidence is preserved for explicit diagnosis/restoration; derived snapshots
do not authorize reconstructing missing journals. This is distinct from strict
content validation and is not automatic journal recovery.

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
journal replay takes precedence. Restart reconstructs valid registered evidence;
file status still requires destination evaluation under the rules above.
Exactly-once effective export identity is required: duplicate event identities
must not duplicate export evidence. This contract does not itself implement or
authorize unrelated general journal-recovery changes.

## Confirmation event structure

Select `polr_confirmation_batch_recorded` in the existing application-scoped
envelope with `task_id = "__app__"`. One operation produces one event containing
the whole validated batch; its envelope `event_id` identifies that batch.
The persisted envelope has exactly `schema_version`, `event_id`, `timestamp_utc`,
`local_timezone`, `task_id`, `event_type` and `payload`. Require the current schema
version, a canonical event UUID and canonical UTC audit seconds with a `Z` suffix.
No extra envelope fields are permitted.

`local_timezone` is preserved audit metadata, not a timezone-rule lookup key.
Require exactly `str`, nonempty and not whitespace-only, with no leading/trailing
whitespace, valid UTF-8 encoding, and no NUL, C0/C1 control characters or DEL.
Preserve the original value without normalization or replacement. Accept
labels such as `America/Chicago`, `UTC`, `UTC-05:00`, `UTC+05:30`, `CDT` and
otherwise well-formed opaque system labels, even if an installed database cannot
resolve them. Validation/replay requires no `ZoneInfo` resolution, IANA database
membership, network access or additional persisted identifier.

The label does not verify geographic existence or timezone rules. Canonical
`timestamp_utc` and the cell's recorded `work_date` remain the temporal evidence;
replay does not use the label for conversion, day attribution, DST, Actual
calculation, frozen export amounts or ordering. This metadata acceptance does not
authorize unverified labels for calendar calculations or alter existing timezone
arithmetic. Offline Windows timezone-data bundling remains a separate release
qualification concern, not an additional dependency of confirmation validation.

The payload has exactly `cells`, a nonempty array. Each cell has exactly:

| Field | Contract |
| --- | --- |
| `task_id` | Canonical UUID with task-creation evidence preceding this batch. Later rename, reassignment or deletion does not invalidate historical identity. |
| `work_date` | Canonical ISO `YYYY-MM-DD` calendar date. |
| `confirmed_hundredths` | Nonnegative integer absolute external task/day total; booleans and floats are invalid. |
| `source_export_id` | Canonical export-event UUID or null for manual confirmation. |
| `expected_prior_confirmation_id` | Canonical latest effective confirmation-batch UUID for this task/day, or null when Unknown. |
| `stale_export_acknowledged` | Boolean, true exactly when the applicable cell-specific stale-export conflict exists. |

Cell array order is unrestricted, but duplicate task/day keys are invalid. Add
no status flags, counters, per-cell timestamps, source classifications or versions.

The event timestamp is confirmation audit time. Unknown means absence of
confirmation evidence, never a numeric zero sentinel; explicit zero is valid.
Manual confirmation needs no export. Export-linked confirmation refers to a valid
committed export preceding the batch in physical journal order. Its task/day must
exist in that export and its confirmed amount must equal the frozen
`decimal_hundredths`, never current recalculated Actual. Replay neither regenerates
the report nor inspects an external file. An intentionally different amount is
manual confirmation with a null source, without claiming frozen export provenance.

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

Replay uses original physical order from read-sequence metadata, with input list
position for events without that metadata, never UUID or audit-timestamp order.
For each incoming cell the expected prior is null only when no effective entry
exists; otherwise it must equal the batch identity last confirming that cell.
Validate every cell against the pre-batch projection before replacing any entry.

Compare source export creation with the latest effective confirmation for that
cell. A stale conflict exists exactly when the source is non-null, the latest
effective confirmation occurs after that export's first registered occurrence,
and the latest confirmed amount differs from the proposed frozen amount. Require
acknowledgement true for that conflict and false in every other case, including
manual confirmations and equal-value proposals. It remains bound to the correct
observed prior confirmation identity.
Acknowledging one conflict does not authorize unrelated replacements. Full-export
and checked-cell confirmation use the same rules. Do not auto-confirm displayed
0.00 cells; explicit zero remains possible. No batch changes timers, Actual
records or exported snapshots.

An identical repeated batch identity is one effective occurrence and cannot
reapply old values after intervening confirmations. Compare event content
structurally and strictly, retaining numeric-type and array-order distinctions.
Different content under the same identity, or an identity shared with another
event type in either journal position, fails closed. Malformed evidence is never
skipped, repaired or rewritten.

The derived mapping is keyed by `(task_id, work_date)`, with values containing
only `confirmed_hundredths` and `batch_event_id`. Absence means Unknown; explicit
zero retains an entry. It lives only in memory, is rebuilt from archived/active
journal evidence, and mutable reader results are detached. Do not put it in the
derived application snapshot or another persisted store.

### Staged confirmation preparation and registration

`TaskTimerService.prepare_polr_confirmation_batch(cells, *, batch_id=None)`
accepts a nonempty list of explicit six-field cell dictionaries, preserves their
order and deep-copies them. It generates a canonical batch UUID if omitted,
captures UTC audit seconds once and preserves the service timezone metadata.
It strictly validates authoritative evidence and the candidate as the next
physical occurrence, without writes, projection changes, accounting, rendering,
selection expansion or automatic zero-cell selection. Reviewed prior identities
and acknowledgements come from the caller; preparation never refreshes them.

`register_prepared_polr_confirmation_batch(prepared_event)` deep-copies and
validates the frozen event, then strictly rereads the journal. Check identity
before prospective new-event validation: reuse exact valid committed evidence at
its original occurrence, reject changed content/cross-type collisions, or validate
all cells against the current pre-batch projection before appending one event.
A new candidate follows all physical read sequences regardless of audit time.
Even an equal-value intervening confirmation changes the required prior identity;
reject the entire superseded proposal without mutation. Unrelated cells need not
invalidate it. Preserve ID, timestamp, cell order, priors and acknowledgements on
retry; never manufacture acknowledgement or retain just a valid subset.

The supported boundary is synchronous serialized use through one service owning
the dataset. Fresh reads are not a thread-safe or multi-process compare-and-append
guarantee. Production integration must enforce writer ownership separately.

After append require the exact valid event in a strict journal read; a silent
no-op cannot succeed. After an append exception, healthy demonstrated absence
preserves the original error with retry context. Exact valid visible evidence
requires successful synchronization before reuse. Conflicting, partial, malformed
or unreadable evidence fails closed, without another append or repair.

Existing-identity reuse and recovery after append exceptions use the bounded
`EventStorage.synchronize_journal()` operation: strictly validate manifest and
journal, open each manifest-indexed segment, active segment and manifest without
creation/truncation, fsync each and close successfully, then strictly reread.
Revalidate complete export/confirmation projections after synchronization. A failed
fsync, close or inspection cannot establish durable success merely because bytes
are visible. No unrelated files are synchronized. No new state, repair authority,
directory-sync or universal power-loss guarantee is implied.

Compute complete replacement evidence projections before installation; return the
batch UUID only after valid authoritative registration and successful installation.
An installation failure retains committed evidence for unchanged-candidate retry.
Reuse after newer batches installs the latest complete projection and cannot
reapply the old batch over them. Do not rebuild Actual/timer state, save a derived
snapshot, create automatic backups, change submissions/checkpoints or publish files.
Pre-append rejection changes no files or projections; failure after writing may
leave complete or partial evidence. Whole-batch integrity is logical event/replay
integrity, not guaranteed filesystem rollback.

A source export establishes frozen-cell provenance, not current file readiness or
independent POL-R verification. This low-level writer does not inspect report
copies. A later workflow relying on a report file must still verify that file
currently under the [materialization boundary](#materialization-and-byte-verification).
Historical replay and recovery remain file-independent.

The inherited export-registration retry path is unchanged: it can accept visible
complete matching evidence after an append exception without this additional
synchronization. This task's confirmation recovery guarantee does not qualify or
repair that separate export durability limitation.

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
acceptance. Pure decimal-hour rendering and immutable export-snapshot registration
are implemented/staged as separate outcomes. Preparation creates no records/files;
registration appends only the frozen export event and verifies the journal.
Separate verified file materialization and read-only five-status evaluation are
implemented/staged without new events, recalculation or persisted completion
state. Confirmation validation, immutable batch replay, effective projection
and dedicated confirmation preparation/registration are also implemented/staged.
Generic service append rejects confirmation events in favor of the dedicated API.
Independent review is required before further integration. Confirmation UI,
reconciliation, production integration, general file-status/recovery UI, automatic missing-file
recovery, general journal repair, migration and installation cutover remain
unimplemented. Architectural documentation does not activate them.

Do not reuse legacy submission markers/checkpoints as this POL-R model. Add no
second database, shadow authoritative export file or independently maintained
Delta counter. Allocation controls/recurrence/overrides and week-change behavior,
first-release allocation inclusion and installation/data cutover remain Open.
POL-R backend allocation administration remains Unverified. Windows/NTFS execution
requires actual platform validation; approval supplies no power-loss guarantee.
