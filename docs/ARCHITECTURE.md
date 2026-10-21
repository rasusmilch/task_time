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
Stage 2B/complete recording is independently accepted. Stage 3A Preview and immutable
export evidence are independently accepted at `d1e775c33982f109337ec237e3c78e8dc7b56f2e`.
Stage 3B protected file Save/status and Saved Reports are independently accepted at
`76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`. Stage 3C confirmation is independently accepted for functional development under
the later Stage 3D GO instruction. Stage 3D connects derived daily/weekly
reconciliation and reminders for independent review. Earlier
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
| Dataset metadata | Schema version, explicit IANA timezone, selected week convention and one nullable canonical reminder-dismissed local date. No computed status/summary ledger. Future upgrades protect new-runtime data; no legacy import. |

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
Custom/provisional-week rules. Stage 3A implements it in pure `polr_allocation`,
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
older development signatures refuse, without a migration path. Export
basis/cells are added in Stage 3A; three confirmation batch/cell/current-reference
tables are added in Stage 3C, preserving stable identities. The exact expanded fresh
schema still uses version 1 and refuses older signatures without conversion. The
current application exposes Timesheet Preview, protected file Save/recovery and
explicit absolute confirmation and derived reconciliation/reminders. Stage 3D adds
only `dataset_meta.polr_reminder_dismissed_local_date TEXT NULL`, SQL shape checks
plus real civil-date validation on read/reopen. The exact fresh schema signature
changes directly; no migration/conversion or automatic dataset recreation. Stage 1B exercises real SQLite
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
active-reader gate for future work types remain separate. Delivery alone did not
establish independent acceptance; the later Stage 3A instruction reports Stage 2
recording independently accepted.

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
Stage 2B/complete Stage 2 recording is independently accepted at
`adc09ba0935e8718c4ad2101057af9c6022074cc`, as reported in the later Stage 3A approval.
The Stage 2B slice introduced no subordinate correction Toplevel, new worker,
persistence mechanism, runtime calendar dependency, Timesheet or POL-R.

## Implemented Stage 3A Timesheet and immutable evidence boundary

`accounting.calculate_daily` is the shared exact attribution seam for main/mini,
History portions and arbitrary Timesheet date windows. `polr_allocation` implements
the [single allocation contract](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation)
and precision conversions. `timesheet` owns frozen dataclasses (`Candidate`,
`TaskLabel`, `Basis`, `Cell`), strict structure/coverage/allocation validation and
one deterministic renderer. It retains immutable tuples, exact microseconds,
displayed hundredths, quarter counts, complete week basis and in-scope cells.
Printable Unicode is preserved; control characters in labels are escaped. LF,
fixed field order and a trailing newline produce exact UTF-8 bytes and SHA-256.
Displayed rollups sum rounded cells; full-week summaries label partial coverage.

Explicit `TimerService` APIs:

- `prepare_timesheet_preview(*, export_id: str, cutoff_utc_us: int, period: str="this_week", start_date: str | None=None, end_date: str | None=None, scope_kind: str="all", task_ids: tuple[str, ...]=()) -> Candidate`.
- `read_timesheet_task_choices() -> dict` (dataset identity and UUID/label/project/deleted rows).
- `register_timesheet_export(candidate: Candidate, *, request_id: str, action_utc_us: int) -> Outcome` (the Request carries strict complete candidate JSON, not raw bytes).
- `list_registered_timesheet_exports() -> list[dict]` and `read_registered_timesheet_export(export_id: str) -> Candidate`.

Preparation captures task/project metadata, effective mixed work, active start,
zone and committed weekday within one read transaction, then calculates detached
facts under the explicit UI observation. All includes retained deleted tasks;
Selected rejects empty/duplicate/unknown IDs. Each intersecting week retains seven
basis dates even for one-day Custom, while visible cells cover exactly the requested
task/dates. Valid empty All is distinct from failure. There is no preparation write.

Four STRICT immutable tables extend fresh schema version 1: `timesheet_exports`,
`timesheet_export_tasks`, `timesheet_export_week_basis`, `timesheet_export_cells`.
Deferred foreign keys allow validated task/basis/cell rows before the master; the
master seals further child inserts. UPDATE/DELETE triggers protect all evidence.
The existing transaction helper appends the exact receipt and commits atomically.
Installed relational coverage is checked before the receipt. Registration validates
the reviewed content/text agreement without reading current Actual or replacing
labels/settings; it stores UTF-8 derived from that frozen text, not fresh work.
Exact receipt reuse precedes validation; uncertainty reconciles the same Request.
Read/reopen validates structure, full allocation proof, exact bytes/digest and
association with the complete original committed request. Recovery preserves old
text without calling a later renderer or current accounting. No file status is stored.

Worker kinds `timesheet_tasks`, `timesheet_preview`, `timesheet_exports` and
`timesheet_export` use the existing serialized thread. Registration uses `mutate`/
`reconcile`; there is no second pending-operation coordinator. `ChronicleApp`
owns one `TimesheetWindow`, opening/return guards and read tokens. Constructor is
withdrawn, with no clocks/reads/preparation; ownership is published before Map.
Map rechecks local-grab eligibility and loads task choices only. Work forms/History
must close first. Modal input blocks main/mini while normal timer/worker delivery
continues. Only eligible surviving origin focus/grab is restored, never a competitor.

This week/Last week/Custom and All/Selected drafts never auto-prepare. Inline
standard-library calendars change drafts only; a valid draft seeds the picker,
otherwise an existing observation or explicit local-date seed observation is used.
Preview alone captures one new report cutoff/UUID. Draft changes abandon readiness
and obsolete delivery; changing back cannot resurrect a candidate. Tokens plus
export/dataset/cutoff checks reject late/mismatched results. Complete content is
prepared before rendering. Partial installation hides untrusted output, preserves
the original diagnostic and allows explicit recovery. Read-only exact text remains
scrollable/copyable. Close can discard outstanding reads and volatile candidates
before registration. Stage 3A/3B/3C are independently accepted for functional
development; Stage 3D below is delivered for independent review, not self-accepted
Stage 3 completeness.

### Connected Stage 3B protected Save and recovery

`timesheet_files` accepts only registered frozen bytes/digest, never accounting or a
renderer. Frozen `Inspection`, `ContentConflict` and `Publication` values distinguish
fresh destination status, eligible stable content conflict and publication phase.
`TimerService.inspect_registered_export_destination(export_id, destination=None)`
validates complete committed evidence first, then inspects the explicit path or
original preferred destination (no path yields PENDING).
`materialize_registered_timesheet_export(export_id, destination, *,
confirmed_overwrite=False, expected_conflict=None)` validates the same authority and
publishes its exact bytes. Consent requires an actual bool and complete typed
conflict observation. No schema change or file-status persistence belongs here.

Dataset lexical/resolved aliases are protected before all staging, even for missing
paths. Complete stable regular-file reads compare bytes and digest; unsuitable
objects or incomplete/unstable/unreadable observations never authorize replacement.
Matching files are reused without rewriting. Absent destinations use exclusive
hard-link publication from private same-directory O_EXCL staging: complete write,
flush/fsync, successful close, ownership and byte verification. Explicit confirmed
replacement rechecks reviewed target type/identity/size/mtime/ctime, then os.replace,
never unlink/truncate/direct-write. Final complete verification precedes success.
Cleanup touches only still-owned staging. Failures retain original traceback/notes,
distinguish prepublication/attempted/returned/verified phases and never roll back
final files. Checks assume trusted directories and serialized ownership, not atomic
compare-and-replace, arbitrary hostile concurrency or hardware power-loss proof.

`ChronicleApp` retains one ephemeral `_TimesheetAttempt` with the frozen Candidate,
current destination, existing Request reference/token, committed outcome, file token,
latest inspection and successful-call path. It is not another request coordinator or
persisted authority. Initial Save temporarily locks preview through an owned .txt
file dialog (`confirmoverwrite=False`); cancel has no service effects. Recheck the
same ready candidate afterward. Populate only an absent preferred_destination,
freeze the exact Request through existing mutate/reconcile, and keep fields/Preview
locked after its first registration attempt. Unknown commitment cannot publish.
Verified expected export UUID/digest queues file work; exact retry reconciles that
same Request. Registered retries/copies use the committed export UUID, never prepare,
recalculate or create another receipt.

Worker kinds `timesheet_status` and `timesheet_publish` run file I/O on the existing
serialized worker. Their dedicated owner tokens plus echoed export/destination
reject stale delivery independently of SQLite mutation tokens. Tk/dialogs stay on
UI thread; no report file inspection/publication occurs there. Executing service
work and owned dialogs guard duplicate Save/open/Close/exit. Busy protection covers
confirmation and path selection before they process events. Return restores only
eligible Timesheet local grab/focus, never another live/global grab.

The same window exposes Save Timesheet, Retry Save, Save Copy As, Check File Status,
explicit Overwrite, Saved Reports and New Preview. Overwrite is available only for
a fresh eligible conflict; its owned exact-path default-No confirmation authorizes
one call. New attempts clear old eligibility; cancel preserves the previous attempt.
Known completion/saved_path is installed before presentation. It records a completed
call, not permanent READY; status can subsequently report missing/changed output.

Saved Reports lists detached registered UUID/date/cutoff/scope/historical-label
context and loads exact text without current work or renderer. A failed render hides
untrusted output and cannot enable publication. Explicit Check/Retry/Copy/Overwrite
revalidates evidence/files on the worker. New Preview deliberately clears the view
and starts This week/All with no calculation until Preview.

Supported Close discards an unregistered preview or completed view. Unverified
registration blocks ordinary abandonment; existing default-cancel exceptional exit
explains possible prior commitment and loss of volatile Request inputs. A registered
incomplete file attempt requires separate default-No confirmation; dispose the
widget and retain only one detached session `(export_id, current destination)`
handoff. Fresh opening never automatically loads/retries it. Saved Reports recovers
it explicitly, including after restart from SQLite and the immutable preferred path;
alternate paths survive only this handoff, not restart policy. Exit warns for current
unfinished registered attempt/handoff, never undoes evidence/files or writes recovery
state. Forced destruction/crash is not a promise to preserve volatile context.
No Save/open/status operation confirms POL-R, stops/resets timers or dismisses a
reminder. Stage 3C confirmation and Stage 3D reconciliation/reminders are described
below; Save remains independent of both.

### Connected Stage 3C absolute confirmation

`polr_confirmation` owns pure strict field/type/canonical-order validation, exact
decimal-text-to-quarter parsing, frozen source metadata/proposals and detached
`ConfirmationCell` values. Manual quantities are nonnegative signed-64-bit-compatible
quarter counts with representable decimal hundredths (`MAX_AMOUNT // 25`); no floats,
rounding or increments. The existing allocation algorithm is unchanged.

Exactly three STRICT tables extend the fresh development schema:
`polr_confirmation_batches` binds batch/request/audit/source/mode;
`polr_confirmation_cells` retains selected task/date/absolute quarters, reviewed prior
identity/amount and individual stale consent; `polr_confirmed_current` retains only
(task, date, batch) references. FK/UNIQUE/CHECK constraints bind current/prior cells.
Immutable UPDATE/DELETE guards protect batches/cells; cell INSERTs are sealed after
the batch receipt exists.
No duplicated current amount, status ledger or Delta table exists.

`confirm_polr_absolute(*, batch_id, mode, source_export_id, source_metadata,
reviewed_rows, selected_keys, manual_cells, acknowledgements, request_id,
action_utc_us) -> Outcome` is the explicit mutation. Every field is present, strict
and canonical. Source metadata contains export/dataset/date/scope/selected UUIDs,
cutoff/timezone/week/digest and frozen task associations in UUID order. Source rows
contain all and only in-scope task/date/name/suggested quarters plus reviewed priors
and actual-bool stale flags, in task/date order. Context-only basis dates are excluded.
Manual mode has no source/review/selection/acknowledgement fields beyond null/empty;
its nonempty cells bind task/date/absolute quarters and reviewed prior identity/amount.

The existing BEGIN IMMEDIATE helper resolves exact receipts before stale checks.
New batches validate complete immutable source coverage (including unchecked/zero),
selected current prior identity/amount and exactly selected newer-differing conflicts
using source/prior committed sequence. Reviewed unchecked prior evidence may be old,
but retains valid shape, history and truthful stale classification; it need not
remain current. Every selected prior is freshly matched; even equal-value intervening
confirmation is stale review. Individual acknowledgements bind exact task/date,
frozen proposal and reviewed prior, never blanket consent. Insert master, selected
cells and current references, then the existing helper inserts the exact receipt.
Receipt-dependent whole-batch/chain/current-pointer checks run before COMMIT.
Failure rolls back all; uncertainty uses independent committed-state reconciliation.
An old exact retry returns its receipt without reinstalling prior values.

Reopen and confirmation reads validate all immutable batch receipts in commit_seq
order, reconstruct historical expected priors for validation, compare complete stored
cells/source/acknowledgements/results with their original Request, then prove every
current pointer identifies the latest committed cell. Ordinary reads join those
current references to immutable amounts. Damaged/missing/extra evidence refuses;
there is no repair/replay ledger or authoritative retained Python projection.

Worker-owned reads are `read_polr_confirmation_proposal(export_id)`,
`read_polr_manual_context(task_id, work_date, *, cutoff_utc_us)`,
`list_polr_confirmation_batches()`, `read_polr_confirmation_batch(batch_id)`,
`read_polr_current_cells(task_date_keys)` and
`read_polr_day_status(task_id, work_date, *, cutoff_utc_us)`.
Manual context always validates task/date/cutoff and reviews the current prior;
optional current accounting failure is reported with unavailable quantities and its
original diagnostic, without inventing values or blocking independent manual entry.
Immediate day feedback reuses shared exact accounting and the Stage 3A allocator
under one explicit cutoff/committed weekday, including full-week adjustment. It is
not a Stage 3D dashboard or coverage/reminder implementation.

The same owned Timesheet window has inline source review, one-cell manual entry
and read-only confirmation history. Source amounts cannot be edited. Positive-only
defaults include equal values; zero is explicit. Scrollable source/acknowledgement/
history areas retain exact UUID/date context. Selected conflicts get independent
unchecked controls; unchecking removes consent, and Refresh review clears it.
Manual task/date changes invalidate prior readiness; decimal validation retains
drafts. Defer clears volatile review only and writes nothing.

Worker read kinds `polr_proposal`, `polr_manual`, `polr_day`, `polr_history`,
`polr_batch` use separate view tokens and identity checks. Mutations use the existing
owner pending Request/mutate/reconcile path. One temporary `_PolrSubmission` aliases
that same Request/token/origin and retains the authoritative Outcome before any
widget effect; it is not another coordinator. Executing/uncertain submissions lock
review changes and ordinary abandonment. Known rollback/unavailability preserves
review; stale prior requires explicit Refresh. Exact Retry/Reconcile freezes batch,
request and content even if the originating widget disappears. The existing owned
default-No exceptional exit remains available; no exit undoes possible commitment.
Known success survives result/read/control failure, permits Close/renewed review,
and refreshes current review/status without rewriting old exports or Actual.

### Connected Stage 3D reconciliation and calendar reminders

`timesheet.scope_labels`, `calculate_scope` and `scope_basis` extract the existing pure UUID
selection/full-week basis calculation shared by frozen preparation and current
reconciliation. They use the existing `accounting.calculate_daily` and unchanged
`polr_allocation.allocate_week`; no new Candidate, renderer, UUID, clock or file
inspection belongs in reconciliation. `reconciliation.project` composes detached
current facts, stable project/name/UUID/date ordering and joined latest confirmation
references. One accounting pass covers visible and optional frozen scopes, with allocation
only for their distinct required weeks; intervening unrequested weeks are not
allocated. Context dates never become extra selectable report cells.

`TimerService.read_polr_reconciliation(*, cutoff_utc_us, period="this_week",
start_date=None, end_date=None, scope_kind="all", task_ids=(), source_export_id=None)`
uses one existing read transaction to capture dataset/zone/week, retained task/project
metadata, effective mixed work, active timer, latest immutable confirmation amounts
and optional validated registered source/committed sequence. It reuses existing
integrity validation once, adding no second full-history validator. Pure projection
follows that snapshot with the explicit cutoff and no further observation.

The detached result carries applied dates/scope, daily cells, task/week and cross-task
summaries, visible totals, coverage/outstanding counts and optional source comparison.
The [semantic owner](EXPORT_EVIDENCE_CONTRACT.md#displayed-reconciliation) defines
classification/precision. Unknown retains NULL amount/identity; explicit zero keeps
its batch. Weekly coverage counts individual applicable cells, not net gaps. Every
intersecting task/week retains seven-date context, exact target/adjustment and known
confirmed subtotal; partial scope cannot claim a complete-week review. Cross-task
summaries sum task targets/adjustments and cell-rounded Actual, never re-round a
combined week or add project groups. No derived status is persisted.

Source comparison retains the export's original scope/labels/amounts/basis. Current
suggestions use the current convention, displaying both week starts if changed.
`CURRENT_SUGGESTION_DIFFERS_FROM_FROZEN` and `NEWER_DIFFERING_CONFIRMATION` are
additional flags; they neither replace base daily classification nor invalidate
immutable exports or bypass existing Stage 3C stale-source acknowledgement rules.

The same owned modal Timesheet contains Reconciliation with independent This week/
Last week/Custom, All/Selected UUID drafts, owned inline calendars and explicit
Apply/Refresh. Read tokens, dataset/cutoff/scope/source checks reject obsolete results.
Draft edits invalidate readiness immediately. Complete strings are prepared before
widget replacement; partial output is hidden/untrusted, with original diagnostics.
A failed read can retain previous trusted rows only under their previous as-of label.
Scrollable daily and full-week summaries distinguish current/frozen/confirmed values,
precise adjustment, partial scope and incomplete known subtotals. Copy Suggested
copies an absolute two-place quarter value on Tk, not Delta or submission evidence.
Navigation reuses saved-report/source/manual confirmation interfaces. Review current
confirmation reads the selected known cell's immutable batch, including manual/zero
confirmations without an export; no new editor,
Toplevel, mainloop or pending-request coordinator. Close remains reachable at the
supported minimum size. Timers and normal worker delivery continue under modality.

`read_polr_reminder_status(*, cutoff_utc_us)` captures the same facts and dismissal
metadata in one read transaction. It uses the same projection/classifier: previous
reporting week on every dataset-local day; current reporting week only on civil
Monday/Friday, independently of the committed reporting-week start. Empty unused
cells require no invented confirmation; worked zero-suggestion Unknown and opposing
daily mismatches remain outstanding. Failure is unavailable, not proof of all-clear. If the metadata snapshot is
readable but calculation fails, the result preserves that date/context and original
diagnostic with unavailable counts/due (NULL), never fabricated zeros. Unreadable
authoritative snapshots remain read errors. This permits truthful same-day
dismissal suppression across restart independently of calculation availability.

`dismiss_polr_reminder_today(local_date, *, request_id, action_utc_us) -> Outcome`
validates a canonical real date against the accepted instant in the dataset zone,
then updates the sole metadata field through existing BEGIN IMMEDIATE/receipt/
COMMIT handling. Same-date no-op creates no receipt. Exact old retry resolves its
receipt before reapplying; uncertain commitment retains the original pending Request.
No work, confirmation, export, file or timezone mutation occurs. New dates expire
suppression by comparison, never by cleanup writes or absent-day notification replay.

`ChronicleApp` adds the compact Open Timesheet / Dismiss for today banner and explicit
Recheck POL-R. Startup readiness, relevant committed mutations, local-date transitions
and recheck queue worker kind `polr_reminder`. One in-flight token plus a latest
requested observation coalesces superseded reads; older/session-mismatched results
cannot replace current status. The ordinary tick detects date changes without
per-second reconciliation queries. Failures preserve previous trusted warnings,
label unavailable evaluation and permit explicit retry while Actual controls remain
independent. Known committed outcomes schedule the authoritative reread before
optional result presentation, so a widget failure cannot suppress that evaluation.
A verified reminder metadata read supplies one ordinary observed dismissal-date
view value, independent of calculation availability. Historical receipt results do
not overwrite that current metadata observation. It suppresses the same-day banner even when calculation fails before or after the
action; the ordinary status still reports unavailability, never clean truth.
Unverified pending mutations defer reminder delivery until resolution, retaining
the trusted state. No separate scheduler/thread/cache is introduced. Dismissal is
reflected only from authoritative metadata reads, never queue acceptance.
Opening/Save/confirmation do not dismiss. Banner opening prefers outstanding previous week, otherwise current
week, and presents Reconciliation through the existing single modal owner with a
fresh observation; other modals prevent competing construction.

Stage 3C is independently accepted for functional development by the later explicit
Stage 3D approval. This delivery requires independent review and Stage 3 functional
completeness adjudication. It establishes no external verification, native Windows,
suspend/power-loss, Stage 4 stabilization or Stage 5 pilot qualification.

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
