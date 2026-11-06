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
reconciliation and reminders. The later explicit Stage 4A GO instruction records
Stage 3 functional acceptance. The later Stage 4B GO independently accepts Stage 4A
recovery. The later Stage 4C GO independently accepts Stage 4B portable reliability;
subsequent independent review accepts Stage 4C cold compatibility inspection,
protected refusal and bounded owned SQLite-native rollback recovery for functional
development (schema 1 at that acceptance). Stage 4 remains IN PROGRESS; native
qualification is incomplete and Stage 5 is not started. Earlier
Qt/PySide6 and nested correction/global pending-retry plans are superseded, not fallback implementation instructions.

The accepted A/B1/B2/C1/C2/D foundation is retained. Package E implements fresh
schema 3 and reusable templates, independently reviewed under the F GO, with application ID
0x4348524E unchanged. Versions 1/2 are incompatible and never migrated, replaced or
adopted through a compatibility mode. F adds qualification evidence and tooling;
native qualification remains separate.

Package F tests connect the existing authorities on one disposable dataset:
worker recording/template/hierarchy → frozen registration/protected publication →
absolute confirmation → correction/reconciliation → worker backup → cold restore →
fresh owner and further work. Separate callback and XTest paths connect actual Tk
controls without another application coordinator. Production DDL, transactions,
uncertainty and accounting remain unchanged.

`scripts/qualify_stage4_windows.ps1` invokes `stage4_qualification.py` for opt-in
full-inventory evidence, separate from the frozen bounded collector scopes. It
reuses Job Object containment, watchdogs and dialog guards. Full callback tests may
create Tk; unknown dialogs receive no answer. The F2-only event sink exclusively
reserves an append descriptor and a separate health descriptor before pytest starts.
Hooks never reopen the event pathname. Captured low-level functions, locked complete
UTF-8 JSON-lines writes, explicit short/interrupted-write handling and sticky errors
isolate instrumentation from test filesystem monkeypatches. Final sync/close failures
produce a nonzero child result. The parent checks final health, sequence, digest,
complete events, actual JUnit, process/session agreement and cleanup; readable health
alone cannot establish successful finalization. No session/JUnit is synthesized.

Full collection retains original node IDs, collected source paths, fixture closures
and exact pytest-derived JUnit identities (including a legitimate empty classname).
Bounded membership uses the collected source relative to the reviewed repository,
not a node-ID basename. Frozen allowlists and fixture/dialog rules remain unchanged.
F2 partitions every node disjointly into supported `tests/rewrite/` plus the root
launcher bridge, a finite reviewed top-level legacy inventory, or UNCLASSIFIED.
Unknown sources block supported qualification. Supported and legacy partitions run
in separate owned sessions with separate manifests, arguments, logs, events, JUnit,
exit codes and cleanup. Their union must reproduce the original inventory exactly.
Legacy failure remains failure in the full-source result.

Recollection rejects missing/additional or duplicate node identities and any changed
resolved source path before execution. `inventory-mismatch.json` retains complete
expected/recollected identities, counts, duplicates, source changes and order
observations; event/console summaries show at most 50 entries per category with
explicit truncation. Order alone does not reject. Diagnostic write failure remains
secondary to the original mismatch and cannot manufacture a valid manifest or PASS.
The four formerly eager legacy UUID parameters are fixed canonical unknown values;
fixture authority checks retain their negative and read-purity semantics.

History details completion and Win32 focus observation are test-only diagnostics.
A details test settles queued selection events, observes the one actual action's
request and matching entry/task/token delivery, and requires rendered immutable
content. Cancellation, stale/wrong delivery and read/render failure are distinct
from success; a null token alone proves none of these. Focus observation distinguishes
Tk client HWND, its native top-level and foreign/same-process foreground windows.
No forced foreground activation, production History change or wrapper option follows.

Raw pytest outcomes and skip reasons remain immutable. Finite exact source/fixture
rules classify native applicability independently; unknown skips and missing required
capabilities prevent PASS. Linux XTest/POSIX omissions do not fill mandatory native
F3/F4 gates. Raw supported execution and delivery-aware supported qualification are
separate: only verified archive delivery can publish the latter as PASS. A legacy
FAIL can coexist with supported automated PASS but never with full-source PASS.
Exclusive manifest reservation, explicit link omissions, fatal traversal errors and
verified absent-target ZIP publication retain evidence on failure. See the
[native runbook](WINDOWS_OPERATOR_QUALIFICATION.md). None of this changes application
runtime, schema, receipts, frozen reporting or recovery authority.

## Small application and responsibility boundaries

One local application operates one selected local-disk dataset with one serialized
writer. Refuse unsupported second-instance writing; do not promise network-drive,
cloud-sync or multiuser safety. No server, cloud bus, ORM, generic command
framework, plugins or speculative enterprise layers.

Use shallow modules, splitting actual responsibilities rather than layers per class:

| Responsibility | Boundary |
| --- | --- |
| Bootstrap / source setup | Explicit CLI/headless recovery or zero-argument local selection; one Tk root, existing worker startup and readiness handoff. |
| Plain records, time and accounting | Typed values and pure calculations; import neither Tkinter nor sqlite3. |
| Explicit use-case services | Complete recording/edit/export/confirmation requests and transaction results through a narrow storage adapter. |
| SQLite adapter | Built-in sqlite3 connection/profile, relational reads/writes, constraints, transactions and request lookup; strict schema admission and protected fresh creation. No widget access or hierarchy migration engine. |
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
| Projects/tasks | Stable UUIDs, optional current membership and preserved archived identities/history. Target Delete removes only eligible unused structure under the administrative boundary below; B1 stores explicit archive metadata and no live soft-delete flag; C1 implements Archive/Unarchive; C2 implements guarded unused-only Delete. Projects own no work/timer. |
| Timed work | Stable entry UUID, task UUID, genuine UTC endpoints, current revision and deletion state. Closed spans positive; active timer represented explicitly without a fabricated stop. |
| Date-only work | Stable entry UUID, task UUID, civil work date and integer duration; no synthetic endpoints. Distinct shape and constraints. |
| Work revisions | Immutable typed prior/new revision facts, audit time, optional comment, ownership and deletion evidence. Current reference changes atomically with revision. |
| Active timer | Persisted task/start with database-enforced at-most-one active timer. Switch closes and opens atomically at the same accepted action instant. |
| Frozen exports/cells | Immutable export identity/scope/labels, exact UTF-8 text/digest, exact task/day Actual and displayed hundredths, suggested quarter counts and sufficient reviewed full-week basis/context. In-scope relational cells support confirmation without parsing text; out-of-scope basis is not extra selectable coverage. |
| Absolute confirmation batches/cells | Immutable batch identity/audit/source and selected task/day absolute integer quarter counts, reviewed prior identity and exact cell-specific acknowledgement. One batch is atomic. No arbitrary hundredth confirmations. |
| Current confirmed references | Each known task/day points to its latest committed immutable confirmation cell/batch; absence means Unknown, an explicit zero row means known zero. No additive confirmed balance. |
| Committed request receipts | Unique request identity, strictly comparable request content and committed result, atomically tied to the use case. Not file-availability state. |
| Dataset metadata | Schema identity, explicit IANA timezone, selected week convention and one nullable canonical reminder-dismissed local date. No computed status/summary ledger or legacy import. Current supported runtime is exact fresh version 3; no old layout is accepted. |

Use enforced foreign keys and appropriate STRICT, CHECK and UNIQUE constraints;
validate bounded integer/date ranges and shapes in services as well. Stage 1A SQL
lives in `src/chronicle/sqlite_store.py`; shallow modules and typed use cases live
in `src/chronicle`. Optional feature tables are not created early. Frozen exports
and confirmation references belong in that initial integrity design even before
their UI is delivered.

## Transactions and exact request reconciliation

Explicit services own complete use cases. For ordinary retained mutating requests
(schema-3 mutations other than project/task/template Delete):

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

C2 unused-entity Delete permits erasing only exclusively owned
administrative requests after complete dependency proof. Its
[bounded exception](#unused-entity-deletion-and-receipt-boundary) deliberately
does not promise historical retry recovery for erased requests. It introduces no
tombstone/registry and changes no surviving or protected request guarantee.

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
datasets exist; no migration or old-schema compatibility is provided. The executing
schema is now exactly 2. Schema-1 files/backups refuse and remain protected.
Cold compatibility inspection below is diagnostic only, not a conversion route.

Stage 4A implements online consistent backup on the existing worker-owned source
connection through `sqlite3.Connection.backup()`. A live main-file copy is never a
backup. Cold restore installs a validated image only into a previously nonexistent
directory and exits before Tk/worker/session construction. Hierarchy will use fresh
creation, not an upgrade path; exact release paths/cutover remain Open.

Filesystem observations retain the raw six-field tuple (device, inode, mode,
size, mtime_ns, ctime_ns). Small shared helpers in `timesheet_files` distinguish
usable nonzero device/file identity plus suitable type, complete same-domain
stability, and pathname-to-descriptor binding. POSIX binding retains all six
fields. The provisional Windows binding requires identical device/file IDs,
type, size and mtime; it permits only pathname synthesis of executable mode bits
and compares birthtime_ns when both observations expose it. It does not equate
pathname legacy creation-time ctime with descriptor change-time ctime. Each
domain still retains all six before/after checks, with bounded complete reads
and byte/digest verification where required. Unknown identity fails closed;
content equality cannot establish ownership. Stage creation-to-completion
ownership checks intentionally compare identity/type rather than changing size
or timestamps. Startup admission remains bounded, cold inspection retains full
fingerprints, and native rollback ordering is unchanged.

Unit A's comparison candidate is independently accepted for portable development
at `ca78e2a833592a780772624f104d6c68c03feda0`. It follows inspected
[CPython Windows implementation semantics](https://github.com/python/cpython/blob/v3.15.0/Modules/posixmodule.c)
and [descriptor metadata implementation](https://github.com/python/cpython/blob/v3.15.0/Python/fileutils.c).
Actual Windows/NTFS field agreement and focused native behavior remain UNVERIFIED,
pending the October 26 metadata observations and qualification; Linux and synthetic
observations do not establish Windows compatibility.

### Consistent backup and cold recovery

`SQLiteStore.backup(destination)` refuses an unhealthy or transactional connection;
the worker also refuses backup while a mutation outcome is unresolved. The main
Backup Chronicle command owns one callback-driven local-modal dialog. Construction
and destination cancellation write nothing. The application retains the accepted
request UUID/token, destination and outcome independently of the view. Busy I/O
blocks duplicate requests, destination edits, ordinary Close/exit and competing
mutations; normal Tk/timer observation continues. Worker serialization captures
committed facts without a Stop, work mutation or backup receipt.

`backup_restore.validate_image(path)` independently opens a stable regular image
read-only, checks the SQLite header/journal profile before opening (WAL must not
create sidecars), then requires DELETE, full `integrity_check`, foreign keys and
the shared `SQLiteStore._verify_complete` gate: full integrity, `_verify` and
`verify_receipts`. The latter additionally checks canonical
request/result content and work/creation/revision/active-correction associations
against their immutable inputs. Existing complete export and confirmation validators
remain authoritative, including whole prior chains/current references. There is no
competing schema, renderer, repair, persisted status or validation cache.

The ordinary SQLite image contains all dataset metadata, work/revisions, active
timer, committed requests, frozen reports/basis/scoped cells, confirmation batches
and current references. External text copies are not bundled. Private O_EXCL staging
in the chosen existing parent receives the SQLite backup, successful connection
close and file fsync. Complete independent validation and stable identity/digest
checks precede exclusive hard-link publication. Final independent validation,
complete byte comparison/digest and stability checks precede verified completion.
All existing destinations and active-dataset paths/resolved aliases are rejected;
there is no matching reuse, overwrite consent or unsafe fallback for backups.

Operation phases are volatile NOT_STARTED, STAGING, VALIDATING,
PUBLICATION_ATTEMPTED, PUBLISHED_UNVERIFIED and VERIFIED. A lost publication
acknowledgement triggers diagnostic reinspection, never deletion of final output
or a false claim of absence/success. Cleanup removes only proven-owned staging;
cleanup faults attach to the primary diagnostic. A verified image with failed
cleanup retains that fact but the overall operation reports the error. Explicit
`--verify-backup` can inspect a possibly published image later.

`--restore-from BACKUP --data-dir NEW` validates stable source evidence/digest before
reserving the absent directory, acquires DatasetLock, backs up read-only source
into private staging, validates again, rechecks source stability, syncs and publishes
the database filename exclusively. Unexpected objects abort; unknown files and the
reserved directory are never swept away. Final independent validation precedes
ownership release and a ready result. `--verify-backup` validates only. Both modes
reject create/timezone combinations; neither constructs a root, worker or app.
A subsequent ordinary launch creates fresh owners, connections and tokens, with no
prior pending request, callbacks, preview or confirmation draft. The persisted
active timer resumes unchanged, including its existing clock-warning behavior.

Restore retains the dataset UUID and every immutable identity/value; the original
and clone must not be operated as competing live authorities. It does not remove
the original, rematerialize reports, confirm POL-R or alter dismissal dates.
Existing file-status/republication and date-derived reminder rules still apply.
These bounded local-disk identity/metadata checks and supported hard links do not
promise hostile-directory, network-filesystem, atomic compare-and-publish or
hardware power-loss protection. Native Windows/NTFS and remaining Stage 4
stabilization still require qualification; no in-place/live restore is selected.

### Cold compatibility inspection and future transition boundary

`backup_restore.inspect_dataset(directory) -> CompatibilityResult` uses one separate
read-only/query-only SQLite connection and a read transaction. It never acquires
DatasetLock, starts Tk/worker, changes schema/metadata or performs recovery. The
operator must close other sessions. It rejects explicit network paths, source or
ancestor directory aliases, database symlinks, unsuitable objects and present
journal/WAL/SHM sidecars. The header/fingerprint path rejects WAL before SQLite
can create sidecars. Bounded regular-file reads, before/after directory/file
metadata and complete digest checks reject detected changes; they are not writer
exclusion or arbitrary hostile-filesystem protection. Supported storage is trusted
local disk; these observations do not qualify unknown network mounts.

Detached results contain classification, candidate path, trustworthy observed
application/version/profile, supported version, completed-validation/startup flags,
concise explanation and original diagnostic. No cursor/connection is returned as
an API field and no result is persisted. Failed close prevents completion; original
errors keep secondary cleanup notes. No replacement connection conceals uncertainty.
The CLI reports deterministic statuses documented in [RUNNING.md](../RUNNING.md#cold-dataset-inspection).

| Classification | Required observation |
| --- | --- |
| SUPPORTED_CURRENT | Chronicle identity/version 4, supported profile, exact DDL/STRICT/guards, complete SQLite/FK and all Chronicle evidence/receipt validation, successful close and stable final fingerprint. |
| OLDER_UNSUPPORTED / NEWER_UNSUPPORTED | Chronicle identity and differing version marker after generic SQLite integrity/FK checks; current Chronicle semantics are not applied to an unknown version. A lower marker does not prove an authentic older schema. |
| UNSUPPORTED_LAYOUT | Current identity/version with a different DDL signature. The selected schema policy supplies exact DDL verification, separate from semantic checks; SQL comparison preserves quoted literals. |
| FOREIGN_DATABASE | A trustworthy SQLite application identity differs. |
| UNSUPPORTED_PROFILE | An identifiable unsupported operational format/profile, including WAL header selection; full Chronicle integrity is not claimed. |
| UNSAFE_OR_UNAVAILABLE | Unsuitable/unstable/unreadable source, outstanding sidecar, integrity/evidence failure or inspection/cleanup uncertainty. A damaged lower-marker file is not accepted as an older schema. |

Normal startup remains a separate owner path. Bounded regular-file/header/profile
and metadata admission replaces whole-file startup fingerprints. WAL headers and
unsuitable paths refuse before writable access. Clean, sidecar-free candidates
still pass non-mutating `_probe`/selected complete verification before lock creation,
preserving unsupported-data refusal without new files or configuration writes.
An outstanding regular rollback journal defers SQL validation until DatasetLock
is held. For schema 4 the paired private recovery preflight below must fully verify
the recovered v4 copy and cleanup/source stability before any original `mode=rw`
connection may recover its supported committed image. Admission is repeated under
ownership; raw header application/version markers are never committed authority.
Chronicle never parses, replays, removes or repairs journals itself.

The owned connection then runs the selected complete verifier in a read transaction, requires
the actual DELETE profile and checks the recovered identity before configuring
and verifying DELETE/EXTRA/foreign keys. Complete validation includes full SQLite
integrity, exact DDL/STRICT/guards, metadata/lifecycle, immutable work revisions,
frozen exports, whole confirmation history and exact receipt content/associations.
Only then may the worker publish readiness. Native recovery may change physical
pages and remove the journal; it does not authorize Chronicle mutations or make
an unsupported recovered schema/evidence acceptable. Failed probe/ordinary
connection cleanup retains its existing handoff and ownership until explicit
worker cleanup succeeds. Cold inspection remains non-recovering with complete
fingerprints; backup image validation reuses the complete gate and cold restore
still validates before directory reservation. No schema definitions or version
markers are changed, and no fallback or migration registry exists.

The earlier Stage 4C hypothetical transition safety requirements remain historical
context, not a migration obligation. The latest project-nesting decision selects
fresh schema 4, application ID 0x4348524E. No schema-3 import/conversion reader,
transformation staging, pending-conversion marker or converted-copy activation
controller is selected. Original v3 files stay untouched. During A/B/C1/C2,
ordinary creation/admission/backup/restore and supported native rollback remained
exact schema 3; A/B/C1/C2 did not activate an ordinary v4 opener/writer.

Package E implements fresh-v4 activation through the existing owner, with explicit
version policy in [schema_policy.py](../src/chronicle/schema_policy.py). Legacy
schema-3 DDL/verifiers and explicit test selection remain intact; ordinary store,
worker and startup default to 4. No public version selector or migration exists.
Clean v3 refuses before writable opening. Raw journaled headers are not authority.
[recovery_preflight.py](../src/chronicle/recovery_preflight.py) copies the admitted
DB/journal pair under DatasetLock to an exclusive private directory outside the
original; checked handles, bounded initial sizes, source metadata and digests
record the copy. SQLite recovers only that pair. Full v4 schema/semantic verification,
successful private connection/file cleanup and repeated source stability checks
must finish before the original opens writable for native SQLite rollback under
the same lock. The recovered original passes the full gate again before ready.
Unknown private files are never recursively removed; failed cleanup retains its
owner and lock for the worker's explicit cleanup retry. The private copy never
becomes the dataset. Cold inspection remains read-only/non-recovering. Native
Windows/NTFS and power-loss qualification remain separate gates.

## Package E production schema-4 ownership

[schema4_runtime_service.py](../src/chronicle/schema4_runtime_service.py) is a thin
Request/read facade over caller-owned C2 services. SQLiteStore alone owns BEGIN
IMMEDIATE, receipt lookup, mutation, insertion, full independent final verification,
COMMIT, rollback and retained connection cleanup. Exact prior receipt lookup precedes
stale-state checks; no-op rolls back without a receipt/sequence advance. Ordinary
uncertainty reconciles the same Request via an independently verified read probe.
Delete uses the existing separate no-receipt path and C2 survivor proof; any uncertain
COMMIT permanently blocks mutation/retry/backup in that session. Presence is current
state only; explicit exit/reopen and a fresh review/typed DELETE remain required.

The same DatabaseWorker serializes all reads/mutations/backup and publishes readiness
only after exact DDL, complete semantic and operational-profile validation. The
facade uses store-owned read snapshots and the existing C2 accounting/history and
shared Timesheet/POL-R/file engines; [service_reads.py](../src/chronicle/service_reads.py)
extracts the existing day calculation without duplicating allocation mathematics.
Production imports no CandidateAdapter or CandidateBridge. Tests reuse the pure read
dispatch but retain distinct transaction ownership/readiness. Normal and explicit
source launches use the same StartupWindow and one root/worker; explicit CLI still
never reads or replaces remembered selection. Supported backup/verify/restore now
select exact v4; the established exclusive publication, staged validation, source
stability, final readback and no-final-unlink rules remain unchanged.

## Implemented main and mini presentation

Main retains its 850x550 initial geometry and 720x420 minimum. Its outer toolbar
contains independent primary-management, secondary-action, display-settings and
guidance frames, avoiding shared column widths between unrelated rows. Primary
holds New Task, Rename task, Create project and Rename project; secondary holds
Move / Reparent, Mini mode, Delete and Templates, plus the schema-4 New child
project. The schema-4 root-project label remains on the same Create project
button/key/callback. Settings retain the existing week/period/sort/Keep Mini
controls. The hint wraps at 680 pixels below them. Widgets are constructed once;
resize changes no commands, bindings, eligibility, requests or persisted layout.
The same frames serve explicit legacy schema 3, ordinary schema4 and the isolated schema4-candidate.

`task_row`/`project_row` distinguish task:UUID, project:UUID and group:unassigned.
D projects the complete effectively active forest from the existing detached worker
snapshot under flat project groups: empty projects remain, task parentage is exact, archived descendants stay
in report accounting. No persistent tree or second calculation/connection exists.
New Task freezes selected project/group/parent UUIDs and reviewed versions before
name entry. Task selection means immediate child, not sibling/root; no selection
means Unassigned root. Depth-three/running-parent controls explain refusal, while
B1 performs final transactional eligibility checks. Parents retain direct History.

Main Individual/Cumulative use session Today/This Week and the existing report;
project Individual is a placeholder. Headline totals use application direct Actual,
never widget rollups. Failure recursively clears every nested row without repeating
a failed formatter; active identity/status remains and a later valid read recovers.

`_render` installs ancestors before children, reparents survivors before obsolete
ancestor deletion, then reorders only changed sibling lists and updates only changed
text/values/tags. UUID selection, expansion, period/sort and meaningful scroll persist.
A-Z uses casefolded sibling names and deterministic UUID ties. Active identity/full-
path changes reveal every ancestor once; ordinary reads respect manual collapse.
Committed creation/movement reveals/selects the accepted task after authoritative
refresh. Navigation never implicitly chooses a replacement for a hidden selection.
Green/red plus text distinguishes leaf Running/Stopped, Running descendant on task
ancestors, and an organizational running-task group. No parent owns a timer.

`move_window.py` is one owned modal with a frozen detached source/destination review.
It builds exact existing B2 fields using `movement.snapshot`, calls the existing
`movement.plan` only for advisory eligibility/no-op diagnostics, and dispatches one
normal Request through the worker. It does not implement SQL or another planner.
Full paths/UUIDs distinguish duplicates. Final B2 validation remains authoritative.
Commit updates current grouping through a fresh read; no-op says unchanged; rejected
review requires closing/reopening. Unverified Move keeps the original Request/token
in ChronicleApp for exact Retry/Reconcile or explicit default-No exceptional exit.
Destroyed/disposed windows cannot lose or retarget accepted requests. The app checks
the exact accepted Request object and delivery token, then settles the matching
dialog through `accept_result_state` before optional presentation notifications.
This method assigns only Python phase/outcome state; `record_result` renders it.
A rendering exception retains the original diagnostic and attempts existing control
restoration without changing the settled outcome, grab or focus. Terminal verified
results remain normally closable; unverified results retain the original Request
and exact Retry/Reconcile guard. Secondary control/diagnostic failures are attached
to the primary error. No automatic close or forced grab release is used. This is
separate from C2's no-retry uncertainty contract. All existing modal/backup/shutdown
exclusions apply; main/mini/Archived Items cannot bypass the owned Move.

Main has no changing started-at/elapsed/as-of label. One-second exact UTC safety,
date/reminder/coalesced worker observation continues; changed-value comparisons
retain minute-oriented visible updates and immediate Stop/Switch capture.
Mini uses the same active eligible leaf, otherwise selected eligible leaf, and the
same Individual Today report. Keep Mini Open defaults Off/session-local; Show Main
closes mini only when Off. Topmost drops while blocked without focus/grab theft.
`app.py` binds one double-click handler only to the Treeview. Coordinate region,
element and UUID-row checks exclude indicators, headings, groups, parents and
stale/archived tasks. Selection and eligibility are revalidated before one existing
Start/Stop/atomic Switch call; rejected events allocate no request/time observation.
`mini_mode.py` uses a 280x125 minimum with natural font/DPI-aware layout, bounded
presentation-only name shortening, a small green/red indicator, Individual Today
and two actions. It removes the prominent banner and routine status copy. Existing
report, pending/executing, worker/cleanup, reminder and typed mutation outcomes
provide concise diagnostics; synchronous preparation/queue errors populate the same
typed outcome field. No independent recovery state is added. Read-only Show Main
has a separate modal/grab guard so unresolved writes still reach Main while all
mutation restrictions and original request identities remain in force.
No additional root, timer, worker, schema or persisted UI settings are introduced.
Native Windows theme/topmost/focus/operator qualification remains outstanding.

## Selected project nesting and pilot usability

The future project architecture and implemented usability slice follow the
[selected organizational model and UX](TIMESHEET_REQUIREMENTS.md#selected--independent-projects-and-tasks).
The delivered A–F task hierarchy remains historical. A/B/C1/C2 kept ordinary schema 3
while building the isolated v4 definition and services. E now selects that exact
fresh schema-4 definition through the existing SQLiteStore, without migration/import/
copy transition. Old data refuses rather than being recreated, cleared or transformed.

Use one self-referencing Project adjacency relation: stable project UUID plus
optional parent-project identity. Root parent is absent; duplicate display names
are valid. No separate Customer relation is needed. Keep existing task project
membership and task ancestry distinct: a project can hold both child projects and
direct task branches. Project nesting has no fixed product depth limit; the
three-task-level limit remains independent. Resource/SQLite safeguards must bound
work with explicit refusal, not silently impose a small business depth or truncate
paths/descendants. Use cycle-safe traversal appropriate to deep project forests.

### Package A isolated schema-4 candidate

[schema_profiles.py](../src/chronicle/schema_profiles.py) owns target version 4,
the unchanged application ID and explicit complete relational DDL. Project
parentage is nullable/canonical, references projects, rejects self/cycles and has
an index. Candidate-only recording, active ancestry and project Archive/reparent
SQL guards traverse every project ancestor without a fixed depth cap. Other
protected evidence definitions remain unchanged. Runtime v3 DDL and its
administrative operation set remain unchanged; importing the candidate registers
no worker operation or launcher path.

`create_candidate` accepts only an empty caller-owned disposable file-backed
SQLite connection, configured DELETE/EXTRA/FK. It is not an existing-dataset
opener. `verify_schema` checks exact definitions/profile; `verify_structure` adds
SQLite/FK integrity and complete project/task forest/active eligibility checks.
`verify_candidate` now delegates to C2's complete candidate semantic verifier and
always reports ordinary_startup_permitted=False. Valid rich work, templates,
configuration and frozen evidence are supported; malformed, unknown or incomplete
evidence refuses. Complete candidate semantics do not grant worker/startup,
backup/restore or native runtime admission.

`hierarchy.ProjectForest` uses iterative complete coverage, immutable detached
parent/children/root/order/archive observations and on-demand complete paths and
descendants. Task observations are a separate candidate helper; original v3 task
functions and MAX_TASK_LEVELS=3 are unchanged. No eager all-path cache is stored.

`administration.verify_schema4_history` independently reconstructs native-v4
root/child creation, project movement, selected-only lifecycle and existing task
creation/rename effects in commit_seq order, with exact canonical bytes, UUIDs, versions, creation owners,
relationships and timestamps. It neither translates v3 history nor supplies B's
transactional executor. A no-op move cannot have a committed receipt. The candidate
administrative set explicitly lists the approved 18 operations, adding only
create_child_project and move_project_subtree to v3's original 16. It is independent
of future runtime classification changes and generates byte-identical candidate
DDL. Classification is not Delete-retirement permission.

Request format 1 and canonical result encoding remain. Root creation uses
project_id/name and returns project_id/version=1. Child creation adds
parent_project_id, expected_parent_version and reviewed_parent_ancestry, ordered
root-to-parent with project_id/expected_version/parent_project_id members. Project
movement has exactly project_id, expected_version, source_parent_project_id,
destination_parent_project_id, expected_destination_parent_version,
reviewed_source_ancestry, reviewed_destination_ancestry, reviewed_projects and
reviewed_tasks. Source ancestry ends at the source parent; destination ancestry
ends at its parent; root paths are empty. Project members are complete and
UUID-sorted with identity/version/parent. Task members are complete and UUID-sorted
with task_id/expected_version/parent_task_id/project_id. A committed result is
project_id/version/parent_project_id; only the moved project's version/time/parent
changes. Child links and immediate task memberships remain unchanged.

These remain isolated candidate contracts. Package B implements the three project
operations below; C1 extends lifecycle/accounting. UI, protected/reporting
admission, v4 source startup and Windows acceptance remain outstanding.

### Package B candidate project services

[project_services.py](../src/chronicle/project_services.py) exposes
`apply_project_operation(connection, request, CandidateProjectContext(dataset_id))`.
It requires an already owned transaction, exact candidate schema/profile and
dataset identity. It opens/closes no connection, owns no path and never begins,
commits or rolls back a transaction. No SQLiteStore/worker/startup route changes.
The caller resolves exact committed requests before current-state evaluation.

Root/child creation uses the accepted UUID/time/name normalization and exact A
contracts. Child creation reviews every root-to-parent identity, relationship and
version, refuses inherited archive, starts at version 1 and leaves the parent
unchanged. Movement reviews both ancestries and complete UUID-sorted descendant
project/task observations. It validates the full current/proposed forest, cycles,
versions and effective archive before writes or no-op recognition. Only the source
project's parent/version/updated timestamp changes. Descendant project rows, task
identity/membership/parentage and all other facts stay unchanged. A fully eligible
same-parent move returns unchanged without UPDATE, receipt or sequence advance.

The service compares installed complete logical facts with pre-write expected
facts. Independent chronological replay remains in administration, not the
service's mutation plan. `verify_candidate_transaction` supplies the complete C2
semantic boundary for a caller-owned transaction; `verify_candidate` retains
its separate read-snapshot/rollback contract. C1 adds administrative lifecycle
replay; C2 extends complete protected/template/reporting verification below.
SQL-only placeholder fixtures still cannot establish complete evidence validity.

[project_candidate.py](../tests/rewrite/project_candidate.py) is test-owned
infrastructure for exclusively owned disposable files, not a supported runtime or
second worker. It uses BEGIN IMMEDIATE, exact receipt lookup/canonical comparison,
full supported pre-validation, service execution, exact administrative receipt
extension, independent final history verification, then COMMIT. No-op rolls back.
Existing commit sequences and all surviving receipt bytes remain authoritative.
Exact retry returns the original result before stale checks; conflicting content
under the same request UUID refuses.

Faults retire the old connection before independent readback. Verified exact
committed evidence recovers the original result after lost acknowledgement;
verified absence under test-owned exclusive ownership permits ordinary retry of
the same Request. Unverified cleanup/evidence reports unverified. No automatic
replacement request or Delete no-retry semantics is introduced. Killed-child
tests join cleanup before reopening. These are candidate transaction experiments,
not implementation of schema-4 worker coordination or power-loss qualification.
C1/C2 and D candidate presentation extend this foundation below. E fresh
activation/backup/restore and F integrated/native acceptance remain unimplemented.

### Package C1 candidate lifecycle and project accounting

[project_lifecycle.py](../src/chronicle/project_lifecycle.py) exposes
`apply_lifecycle_operation(connection, request, CandidateProjectContext(dataset_id))`
over an already caller-owned exact schema-4 transaction. A pure `transition`
calculates one selected row; one SQL UPDATE changes only is_archived,
archived_at_utc_us, version and updated_utc_us. No connection/transaction/clock/UUID
ownership or runtime registration is added. Exact arguments remain entity UUID
and expected_version; result remains entity UUID and new version. Archive stamps
the accepted instant, Unarchive clears the selected date, and repeated explicit
state validates the complete current structure before returning unchanged.

Archive checks every descendant project and every directly assigned task at all
three task levels, or every descendant of the selected task. Any contained active
timer refuses; unrelated active work is preserved. Descendant explicit flags,
versions, timestamps, adjacency and all work/frozen facts are unchanged. Complete
logical-fact comparison must succeed; the transaction owner rolls back on failure.
The existing test adapter dispatches lifecycle, compares the exact permitted row
and receipt extension independently, and retains B's transaction/reconciliation
contract. No second coordinator is introduced.

Candidate task observations expose depth, is_leaf, explicit_archived,
ancestor_task_archived, project_effective_archived, effective_archived and
eligible_for_new_work. ProjectForest's immutable archive mapping and complete
ancestry are reused. Pure candidate_project_ancestry, candidate_project_destination,
candidate_task_destination and candidate_active_in_project_subtree support future
reviews without cached mutable paths. A task destination checks inherited archive,
three-level parent capacity and a running parent; movement branch-height checks
remain the caller's responsibility. None has no project ancestor and remains a
virtual root/Unassigned context, never a persisted container.

Independent schema-4 replay reconstructs the four lifecycle effects in commit_seq
order without calling the service transition, verifies canonical bytes, versions,
accepted timestamps and full surviving project/task rows, and rejects retained
no-op or contradictory/missing history. Schema-3 replay is unchanged. Protected
timer chronology and complete protected evidence are supplied by C2 below; old
placeholder fixtures remain SQL/structural evidence only.

[project_accounting.py](../src/chronicle/project_accounting.py) exposes pure
`project_report(report, tasks, projects)` over one coordinated successful
accounting.calculate report and complete current forests. It retains the exact
cutoff and all original task Individual/Cumulative/application fields. It computes
report["project_direct"] from each immediate task Individual once, then folds
those groups in verified reverse project order into report["projects"] Cumulative.
Every real project has a valid zero when empty; None keeps independent Unassigned
amounts. Nonnegative signed-64-bit checked integer sums refuse overflow. Missing,
inconsistent or unavailable amounts refuse instead of becoming zero.

The projection does not split work, calculate local dates/DST, measure elapsed
time, round, allocate POL-R, read frozen submissions or persist totals. Existing
accounting.py owns attribution. Archive visibility does not discard retained
Individual work. Project reparenting changes live rollups while task/application
Actual remains unchanged. This C1/C2 execution split retains Package C's original
complete lifecycle/accounting/integration objective; C1 alone does not complete C.

### Package C2 complete candidate backend

[schema4_evidence.py](../src/chronicle/schema4_evidence.py) exposes
verify_transaction(connection) for an owned transaction. schema_profiles keeps
its separate-snapshot verify_candidate API and caller-owned
verify_candidate_transaction delegate. Both validate the exact unchanged v4 DDL,
profile, all tables, integrity/FKs, metadata/pinned timezone, forests, lifecycle,
work/revisions/active corrections, templates, frozen exports, confirmations,
configuration and complete retained request associations. Unknown operations or
malformed canonical bytes refuse. Candidate semantic_verified never grants ordinary
startup permission. Observed receipt sequence high water must cover retained
chronology; legitimate retirement gaps remain valid.

SQLiteStore's version-independent revision/receipt checks accept an explicit
verification context; default v3 calls preserve existing behavior. A named-row
connection view opens no connection and changes no caller row_factory. Existing
export, confirmation, calendar and POL-R validators remain authoritative. The
independent candidate chronology maintains historical active identity/start/version,
entry/revision state, task eligibility and configuration in commit_seq order. It
checks new work against the historical leaf/archive state, including full project
ancestry. Final current flags never substitute for historical eligibility.

[schema4_services.py](../src/chronicle/schema4_services.py) exposes
apply_operation(connection, Request, CandidateProjectContext) over caller-owned
transactions. A/B project contracts and C1 lifecycle remain unchanged. Shared
recording_services extracts the existing recording/configuration/export/confirmation
operation path; it owns no dataset, transaction or worker. The schema-3 TimerService
uses that same path with its original eligibility and request contracts. Shared
History reading and template SQL installation retain their existing domain logic.

Schema-4 create_task and apply_template require
reviewed_destination_project_ancestry. assign_task_to_project and move_task_branch
require reviewed_source_project_ancestry and reviewed_destination_project_ancestry.
Each is the exact ordered root-to-immediate-project list of
project_id/expected_version/parent_project_id members, or [] for Unassigned. All
existing UUID/version/subtree reviews remain required as applicable; parent moves,
renames/version changes and archive changes stale the new review. Schema-3 shapes
and Request format 1 are unchanged. Independent replay checks the same native-v4
contracts without interpreting v3 receipts as v4. Task movement stays separate
from project movement, preserves all work/flags and retains three task levels.

Template management and Apply reuse the existing pure task-only template model.
Complete destination ancestry, task capacity and running-parent checks precede
fresh task creation. Apply/Duplicate source snapshots remain self-contained after
proven definition erasure; historical uniqueness/provenance across erased intervals
remains deliberately unverifiable. No project template nodes or copied work exist.

[schema4_delete.py](../src/chronicle/schema4_delete.py) exposes preview and
apply_delete on the same caller-owned candidate connection. Project scopes contain
every descendant project and all immediately assigned tasks at every task level;
task scopes contain the whole task subtree. The detached deterministic review
contains selected rows, UUID-sorted scope/counts, source project ancestry, task
context, eligibility reasons, exact receipt retirements and irreversible context.
Exact typed DELETE and current review/version equality are mandatory. No receipt
is inserted, and sqlite_sequence is preserved.

Retirement is finite: project creation/child creation/rename/lifecycle owns only
its included project; task creation/rename/assignment/lifecycle owns only its
included task. Task movement requires every reviewed/changed task in scope.
Project movement requires every reviewed project/task and changed project in scope.
Apply requires its entire created task set. Passive ancestry is not ownership and
never overrides survivor proof. Template management retires only through separate
definition Delete. Unknown dependency classes, protected references (including
zero/deleted work and old frozen project context) or unprovable surviving history
block the entire scope. No receipt splits or protected retirement are permitted.

Tasks delete deepest-first, projects in reverse forest order. Full independent
semantics and exact complete survivor comparison precede COMMIT. The existing
test-owned CandidateAdapter supplies a separate no-receipt Delete method under
the same file ownership: any attempted-COMMIT uncertainty or unverified cleanup
blocks further mutation/review. Delete never enters exact-receipt reconciliation
or automatic retry. Presence is explicitly current state only; explicit exit and
reopen plus a fresh review/typed confirmation is required for another Delete.
No tombstone/ledger is added; fully erased administrative requests cannot promise
historical retry recognition. Normal creation uses fresh caller-supplied UUIDs.

Backend read_state, history, reconciliation and reminder consume one caller-owned
snapshot/cutoff and existing attribution/allocation engines. They return complete
relationships, explicit/effective eligibility, active identity, templates, direct
task History and task/project Direct/Cumulative values. Calculation failure stays
unavailable instead of becoming zero. Frozen reports remain independent of live
reparenting/renaming. No mutable report/hierarchy cache is persisted. D adds candidate rendering
below; E now connects ordinary fresh-v4 startup/backup/restore for review. F native acceptance remains pending.

### Package D candidate graphical integration

ChronicleApp retains the only Tk root, accepted Request owner and matching delivery
handler. The ordinary StartupWindow explicitly selects presentation_profile=schema4
only after production ready contains schema_version=4, semantic_verified=True and
ordinary_startup_permitted=True. Every snapshot must match. schema4-candidate is
still test-only and requires candidate_verified=True without ordinary permission.
The default direct-construction schema3 profile preserves explicit historical tests;
no schema4 request may reach that legacy presentation/worker. One shared structural
predicate serves both v4 profiles; candidate backup restrictions remain separate.
Mismatch refuses before the application can mutate.

[project_ui.py](../src/chronicle/project_ui.py) supplies pure projections and
detached selected-destination reviews. ProjectForest and existing task observations
own relationships/eligibility. Typed project:/task: UUIDs and one virtual
group:unassigned preserve duplicate names and independent namespaces. Main reads
task Individual/Cumulative and project Cumulative from the coordinated C2 report;
project Individual remains —. Application totals are never summed from tree rows.
All active project/task ancestors expand, while collapsed and archived work remains
in the report. Missing accounting remains unavailable.

[tree_install.py](../src/chronicle/tree_install.py) installs parent-first and moves
survivors before removing obsolete rows deepest-first, all iteratively. It retains
valid selected UUID, expansion, sibling order and scroll; unchanged rows receive
no unnecessary item updates. Sort A-Z is sibling-only/session-local. Pure tests
exercise depth beyond Python recursion; connected Tk tests use navigable depths.

Visible root/child project controls freeze destination identity/version/ancestry
before prompting; cancellation generates no mutation/request/action observation.
Successful creation reveals the authoritative new UUID. Rename preserves identity.
[ProjectMoveWindow](../src/chronicle/project_move_window.py) shares MoveWindow's
owned modal/request lifecycle, with exact B project requests. Its compact forest
shows Root and real projects, with advisory refusals, full selected paths/UUIDs and
one frozen source closure. It builds only the chosen destination's complete review,
not a subtree/plan or full path for every destination. Task Move remains separate
and includes both C2 ancestry lists. New Task and Template Apply include the C2
destination ancestry. All final stale/eligibility checks remain in C2.

Archived Items preserves complete project/task context, one typed UUID each and
the four existing sibling orders. Explicit rows use their own accepted archive
timestamp; inherited tasks prefer nearest explicit task ancestry before nearest
explicit project ancestry. Active context has no fabricated archive flag/date and
cannot be deleted/unarchived through context actions. Dates use the dataset IANA
zone and numeric offset. Complete Delete scope/counts and backend refusal reasons
are rendered without another eligibility engine. Incomplete parsing cannot enable
confirmation. Typed DELETE, final backend review equality and no-retry uncertainty
remain unchanged. Template definition Delete remains separately owned.

Mini, direct-task History, task-only reporting selection and frozen formats remain
unchanged. Live task-choice paths/UUIDs are display labels checked against current
relationships; they never alter TaskLabel or persisted frozen project context.
Both Move operations share app-owned correlation, exact retries and shutdown
handling; destroyed or failed presentation cannot orphan an accepted Request or
turn an authoritative commit into a rejection.

[schema4_ui_bridge.py](../tests/rewrite/schema4_ui_bridge.py) is test infrastructure:
one serialized thread/Message queue over the existing disposable CandidateAdapter
and C2 services. It emits verified readiness, real outcomes and read snapshots,
preserves the separate Delete path, and joins bounded cleanup. It is not a
production worker or public launcher. Unsupported test messages refuse explicitly.
No GUI software is installed to obtain acceptance. Without a usable display,
connected Tk tests remain skipped/unverified; model and real worker/SQLite results
are reported separately. E now connects production activation/backup/restore for review;
F native qualification remains outstanding. Stage 4 IN PROGRESS; Stage 5 NOT STARTED.

Remaining integration and selected backend contracts:

- Schema/FKs and independent cold admission validate project parent existence,
  canonical identity, same-dataset references and the full acyclic forest. A local
  FK/self-parent guard alone is insufficient for cycle or archive validation.
- Services review Create root/child, Rename and complete-subtree Move / Reparent
  with full ancestry/UUIDs and stale source/destination checks. One worker-owned
  transaction validates and commits all or none. Moving a project changes project
  ancestry, not task UUIDs, direct work or immediate task project IDs. Task-branch
  movement retains its existing reviewed semantics. No structural operation
  implicitly stops/switches the sole timer or makes an active task ineligible.
- Administrative receipt/replay and complete survivor validation must cover new
  creation/movement/version effects and parent associations. Specify the exact
  retained administrative dependencies during schema design; do not bypass replay,
  protected receipts or uncertainty rules to admit a graph.
- Effective archive state follows project ancestry and then task ancestry.
  Archive/Unarchive changes selected explicit state only; independent child flags
  survive. Active descendants block unsafe Archive/Delete. Unused-only Delete
  reviews the entire project-and-task dependency closure, typed confirmation and
  protected references before atomic removal; C2's no-retry uncertainty and strict
  survivor proof remain mandatory, not an automatic broadened retirement allowlist.
- Worker snapshots derive Main and Archived Items trees with project/task UUID
  rows, mixed direct tasks/child projects, sibling sorting, full destination paths,
  preserved valid expansion/selection and active-path expansion. Do not store a
  second tree, authoritative path cache or duplicated project-owned work.
- Shared reporting derives Direct project grouping from task Individual facts
  with that immediate project ID, and Cumulative grouping from the union across
  descendant projects. Each task contributes once, including retained parent or
  archived work when in scope; never aggregate task/project rollups again. Empty
  valid groups may be zero; unavailable reports remain unavailable. Timesheet and
  reconciliation grouping remain presentation over independent task/day units,
  not new external POL-R submission groups or scope expansion.
- Immutable exports keep their recorded project/task context and exact bytes,
  allocation, confirmations and receipts after any move. Future live ancestry is
  not permission to rewrite frozen context or invent ancestor evidence for old
  reports. Any new frozen representation needs its own reviewed format contract;
  the [existing mathematics](EXPORT_EVIDENCE_CONTRACT.md) remains unchanged.
- Backup, restore, ordinary open and cold validation must independently admit the
  exact approved future schema/forest/evidence while retaining original/destination
  protections. Template definitions remain task structures; destination eligibility
  must honor project ancestors' effective archive state at any project depth and
  the independent task-depth/running-parent rules.

The separate [pilot usability workstream](ROADMAP.md#selected-project-nesting-and-pilot-usability-workstreams)
is implemented for independent review. Eligible task double-click uses existing
Start/Stop and one atomic Switch request when another task runs; ChatGPT adjudicated
that previously Open case in the [usability decision](DECISIONS.md#pilot-usability-implementation-adjudication).
Existing eligibility, modal/pending/uncertainty and repeated-input guards remain.
Compact Mini targets about 280x125 (approximately 300x150 or less with default fonts),
while natural layout can accommodate fonts/DPI and exceptional diagnostics. It uses
the same active/eligible selected task and Individual Today report. Full resolution
stays in Main/owned modals; read-only navigation cannot enable mutation or bypass
modal ownership. Keep Mini Open remains Off/session-local and topmost remains
guarded. No new root, timer, worker or persistence is introduced. Native Windows
layout/input acceptance remains outstanding; E now connects the accepted nested
backend and D presentation to ordinary schema 4.

## Fresh hierarchy foundation

This section records the delivered task-hierarchy foundation under flat projects;
the project-nesting E architecture above supersedes its ordinary version selection.
The schema-3 interfaces/DDL below remain historical and explicit regression policy.

**A/B1/B2/C1/C2/D/E ACCEPTED FOR FUNCTIONAL DEVELOPMENT; F DEVELOPMENT REVIEW PENDING.**
Package E implements templates. Schema version 3 and application
ID 0x4348524E identified that fresh layout, together with exact DDL. Current E
selects exact schema 4 with unchanged application ID and an added nullable project parent.
Versions 1/2 refuse without conversion/replacement or clearing remembered selection.
Creation uses the existing exclusive new/empty-directory path. Current normal
owned native SQLite recovery and cold non-recovering inspection retain their
separate guarantees; recovery is not compatibility or migration.

`sqlite_store.py` owns the schema, SQL guards, complete forest and receipt checks.
`services.py` extends create_task with nullable parent and reviewed destination
versions. `hierarchy.py` reconstructs bounded paths/derived observations afresh from
one relational snapshot; it stores no projection or cache. `accounting.py` retains
direct task/day values and derives Individual/Cumulative/project dictionaries at
the same cutoff. `timesheet.py`/POL-R still use direct facts, never rollups.
D connects full main hierarchy and management to these same B1/B2/C contracts.
Legacy tree/template source remains interface evidence, never runtime authority.

B1 task creation is atomic with its administrative receipt. Child creation reviews
parent identity/version, effective archive path, depth and running state inside
BEGIN IMMEDIATE. Omitted child project inherits the parent's project; an explicitly
supplied value, including NULL, must match exactly. Root creation in a real project
requires its reviewed version; child creation requires the reviewed parent version
and checks a project version if supplied. Root creation has no parent review.
Parents receive no artificial version increment. Standalone-root assignment stays
available; that legacy assignment still refuses nested branches. B2 uses the
separate move_task_branch operation below.

Every new work identity and active insert has SQL active-leaf guards. Task edge
INSERT/UPDATE guards enforce matching project, no running parent and bounded
cycle/depth checks; archive-flag updates cannot hide an active timer. Complete
validation independently walks every forest and verifies active eligibility, not
just service results. Historical work remains owned by the same UUID and can be
corrected/deleted by immutable revisions even after it becomes a parent.

`committed_requests.receipt_class` is constrained to administrative/protected and
derived from the finite operation list in `records.py`, never caller metadata.
Implemented administrative operations are create/rename project, create/rename task
and assign_task_to_project. B2 implements move_task_branch; C1 implements
archive_project, unarchive_project, archive_task and unarchive_task. All other operations are
protected. SQL prohibits every receipt UPDATE and every protected receipt DELETE.
No B1 service deletes administrative receipts. Creation ownership FKs are deferred;
independent validation proves each creation owns a surviving entity and every
survivor has its creation, canonical result, contiguous version effects, current
name/membership/timestamps, explicit archive flag/current archive timestamp and
historically reviewed destination versions. Missing
or orphaned administration is damage, not an assumed prior Delete. This detached
validation installs no replayed hierarchy authority.

### Implemented B2 subtree movement

Schema 2 and its exact DDL remain unchanged. `TimerService.move_task_branch`
accepts task_id/expected_version, source_parent_task_id/source_project_id,
destination_parent_task_id/destination_project_id, expected_destination_parent_version,
expected_destination_project_version, and reviewed_subtree. The latter is a complete
UUID-sorted list of task_id/expected_version/parent_task_id/project_id records.
Names and widget rows never authorize movement. Destination versions are required
for present identities and NULL for absent identities. Request identity/content is
frozen once; existing receipt resolution precedes all stale checks.

Within the existing BEGIN IMMEDIATE, read the actual forest, subtree, destination
and active timer. Check complete review, source/destination eligibility, deepest
resulting depth, membership and active leaf. A true no-op rolls back without a
receipt. For cross-project moves detach every branch edge, update isolated member
projects, attach the selected root, then reconstruct internal edges parent-first.
Every statement respects existing FK/triggers; no disabled guard or committed
intermediate state. Same-project movement changes only the root edge.
Increment each finally changed row once with the accepted action timestamp; do
not alter creation/archive fields. Compare the complete installed rows and active
timer against the proposed final snapshot before the single receipt/COMMIT.
Result: task_id plus UUID-sorted changed_tasks records (task_id/version).

`administration.py` independently reconstructs chronological administrative effects
for validation only, including complete historical move scope and multi-row version
results. Protected timer receipt order supplies active context for historical move
checks. Compare every surviving creation/name/structure/version/timestamp with SQL;
missing, extra, orphaned or inconsistent effects refuse startup/backup validation.
This transient verification is neither runtime authority nor persisted projection.
C2 retires a move receipt only when its complete reviewed_subtree and changed_tasks
are within the deletion scope and strict retained-history verification succeeds.
No receipt is split or rewritten; surviving/protected requests retain exact results.

Movement preserves work/revisions, active entry/start, independent archive states,
frozen Timesheets and confirmations. Direct Actual/application totals do not change;
current parent cumulative/project grouping does. No Move UI or implicit Stop.

### Implemented C1 archive lifecycle and management

The four typed operations accept exactly the selected entity UUID and expected_version.
The existing Request carries the accepted action instant; callers cannot supply an
archive timestamp or descendant list. Resolve exact retries before reviewed-state
checks. A valid repeated explicit state is unchanged with no receipt/version/time
write. A changed action updates only that entity's flag, current archive timestamp,
version and updated timestamp; Unarchive clears the flag/time. Archive refuses an
active task anywhere in the containing project/subtree, with no implicit timer event.
Existing transaction/FK/trigger guards and full lifecycle checks remain enabled.

Independent administrative validation reconstructs archive state at each commit,
including active-timer eligibility and B2 movement in its historical context. It
compares final explicit state/timestamps as well as all former survivor effects.
Missing/altered/orphaned archival receipts refuse startup, inspection and recovery.
C1 introduces no receipt retirement or DDL change; C2 adds only the finite
unused-scope retirement path below, retaining the same schema.

`archived_window.py` is one modeless owner-created Toplevel consuming the same
worker-produced state/report cutoff as main/mini. It has no connection, timer or
accounting algorithm. Full original archived branches appear once per UUID;
independent branches under active ancestors carry their original path as context.
Own explicit time takes precedence, otherwise nearest archived task ancestor,
otherwise archived project time. Local display includes numeric UTC offset for DST
repeated hours; date sorting uses UTC microseconds. Four sibling/top-level sorts
retain UUID ties, expansion and surviving selection through in-place row updates.
Today/This Week uses existing Individual/Cumulative results, with unavailable
placeholders on failed calculation. Archive confirmation is default-No, identifies
the reviewed node/descendant count and never hides optimistically. Selected explicit
Unarchive and direct-task History use the app's pending Request and modal guards;
inherited-only Unarchive explains the owning ancestor. Closing/destroying the
modeless window cannot discard accepted work. History returns legitimate focus to
its live origin. Existing owned modals block main/mini/archived actions. C1 supplies no Delete;
C2 now adds the owned preview/confirmation below. D now connects movement and full nested active navigation; templates remain later.

### Relational shape and invariant ownership

Keep one SQLite authority, existing built-in driver/profile, one worker connection,
BEGIN IMMEDIATE/COMMIT/ROLLBACK, immutable evidence and exact atomic receipts.
No separate JSON tree, template JSON store, persistent descendant totals, closure
cache, new worker or Python hierarchy projection becomes authoritative.

| Relation / implementation status | Fields/relationships and purpose |
| --- | --- |
| projects | Historical B1/schema 3: stable UUID, name, reviewed version, explicit archive flag, nullable current UTC archive timestamp and owning created_request_id deferred FK; no project-parent column. No target soft-delete flag. Eligible unused Delete removes the row, not protected evidence. Duplicate names are valid; projects own no work/timer. |
| tasks | B1: stable UUID, optional project FK, optional self-parent FK, name, reviewed version, explicit archive flag/current UTC timestamp and owning created_request_id deferred FK. No target soft-delete flag; parent cannot be self. Duplicate names are valid. Eligible unused Delete removes the row under the dependency boundary below. |
| task structure | Parent adjacency is the authority. A subtree shares current project membership; root project may be NULL. B1 stores matching project_id on every descendant; root membership may be NULL. Parent adjacency is the only hierarchy authority, with tasks_project/tasks_parent indexes. B2 implements atomic subtree movement with the unchanged guards; do not add a second mutable membership authority. |
| template_definitions | Implemented E: template_id/name/name_key/version/is_archived/archived_at_utc_us/unique creation receipt/created and updated UTC timestamps. STRICT range/archive guards, partial unique name_key index for active rows; Python canonical casefold verified independently. |
| template_nodes | Implemented E: node_id/template_id/parent_node_id/name/position. Same-template composite deferred parent FK, unique positions/identities, canonical contiguous preorder, one or more nodes, three levels. Current graph is owned by definition version; no work/timer state. |
| existing evidence families | Retain direct task ownership in work_entries/revisions, active timer/corrections, frozen export/task/basis/cells, confirmation batches/cells/current references and committed_requests. Adapt fresh FK/guards to the reviewed fresh schema; never introduce parent cumulative work rows. |

Use canonical UUID, type, NOT NULL, FK, CHECK, UNIQUE and STRICT guards for local
shapes, self-parent refusal, positive versions, boolean states and retained
identities. Task UUIDs must not change, and work ownership remains immutable.
Indexes should serve parent-child lookup, project navigation, template-node lookup
and existing task/day/evidence readers; justify them by actual query paths. No
materialized daily/project/ancestor aggregate tables are selected.

Foreign keys alone cannot prove bounded acyclic ancestry, same-project consistency
when NULL is involved, effective inherited visibility, leaf eligibility, subtree
height at a new destination or absence of an active descendant. B1 service
validation uses bounded ancestry/subtree reads (recursive CTE or equivalent
transactional queries) and final lifecycle checks inside the write transaction.
B1 SQL triggers enforce local active-leaf/structural guards; do not claim a CHECK
with cross-row reads exists in SQLite. Future changes to these guards require separate review.
Full startup/image validation must independently establish the complete forest,
depth, membership and lifecycle invariants as well as every existing evidence
chain. Direct-SQL invalid states must reject wherever selected constraints can
enforce them; service-only guards must be identified explicitly in that review.

Real projects and virtual Unassigned both allow three task levels. Unassigned is
presented as a group, with no additional persisted project UUID; proposed root
membership remains NULL. No selection for New Task means an Unassigned root;
D's nested GUI uses the selected group/project or eligible parent task; A's
former project-scoped-only task selection is superseded.

Archive changes only the selected node's explicit flag and stores the exact
accepted UTC instant. Unarchive clears that flag/current timestamp, never descendant
flags or edges. B1 implements a CHECK binding explicit is_archived to non-NULL
archived_at_utc_us within the existing valid UTC-integer range. C1 supplies the four selected-node archive mutation services. Effective archived state comes from ancestry. Independently archived
nodes use their own timestamp; inherited-only nodes use the nearest archived
ancestor's timestamp for display. Convert with the stored IANA zone/DST rules;
date sorting uses the genuine UTC instant, not ambiguous formatted local text.
No historical archive-date journal is needed for this view.

Archive preserves membership/work/evidence and refuses an active containing
branch. Refuse Move on an effectively archived selection until unarchived;
allowed moves retain descendant archive flags. No inherited state is written
into every descendant. Delete is actual unused-subtree removal, not a flag or
restoration route; no target Deleted Items relation, identity tombstones or
materialized cumulative-time authority is selected.

### Explicit operations, atomicity and uncertainty

Extend the existing explicit TimerService/worker route, not a generic update-dict
API. B1/B2 implement creation/rename, standalone assignment, explicit subtree
movement, recording, C1 Archive/Unarchive, C2 unused-only Delete and detached reads
as above. E implements the template operations below on fresh schema 3:

| Use case | Strict reviewed inputs / result |
| --- | --- |
| Create project/task | Explicit new UUID/name and fixed destination project/parent UUIDs, plus destination reviewed versions; return created UUID/version. No selection creates an Unassigned root; virtual group selection carries no invented project UUID. |
| Rename project/task | Entity UUID, expected version and name; retain all relationships/work. |
| Move task branch / assign project | Root UUID and expected version, reviewed source/destination identities and versions, new parent/project (or selected root/Unassigned); return affected identities/versions. Validate current subtree, ancestry, membership and active eligibility atomically; refuse effectively archived selection and retain descendant states. |
| Archive/Unarchive project or task branch | Exactly project_id/expected_version or task_id/expected_version; operation name selects the explicit flag. Archive stores the Request accepted UTC instant, Unarchive clears current flag/time. Validate active descendants/inherited context and preserve independent child flags/work. |
| Preview/Delete unused branch | Implemented C2: read_delete_preview(entity_type,entity_id), then delete_task/delete_project with exact entity UUID, expected_version, frozen review and confirmed_text="DELETE". Complete closure/counts, cannot-undo warning and exact transactional recheck. No archive prerequisite, persistent Delete receipt or retained deletion state. |
| Create/Edit/Duplicate/Archive/Unarchive/Delete template | Explicit definition UUID/version and complete typed node set for changes; validate graph and active trim/casefold name uniqueness. Duplicate uses fresh definition/node IDs; applied tasks are independent. Definition Delete may follow Apply; only owned management history retires, preserving self-contained Apply/Duplicate evidence without tombstones. |
| Apply template | Reviewed template UUID/version, fixed destination UUID/version, and a frozen mapping of every template node to a fresh task UUID; return that same created mapping. Validate full prospective depth and leaf/active eligibility before insertion. |
| Detached reads | One consistent structure/state snapshot plus current direct daily facts at one cutoff; management/archived/template readers expose stable IDs/versions and archive-time provenance, never widget row indices as authority. |

Ordinary retained hierarchy mutations use the existing Request dataset/UUID/accepted
UTC instant and strict canonical arguments. Resolve an exact committed retry before stale checks;
changed content under the UUID rejects. New operations validate relevant source,
destination and definition versions plus current affected membership inside the
transaction. Recheck final invariants after all changes and before the existing
atomic receipt commits. New subtree/template writes, current references and receipt
are all-or-nothing. Template creation identities are frozen before queueing so an
uncertain Apply cannot generate a second branch on retry. Partial insertion,
stale review or depth/cycle failure rolls back everything. Unexpected post-COMMIT
delivery uses the same independent receipt reconciliation; rendering failure is
not rollback. Process death before/after COMMIT preserves the existing boundary.

An explicit Stop/Switch must commit first when an operation would make the running
task a parent or otherwise ineligible, or archive its containing branch. Delete
separately refuses any active timer and all protected recorded work.
No management service may perform an implicit timer operation. An eligible active
branch move must retain the same active entry/start and pass all destination
invariants, including effective archive refusal and independent descendant states.

### Unused-entity deletion and receipt boundary

**Selected and implemented C2; delivered for independent review.** No schema change,
recoverable deletion tier, tombstone, permanent UUID registry or deletion ledger.
`deletion.py` computes one volatile exact review from a validated consistent worker
transaction. A task selects itself/all current descendants; a project selects itself
and all currently assigned tasks. Virtual Unassigned is never a deletable entity.
Archive is not a prerequisite. Review includes dataset/selected identity and version,
name, explicit/effective archive state, complete task rows and passive ancestry/project
context, counts, exact original administrative request/result content, eligibility
and reasons. Canonical full values, not just a digest/count, authorize final recheck.

The exact retirement allowlist is create_project, rename_project, archive_project,
unarchive_project, create_task, rename_task, assign_task_to_project, archive_task,
unarchive_task, move_task_branch and E apply_template (only the whole unused created
task set). Project effects require that project in scope;
single-task effects require that task in scope. Creation's reviewed parent/project
is passive context, not a mutation of that destination. A move requires its entire
reviewed_subtree and changed_tasks within scope; mixed survivor effects refuse.
No retained request may be split, changed or orphaned. Classification alone is never
permission to retire a receipt.

Both relational facts and finite typed protected-request fields are checked. Any
work identity/revision (including deleted work), active/correction evidence, frozen
task/project/scope/basis/cell reference including zero, confirmation/current/prior
relationship or protected request reference blocks. Names/comments are not UUID
keys. Unknown/unclassified dependencies refuse. `administration.verify_records`
strictly reconstructs candidate surviving history with the same semantics used by
the complete current verifier: every remaining creation, result, version, name,
relationship and archive timestamp must agree. Missing destination context or a
survivor's required retired effect refuses. This is ephemeral verification, not a
runtime hierarchy projection or a mode that ignores missing entities.

`SQLiteStore.delete_unused` is a narrow alternative to ordinary `transact`, called
by the explicit Delete services only. It validates canonical Request/dataset identity,
uses the existing BEGIN IMMEDIATE, runs complete current validation, refuses a UUID
already owned by a retained request, recomputes the full review, compares it exactly,
requires confirmed_text == "DELETE" and refuses all blockers. It deletes task rows
deepest-first, then the selected project when applicable, then only the finite
approved administrative receipts. Foreign keys/triggers stay enabled. Complete
SQLite/FK/hierarchy/receipt/work/export/confirmation validation runs again. Compare
every surviving logical row and byte value with the pre-delete transaction snapshot,
excluding exactly the authorized entity/receipt rows, before COMMIT. No unrelated
metadata, sequence state, active identity, work or protected evidence may change.
Any failure before a definitively rolled-back commit preserves the whole original
logical state. No vacuum, dataset-file deletion or backup rewrite occurs.

Delete operations do not enter the persisted receipt allowlist and write no Delete
receipt at all. Known normal COMMIT completion returns only entity type/UUID and
removed project/task/administrative-request counts. Missing targets reject, not an
inferred old success. Retired administrative sequence gaps are valid. Startup,
cold inspection, backup verification and restore use the same strict survivor
verifier, without reconstructing erased unused entities or proving past deletion.

**Uncertainty is deliberately distinct from ordinary exact reconciliation.** Every
COMMIT exception is reported conservatively as UNVERIFIED; no independent receipt
exists to recover that request's historical result. Failed rollback/close retains
truthful diagnostics and existing connection/lock cleanup ownership. The worker
explicitly excludes Delete from reconcile-absent-then-execute and blocks mutation
while a Delete is unresolved. `read_delete_presence` is a read-only current-state
inspection through the same worker; PRESENT/ABSENT never proves the original
request's historical outcome or clears uncertainty. The app retains its accepted
Request in session, hides ordinary Retry/Reconcile, offers Inspect Delete state and
explicit Exit and reopen, and blocks further mutation. Only a subsequent fresh
selection/review/typed confirmation in a new session may initiate another Delete.
No unresolved-delete journal or persistent anti-replay marker is written. Ordinary
surviving/protected requests retain their exact retry/conflict guarantees. Erased
administrative requests deliberately cannot promise later recognition or prevent
an old raw request from reintroducing its UUID; normal Create generates fresh UUIDs.

`delete_window.py` is one application-owned modal Toplevel, with worker-backed
complete hierarchy/counts/refusal reasons and the cannot-be-undone warning. Typed
confirmation is exact and Cancel writes nothing. No optimistic hiding: only a
matching committed outcome followed by authoritative reads refreshes main/Archived
Items. Stale/refused decisions require a new preview. Pending context belongs to
ChronicleApp even if the view is destroyed. Known commitment precedes fallible
presentation, while lost delivery/worker stop retains uncertainty. Main, mini,
History, Timesheet, backup, focus/grab and shutdown guards remain authoritative.
D connects full nested active management; E adds the template boundary below.

### Package E template authority and erased provenance

`templates.py` validates canonical complete graphs, current definitions and finite
operation effects. `administration.verify_records` extends transient chronological
verification to definitions and Apply-created task batches; it is never runtime
state. Schema 3 adds only template_definitions/template_nodes and active-name/node
indexes, and replaces tasks.created_request_id UNIQUE with a nonunique indexed
deferred FK. Ordinary create_task still owns exactly one task; apply_template owns
its complete mapped task set. Application identity/profile/worker/locking remain.
Versions 1/2 are refused without migration, import, replacement or remembered-data
clearing. Current exact DDL, cold inspection, backup validation and restore all use
schema 3 and complete template/receipt verification.

create_template, edit_template, duplicate_template, archive_template,
unarchive_template and apply_template are finite administrative operations. Request
identity/content and original results remain immutable; exact retry precedes stale
checks and no-ops write no receipt. Edit replaces the current graph atomically,
retains continuing UUIDs and rejects reuse of removed IDs in retained history.
Duplicate freezes full source and a UUID-sorted fresh node mapping. Apply freezes
full source/version, exact destination/versions and position-ordered node/task pairs.
It validates the complete proposed forest/active leaf before parent-first insertion,
sets version 1/current archive false/accepted timestamps and one owning receipt,
and performs complete verification before commit. No parent bump or copied work.

Historical active-name uniqueness covers retained reconstructible states only,
under the explicit Package E clarification. Canonical names/keys, all retained
versions/archives/effects/results and contradictions are verified. While a source
history survives, Apply/Duplicate snapshots must equal that source at commit order.
If the source and its owned management history were erased, only the complete
frozen source graph, mapping/result and surviving entity effects can be verified.
No claim about erased earlier name/archive occupancy is made; those intervals are
historically unverifiable. Current name-key uniqueness always covers ALL active
definitions, transactionally and at independent startup/inspection/backup/restore.
No missing-management exception exists for a surviving definition.

Template Delete extends the existing C2 unreceipted boundary, not ordinary transact.
Its exact worker preview contains the graph/version/archive state, retained Apply/
Duplicate context and finite owned management receipts. Typed DELETE, BEGIN
IMMEDIATE, complete before/after verification and exact unrelated survivor equality
remain mandatory. Delete nodes, definition, then only its create/edit/duplicate/
archive/unarchive management receipts. Retain every Apply and surviving Duplicate
byte unchanged; unsafe survivor dependencies refuse. No tombstone, Delete receipt,
name registry or replacement proof is installed. An unknown COMMIT remains
UNVERIFIED, blocks mutation, allows readonly presence and requires explicit exit/
reopen; no destructive retry. Task/project C2 retirement additionally recognizes
apply_template only for its ENTIRE unused created set, never partial batch splitting.

`template_window.py` supplies one modeless manager and owned draft/Apply modals,
with app-owned accepted Request lifetime and exact tokens, existing modal/main/mini/
Archived Items guards, no SQL/Tk worker crossing and no nested authored event loop.
The graph editor holds only volatile drafts; normal refresh uses typed rows in
place. Duplicate IDs and Apply mappings freeze once; ordinary uncertainty uses exact
Retry/Reconcile. Definition Delete reuses the owned C2 preview/confirmation modal
and its distinct no-retry policy. Applied tasks enter existing D/B/C services as
independent tasks; all protected accounting/reporting remains unchanged.

### Archived Items presentation

Use one application-owned view through the existing worker/read-token and Tk
ownership boundary, not a second connection, timer or persisted archive index.
A consistent detached snapshot carries original project/task identities, parent
edges, explicit flags/current timestamps, effective ancestor provenance, versions
and shared Individual/Cumulative values for the displayed period/cutoff.

C1 projection uses archived projects and maximal effectively archived task
branches as entries. An independently archived child with active ancestors carries
their identifying context; it is not reparented in storage. An inherited-hidden
descendant stays beneath its archived ancestor, including independently archived
nested children. Render one identity once, with expand/collapse at all available
project/task/subtask/sub-subtask levels. Do not flatten or double-count contextual
paths. Direct History targets only the selected task's work; C1 offers explicit-node
Unarchive; C2 also supplies eligible unused-only Delete through a separate owned
review/typed-confirmation modal. Explain inherited
hiding or dependency refusal; expose no recording controls or manual-work route.

The four primary orders are Name A–Z, Name Z–A, Date Archived Newest first (default)
and Date Archived Oldest first. Sort siblings and top-level entries on their own
name or authoritative effective archive instant, then a stable UUID tie-break.
Archive timestamps display in the dataset IANA zone; inherited-only entries use
their nearest archived ancestor's value, independent entries their own. Equal names
or repeated local clock values never authorize identity substitution. Sorting
reuses detached facts and changes no accounting order, work or metadata.

Keep selected UUID where visible and expansion state while open, including sort
and normal refresh. Sort choice may initially be session-local. Reconcile only
changed rows/edges; Archive/Unarchive queues targeted main/archived refresh and
retains independent descendants if an ancestor entry disappears. Mini remains
subject to modal focus/grab protection. No application-authored nested event loop,
settings subsystem or recording eligibility inferred from visibility is selected.

### Accounting, tree presentation and evidence integration

Extend the existing pure accounting result from exact **direct task/day** facts
with derived ancestor sums: Individual(task) = direct period amount;
Cumulative(task) = Individual(task) + sum(Individual(descendants)). Each UUID
appears once in a subtree sum. Project totals sum their member tasks' Individual,
never add parent Cumulative; application totals sum all direct task facts once,
including retained archived history. Collapse and navigation filters do not
filter the authoritative accounting input. A former leaf's old direct work remains
Individual; its History/edit requests still target that UUID's own entries.

Main tree and mini consume the same detached report/cutoff. Proposed row keys are
typed project/task identities to prevent collision; selection/expansion stays
presentation state, never authorization. Reconcile changed nodes/values in place;
Sort A-Z orders siblings without losing parentage and is initially session-local.
Active ancestors expand and
show a distinct descendant-running indicator, not extra active timers. Disable
new-time actions on projects/nonleaves/effectively archived tasks both in
UI and in the service. Management remains reachable from visible main entry points;
owned dialogs keep existing callback-only lifecycle and pending-request ownership.

Minute-boundary amount repaint and immediate operation/period refresh replace
unnecessary row rebuilding, while observation still detects clock jumps, date
rollover and unavailable totals. Existing `_tick` is not permission to delay action
timestamps or persist ticks. Keep Mini Open defaults Off and remains session-local;
Show Main keeps mini visible only while it is On. Mini/topmost handling must never
steal focus or grabs from owned modals. Native modal/focus tests remain required;
no second root, timer or worker is justified.

Timesheet and POL-R continue to read direct task/day amounts and the unchanged
allocation contract; a parent selection is not subtree scope. Current project
membership groups historical work; saved exports retain original labels/context,
exact bytes/digest, cells and basis. No move/archive/unarchive/template-edit operation
rewrites work revisions, confirmations, existing receipts or frozen evidence.
Backup validation/restore must understand the separately approved fresh schema
and all its facts before it can be called supported; neither becomes a conversion
route for old datasets. Existing cold non-recovering inspection and owned ordinary
native rollback recovery ordering remain mandatory for supported new data.

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

Main/mini share a coordinated cutoff; each task's Individual remains its own work
and application totals include archived/parent direct work. B1 adds only the
derived Cumulative presentation described above; no live soft-delete flag exists. Current
project grouping is derived, non-additive. Displayed Actual rounds each task/day
once to integer hundredths;
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

Stage 1A established explicit data-dir/create/zone startup; current `bootstrap`
also supports the source setup/remembered selection described above. `dataset_lock` holds
OS ownership before writable open; unknown/nonempty create targets and unknown
schema versions refuse without data cleanup. `sqlite_store` owns isolation_level=None,
BEGIN IMMEDIATE/COMMIT/ROLLBACK and checked STRICT fresh schema (originally version 1, then 3; current project-nesting E selects version 4). Dataset/task/
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
validation-probe close. An independently opened reconciliation probe is retained
by the store until its close succeeds. Recovery closes it before reuse; backup
refuses it, and store shutdown cannot release DatasetLock while its close remains
unestablished. Cleanup retries remain on the existing worker, without a new
connection coordinator.
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
attempt or editor. Mutation/reconciliation replies echo the original immutable
Request as well as their unique delivery token; mismatched dataset/operation/content
cannot consume pending work. File replies also validate export/destination context
before consuming an accepted operation. The app records the matching Outcome
before optional main-status rendering and still delivers it to the owning editor
after a status failure. A definitive stopped worker retains an unresolved Request
as unverified, clears executing state, disables main Retry and refuses another
queue submission; explicit exceptional exit/reopen is required. This is not a
watchdog or automatic worker restart. Root Close cannot interrupt executing work; idle unverified
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
schema used version 1 at those stages; E now uses only version 3 and refuses
all earlier signatures without conversion. The
current application exposes Timesheet Preview, protected file Save/recovery and
explicit absolute confirmation and derived reconciliation/reminders. Stage 3D adds
only `dataset_meta.polr_reminder_dismissed_local_date TEXT NULL`, SQL shape checks
plus real civil-date validation on read/reopen. The exact fresh schema signature
changes directly; no migration/conversion or automatic dataset recreation. Stage 1B exercises real SQLite
process death at transaction/receipt/commit boundaries, atomic Switch, historical
exact retries, active restart/calendar continuity, ordinary ownership races and
rollback-journal pre-COMMIT and post-cleanup boundaries. These bounded local
experiments are not arbitrary power-loss,
hostile/multiwriter or native Windows evidence. Stage 4A supplies consistent backup
and cold restore, independently accepted by the later Stage 4B GO. Stage 4B adds
complete-fact transaction faults, reminder/file/backup barrier-controlled child
interruptions, queued Start/Stop/Switch exit and a connected uncertain-save/backup/
cold-restore/new-session scenario. Measured full-history validation cost is retained
without caches or weaker evidence checks; [timings and limits](TESTING_STRATEGY.md#portable-operational-measurements)
are engineering evidence. Fresh hierarchy implementation and remaining stabilization
are separate; no upgrade machinery is selected. Native Windows source operation
remains a deployment qualification.

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
DELETE/EXTRA/FK and 2; there is no automatic upgrade, conversion or recreation.

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
Within-day UTC segment start/stop order follows the selected date/time direction;
identical timestamps retain stable UUID ties and date-only rows remain after timed
rows without invented endpoints. Linked selection is visual only. A failed
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
facts under the explicit UI observation. All includes archived tasks and direct parent work;
Selected rejects empty/duplicate/unknown IDs. Each intersecting week retains seven
basis dates even for one-day Custom, while visible cells cover exactly the requested
task/dates. Valid empty All is distinct from failure. There is no preparation write.

Four STRICT immutable tables originated in schema 1 and remain protected in schema 3: `timesheet_exports`,
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
development. The later Stage 4A GO instruction records independent acceptance of
Stage 3 functional completeness, including Stage 3D below; native/pilot gates remain.

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
replacement performs a fresh complete stable target inspection after staging,
requiring the original typed conflict metadata and content digest, then immediately
rechecks target type/identity/size/mtime/ctime before os.replace. Changed bytes
reject even when size/mtime and the other observed fields are unchanged. Consent
is never renewed automatically. Never unlink/truncate/direct-write. Final complete
verification precedes success.
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
Stage 3D approval. The later Stage 4A GO instruction records independent Stage 3
functional acceptance. That acceptance establishes no external verification, native
Windows, suspend/power-loss, complete Stage 4 stabilization or Stage 5 pilot qualification.

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

## Source startup and launcher selection

`bootstrap.main` retains explicit CLI and headless recovery semantics. With no
arguments it creates one root and `startup.StartupWindow`; no ChronicleApp or
worker exists merely because setup is displayed. Readable timezone labels map to
explicit pinned offline IANA rules. Only exact Windows `TimeZoneKeyName` values
from the approved map suggest a label; missing/unknown keys require choice.
Other zones use Advanced / Other. No stored timezone-changing feature is added.

`launcher_selection` owns only a bounded versioned JSON path preference in the
per-user source-mode Chronicle directory. Windows uses LOCALAPPDATA; Linux uses
absolute XDG_DATA_HOME or HOME/.local/share; macOS uses HOME/Library/Application
Support. Unavailable/unsafe bases require explicit choice. The proposed Data
folder is an opt-in source convenience, not production installation policy.
No setup-time mkdir or legacy search occurs. Missing records discover only this
suggested folder; damaged records block implicit discovery and remain retained.

Accepted setup paths reject existing links/reparse redirection and explicit remote
storage. Create delegates to the existing worker/store final empty-directory and
exclusive reservation checks; Open passes create=False/timezone=None, without cold
inspection. The startup controller drains only initial worker results. Failure
retains diagnostics/drafts; failed cleanup retains that worker and ownership for
explicit Retry cleanup. No new connection/initializer/recovery engine exists.
Only a real ready result removes setup controls and constructs ChronicleApp on
the same root, delivering that result through its normal handler. Setup callbacks
and bindings are removed, and the ordinary owner manages shutdown thereafter.

Remembering runs only after readiness. Strict bounded regular-file reads compare
path/descriptor identity and each domain's complete stability. Duplicate/extra
fields, unknown versions and linked/damaged files refuse. Publication writes an
exclusive private stage, syncs/closes/verifies it, reinspects any valid reviewed
old record, then uses absent-target hard-link publication or replaces only that
unchanged valid record. Cleanup touches only owned stages; final verification is
required. No hostile-directory atomic CAS or power-loss guarantee is claimed.
Explicit commands do not load/update launcher preferences. A remembering failure
adds a persistent notice without invalidating the open database. Preferences are
not a second work/timezone/evidence authority and are not part of database backup.

The new first-run GUI remains subject to independent/native Windows qualification.
Stage 4 remains IN PROGRESS, Stage 5 NOT STARTED, and installation/cutover remains Open.

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
