# Chronicle target architecture

## Authority and implementation boundary

This is the single selected target technical owner for the clean Python +
**Tkinter/ttk + transactional SQLite** rewrite. The user supplied these decisions;
Codex records them, not alternative architecture. Product behavior belongs to
[TIMESHEET_REQUIREMENTS.md](TIMESHEET_REQUIREMENTS.md); frozen export/POL-R
semantics and the single full-week quarter-hour algorithm to
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md); sequence
to [ROADMAP.md](ROADMAP.md); validation to [TESTING_STRATEGY.md](TESTING_STRATEGY.md).
[DESIGN_NOTES.md](../DESIGN_NOTES.md) describes retained, unshipped JSONL source.
Stage 1A implements the connected SQLite timer/worker/main/mini foundation.
Inline History editing and later Timesheet/POL-R remain unimplemented. Earlier
Qt/PySide6 and nested correction/global pending-retry plans are superseded, not fallback implementation instructions.

## Small application and responsibility boundaries

One local application operates one selected local-disk dataset with one serialized
writer. Refuse unsupported second-instance writing; do not promise network-drive,
cloud-sync or multiuser safety. No server, cloud bus, ORM, generic command
framework, plugins or speculative enterprise layers.

Use shallow modules, splitting actual responsibilities rather than layers per class:

| Responsibility | Boundary |
| --- | --- |
| Bootstrap | Runtime checks, selected fresh dataset, worker startup and Tk root. |
| Plain records, time and accounting | Typed values and pure calculations; import neither Tkinter nor sqlite3. |
| Explicit use-case services | Complete recording/edit/export/confirmation requests and transaction results through a narrow storage adapter. |
| SQLite adapter | Connection/profile, relational reads/writes, constraints, transactions, request lookup and upgrades. No widget access. |
| Reports, files and backups | Frozen report rendering, protected publication/verification and supported database backup/restore. |
| Tk views and small controllers | Drafts, detached display rows, explicit requests, completion/error presentation and owned-window lifecycle. No SQL. |

A few concrete functions/classes and a small transaction helper suffice. Do not
introduce a generic dispatcher or duplicate accounting in views/services/adapters.

## Authoritative persisted facts

SQLite is the **sole** replacement authority. Store queryable relational current
records plus immutable typed revisions/evidence, not JSONL blobs whose ordinary
reads require replay. Do not retain a second JSONL journal, authoritative Python
projection, JSON snapshot, persisted derived total or independent Delta counter.

The core schema/transaction design must reserve the following from Stage 1;
complete behavioral slices follow the roadmap, not optional post-pilot bolt-ons:

| Facts | Required relationships and invariants |
| --- | --- |
| Projects/tasks | Stable UUIDs, optional current membership, retained deleted identities. Projects own no work/timer. |
| Timed work | Stable entry UUID, task UUID, genuine UTC endpoints, current revision and deletion state. Closed spans positive; active timer represented explicitly without a fabricated stop. |
| Date-only work | Stable entry UUID, task UUID, civil work date and integer duration; no synthetic endpoints. Distinct shape and constraints. |
| Work revisions | Immutable typed prior/new revision facts, audit time, optional comment, ownership and deletion evidence. Current reference changes atomically with revision. |
| Active timer | Persisted task/start with database-enforced at-most-one active timer. Switch closes and opens atomically at the same accepted action instant. |
| Frozen exports/cells | Immutable export identity/scope/labels, exact UTF-8 text/digest, exact task/day Actual and displayed hundredths, suggested quarter counts and sufficient reviewed full-week basis/context. In-scope relational cells support confirmation without parsing text; out-of-scope basis is not extra selectable coverage. |
| Absolute confirmation batches/cells | Immutable batch identity/audit/source and selected task/day absolute integer quarter counts, reviewed prior identity and exact cell-specific acknowledgement. One batch is atomic. No arbitrary hundredth confirmations. |
| Current confirmed references | Each known task/day points to its latest committed immutable confirmation cell/batch; absence means Unknown, an explicit zero row means known zero. No additive confirmed balance. |
| Committed request receipts | Unique request identity, strictly comparable request content and committed result, atomically tied to the use case. Not file-availability state. |
| Dataset metadata | Schema version, explicit IANA timezone and selected week convention. Future upgrades protect new-runtime data; no legacy import. |

Use enforced foreign keys and appropriate STRICT, CHECK and UNIQUE constraints;
validate bounded integer/date ranges and shapes in services as well. Stage 1A SQL
lives in `src/chronicle/sqlite_store.py`; shallow modules and typed use cases live
in `src/chronicle`. Optional feature tables are not created early. Frozen exports
and confirmation references belong in that initial integrity design even before
their UI is delivered.

## Transactions and exact request reconciliation

Explicit services own complete use cases. For a mutating request:

1. Validate shape/identity and resolve the same request ID in authoritative SQLite.
2. An exact committed reuse returns its original committed result **before** stale
   revision/prior checks. Changed content under that ID fails closed.
3. For a new request, validate current ownership, expected revision/confirmation
   prior, all affected values and all constraints inside the transaction.
4. Apply mutation, immutable revision/evidence, current references and committed
   request receipt in one transaction. A rejected batch changes no subset.
5. Return the committed result; refresh/render is separate and cannot undo commit.

Unchanged work edits create neither a revision nor an artificial receipt write.
Identity comparison must preserve relevant value/type distinctions; an ID alone
or matching visible text is not authorization. Stable entry UUID plus expected
revision replaces the old replacement-interval/tombstone identity mechanism.

Frozen export commitment atomically records reviewed full-week allocation basis,
scoped Actual/display/suggested-quarter cells, context/labels, exact text/digest and
request receipt before external publication. It freezes enough source to reproduce
allocation without later Actual or unnecessary aggregate caches. It never adds
work. Confirmation atomically validates every selected task/day against reviewed
prior references, applicable complete frozen source coverage including unchecked
cells, exact acknowledgement keys and quarter units. It appends immutable batch/
cells, updates current confirmed references and records its receipt. Unchecked
cells do not change; newer unchecked confirmations need not invalidate an otherwise
valid checked selection. Positive frozen defaults include already-equal values;
zeros are explicit only. The [confirmation contract](EXPORT_EVIDENCE_CONTRACT.md#reviewed-source-integrity-and-default-selection)
owns the detailed guards; do not infer consent from a UI stale flag. Transaction
commit order/current references, not wall-clock audit sorting, establishes the
latest confirmation. Source-export precedence and cell-specific stale checks
must be transactionally established without physical journal read sequences.

If commit outcome is uncertain, retain the same request identity/content and
query/reconcile its committed receipt through the worker. Do not blindly allocate
a new request, infer failure from a lost response, or infer success from widget
closure. A committed result remains committed if a view refresh fails. The
application owner reconciles submitted mutations even after their originating
view closes. No global one-pending-correction slot or persisted recovery ledger.

## SQLite profile, backup and restore

Use local-disk WAL with synchronous FULL and enforced foreign keys. Stage 1A
requires SQLite STRICT feature floor 3.37 and a supported WAL-reset-fixed runtime
3.51.3+ (excluding withdrawn 3.52.0); feature compatibility alone is insufficient.
Record actual SQLite source ID/compile options and effective profile. Check the
actual SQLite runtime and effective pragmas/constraints at startup rather than
assuming requested configuration succeeded. Use bounded lock handling and
truthful busy/storage errors, not infinite retries or silent profile downgrades.
One worker owns its connection; do not set `check_same_thread=False` to share it.
No universal power-loss, hostile filesystem or multi-process guarantee follows
from WAL/FULL or fixture tests.

Use SQLite's supported backup API to obtain a consistent backup, including
committed WAL contents. Never copy only a live WAL database's main file. Validate
backup independently and test restore before relying on it. Restore runs under
serialized ownership, protects current new-runtime data, validates the candidate
and invalidates prior dataset session/results/callbacks before reuse. Versioned
schema upgrades require protected backups and rollback/refusal evidence where
applicable. This is future rewritten-data protection, not migration of old JSONL.
Exact release paths and retired-data cleanup remain Open.

## Time and one accounting implementation

Persist UTC instants and durations as **integer microseconds**, civil work dates
separately, and an explicit dataset IANA timezone. Bundle offline tzdata for
Windows; do not depend on network lookup or opaque abbreviations for calendar
rules. Validate supported conversion/range boundaries, DST gaps/repeats and
positive UTC spans. Dataset-timezone change policy remains Open before affected
configuration/accounting implementation.

One pure accounting implementation splits genuine elapsed work into local dates
and assigns dated amounts wholly to declared dates. Running work uses one explicit
observation cutoff; dated work retains date semantics, including future declared
dates in a requested week. Sum integer units, never binary-float work accumulation
or per-tick persistence. Week calculations use civil-date arithmetic and the
selected weekday (Sunday initially), not fixed 168-hour UTC spans.

Main/mini share a coordinated cutoff; each task shows its own work and application
totals include retained deleted-task work. Current project grouping is derived,
non-additive. Displayed Actual rounds each task/day once to integer hundredths;
its rollups sum those cells. **Submission is a distinct pure calculation** over
exact full-task/week work, yielding suggested quarter counts with no carryover.
The single [algorithm/proof owner](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation)
defines weekly upward rounding, largest remainders, earlier-date ties and partial
Custom/provisional-week rules. Implement later in plain domain/application logic,
not widgets, SQL formatting or another accounting implementation.

Confirmed is latest absolute quarter-unit evidence or Unknown. Daily Delta uses
displayed Actual hundredths minus converted Confirmed; Enter/Suggested POL-R is
the valid quarter-hour allocation, not daily Actual or Delta. Derive suggested-entry
gap and exact weekly rounding adjustment separately. Unknown is not zero; expected
rounding differences do not by themselves establish allocation mismatch. A current
correction may change other dates' suggestions within its task/week, never older
frozen allocations or confirmations. No rounding ledger, carryover bank, cached
suggestion authority or new timed/dated work represents the adjustment.

## Tk thread and worker bridge

Use one Tk root/mainloop and ordinary ttk Treeview plus Entry/forms. Retain
detached row-to-record metadata; handles, row numbers and formatted clocks never
authorize writes. No custom spreadsheet/cell editor engine.

**All Tk calls are UI-thread-only**, including Variables, `after`, focus and
destruction. One worker owns SQLite and database/file I/O. Exchange plain request
and result values through standard-library queues. One bounded UI-thread `after`
result drain delivers completions; the worker never calls Tk. No thread pool,
asyncio integration or arbitrary connection sharing.

Coalesce obsolete read refreshes; use only session/view/request context needed
to reject stale results. The result drain is message delivery, not replay, work
creation or a separate authority. Timer display processing remains responsive
independently of slow I/O. Reject obsolete view results while still reconciling
committed mutations at the owner. Restore invalidates old dataset sessions.

Constructors construct only. Use explicit presentation and completion callbacks,
not constructor waits, application-authored nested mainloops, `update` loops or
blocking modal sequencing. Modal History/Timesheet uses local ownership while
the mainloop continues timers/queue delivery; main/mini input stays blocked.
Short toolkit/native file and confirmation dialogs may internally wait: explicitly
parent them, guard reentry and return legitimate grab/focus without stealing a
competing live/global owner. A small owned-window-return helper is sufficient;
no global modal registry or polling-based focus workaround.

Main selection → one task-bound History → inline editor is the rewrite route.
Preserve applied period, unapplied Custom drafts, session sort, whole-entry
identity and explicit refresh. Cancel/unchanged returns without writes; validation
or stale conflict retains the draft. Save completion follows authoritative result,
not destroyed widgets. Do not carry the subordinate correction Toplevel/global
pending-event plan into this rewrite.

Shutdown rejects new submissions, drains or reconciles in-flight requests and
closes the worker/connection orderly without UI-thread joining a running worker
or silently terminating it. Keep Tk event delivery alive until completion can be
reconciled. Approved Stage 1A uses accepted wall UTC captured once before queueing;
sleep/exit never stops work and restart restores the same committed active UUID.
Impossible observations display unavailable/clock warnings; explicit minute/DST
active-start correction retains immutable original/prior/new values and receipt.
Idle unverified outcomes offer exact Retry/Reconcile or default-cancel exceptional
exit, explaining possible commitment and volatile retry loss. Executing I/O is
not interrupted. No repaint/shutdown infers missing stops.

## Implemented Stage 1A boundary

`bootstrap` requires explicit data-dir/create/zone arguments. `dataset_lock` holds
OS ownership before writable open; unknown/nonempty create targets and unknown
schema versions refuse without data cleanup. `sqlite_store` owns isolation_level=None,
BEGIN IMMEDIATE/COMMIT/ROLLBACK and checked STRICT schema version 1. Dataset/task/
project UUIDs, optional membership, timed work identities/current immutable revisions,
one active row, immutable active-start audits and committed receipts are relational.
Original start never changes; active effective start/version follows its audit chain.
Triggers enforce immutable facts/prohibited transitions; a final service lifecycle
check rejects orphan or simultaneously active/closed identities before COMMIT.

Exact receipt reuse precedes current-version checks. Failed COMMIT checks transaction
state, attempts rollback/close and isolates the connection. Independent healthy
committed reads establish receipts; an uncommitted same-connection row cannot prove
success. Failed rollback/close plus healthy absence remains unverified while that
transaction may live. Preserve primary/secondary diagnostics. Known completion
survives later read/render failure. No new request identity is allocated for retry.

`services` exposes explicit task/project/Start/Stop/Switch/correct-active-start/read/
reconcile operations. `accounting` splits integer elapsed units into local dates;
main/mini consume one report/cutoff. Unavailable numbers never substitute zero.
`worker` serializes I/O on one non-daemon thread. `app` owns retained pending request,
bounded queue drain, read invalidation and orderly shutdown. `mini_mode` delegates
controls and renders supplied values. Constructors do not wait. Short toolkit
metadata/confirmation dialogs are owned and guarded; correction uses callback-driven
local modal presentation. Workers never call Tk. Temporary detached UI state is not
another datastore. No settings, snapshots, exports or per-tick writes are added.

Future dated revisions/export basis/confirmation batches/cells/current references
extend schema under protected versioned upgrades, preserving stable identities.
Stage 1A exposes none of those writers or workflows. Operational interruption,
backup/restore and native Windows qualification remain later evidence gates.

## Frozen files and core POL-R

The [export contract](EXPORT_EVIDENCE_CONTRACT.md) owns complete frozen content,
rounding, protective default publication, explicit one-call overwrite, current
file verification and absolute confirmation semantics. File publication is a
separate resource after SQLite commit: it cannot be made atomic with the database.
Failure retains the committed snapshot for same-report retry independently of
widgets. Never delete/roll back a final file to pretend commit/publication failed.
No stored READY flag, file registry or publication-history ledger is required.

Core schema, services and UI must support whole applicable export confirmation,
checked cells, explicit zero, defer/review and manual absolute quarter-hour
confirmation with full source integrity, exact stale acknowledgements, fresh
selected-prior rejection and immutable history. Daily/weekly reconciliation and the
selected previous-week/current-Friday-and-Monday reminders are core Stage 3,
mandatory before pilot. Unknown or unavailable POL-R never blocks Actual.
Weekly submission distribution is core, distinct from optional allocation budgets.
Employer/customer redistribution authorization and the external representation of
worked days receiving zero suggestion need validation before affected Stage 3
connected official reporting/pilot. This is not independent compliance approval
or permission to reopen the selected formula. No extra worker, scheduler, datastore
or persistence service is justified. Optional budget allocations and any future
external connection remain separately approved.

## Deployment and next boundary

Windows is the native desktop/package qualification target. Start early onedir
smoke in Stage 1 and integrate native Tk, offline timezone data, SQLite profile,
publication and backup/restore evidence through stabilization/pilot. Existing
[BUILDING.md](../BUILDING.md) commands now target the replacement runtime, but
source/spec alignment is not proof of a qualified native Windows executable.
Do not invent performance targets or exact version pins without validation. Linux/unit evidence is not Windows, concurrency or universal
power-loss qualification.

Stage 0's documentation is independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`. The authorized
`feature/chronicle-rewrite` workstream originates there; preserve the old
`feature/chronicle-projects-timesheets` source/history branch. Stage 1 remains
In Progress: approved Stage 1A is implemented, while operational/native Windows
qualification remains pending. Later execution requires independent review under
[AGENTS.md](../AGENTS.md); no data-path cutover or Open policy is authorized here.
