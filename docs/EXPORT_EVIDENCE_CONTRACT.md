# Chronicle export evidence and absolute POL-R contract

## Authority and availability

This owner specifies selected frozen report, decimal, publication/verification,
absolute confirmation and reconciliation semantics. [ARCHITECTURE.md](ARCHITECTURE.md)
owns replacement SQLite schema/transaction/thread boundaries;
[TIMESHEET_REQUIREMENTS.md](TIMESHEET_REQUIREMENTS.md) owns product behavior;
[ROADMAP.md](ROADMAP.md) sequences core delivery before pilot. Approval is not
implementation or platform qualification.

**SQLite supersedes the earlier mandatory JSONL envelope, segment manifest,
physical replay order, fsync/synchronize-journal and Python projection mechanisms.**
There is one replacement authority, not SQLite alongside a required journal.
Current source still uses those JSONL mechanisms, documented in
[Design Notes](../DESIGN_NOTES.md#immutable-export-snapshot-registration-staged).
They and the accepted old Phase 2 gate are legacy implementation/historical
evidence only, not replacement instructions. Semantic guarantees below remain
binding; old API/event field layouts are not backward-compatibility requirements.

## One authoritative export snapshot

One committed immutable SQLite snapshot is export truth; zero or more external
files are reproducible copies. Neither export nor confirmation adds Actual.
Freeze the exact reviewed values, context and text before external publication.
Later work, correction, deletion, rename, project movement or week-setting change
cannot rewrite saved evidence. Retry/recovery reads that snapshot, not current
accounting or a retained widget. A registered report remains recoverable even
with no currently verified external copy.

## Export identity and contents

Use one stable export UUID and immutable typed relational evidence/cells, with
a committed request receipt in the same transaction. Preserve:

| Fact | Required frozen content |
| --- | --- |
| Dates and cutoff | Inclusive civil start/end dates, one UTC accounting observation. |
| Calendar | Explicit IANA report timezone and selected week-start weekday (Monday=0, Sunday=6). |
| Scope | All/explicit UUID selection, original request and deleted-task inclusion. Preserve any supported task/project/Unassigned request rather than infer it later. |
| Identity/labels | Task UUIDs, historical names and current-at-export project UUID/group labels; duplicate names remain distinct. |
| Cells | Task/day full-precision integer duration and displayed integer hundredths. |
| Report | Complete exact text/UTF-8 bytes and SHA-256 digest. |
| Destination | Original preferred destination if supplied; alternative publication paths do not mutate evidence. |

Structured cells and text come from one calculation and are validated together.
Keep exact text so renderer changes cannot alter old bytes; never parse a human
report to reconstruct confirmation values. Immutable snapshot commitment is a
separate action from nonpersistent preview preparation.

## Decimal-hour representation

Exports and POL-R-facing values have exactly two decimal places. Work remains
exact in integer microseconds. One hundredth of an hour is 36 seconds:
`hundredths = ROUND_HALF_UP(duration_microseconds / 36_000_000)` using exact
integer/decimal arithmetic, not binary-float accumulation/rounding.

Round each task/day **once**. Weekly/project/overall displayed rollups sum those
hundredths, not independently rounded raw aggregates. Project subtotals are
non-additive. Do not add exported hundredths back to Actual. Positive underlying
work rounding to 0.00 remains nonzero and is not automatically confirmed zero.

| Work | Decimal hours |
| --- | --- |
| 3 hours | 3.00 |
| 3 hours 15 minutes | 3.25 |
| 3 hours 20 minutes | 3.33 |
| 1 hour 30 minutes | 1.50 |
| 45 minutes | 0.75 |
| 1 minute | 0.02 |

## Snapshot-first creation and publication

1. Explicit Preview captures one cutoff and calculates the selected work once.
2. Prepare consistent detached cells/text/context and a stable candidate identity.
3. Changed drafts invalidate readiness; Save requires the reviewed current candidate.
4. Commit the exact snapshot/cells/request receipt atomically in SQLite, with
   validation and authoritative same-request reconciliation.
5. Only after registration is verified, materialize its exact frozen bytes.
6. Verify complete final bytes and digest before reporting successful Save.

Registration uncertainty prohibits publication. Reconcile the same request/export
identity; never generate a second event because a response was lost. Commit is
not rolled back or relabeled failed by later file/UI failure. Saving is not
confirmation, reminder dismissal, submission, checkpoint, deletion or timer Reset.

## Materialization and byte verification

Read valid committed SQLite evidence, not cached UI status. Default attempts
reuse a completely inspected matching regular file without rewriting; reject
conflicting/unsuitable objects; absent destinations use exclusive no-overwrite
publication. Keep complete private same-directory staging: write frozen bytes,
flush/fsync, successfully close and verify ownership before publication. Existing
hard-link exclusive publication on supported filesystems is the current bounded
mechanism; no unsafe direct-write fallback is authorized.

Only a verified stable regular-file content conflict can offer explicit Overwrite.
Use an owned default-cancel confirmation naming the exact destination; permission
is for **one call**, not a field in immutable evidence or reusable retry permission.
Ordinary Retry and alternate paths never inherit it. Matching files are still
reused; initially absent destinations still use exclusive creation.

Reject directories, symlinks, unsupported objects, unstable/incomplete reads and
inspection failures as replacement authorization. Protect the active dataset tree,
including resolved aliases, before replacement staging. Use complete owned staging
then `os.replace()`, never unlink first, truncate or write directly to target.
Recheck the target's regular-file type, identity, size, modification/change metadata
against its stable observation immediately before replacement. Detected changes
abort without replacing the newly observed target. Verify complete final bytes
and digest before success.

These bounded checks assume trusted directories and serialized ownership; they
are **not atomic compare-and-replace**, arbitrary hostile/concurrent-directory
protection, universal filesystem support or power-loss proof. Different platforms'
timestamp semantics must not be assumed identical. Narrow typed content-conflict
signaling distinguishes eligible conflict from arbitrary FileExistsError or
unsuitable-object failures; no message-text classification.

Distinguish attempted replacement, known publication and verified success.
An error after publication does not prove the old file survives or new file is
absent. Preserve original traceback/notes. Cleanup removes only owned staging;
`os.replace` may consume its path. Never delete/roll back final output to hide an
uncertain outcome. A later explicit retry reuses frozen bytes and can recognize a
matching copy without rewriting. Database and filesystem are separate resources.

## Derived pending and recovery outcomes

Validate committed evidence first; invalid/unknown registration is not a file
status. Evaluate an explicit destination, otherwise a frozen preferred path.
Status is a current observation for that destination, not global persisted state:

| Outcome | Meaning |
| --- | --- |
| PENDING | Valid snapshot but no explicit/preferred destination for evaluation. No attempted write implied. |
| READY | Suitable regular file currently matches complete bytes and digest. |
| MISSING | Selected destination currently absent; no publication history inferred. |
| CONFLICT | Selected object/bytes are unsuitable or disagree. Only stable regular-file content conflict can authorize confirmed overwrite. |
| UNVERIFIABLE | Inspection cannot safely establish current contents/status. |

Reevaluate rather than retain READY as permanent proof. Restart/saved-report
recovery uses SQLite evidence and a chosen destination, not stored publication
history or an assumed remembered alternate path. Missing does not prove prior
publication or deletion. File failure leaves committed evidence for same-report
retry; a deliberate later export has a new identity/cutoff. No file registry,
publication ledger, durable READY state, automatic recovery writer or separate
authority is selected.

## Transaction interruption and idempotency

Follow [atomic request rules](ARCHITECTURE.md#transactions-and-exact-request-reconciliation).
Exact committed request reuse returns its original result before stale checks;
changed content under that ID fails. Mutation/evidence/current reference/receipt
commit atomically. Unknown commit outcome requires database reconciliation of the
same request, not a new identity or JSONL synchronization. A post-commit refresh
failure changes neither committed evidence nor newer current confirmations.

Reject invalid evidence; do not repair it silently or infer success from UI/file
visibility. New-runtime backup/restore and schema upgrade protection follow the
SQLite owner, not archived journal replay or derived snapshot precedence.

## Absolute confirmation batches

Use immutable relational confirmation batch/cell evidence, not the old JSONL
event envelope. One operation has a stable batch/request identity and audit instant. Its nonempty
selected task/day cells retain:

- Task UUID and canonical civil work date.
- Nonnegative integer absolute confirmed hundredths (not bool/float).
- Optional source export UUID; export-linked amount equals its frozen cell.
- Expected prior confirmation identity, or absent for Unknown.
- Cell-specific stale-export acknowledgement where required.

Duplicate task/day keys reject. Manual confirmation needs no source export and
may differ from current Actual/export. Unknown is absent evidence; explicit zero
is a known value with identity. Keep immutable prior history and relational
current references; do not persist independent additive balances or Delta.
A source records frozen provenance, not independently verified external POL-R.
When workflow relies on a report copy, verify current file bytes; historical
confirmation validity does not depend on that file remaining available.

## Whole-batch validation, concurrency and stale exports

Within one transaction validate all selected identities, values, source cells,
reviewed priors and acknowledgements **before** committing the batch/current
references/receipt. Reject the whole stale/invalid batch; no partial confirmation.
Unchecked cells and earlier evidence remain untouched. Latest references follow
committed database ordering, not audit-clock sorting or physical JSONL metadata.

If a source export predates a newer differing current confirmation, identify the
specific conflicting cell and require acknowledgement bound to that reviewed
prior. A changed prior rejects even after acknowledgement; it is not blanket
permission to overwrite subsequent evidence. Equal source/current values require
no extra manual entry, but intervening equal-value confirmation still changes the
reviewed prior. Full and checked workflows use the same rule.

Proposals use frozen export amounts/names and latest reviewed priors, never
recalculated Actual. Ordinary applicable bulk selection does not automatically
confirm zero; explicit checked zero is allowed. Empty selection is not All.
Deferral writes nothing; later review obtains fresh priors. Exact batch request
reuse cannot reapply old values after newer confirmations. Manual confirmation
records what the user reports externally, not backend verification. No confirmation
changes Actual, active timer or frozen exports.

## Displayed reconciliation

| Field | Derived rule |
| --- | --- |
| Actual | Current exact task/day work rounded once to integer hundredths. |
| Confirmed POL-R | Latest absolute confirmed hundredths or Unknown. |
| Delta | Actual hundredths minus known Confirmed; otherwise Unverified. |
| Enter in POL-R | Whole current Actual hundredths, never Delta. |

Mandatory: frozen 3.00, another 2.00 work, confirm 3.00 →
**5.00 / 3.00 / +2.00 / 5.00**. Confirm 5.00 → Delta 0.00.
Correct Actual to 2.50 against 3.00 → **2.50 / 3.00 / -0.50 / 2.50**.
Keep older exports/confirmations unchanged. Zero-work dates may have known positive
confirmation and negative Delta. Underlying positive work rounded to zero remains
precise. Project rows are informational, never extra cells/work.

Daily and weekly presentation must not hide Unknown/disagreement through opposing
weekly deltas. Required previous-week/application-used-day and current-Friday/
Monday reminders compare task/day truth; explicit Dismiss today is separate from
opening/Save. No external outage blocks Actual. Complete this core Stage 3 workflow
before pilot; it is not optional Stage 6 scope.

## Implementation boundaries and remaining decisions

Current JSONL preparation/registration/materialization/status and confirmation
services are evidence of semantic foundations, **not SQLite implementation**.
Their exact event layouts, replay, synchronization and retained Save-widget
recovery are superseded target mechanisms; see [current source](../DESIGN_NOTES.md).
Do not reuse legacy checkpoint/submission markers as absolute POL-R evidence.

The rewrite preserves semantics through SQLite transactions, exact units and
callback-driven Tk views. Core saved-report recovery is independent of widgets.
Allocation policy, dataset-timezone changes, abnormal clock/restart rules and
release paths remain with the [reserved decision gates](TIMESHEET_REQUIREMENTS.md#open--reserved-userchatgpt-decisions).
No migration or new external integration is selected. Windows/NTFS, packaging,
concurrency and power-loss claims require applicable evidence, not this approval.
