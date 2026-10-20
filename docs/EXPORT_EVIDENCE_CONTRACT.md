# Chronicle export evidence and absolute POL-R contract

## Authority and availability

This owner specifies selected frozen report, decimal, publication/verification,
absolute confirmation and reconciliation semantics, including the selected
weekly quarter-hour submission policy. The full allocation algorithm lives only
in this owner; other documents reference it. [ARCHITECTURE.md](ARCHITECTURE.md)
owns replacement SQLite schema/transaction/thread boundaries;
[TIMESHEET_REQUIREMENTS.md](TIMESHEET_REQUIREMENTS.md) owns product behavior;
[ROADMAP.md](ROADMAP.md) sequences core delivery before pilot. Approval is not
implementation or platform qualification.

Stage 3A implements exact weekly allocation, detached frozen candidates and the
connected read-only modal Timesheet Preview. Four immutable SQLite tables retain
master context, frozen tasks, full-week basis and scoped cells through the existing
atomic registration/receipt service. Detached list/read and restart validation
check original committed request content and exact bytes/digest without current
Actual or a later renderer. Preview itself writes nothing. File Save/materialization,
status/overwrite and recovery UI remain Stage 3B; confirmation is Stage 3C and
reconciliation/reminders Stage 3D. No Stage 3A UI Save/Confirm action is exposed.

**SQLite supersedes the earlier mandatory JSONL envelope, segment manifest,
physical replay order, fsync/synchronize-journal and Python projection mechanisms.**
There is one replacement authority, not SQLite alongside a required journal.
Retained, unshipped source still uses those JSONL mechanisms, documented in
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
| In-scope cells | Exact task/day Actual microseconds, displayed Actual hundredths and suggested POL-R integer quarter counts. Actual and suggestion are visibly separate. |
| Full-week basis | For every included task/week intersecting the report, all seven civil dates with exact reviewed daily Actual and computed suggestions, cutoff, timezone and week convention, sufficient to prove/reproduce allocation without later Actual. Context outside report dates is not an extra report/confirmation cell. |
| Report | Complete exact text/UTF-8 bytes and SHA-256 digest. |
| Destination | Original preferred destination if supplied; alternative publication paths do not mutate evidence. |

Structured cells and text come from one calculation and are validated together.
Keep exact text so renderer changes cannot alter old bytes; never parse a human
report to reconstruct confirmation values. Immutable snapshot commitment is a
separate action from nonpersistent preview preparation.

## Decimal-hour representation

Keep three precision domains separate:

| Domain | Authoritative or derived representation |
| --- | --- |
| Actual | Exact nonnegative integer microseconds from genuine intervals or declared date-only amounts. Original work dates/instants/revisions never change because of POL-R rounding. |
| Displayed Actual | Completed-minute HH:MM where selected, or task/day ROUND_HALF_UP integer hundredths of an hour. Displayed Actual rollups sum these task/day hundredths. |
| POL-R submission/confirmation | Nonnegative integer **quarter-hour units**, displayed with two decimal places. Five quarters display 1.25. Do not store arbitrary hundredths as confirmed POL-R. |

One quarter is 15 minutes = 900 seconds = **900,000,000 microseconds** =
25 decimal-hour hundredths. Actual display conversion remains
`actual_hundredths = ROUND_HALF_UP(actual_microseconds / 36_000_000)`.
Use exact integer/decimal arithmetic, never binary floating point for work,
submission or rounding. Round displayed Actual task/day once; sum those cells for
its weekly/project/overall display, without independently rounding raw aggregates
or adding project subtotals again. That display rounding is **not** input to the
weekly submission calculation. Neither rounded display nor submission adds Actual.

| Work | Displayed Actual hours (not necessarily valid POL-R input) |
| --- | --- |
| 3 hours | 3.00 |
| 3 hours 15 minutes | 3.25 |
| 3 hours 20 minutes | 3.33 |
| 1 hour 30 minutes | 1.50 |
| 45 minutes | 0.75 |
| 1 minute | 0.02 |

Manual decimal entry must resolve exactly to a nonnegative integer quarter count;
reject non-quarter values rather than round them into a confirmation. Validate
integer units/types (excluding bool/float) and supported bounds. Displayed Actual
hundredths and submission quarter counts are different quantities, not aliases.

## Full-week quarter-hour allocation

This is the single complete algorithm owner. For each task and each complete
seven-date local calendar week, use the report's selected week-start convention,
explicit accounting cutoff and dataset IANA timezone. Let `Q = 900_000_000`
microseconds and `a[d]` be exact nonnegative Actual microseconds for each date.
Validate date representability and integer/intermediate/result bounds first;
never clip a required week or overflow a stored duration/conversion.

1. Set `W = sum(a[d])` over all seven dates.
2. Set `weekly_target_quarters = (W + Q - 1) // Q`, the **upward ceiling**.
   Zero work yields zero; any positive sub-quarter week yields one; an exact
   quarter multiple remains exact. Do not use nearest rounding, daily ceilings,
   displayed Actual decimals, project totals or application totals as its basis.
3. For each date set `base[d] = a[d] // Q`, `remainder[d] = a[d] % Q` and
   `suggested_quarters[d] = base[d]`.
4. Set `extra = weekly_target_quarters - sum(base[d])`.
5. Eligible dates have **positive remainder**. Order them by descending exact
   remainder, then ascending local civil date. Add exactly one quarter to each
   of the first `extra` dates. No date gets a second extra quarter in this pass.

Proof of sufficiency: write `R = sum(remainder[d])` and let `m` be the number of
positive remainders. Then `extra = ceil(R / Q)`. If `m = 0`, `R = extra = 0`.
Otherwise `0 < R < m * Q`, so `1 <= extra <= m`. There are always enough eligible
dates. Zero-work dates have zero base/remainder and never receive an allocation.

Every suggestion is a nonnegative integer quarter count; their sum is exactly the
weekly target. The exact adjustment `weekly_target_quarters * Q - W` is nonnegative
and less than Q (15 minutes). It is not work. Allocation depends only on that
task's exact week and deterministic tie order, never iteration order or floats.
No quarters/remainders transfer between tasks or weeks; no persistent carryover
bank, rounding balance, synthetic work entry or derived-total ledger is created.

### Report scope, partial weeks and provisional work

For This week, Last week or inclusive Custom, calculate the **full seven-day basis**
for every selected task/week intersecting the requested dates, using the same
explicit cutoff. Allocate all seven dates, then expose only the requested dates
and task scope as report/confirmable cells. Multiple weeks are independent.
Never recompute a separate target from a displayed partial-week subset. Visible
suggestions need not sum to the full-week target; label scope truthfully rather
than report that expected difference as an error. Never silently publish/confirm
out-of-scope task/day cells. Retained full-week source context is immutable proof,
not permission to extend the reviewed scope or a second current Actual counter.

Timed contributions are capped by the cutoff; existing whole-date attribution,
including later declared dates within the week, still applies. Do not predict
future stops. Current-week suggestions are provisional: more work, dated entries
or corrections can change the target/ranking. Explicit fresh Preview recalculates;
an already committed export, its suggestions and older confirmations never change.
A frozen proposal may still be reviewed/confirmed under the expected-prior/stale
rules below; subsequent Actual alone does not rewrite or invalidate its evidence.

### Mandatory allocation examples

Each row is one task in a Sunday-start week (the initial convention); other
dates have zero Actual. POL-R values below display integer quarters, not displayed
Actual rounding inputs. Other week-start choices use their actual seven-date groups.

| Case | Monday Actual | Tuesday Actual | Exact weekly Actual | Weekly target hours | Suggested Mon / Tue | Exact upward adjustment |
| --- | --- | --- | --- | --- | --- | --- |
| C — exact total | 1:08 | 1:07 | 2:15 | 2.25 | 1.25 / 1.00 | 0 minutes |
| D — upward | 1:08 | 1:08 | 2:16 | 2.50 | 1.25 / 1.25 | +14 minutes |
| E — no carryover | 1:10 | 0:20 | 1:30 | 1.50 | 1.25 / 0.25 | 0 minutes |
| F — small tie | 0:03 | 0:03 | 0:06 | 0.25 | 0.25 / 0.00 | +9 minutes |
| G — exact quarters | 0:15 | 0:30 | 0:45 | 0.75 | 0.25 / 0.50 | 0 minutes |

In F, the earlier date wins the equal remainder; Tuesday Unknown stays Unknown.
In C, a Tuesday-only Custom view still suggests 1.00 using the full week, not an
independent Tuesday ceiling. E creates no carryover to the next week.

## Snapshot-first creation and publication

1. Explicit Preview captures one cutoff, calculating selected work with the full
   intersecting-week context required by the allocation contract.
2. Prepare consistent detached Actual/suggestion cells, full-week basis, text,
   scope/context and a stable candidate identity. Show Actual and suggested POL-R
   separately; no later recalculation belongs in Save.
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
event envelope. One operation has a stable batch/request identity and audit instant.
Its nonempty selected task/day cells retain:

- Canonical task UUID and canonical civil work date.
- Nonnegative **integer absolute quarter count**, excluding bool/float.
- Optional source export UUID; an export-linked count equals its frozen suggested
  POL-R quarter count, never its displayed Actual hundredths or current allocation.
- Expected prior confirmation identity, absent only when that cell is Unknown.
- Cell-specific stale-export acknowledgement exactly where required below.

Duplicate keys, invalid dates/identities/units/source relationships reject. Manual
confirmation needs no export, may differ from Actual/suggestion/export, and must
still be quarter-constrained with fresh current-prior validation. No source means
no source-export stale acknowledgement. Unknown is absent evidence; explicit zero
is known with identity. Do not reinterpret old arbitrary Actual decimals as valid
quarter-hour confirmations. No legacy schema/import compatibility is required.

Keep immutable prior history and current references, not additive balances or a
persisted Delta/rounding ledger. A source proves frozen provenance, not independent
POL-R verification. When workflow relies on a report copy, verify its current
bytes; historical confirmation does not depend on that file remaining available.

## Reviewed source integrity and default selection

An export-linked proposal is a detached reviewed value, not new authority.
Validate the complete applicable **in-scope frozen source coverage**, including
unchecked/zero cells, against authoritative SQLite evidence. Require exact source
identity, scope/relevant association, canonical task UUID/date, historical task
name and frozen **suggested quarter count** for every source row. Full-week context
outside report dates does not become selectable coverage. Never derive source
cells from widgets, parsed report text, current names or recalculated Actual.

Require unique rows in canonical task-UUID then ISO-date order. Reject missing,
extra, substituted, duplicated, reordered-as-new-evidence or tampered source rows,
including unchecked ones. Validate reviewed prior shape: known prior amount and
identity are both present; Unknown has neither; counts are valid quarter integers
and stale classifications are actual booleans. Do not silently repair a proposal.

Whole-report default selection is **every in-scope frozen suggestion > 0**,
including positive amounts already numerically equal to current Confirmed POL-R.
Do not select by positive raw work or displayed Actual hundredths. Zero suggestions
are never default-selected, even on positive-work dates. Explicit checked selection
means exactly those genuine canonical source keys, including zero if specifically
selected. Reject malformed/duplicate/unknown keys; an empty effective selection is
an error, never All. Selected input order does not change canonical source/batch
order. Unchecked confirmations remain untouched.

Newer confirmations on unchecked cells need not invalidate checked selection,
provided all frozen source coverage is exact and reviewed fields retain valid
shape. Every **selected** prior identity, amount and stale classification must
still match fresh authoritative evidence inside the committing transaction.

## Whole-batch validation, concurrency and stale exports

For a new request, one SQLite transaction validates applicable complete immutable
source coverage, selected keys/units, reviewed priors and exact acknowledgements before
committing immutable batch/cells, current references and request receipt. One
invalid/stale selected cell rejects the **whole batch**, changing no subset.
Use committed SQLite ordering/current references, never old physical JSONL read
sequences, UUID order or audit-clock sorting, to establish source precedence.

A source-export stale conflict exists exactly when a selected cell has a source,
its current confirmation is newer than that export, and its confirmed quarter
count differs from the frozen proposed count. Acknowledgement keys must equal
**exactly** the selected conflict keys. Reject missing, extra, duplicate,
unselected or nonconflicting acknowledgements, blanket acknowledgement, and any
acknowledgement bound to a changed reviewed prior. Bind consent to the selected
task/day, frozen proposed count and reviewed prior identity. No acknowledgement
may be inferred merely from a displayed conflict flag.

Manual confirmations and equal-value source proposals have no source-export
acknowledgement requirement. They still require current-prior checks. Even an
intervening equal-value confirmation changes identity and invalidates a reviewed
proposal; acknowledgement never bypasses a changed prior. Reject the whole batch
and require renewed review, without silently refreshing priors or retaining a
valid subset. Whole and checked selection use the same rules.

Exact committed request reuse returns the original result **before** stale-prior
checks and cannot reapply old confirmations after newer batches. Different content
under one request identity fails closed; canonical request comparison cannot
launder reordered/tampered evidence into a new request under that identity.
Retain exact request/identity through uncertainty, not a newly generated proposal.
Deferral writes nothing; later review obtains fresh priors. No confirmation adds
Actual, changes a timer, rewrites an export or automatically updates POL-R.

## Displayed reconciliation

| Field | Derived rule |
| --- | --- |
| Actual | Exact task/day recorded work; HH:MM and displayed Actual hundredths follow their existing conventions. |
| Suggested POL-R / Enter in POL-R | Current task/day quarter-hour allocation from its full task/week, an absolute replacement value rather than Delta. |
| Confirmed POL-R | Latest explicitly confirmed absolute quarter count or Unknown; its decimal display converts quarters to hundredths exactly. |
| Daily Delta | Displayed Actual hundredths minus `25 * confirmed_quarters`; Unknown gives Unverified. |
| Suggested-entry gap | `suggested_quarters - confirmed_quarters`, formatted in compatible units; Unknown is unresolved, never assumed zero. |
| Weekly rounding adjustment | Exact full-week target duration minus exact full-week Actual; show accurately in minutes/seconds or exact compatible units, not a rounded visible-subset difference. |

The nonnegative full-week upward adjustment is less than 15 minutes per task and
is **not additional Actual**. Daily Actual-minus-Confirmed Delta can legitimately
be nonzero when Confirmed matches the approved allocation. Conversely, equal
weekly totals do not reconcile mismatching daily allocations. Distinguish Unknown/
not confirmed, suggestion matches confirmation, known allocation mismatch,
incomplete review/confirmation coverage, explained weekly upward adjustment and
stale proposals after later work/correction/confirmation. Do not collapse these
into numeric Delta or a weekly net. No independent persisted differences/ledger.

A positive-work day may receive a zero suggestion. That does not mean no work,
known zero, or complete reconciliation. Never auto-confirm it or default Unknown
to zero. Explicit zero remains possible through reviewed confirmation. External
zero-entry versus omitted/no-entry behavior needs validation before affected
Stage 3 connected official reporting and pilot. Until resolved, an unconfirmed
zero-suggestion date is not fully reconciled solely because its suggestion is zero.

### Compatible mandatory confirmation examples

A: frozen suggestion 3.00, then 2.00 more work on that date →
**Actual 5.00 / Confirmed 3.00 / Daily Delta +2.00 / Suggested 5.00**.
After explicit confirmation of 5.00, Confirmed is 5.00 and suggested-entry gap is
0.00 (Daily Delta also 0.00). B: correct Actual to 2.50 against Confirmed 3.00 →
**Daily Delta -0.50 / Suggested 2.50**. Old exports/confirmations stay unchanged.
These exact-quarter compatible cases do not prove arbitrary Actual decimals are
valid POL-R inputs or that Enter always equals displayed daily Actual.

Correction/deletion recalculates current suggestions from effective work; it may
change other dates' suggestions in the same task/week as target/ranking changes.
Preserve historical frozen allocations and confirmation identities/values. Show
new mismatches and require explicit review/confirmation, never automatically
redistribute confirmations or create synthetic work/cross-week carryover. Older
frozen reports remain confirmable only with their frozen suggestions and the
reviewed-prior/stale protections above.

Daily/weekly summaries and required previous-week/application-used-day plus
current-Friday/Monday reminders retain cell-level Unknown, coverage and allocation
mismatches even when weekly sums agree. Open/Save never dismisses or confirms.
External unavailability does not block Actual. This is mandatory core Stage 3
before pilot, not optional allocation-budget Stage 6 work.

## External-policy validation boundary

POL-R's 0.25-hour daily restriction is accepted **user-provided context**. The user
approved Chronicle's weekly ceiling/distribution calculation. Employer/customer
authorization to redistribute hours across days, and external treatment of 0.00
on a worked day, are **not independently verified**. Validate those boundaries
before affected Stage 3 connected official reporting/pilot use. Do not claim
external compliance, synchronize/query POL-R automatically, reopen the approved
formula because of that uncertainty, or modify Actual date attribution.

## Implementation boundaries and remaining decisions

Retained unshipped JSONL preparation/registration/materialization/status and confirmation
services are evidence of semantic foundations, **not SQLite implementation**.
They do not implement the newly selected quarter-hour policy. Their arbitrary
hundredth confirmations/Actual-as-Enter are retained legacy behavior, not the target.
Their exact event layouts, replay, synchronization and retained Save-widget
recovery are superseded target mechanisms; see [retained source](../DESIGN_NOTES.md).
Do not reuse legacy checkpoint/submission markers as absolute POL-R evidence.

The rewrite preserves semantics through SQLite transactions, exact units and
callback-driven Tk views. Core saved-report recovery is independent of widgets.
Stage 1A approved clock/restart and active-start recovery in the
[recording requirements](TIMESHEET_REQUIREMENTS.md#selected--recording-and-timer-operation).
Allocation policy, dataset-timezone changes and release paths remain with the [reserved decision gates](TIMESHEET_REQUIREMENTS.md#open--reserved-userchatgpt-decisions).
No migration or new external integration is selected. Windows Python-source/Tk/NTFS,
concurrency and power-loss claims require applicable evidence, not this approval.
