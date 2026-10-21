# Chronicle replacement requirements

## Authority and status

Chronicle is a small local desktop application for recording task Actual **and
explicit absolute POL-R reconciliation**. Both are core. Confirmation,
reconciliation, daily/weekly summaries and reminders must be complete before
core pilot signoff; allocations are optional expansion.

This document owns user-selected behavior. [ARCHITECTURE.md](ARCHITECTURE.md)
owns the selected Python + Tkinter/ttk + transactional SQLite design;
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md) owns frozen export,
displayed-Actual decimal, quarter-hour submission and confirmation semantics.
[ROADMAP.md](ROADMAP.md) owns Stages 0–6.
[DESIGN_NOTES.md](../DESIGN_NOTES.md) describes retained, unshipped JSONL source,
not the replacement architecture. Source/tests establish implementation/evidence,
not product choices. [DECISIONS.md](DECISIONS.md) preserves superseded approvals.
The user and ChatGPT decide behavior and architecture; Codex implements approved
outcomes and returns material unresolved choices for adjudication.

Selected does not mean implemented. This documentation selects a clean Tkinter
rewrite, not a Qt/PySide6 frontend and not incremental JSONL compatibility work.
Stage 1A delivers the connected SQLite timer foundation. Stage 2A adds connected
manual work, revision/read services, mixed accounting and week configuration.
Stage 2B/complete Stage 2 recording and Stage 3A Preview/allocation/immutable export
evidence, Stage 3B file Save/recovery and Stage 3C absolute confirmation are
independently accepted for functional development. Stage 3D connects comprehensive
reconciliation/reminders; this is not deployment/pilot readiness.
The later explicit Stage 4A GO instruction records independent Stage 3
functional acceptance; backup/cold restore is delivered for independent review,
without completing Stage 4 or authorizing pilot.

## SELECTED — Replacement installation and data boundary

One local desktop application operates one selected dataset with one serialized
application writer. The replacement starts with fresh data. No historical import,
migration, old schema/API support, automatic old-data discovery, dual-write or
parallel legacy runtime is required. Direct Python source execution selects one runtime.
Temporary old source during development creates no compatibility obligation.

Existing files must remain protected during development. Absence of a release
preservation obligation for the retired dataset does not authorize arbitrary
startup deletion. Exact release paths, installation/cutover and cleanup remain
Open. Protect new-runtime audit history and future schema/data upgrades.

## SELECTED — Independent projects and tasks

Tasks have stable UUIDs and own independent work. Duplicate names are valid;
POL-R uses names rather than invented external task numbers. A task may belong
to one optional organizational project or be Unassigned. Projects have stable
UUIDs, names and optional descriptions but own no time or timer.

Moving or renaming a task preserves its identity/work. Reports group all its
historical work by **current** project membership. Derived project subtotals are
informational; never add them again to their tasks. Parent/descendant display
must not turn another task's work into a task's own Actual.

## SELECTED — Recording and timer operation

Provide Start, Stop and Switch. Only one task is active. Switch atomically stops
the old task and starts the new task at one accepted action time. Persist the
active timer; reopening must not silently lose it. Rendering observes time and
never records work, guesses missing stops or persists a tick counter.

Unknown POL-R values, external unavailability or exhausted/unknown allocations
never block Actual recording. Start/Stop/Switch capture one aware wall-UTC action
instant before queueing; worker delay never moves it. Derive running elapsed from
the persisted effective start and explicit observation, not ticks. Sleep and
normal exit do not stop a timer. Normal restart/crash restores the same committed
entry UUID/start without a new Start or fabricated Stop. Forward clock movement
is not automatically rewritten; impossible/nonpositive Stop/Switch rejects and
preserves the timer. An observation before its start shows unavailable values and
a clock/start warning, never zero or negative work.

Correct active start is explicit recovery, not historical editing. The operator
supplies a date/minute in the dataset IANA zone; gaps reject and repeats require
first/second choice. Preserve unchanged microsecond precision. Changed start must
not exceed the accepted correction observation. Require current active UUID and
version; preserve original, prior and corrected starts, audit observation, optional
comment and request identity immutably in the same transaction as the receipt.
An unchanged correction writes nothing. No automatic recovery, timer deletion,
idle detection or sleep subtraction is selected.

Queue acceptance is not correction completion. Keep the modal active-start draft
until a matching authoritative result: committed/unchanged closes it; validation,
known rollback and pre-execution unavailability retain editable values. A stale
UUID/version retains the reviewed draft without retargeting; close and reopen for
fresh review. Executing requests lock fields and ordinary Close. Unverified
requests remain frozen with editor-local exact Retry/Reconcile and the existing
default-cancel exceptional exit, never a second correction identity. Unexpected
view destruction does not erase the application owner's pending request. A later
report failure cannot reclassify a verified correction.

Normal shutdown rejects new submissions, lets accepted operations finish and
reconciles them without joining a live worker on Tk. When work has finished but
storage truth remains unverified, offer Retry/Reconcile or Exit despite unresolved
save, with default-cancel confirmation. Explain possible prior commitment and loss
of volatile retry inputs. Do not interrupt executing I/O, create a new request,
rollback evidence or claim an unknown outcome is failed/successful. Finite SQLite
busy timeouts do not promise recovery from an indefinitely hung OS call.

Mini represents the active task, otherwise the main selected task, otherwise no
task. It consumes the owner's status/report and cannot create independent Actual.

## SELECTED — Actual-time records

Actual combines two distinct shapes, assigned to local work dates:

- Genuine timed intervals with real start/stop instants and UTC elapsed duration,
  split correctly at local midnight, week boundaries and daylight-saving changes.
- Date-only manual amounts with task UUID, civil date and duration, without
  fabricated endpoints. A 14-hour Saturday amount stays entirely Saturday.

Manual date-only entry uses a genuine YYYY-MM-DD date and strictly positive
H:MM duration (two minute digits 00–59, unbounded hours within integer-microsecond
limits). Trim surrounding whitespace; reject decimals, seconds, fractions and
overflow. Future civil dates are allowed. New genuine timed work must end no later
than its accepted submission observation; resolve start/end independently, with
no inferred overnight rollover or automatic overlap adjustment.

The Add timed work and Add date-only work forms are task-bound and initialize
dates to the current dataset-local date, clocks/duration/comment empty. Save alone
submits one frozen request through the existing worker. Cancel writes nothing;
verified completion closes the form. Validation, stale rejection, known rollback
and unavailable storage preserve editable drafts; uncertainty freezes the same
request for owner-mediated Retry/Reconcile or the approved exceptional exit.
Main/mini actions are blocked through the modal form while running time continues.

Both support correction/deletion with immutable prior values and audit details.
Work-entry UUID remains stable across revisions; reviewed revision changes reject
stale edits. A displayed daily portion always targets its complete underlying
entry, never a clipped replacement. Deleting a spanning interval warns about the
other affected dates. Editing preserves entry type.

Timed entry, changed endpoints and History clocks use minute precision with
separate start/end dates/times. Reuse accepted clock formats; reject seconds or
fractions in new clock input. Repeated local minutes require explicit first/second
UTC-ordered occurrence selection; nonexistent minutes reject. Do not guess
rollover, an occurrence or a gap adjustment. UTC endpoints determine positivity,
including earlier-looking fallback stops and cross-date work.

Ordinary timed editing is for closed genuine intervals, independently of another
running timer. Unchanged Save, including a comment-only change, writes nothing.
Changing one endpoint preserves the other exactly, including seconds/fractions.
A draft equivalent to the original minute and occurrence preserves that original
precision, including after changing back. Preserve it before span validation.
A stored repeated occurrence may initialize from its instant; changed repeated
times require explicit selection. Comments are optional. Original/revised values,
revision identity and audit time remain available. No billing rounding changes
raw work.

Replacement Reset actions and resettable counters do not exist. Reset boundaries,
exports and confirmations neither erase nor increase calendar Actual.

## SELECTED — Calendar Actual displays

Main task rows show **Today** and **This week**, each task's own work, including
parents. Mini-mode shows **Today** for its displayed task and retains Start/Stop.
Application totals include retained work of deleted tasks, while the active list
omits deleted tasks. One coordinated refresh uses one aware UTC cutoff and local
observation date for main/mini. This week is the complete containing calendar
week. Timed work is cutoff-capped; dated amounts belong wholly to their declared
dates, including later dates within that week.

Show completed-minute HH:MM without changing underlying precision. Calculation
failure shows **—** and one short “Time totals unavailable.” inline message per
affected window. Keep Start/Stop available; a later normal refresh can recover.
Do not present stale numbers as current or silently omit unsupported work.

## SELECTED — Mixed work history

One task-bound modal History shows effective genuine intervals and date-only
amounts; earlier revisions/deletions are available through details. Main task
selection → History → **inline editor on that surface** is the replacement route.
Do not introduce a subordinate correction Toplevel. Metadata forms need not open
History; legacy recursive task-editor routing is not a target requirement.

At most one History is presented per application. Close it before main/mini
interaction or choosing another task. It supplies History controls and Close,
not main-window Start/Stop. Timers continue. Duplicate/reentrant requests do not
retarget, replace or refresh it. Every application starts newest-first; successful
date-direction changes persist only in that application session across openings,
not in settings or a preference file. Within-day timed portions stay chronological;
dated entries follow without fabricated clock positions.

Default Current week, inclusive Custom and All history are available. Load on
presentation, Apply, switching to Current week/All and explicit Refresh. Sorting
by date reorders displayed rows without new work, cutoff capture or applying
drafts. Successful replacement/sorting clears selection. Current week is seven
local dates using the selected week convention, recalculated on refresh.

Custom dates permit typing and owned calendar pickers. Trim surrounding space,
then require canonical YYYY-MM-DD, real ordered dates and representable boundaries.
Typing, focus, calendar selection and entering Custom do not Apply. Preserve
invalid/unapplied drafts across failures and period switches. Refresh uses the
last applied period and committed Custom bounds; before first success it retries
Current week. Report last-successful period/as-of truthfully; distinguish not
loaded, valid empty and failed loading. Prepare complete display content before
replacement; do not present partial output as successful. Widget failure invalidates
untrusted output, with explicit later recovery rather than claimed GUI rollback.

Keep full detached row metadata behind temporary widget handles. Linked daily
portions share the original entry identity, endpoints and continuation flags.
Columns are link, Date, Kind, Start, End / as of and Duration:

- Date is YYYY-MM-DD; Kind distinguishes Timed, Date only and Running. Dated
  clocks are blank. Running boundaries are observations, not recorded stops.
- Segment endpoints use HH:MM, prefixed by actual date when different from the
  row date (including next-date midnight). Repeated minutes append the actual
  UTC offset, including non-hour offsets; use valid candidates to detect repeats.
- Duration: 0:00 for zero, <1 min for positive sub-minute work, otherwise completed
  minutes as unbounded H:MM. Preserve precise metadata and supplied work amounts.
- Show ↔ for continuing portions. Selecting a portion highlights related visible
  task/kind/entry portions without multiselection; running linkage is task-scoped.
  Dated rows do not link. No routine explanatory text is required.

Inline Cancel and unchanged Save return to browsing without writes. Validation or
stale conflicts retain the draft, without retargeting a successor. Verified edits
refresh the last applied period, preserve direction/unapplied drafts and report
refresh failure truthfully. Database outcome, not widget destruction, establishes
completion. All active readers must include each exposed work type before its
writer is activated; History alone does not satisfy this gate.

The UI consumes one detached snapshot containing dataset/task identity, observation,
resolved period bounds, committed week convention, effective rows and a task-scoped
deleted-entry index, collected in one read transaction. Details exposes immutable
creation, correction, deletion and active-start evidence in revision order. Deleted
identities remain discoverable without adding them to effective Actual.

The standard-library inline calendar owns one panel, changes drafts only and never
captures another accounting observation. History uses callback-driven local modal
ownership, without application-authored waits or another event loop. Close restores
only a surviving eligible origin grab/focus and never displaces a competing owner.

Edit/Delete use the application's existing pending request. Executing I/O blocks
ordinary Close. Unverified outcomes lock the exact request for Retry/Reconcile or
the History-owned default-cancel exceptional application exit. Stale reviews keep
the original draft and disable Save until Cancel, explicit Refresh and fresh review.
Committed corrections refresh the applied period once; later display failure does
not undo commitment or make old rows current. Unchanged Save reloads no History.

## SELECTED — Configurable week convention

Any weekday may begin the week; Sunday is the initial default, not permanent
policy. The setting controls weekly totals, Timesheet periods/columns, project
subtotals, reconciliation summaries and later allocation periods. It does not
change civil work dates, amounts, daily confirmations, immutable exports or prior
work. Exports freeze their original convention. Stage 2A persists the selector in
dataset metadata, Monday=0 through Sunday=6, with an expected-prior check and
atomic receipt. Unchanged selection writes nothing. Shared totals and Current
week history reads use the committed convention. Allocation override effects
remain reserved for optional expansion; dataset timezone changes remain Open.

## SELECTED — Actual, Exported and Confirmed POL-R are distinct

| Fact | Meaning |
| --- | --- |
| Actual | Current genuine/date-only work by task UUID and local date. |
| Exported | Immutable snapshot of a reviewed Timesheet's values, labels and context. |
| Confirmed POL-R | Latest explicitly user-confirmed absolute external task/day value in integer quarter-hour units, or Unknown. |

Export and confirmation never add Actual. No automatic POL-R synchronization or
independent backend verification is selected. User confirmation records reported
external content, not an independently verified query.

## SELECTED — Decimal-hour replacement output

Keep exact Actual, displayed Actual and POL-R submission distinct. Exact Actual
retains integer microseconds, genuine instants and declared civil dates. Displayed
Actual uses the existing completed-minute HH:MM or two-place decimal convention:
ROUND_HALF_UP once per task/day to integer hundredths; displayed Actual rollups
sum those cells rather than independently round raw aggregates. This is display
only, not input to submission rounding. Project subtotals are not additional work.

Proposed and manually/export-confirmed POL-R values must instead be nonnegative
integer **quarter-hour units**, displayed as multiples of 0.25. Reject invalid
non-quarter confirmation input, rather than round it into evidence. Positive work
or a zero suggestion never automatically creates a zero confirmation. See the
[precision contract](EXPORT_EVIDENCE_CONTRACT.md#decimal-hour-representation).

## SELECTED — Weekly POL-R suggestions

For each task independently, always round its exact complete-week Actual **up**
to a quarter-hour total. Distribute that total over worked dates by largest exact
remainder, breaking ties by earlier work date. Zero-work dates receive nothing;
no date receives more than one additional quarter in the remainder pass. There
is no cross-task/cross-week transfer or carried remainder. Never modify Actual,
work dates/revisions or fabricate work to represent the upward adjustment.

Use the selected week-start convention, dataset IANA zone and one explicit
accounting cutoff. This week, Last week and arbitrary inclusive Custom views
always calculate the full seven-day basis for every intersecting task/week, then
show only requested dates/tasks. Partial views need not sum to the complete-week
target; do not recompute from a subset or expose out-of-scope confirmation cells.
Freeze sufficient full-week context to prove the reviewed distribution later.

Current-week suggestions are provisional. Further work, later declared dated
amounts or correction may change target/ranking, including suggestions on other
dates of that task/week. Timed work remains cutoff-capped; existing future-dated
amount semantics remain binding. No predicted stop or automatic POL-R adjustment.
The exact algorithm, proof and mandatory examples have one
[technical owner](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation).

## SELECTED — Daily reconciliation

Show distinct task/day values:

- **Actual:** exact recorded work with its existing HH:MM/decimal display.
- **Suggested POL-R / Enter in POL-R:** the current full-week allocation for that
  date, an absolute quarter-hour replacement value, not arbitrary daily Actual
  decimals and not Delta.
- **Confirmed POL-R:** latest explicitly confirmed absolute quarter-hour value,
  or Unknown; known zero retains confirmation identity.
- **Daily Delta:** displayed Actual hundredths minus the confirmed quarter amount
  converted exactly to hundredths when known; otherwise Unverified. Keep this
  diagnostic, but do not treat every nonzero Actual-minus-Confirmed value as an
  allocation mismatch.
- **Suggested-entry gap:** suggested minus known confirmed amount; Unknown stays
  unresolved, never an invented zero prior.
- **Weekly rounding adjustment:** exact complete-week target duration minus exact
  weekly Actual, accurately expressed in minutes/seconds or compatible exact units.
  It is nonnegative and less than 15 minutes per task/week, not extra work.

Base daily classifications are NOT_APPLICABLE (zero work/suggestion with no
confirmation), UNKNOWN (positive work or suggestion without confirmation), MATCH
(known confirmation equals suggestion), MISMATCH (known differing amount), and
UNAVAILABLE (required evidence/calculation cannot be established). Known zero has
identity and may match zero. Coverage includes positive work/suggestion/confirmation
and explicit known zero, but does not demand confirmation for unused dates.
UNKNOWN and MISMATCH are actionable; unavailable is never all-clear. A complete
week requires all applicable individual cells to be known and matching. Inclusive
partial Custom views preserve full-week context and are not complete-week reviews.

Distinguish Unknown/not confirmed, matching suggestion/confirmation, known daily
allocation mismatch, incomplete review/confirmation coverage, explained upward
rounding and stale proposals after subsequent work/correction/confirmation.
Matching weekly totals cannot hide daily mismatches; nonzero Daily Delta may be
explained when Confirmed matches the approved allocation. Do not persist separate
Delta, suggestion or rounding-balance counters. See the
[reconciliation contract](EXPORT_EVIDENCE_CONTRACT.md#displayed-reconciliation).

A worked day may receive 0.00 Suggested POL-R without becoming zero Actual.
Never auto-confirm zero or mark an Unknown cell fully reconciled solely because
its suggestion is zero. Explicit checked/manual zero remains supported. External
zero-entry versus omitted/no-entry treatment requires validation before affected
Stage 3 connected official reporting and pilot; it does not reopen the formula.

## SELECTED — Mandatory 3:00 → 5:00 contractual behavior test

Retain compatible cases A and B: save a 3.00 suggestion, record 2.00 more, confirm
frozen 3.00 → **Actual 5.00 / Confirmed 3.00 / Daily Delta +2.00 / Suggested 5.00**.
Explicitly confirm 5.00 → suggested-entry gap 0.00 (Daily Delta also 0.00).
Correct Actual to 2.50 against Confirmed 3.00 → **Daily Delta -0.50 / Suggested 2.50**.
Earlier exports/confirmations remain unchanged. These exact-quarter cases do not
make arbitrary displayed Actual decimals valid POL-R inputs.

Also mandatory are [cases C–G](EXPORT_EVIDENCE_CONTRACT.md#mandatory-allocation-examples):
exact weekly distribution, upward adjustment, no carryover, small positive work
with an earlier-date tie and a zero suggestion, and exact-quarter work.
Stage 3A implements these examples and partial-Custom/full-week behavior;
passing implementation evidence does not establish external-policy qualification.

## SELECTED — Preview and saved exports

One modal Timesheet/POL-R workflow replaces old export workflows. Main/mini input
is blocked while timers continue. Fresh preview defaults to This week/All tasks;
Last week and Custom, typed dates/pickers, All or explicit task UUIDs are supported.
Do not expand descendants. Duplicate names remain separate; retained deleted-task
work stays reportable. Calendar selection only edits drafts, cancellation preserves
them, and invalid drafts remain correctable. Resolve relative periods at explicit
Preview/Refresh, not by silently advancing an old preview.

Preview prepares a detached frozen candidate with one cutoff and complete text,
without evidence/file writes. Changed dates/scope/checks invalidate Save readiness
immediately, even after changing back. Keep old report labeled as previous.
Preparation/render failure invalidates readiness and reports the original error;
valid empty All differs from invalid empty Selected. Show applied dates/cutoff,
not unapplied drafts. Show exact/displayed Actual and suggested POL-R separately.
The candidate retains full-week allocation context, computed quarter counts and
reviewed scope. Save publishes exactly that candidate, without recalculation.
Later work, rename or regrouping does not change it.

Commit the immutable snapshot in SQLite before file publication. Unknown commit
outcome cannot authorize publication; reconcile the same request/identity against
the database. File failure retries the saved report independently of any retained
widget; no global one-pending-operation slot or widget lifetime is authority.
Default Save/Retry protects existing files, reuses fully verified matching copies
and creates absent files exclusively. A stable regular-file content conflict
allows a separate default-cancel confirmation naming the destination; Overwrite
permission is for that call only. Reject unsuitable/unreadable/unstable objects
and protect the dataset tree/aliases from all publication, including absent paths.
Preserve exact frozen
bytes/digest, staging-only cleanup and truthful post-publication diagnostics;
see [file rules](EXPORT_EVIDENCE_CONTRACT.md#materialization-and-byte-verification).

Export never stops/resets timers, confirms POL-R, submits legacy markers,
deletes tasks or dismisses reminders. Saving and later explicit confirmation are
distinct. Save Timesheet, Retry Save, Save Copy As, Check File Status and Saved
Reports are explicit actions. The first selected path can populate absent original
preferred-destination metadata before registration without changing reviewed values
or text; later paths never rewrite it. Recovery loads frozen context/text by UUID,
including after restart, without current accounting or a later renderer. READY is
an observation, never persisted proof or permanent success status.

Before registration, Close discards the preview; after verified completion it permits
a fresh opening. Executing Save/dialogs block Close/exit/reentrant actions. Unverified
registration retains the exact Request and prohibits ordinary abandonment; explicit
reconciliation or the existing default-cancel exceptional application exit remain.
Registered but unfinished file Save requires default-No Close confirmation, then
disposes the window and retains only an in-memory UUID/current-path handoff. Fresh
openings remain This week/All and require Preview; use Saved Reports explicitly to
recover. Exit warns before losing volatile context without implying evidence/files
are removed. No hidden retained window, persisted recovery state or automatic retry
is selected. Overwrite permission is one-call only, never a frozen field.

## SELECTED — Explicit POL-R confirmation workflow

Offer whole applicable saved-export, checked task/day, defer/later review and
manual absolute confirmation without an export. Source-linked proposals use the
report's **frozen suggested quarters**, never current recalculated Actual or its
old daily decimal representation. Manual amounts may differ from suggestions,
but must be valid quarters; show resulting Daily Delta and suggested-entry gap.

Default-select every in-scope frozen suggestion greater than zero, **including
positive values already equal to current confirmation**. Never default-select
zero, even on a worked date. Explicit selection means exactly checked source
cells, including zero if selected. Empty selection is not All; unchecked cells
retain their previous state. Ordinary bulk confirmation requires neither retyping
all cells nor a free-text reason per cell.

## SELECTED — Confirmation evidence and batch integrity

Retain complete reviewed in-scope frozen source coverage, including unchecked
cells: exact source identity/scope/association, canonical task UUID/date, historical
name and suggested quarter count. Reject partial, substituted, tampered or
reordered-as-new-evidence proposals. Selection/acknowledgement keys must be genuine
canonical source keys. Unrelated newer unchecked confirmations need not invalidate
checked selection when source coverage remains exact.

One transaction freshly validates all selected priors, amounts and stale conflict
classifications and commits the whole immutable batch/current references/receipt.
A source older than a newer differing confirmation requires cell-specific
acknowledgement **exactly** for selected conflicts. Reject missing, extra, duplicate,
unselected, nonconflicting, blanket or changed-prior acknowledgements. Bind consent
to task/day, frozen amount and reviewed prior identity. Even intervening equal-value
confirmation changes identity and rejects stale review. Manual confirmation has
no source-export acknowledgement, but still checks current prior. Do not refresh
reviewed priors silently or apply a valid subset.

Exact committed request reuse returns its prior result before stale checks,
without reapplying old values over newer batches; different content under one ID
fails closed. Deferral writes nothing. No confirmation changes Actual/timers or
exports. The [technical contract](EXPORT_EVIDENCE_CONTRACT.md#reviewed-source-integrity-and-default-selection)
owns the precise selection, coverage and acknowledgement rules; JSONL mechanics
remain superseded, not prerequisites.

## SELECTED — Corrections and stale exports

Correcting/deleting Actual remains permitted after export/confirmation. Recalculate
current suggestions from effective exact work, including changed allocations on
other dates of that same task/week. Retain original frozen weekly context,
suggestions, saved bytes, confirmations and identities. Show new mismatches and
require explicit review/subsequent absolute confirmation; never silently revise
or redistribute confirmed POL-R values, create synthetic work or carry to a new week.
Older sources may be confirmed only using frozen suggestions with complete source,
reviewed-prior and stale-acknowledgement safeguards. Do not reinterpret historical
Actual decimals as new valid quarter-hour evidence.

## SELECTED — Incomplete current workdays

Preview/export/confirmation need no formal day closure. Distinguish running
observation from a recorded stop. Later work can change Actual, current weekly
suggestions and gaps, not previous confirmation or committed exports; no automatic
resubmission, Reset or timer interruption occurs.

## SELECTED — Low-friction primary workflow

Show cells needing attention, copyable absolute quarter-hour suggestions, signed
Daily Delta, suggested-entry gaps, explained weekly adjustment and visible Unknown.
Support bulk/checked confirmation, defer/review and
manual correction without duplicating a second manual timesheet. Recording and
reconciliation are both core; neither allocations nor an unavailable external
system may block Actual.

## SELECTED — Reconciliation reminders

Check the previous week every local day the application is used, including
opening after absence and date rollover while running. Check current week on
Friday and Monday. Use task/day allocation agreement and review/confirmation
coverage, not a weekly net that hides opposing mismatches or unexplained Unknown.
Daily Actual-minus-Confirmed rounding differences alone do not establish an
allocation mismatch. Banner actions are Open Timesheet and explicit Dismiss for today.
Opening or saving does not dismiss or confirm. Dismiss for today persists one
canonical nullable dataset-local date, suppressing both categories across same-day
restart even after later work. A new date expires suppression by comparison, with
no cleanup write or replay of absent-day notifications. Friday/Monday are civil
weekdays independent of the configured reporting-week start. Startup, date rollover,
relevant committed work/confirmation/week changes and explicit Recheck trigger
coalesced worker reads; numeric ticks do not query reconciliation each second.
Evaluation failure is unavailable, never proof of a clean week. Required reminders
and daily/weekly reconciliation are complete before pilot; monthly prompts belong
to retained legacy source, not the shipped schedule.

## SELECTED — Optional weekly allocations; implementation DEFERRED

Stage 6 optional expansion, after reserved decisions: user-supplied informational
allocations with Unknown distinct from zero, task-specific weeks, recurring
defaults, overrides and manual correction. Allocation minus confirmed and projected
remaining after Actual are separate estimates, **not reconciliation Delta**.
Limits may warn but never block recording. Allocation controls, recurrence/override
rules and week-change interactions require adjudication. They are not core pilot
gates; no automatic external allocation verification is established.

## Scope inventory — core, optional and unresolved

| Capability | Placement / boundary |
| --- | --- |
| Tasks, optional project grouping, Start/Stop/Switch, main/mini | Core Stage 1 foundation; not a complete MVP/pilot. |
| Manual timed/dated work, corrections/deletions/revision details, History, week setting | Core Stage 2 with all required readers. |
| Frozen exports/full-week quarter-hour suggestions, saved-report recovery, absolute quarter confirmations, daily/weekly reconciliation/reminders | Core Stage 3; mandatory before Stage 5 pilot, with external reporting-policy validation. |
| Tags and other conveniences | Inventory retained; separately prioritize in Stage 6, no automatic promotion into foundation. Tags do not create exclusive or additional Actual. |
| Subtask templates | Existing legacy convenience; replacement semantics Open before any optional implementation. No silent carryover of hierarchy/duplicate-name rules. |
| Allocations / external POL-R integration | Optional Stage 6 only after their decisions/explicit approval. |

## CURRENT IMPLEMENTATION — Inspected staged and production status

The sole shipped source route uses `src/chronicle`: explicit fresh SQLite
paths, independent task/project controls, Start/Stop/atomic Switch, immutable timed
revisions, audited active-start recovery, exact receipts, worker-owned I/O and
coordinated main/mini Actual. It does not discover or modify the former default
JSONL directory. The retained `task_timer` package and its tests are unshipped
historical/semantic evidence, not a parallel runtime or compatibility guarantee.

Stage 1A is independently accepted. Stage 1B portable interruption/ownership and
cleanup reliability is independently accepted at `1e84a043c1c055aced9b8c4b000ef766bbf6d178`.
Stage 1C selects built-in sqlite3, DELETE/EXTRA/foreign keys, SQLite 3.37.0+ STRICT
and direct Python execution with pinned pip-installable tzdata. No production
SQLite databases exist; development datasets are disposable without automatic
conversion/deletion. Executable-build and WAL-reset version requirements are
superseded. Stage 1 functionality is independently accepted; native
Windows source evidence remains required before deployment/pilot, not as a
permanent Stage 2 development blocker.
Stage 2A delivers connected Add timed/date-only work and week-start controls,
immutable closed/date-only correction/deletion services, detached history/revision
reads and mixed main/mini/daily Actual. All active readers include both exposed
work types. Stage 2A is independently accepted at
`7bc1bce2894fd5d4ccddbcedfd7ae0f4e7c1323f`. Stage 2B now connects the main Work History
command, modal browser, inline whole-entry correction/deletion and immutable details.
The later Stage 3A approval reports Stage 2B/complete Stage 2 recording independently
accepted at `adc09ba0935e8718c4ad2101057af9c6022074cc`.
Stage 3A connects Timesheet / POL-R from the main window: This week/Last week/Custom,
All/explicit UUIDs including deleted tasks, draft-only calendars and explicit
Preview/Refresh. It retains immutable full-week basis, in-scope cells, exact text
and digest without writes during Preview. Stage 3A is independently accepted at
`d1e775c33982f109337ec237e3c78e8dc7b56f2e`. Stage 3B now connects verified protected
Save/retry/copy, default-No one-call overwrite, fresh status and Saved Reports.
Exact committed registration precedes file publication; unknown
commit cannot publish. Recovery reads immutable evidence independently of widgets.
Stage 3B is independently accepted at `76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`.
Stage 3C connects inline source/manual confirmation and read-only immutable history
through the existing owner/worker. Positive frozen defaults include equal values;
zero is explicit, unchecked cells stay unchanged, complete source coverage and fresh
selected priors are validated atomically with exact individual stale consent.
Current references join immutable absolute quarter cells; Unknown has no reference.
Immediate task/day feedback is delivered, with optional unavailable calculation
context shown truthfully. Source/manual drafts and exact uncertain Requests remain
protected; committed confirmation cannot be undone by display failure.
The later explicit Stage 3D GO instruction independently accepts Stage 3C for
functional development. Stage 3D supplies read-only daily classifications
NOT_APPLICABLE/UNKNOWN/MATCH/MISMATCH/UNAVAILABLE, cell-based coverage, full-task/week
and cross-task summaries, partial-scope explanation, current/frozen comparison and
copyable absolute suggestions in the existing modal Timesheet. Work corrections
change current suggestions, never immutable reports or confirmations. The main
banner uses the selected local-calendar schedule and explicit durable Dismiss for
today. Unverified dismissal retains the exact Request; queue acceptance is not
suppression. The later explicit Stage 4A GO instruction records independent Stage 3
functional acceptance. Stage 4A connects consistent SQLite backup, full independent
validation and cold restore to new directories; it remains subject to independent
review and does not complete Stage 4.
Retained JSONL services do not satisfy these gates. Earlier Phase 2 acceptance
remains bounded historical evidence. No core/pilot or native qualification follows.

## SELECTED — Consistent backup and cold restore

Backup Chronicle explicitly captures committed SQLite facts through the existing
worker and supported backup API, without changing work or stopping timers. It
publishes one independently validated ordinary SQLite image to an absent external
file; all existing objects and active-dataset paths/aliases are protected. No
backup overwrite, schedule, registry or persisted operation status is selected.
A failed/uncertain publication is not success or proof of absence; final output is
never deleted as rollback. Only proven-owned staging may be removed.

Explicit backup validation is read-only. Cold restore first validates complete
schema, work/audit/receipt, frozen export and confirmation evidence, then installs
through private staging/exclusive publication into a previously nonexistent local
dataset directory. Existing directories, even empty, refuse. Restore exits before
application construction; a later normal launch creates fresh Tk/app/worker/read
sessions. No live connection swap or in-place overwrite is allowed.

The original remains untouched. Restored dataset UUID, timezone/week/dismissal,
active timer and immutable identities/bytes remain unchanged. Original and clone
must not be operated as competing live authorities for the same work. External
report copies are not bundled or written on restore; existing recovery can publish
them explicitly. No restoration confirms POL-R, reconciles work or dismisses a
reminder. Stage 4A delivers this slice for review; native qualification and the
remaining Stage 4 gate precede complete pilot.

## OPEN — Reserved user/ChatGPT decisions

| Decision | First affected gate |
| --- | --- |
| Dataset-timezone changes and historical date attribution under changes | Stage 1 dataset configuration / Stage 2 accounting, before implementation. Explicit fixed dataset zone is required; change policy is not guessed. |
| Replacement template semantics | Before optional Stage 6 template implementation. |
| Exact release paths, installation/cutover and retired-data cleanup | Before affected deployment/Stage 5 fresh pilot setup; startup deletion is unauthorized. |
| Allocation controls/recurrence/overrides/week-change effects | Before optional Stage 6 allocation work. |

These reservations do not reopen Tkinter/SQLite or defer core POL-R. Resolve only
the affected work; they do not block this authority reconciliation.

## UNVERIFIED EXTERNAL BEHAVIOR — POL-R backend

The 0.25-hour daily input restriction is accepted user-provided context and the
user approved Chronicle's calculation. Employer/customer authorization for weekly
redistribution and external zero-entry versus omitted/no-entry treatment on a
worked zero-suggestion day are not independently verified. Validate them before
affected Stage 3 connected official reporting and Stage 5 pilot; do not claim
external compliance or reopen the approved mathematical policy. Unconfirmed zero
suggestions remain unresolved pending that external boundary.

External allotment administration/enforcement and other direct backend behavior
are not independently established. User-entered confirmations/allocations are not
external verification. Future external integration needs explicit approval.

## DEFERRED — Approved implementation work

Stage 0's authority set is independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`. The authorized
`feature/chronicle-rewrite` now contains the approved Stage 1A connected timer
foundation, independently accepted at `897aec2c0d57b6d4aa5c0c5109f55270a4bb1968`.
Stage 1B portable reliability and Stage 1 functionality are accepted after Stage 1C
source/runtime simplification; native Windows source
qualification is separate and remains required before real deployment/pilot.
Stage 2 recording and Stage 3A/3B/3C are independently accepted for functional
development. Stage 3 is functionally accepted under the later Stage 4A approval;
remaining Stage 4 stabilization,
Stage 5 pilot and native qualification are not delivered. Open policies stay
reserved before their affected work.
