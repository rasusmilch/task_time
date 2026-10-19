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
Stage 1A now delivers the connected SQLite timer foundation. Recording/History,
Timesheet and POL-R completeness remain later gates; the foundation is not a pilot.

## SELECTED — Replacement installation and data boundary

One local desktop application operates one selected dataset with one serialized
application writer. The replacement starts with fresh data. No historical import,
migration, old schema/API support, automatic old-data discovery, dual-write or
parallel legacy runtime is required. Replacement packaging ships one runtime.
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

## SELECTED — Configurable week convention

Any weekday may begin the week; Sunday is the initial default, not permanent
policy. The setting controls weekly totals, Timesheet periods/columns, project
subtotals, reconciliation summaries and later allocation periods. It does not
change civil work dates, amounts, daily confirmations, immutable exports or prior
work. Exports freeze their original convention. Core implementation is Stage 2;
allocation override effects remain reserved for optional expansion.

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
They and partial-Custom/full-week behavior constrain later tests; they are not
claims of implemented SQLite allocation.

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
and protect the dataset tree/aliases from replacement. Preserve exact frozen
bytes/digest, staging-only cleanup and truthful post-publication diagnostics;
see [file rules](EXPORT_EVIDENCE_CONTRACT.md#materialization-and-byte-verification).

Export never stops/resets timers, confirms POL-R, submits legacy markers,
deletes tasks or dismisses reminders. Saving and later explicit confirmation are
distinct. General new-runtime saved-report recovery belongs in the core workflow;
the current retained-window implementation is not the target recovery mechanism.

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
Opening or saving does not dismiss or confirm. Required reminders and daily/weekly
reconciliation are complete before pilot; current monthly prompts are legacy,
not the selected replacement schedule.

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

The sole shipped source/build route uses `src/chronicle`: explicit fresh SQLite
paths, independent task/project controls, Start/Stop/atomic Switch, immutable timed
revisions, audited active-start recovery, exact receipts, worker-owned I/O and
coordinated main/mini Actual. It does not discover or modify the former default
JSONL directory. The retained `task_timer` package and its tests are unshipped
historical/semantic evidence, not a parallel runtime or compatibility guarantee.

Stage 1A is independently accepted. Stage 1B adds bounded portable interruption,
ownership/cleanup tests and controlled Windows build inputs; native operational
and package qualification remains pending, so Stage 1 is not Complete.
Stage 2 manual timed/dated writers, History/inline historical correction and week
settings are not shipped. Stage 3 frozen export/confirmation/reconciliation,
quarter-hour allocation and weekly reminders are not shipped. Retained JSONL
services do not satisfy those gates. Earlier Phase 2 acceptance remains bounded
historical evidence. This timer foundation is not complete core/pilot readiness.

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
Stage 1B portable engineering does not replace required native Windows evidence
or independent Stage 1 completion adjudication. Later recording and mandatory POL-R
remain approved, unimplemented stages. Open policies stay reserved before their affected work.
