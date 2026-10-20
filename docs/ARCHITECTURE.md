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
Stage 1A implements the connected SQLite timer/worker/main/mini foundation;
Stage 2A adds connected manual work, typed revision/read services, mixed accounting
and persisted week configuration.
Stage 2B connects owned modal History and inline correction/deletion for independent
review. Later Timesheet/POL-R remains unimplemented. Earlier
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
| SQLite adapter | Built-in sqlite3 connection/profile, relational reads/writes, constraints, transactions and request lookup; future protected upgrades. No widget access. |
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

Use Python's built-in **sqlite3**, local-disk **DELETE** rollback journaling,
**synchronous=EXTRA (3)** and **foreign_keys=ON (1)**. SQLite **3.37.0+** is required
for STRICT tables; no WAL-reset-specific floor or excluded later release applies.
Check `sqlite3.sqlite_version_info`, reporting actual/minimum on rejection. Python
version alone proves no linked SQLite version. No alternative driver, custom DLL
or database abstraction is selected.

Establish and read back the profile outside transactions, before initialization or
ordinary mutations; reject settings that do not match. Existing unsupported
journal profiles refuse before writable configuration, without conversion. Record
Python/SQLite versions, available source ID, compile options and actual profile;
the GUI reports those effective settings. See SQLite's [PRAGMA reference](https://sqlite.org/pragma.html#pragma_journal_mode)
and [EXTRA semantics](https://sqlite.org/pragma.html#pragma_synchronous).
Keep a finite busy timeout, explicit `isolation_level=None`, BEGIN IMMEDIATE,
COMMIT/ROLLBACK, and one serialized worker-owned connection. Do not set
`check_same_thread=False`. Local locks and fixture tests establish no universal
power-loss, hostile-filesystem or concurrent-writer guarantee.

New databases start in DELETE mode. A rollback journal may exist during a write;
orderly DELETE commit removes it. Never delete journals/sidecars as application
cleanup. Development datasets are disposable, but incompatible/damaged/unknown
files are refused, not recreated, repaired or converted. No production SQLite
datasets exist and no migration/compatibility workflow is needed. Schema stays 1.

Future Stage 4 backup/restore uses SQLite's supported consistent backup API,
independent validation and serialized ownership. A live main-file copy is not a
supported backup. Restore protects current new-runtime data and invalidates old
sessions/results/callbacks. Future protected rewritten-data upgrades are distinct
from this development simplification; exact release paths/cutover remain Open.

## Time and one accounting implementation

Persist UTC instants and durations as **integer microseconds**, civil work dates
separately, and an explicit dataset IANA timezone. Install pinned offline tzdata for
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
BEGIN IMMEDIATE/COMMIT/ROLLBACK and checked STRICT fresh schema version 1. Dataset/task/
project UUIDs, optional membership, timed work identities/current immutable revisions,
one active row, immutable active-start audits and committed receipts are relational.
Original start never changes; active effective start/version follows its audit chain.
Triggers enforce immutable facts/prohibited transitions; a final service lifecycle
check rejects orphan or simultaneously active/closed identities before COMMIT.

Exact receipt reuse precedes current-version checks. Failed COMMIT checks transaction
state, attempts rollback/close and isolates the connection. Independent healthy
committed reads establish receipts; an uncommitted same-connection row cannot prove
success. Failed rollback/close plus healthy absence remains unverified while that
transaction may live. Preserve primary/secondary diagnostics, including a failed
validation-probe close.
If initialization cleanup fails, a temporary exception handoff lets the worker
retain the partial store solely for cleanup; it removes that explicit handoff before
reporting the original error to Tk. Failed close never means stopped or releases
ownership early. The existing explicit cleanup retry loop remains on the worker.
The UI retains cleanup failure/Retry even after selection refresh and cannot cancel
back into mutations once the worker has left its operation loop. Cleanup handoff
adds no schema, pending registry or automatic recovery loop. Known completion
survives later read/render failure. No new request identity is allocated for retry.

`services` exposes explicit task/project/Start/Stop/Switch/correct-active-start/read/
reconcile operations. `accounting` splits integer elapsed units into local dates;
main/mini consume one report/cutoff. Unavailable numbers never substitute zero.
`worker` serializes I/O on one non-daemon thread. `app` owns retained pending request,
bounded queue drain, read invalidation and orderly shutdown. `mini_mode` delegates
controls and renders supplied values. Constructors do not wait. Short toolkit
metadata/confirmation dialogs are owned and guarded; active-start correction uses
callback-driven local modal presentation. One temporary `_WorkEditor` holds
the original UUID/version, fields/occurrence/comment and the owner's submitted
Request/token. Queue acceptance retains the window and locks fields/Close; only a
matching committed/unchanged result disposes it. Validation, known rollback and
unavailable outcomes preserve drafts and permit a new Save; typed stale rejection
requires closing/reopening without retargeting. Changing date/time still clears
occurrence, but worker completion/control state changes do not.

Unverified correction retains the exact immutable Request and offers Retry/Reconcile
and exceptional exit inside the modal editor. Reconciliation delegates to the
owner/worker; each dispatch has a new delivery token while request UUID, accepted
instant and content stay unchanged. Duplicate/old results cannot settle a later
attempt or editor. Root Close cannot interrupt executing work; idle unverified
correction reaches the same default-cancel exit warning, parented to the editor.
Canceled exit retains its session; confirmed exit closes orderly without undoing
possible commitment. External editor destruction clears widget references only;
the owner still reconciles pending evidence. Committed diagnostics and later
presentation/cleanup errors remain distinct from the verified result. Main/mini
callbacks respect editor ownership, with a narrow owned-work-form submission.
Workers never call Tk. Temporary detached UI state is not another datastore.
No UI-settings files, snapshots, exports or per-tick writes are added.

Stage 2A extends the fresh development schema directly for date-only revisions;
older development signatures refuse, without a migration path. Future export
basis/confirmation batches/cells/current references remain Stage 3 work, preserving
stable identities. The current application exposes none of those export/POL-R workflows. Stage 1B exercises real SQLite
process death at transaction/receipt/commit boundaries, atomic Switch, historical
exact retries, active restart/calendar continuity, ordinary ownership races and
rollback-journal pre-COMMIT and post-cleanup boundaries. These bounded local
experiments are not arbitrary power-loss,
hostile/multiwriter or native Windows evidence. Supported backup/restore/upgrades
remain Stage 4; native Windows source operation remains a deployment qualification.

The supported deployment is ordinary Python 3.11+ source execution through
`run_chronicle.py` → `chronicle.bootstrap.main`, without task_timer fallback.
The launcher resolves src directly. Install only `tzdata==2026.5` through ordinary
pip within available permissions; stdlib supplies sqlite3, Tkinter/ttk and the
worker queues/threading. Missing Tk/rules fail actionably, never auto-download.
No executable builder or project build is required. [RUNNING.md](../RUNNING.md)
is the single source-running guide; `scripts/run.ps1` is a thin optional launcher.

## Implemented Stage 2A mixed-work boundary

`work_entries` is the shared immutable task/UUID/kind identity. Timed identities
retain a genuine original start; date_only identities require NULL original start
and a current revision. `work_revisions` is the sole immutable closed/date-only
revision authority. Timed revisions have positive genuine UTC endpoints and NULL
date/duration fields. Date-only revisions have a canonical civil date and positive
integer duration_us, with NULL endpoints. Services parse complete calendar dates;
SQL shape checks do not prove date validity. Initial closed/manual creation writes
identity, revision 1, current reference and receipt atomically. Stop still closes
the active entry under the same typed model.

Edits append the next revision and atomically advance the current reference.
Deletion appends a deleted revision preserving the previous work values; no
identity/revision is physically removed. Kind/ownership/original start remain
immutable. Triggers enforce successor/deletion shape, forward references,
active-only start audits and timed-only active ownership. Final transaction/reopen
checks validate complete contiguous chains, current references, deletion terminality,
real dates and original/active-start evidence. Exact schema-object signatures
reject incompatible or unknown structures. The profile and schema version remain
DELETE/EXTRA/FK and 1; there is no automatic upgrade, conversion or recreation.

The explicit `TimerService` mutation interfaces below all return Outcome and
require keyword-only `request_id: str, action_utc_us: int`; dataset identity comes
from the owned store or is validated on an explicit frozen Request. Common
`comment: str = ""` is keyword-only. Input dates/clocks/duration are text.

| Method | Work-specific arguments |
| --- | --- |
| add_timed_work | task_id, entry_id, start_date, start_time, end_date, end_time; keyword start_occurrence=None, end_occurrence=None, comment="". |
| add_date_only_work | task_id, entry_id, work_date, duration_text; keyword comment="". |
| edit_closed_timed_work | task_id, entry_id, start_date, start_time, end_date, end_time; keyword expected_revision: int, start_occurrence=None, end_occurrence=None, comment="". |
| edit_date_only_work | task_id, entry_id, work_date, duration_text; keyword expected_revision: int, comment="". |
| delete_work_entry | task_id, entry_id; keyword expected_revision: int, comment="". |
| set_week_start | week_start: int; keyword expected_week_start: int (no comment). |

Identity arguments are canonical UUID strings; date/time arguments are str and
occurrences are str | None, limited to first/second or None. The source signatures
are typed. New work requires a live task; revision operations validate the retained
owning task UUID, effective closed kind and expected revision within the transaction.
Running/deleted/wrong-kind/stale work rejects without retargeting. Unchanged dates,
amounts/endpoints or comment-only edits write no revision or receipt. Equivalent
minute/occurrence input preserves stored endpoint microseconds, including after
reverting a draft. Changed/new timed endpoints are strict minutes, positive in UTC
and cannot end after the accepted observation; date-only positive H:MM inputs are
bounded exact integer microseconds and may be future dated.

`accounting.timed_portions` is shared by totals and the pure `work_history` reader;
no view recomputes splitting. One metadata/read transaction captures current work,
active timer and week convention, followed by pure accounting under one explicit
cutoff. Closed/running timed contributions are cutoff-capped; dated work is wholly
attributed to its date. Deleted effective work contributes nothing; retained deleted
tasks remain included in application totals. Main/mini share this one report.

Read signatures:

- read_task_work_history(task_id: str, *, cutoff_utc_us: int, period: str="current_week", start_date: str | None=None, end_date: str | None=None) -> list[dict].
- read_work_entry_revisions(entry_id: str) -> dict.

History periods are current_week using committed metadata, custom with both ordered
inclusive ISO dates, or all without bounds. Custom needs a representable following
boundary. Detached rows are newest-date-first, then genuine UTC portions followed
by date-only UUIDs. Rows carry kind, revision, complete effective endpoints,
original start, precise duration_us, daily segment endpoints/actual offset seconds,
continuation flags, task/kind/entry linkage, comment and request/audit references.
Running uses its real entry UUID, active version, NULL recorded stop and an explicit
observed segment boundary; a just-started zero observation creates no closed work.
Date-only rows have no endpoints or interval linkage. Revision details return the
identity, ordered immutable revisions (including deletion) and active-start audits.
These are current effective reads, not audit-clock as-of replay. Worker history and
revisions messages dispatch these explicit read services on the existing thread.

Week metadata is read from SQLite, never retained as an authoritative Python cache.
The main weekday selector submits an expected-prior checked request, writes no-op
nothing and refreshes the containing seven civil dates after verified completion.
It changes neither timezone nor work facts; restart retains it.

The two task-bound Add controls use ordinary fields and one existing `_WorkEditor`
slot shared with active-start correction, not another coordinator. Dates initialize
from the dataset-local observation, other fields empty. Save captures one accepted
instant/request before queueing. Main/mini actions remain blocked while the local
modal form is owned; normal timer/read delivery continues. Only matching verified
completion closes it. Rejected/manual stale drafts stay editable; uncertainty
locks the same Request and exposes owner Retry/Reconcile/exceptional exit.
Unexpected view destruction does not discard owner-held pending evidence.

At the Stage 2A approval, History rendering and inline editing were still pending;
the later Stage 2B integration below connects them. Stage 3 export/POL-R and the
active-reader gate for future work types remain separate. Delivery is not
independent Stage 2 acceptance.

## Implemented Stage 2B History boundary

`ChronicleApp.open_history()` owns one `history_window.HistoryWindow`, bound to a
detached live selected task. Ownership is published before callback-driven Map
presentation. Constructors do not load, observe clocks or wait. The application
captures the origin's eligible local grab/focus; Map rechecks ownership before a
local grab. Matching disposal restores only a surviving eligible origin, including
object-identity checks against reused Tcl paths. Competing local/global grabs are
never replaced. Construction, disposal and return guards prevent reentrant opening;
primary launch errors retain cleanup/return diagnostics. Root destruction cleans
the view and leaves the existing worker shutdown path intact.

`TimerService.read_history_snapshot(task_id: str, *, cutoff_utc_us: int,
period: str="current_week", start_date: str | None=None,
end_date: str | None=None) -> dict` collects one transaction's dataset/task identity,
cutoff, period, resolved inclusive bounds (NULL for All), committed `week_start`,
effective rows and task-scoped `deleted_entries`. The deleted index includes UUID,
kind, current revision/deleted flag and retained date/duration or genuine range.
It is audit navigation, not Actual. `read_task_work_history` retains its row-list
contract through this same reader. Shared pure `work_history.build_history` and
`accounting.timed_portions` remain the only portion calculation. No schema changes
or cached History authority are added.

The worker adds `history_snapshot` read routing and reuses `revisions`. Application
delivery tokens are unique across dispatches; each live History stores only its
latest snapshot/detail token and selected detail identity. Obsolete/closed-session
deliveries cannot install in a later window or consume a mutation result. Read
failure is unavailable data, never an unverified write.

The component owns Current week/Custom/All, last-successful snapshot/applied bounds,
as-of reporting, detached handle metadata and inline panels. Current/All switch
loads immediately; Custom needs Apply. Refresh uses last applied bounds, or Current
week before first success. One standard-library `calendar` panel changes drafts
only; Cancel/Escape and bounded month navigation keep the local modal owner.
`history_display` prepares complete strings and date-group ordering without I/O.
Within-day UTC order remains stable. Linked selection is visual only. A failed
preparation retains trusted prior rows; a failed widget installation invalidates
and hides untrusted handles. Old rows are never represented as current after a
failed read. Explicit Refresh recovers. Sorting uses no new cutoff/read; only a
completed render commits direction. Owner-notification failure preserves that
sort and reports the distinct session-memory handoff failure.

One application boolean starts newest-first and survives sequential History
openings only in that application. It is never persisted. Inline Edit fixes the
original task/entry/kind/revision and complete endpoints; the existing strict
minute/occurrence services retain unchanged precision and reject stale mutation.
Date-only editing retains whole-date shape. Delete names the complete work and
warns about other affected dates, using stop-minus-one-microsecond for the last
affected date. Confirmation is History-owned and defaults No.

History submits through `ChronicleApp._submit` with an explicit verified origin;
it does not own a second coordinator. Request/token correlation precedes queue/UI
effects. Main/mini controls stay blocked, running timers and normal reads continue.
Executing Close is rejected. Unverified work locks the identical Request for
owner Retry/Reconcile or owned default-cancel exceptional exit. Unexpected widget
destruction leaves owner evidence intact. Stale drafts disable Save without
retargeting. Committed results remain committed through later GUI failures and
refresh the applied History period once plus the normal coordinated main/mini path.
Unchanged/cancelled edits reload no History. Details renders immutable creation,
correction, deletion and active-start revisions in authoritative order; no earlier
revision or deleted identity becomes editable.

Stage 2A is independently accepted at `7bc1bce2894fd5d4ccddbcedfd7ae0f4e7c1323f`.
Stage 2B/complete Stage 2 functionality awaits independent adjudication. No
subordinate correction Toplevel, new worker, persistence mechanism, runtime calendar
dependency, Timesheet or POL-R is introduced.

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

Windows native Python source operation is the deployment qualification target.
Validate actual bundled SQLite/Tk, offline rules, NTFS ownership, timer persistence,
main/mini, active-start correction, modal input/focus and normal reopen before real
use or complete core pilot. No executable build is required. Stage 1 functionality
is independently accepted; absent work-computer
access does not permanently block Stage 2. Later core and Stage 4/5 integration
still require applicable native evidence. Linux/unit results are not Windows,
concurrency, hardware power-loss or release qualification.

Stage 0's documentation is independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`. The active
`feature/chronicle-rewrite` originates there; preserve the historical
`feature/chronicle-projects-timesheets` branch. Stage 1A and Stage 1B portable
reliability and Stage 1 functionality are accepted. Subsequent work remains
independently reviewed under
[AGENTS.md](../AGENTS.md), without data-path cutover or resolution of Open policy.
