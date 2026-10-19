# Chronicle replacement requirements

## Authority and status

Chronicle is a small local desktop application for recording task Actual **and
explicit absolute POL-R reconciliation**. Both are core. Confirmation,
reconciliation, daily/weekly summaries and reminders must be complete before
core pilot signoff; allocations are optional expansion.

This document owns user-selected behavior. [ARCHITECTURE.md](ARCHITECTURE.md)
owns the selected Python + Tkinter/ttk + transactional SQLite design;
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md) owns frozen export,
decimal and confirmation semantics. [ROADMAP.md](ROADMAP.md) owns Stages 0–6.
[DESIGN_NOTES.md](../DESIGN_NOTES.md) describes the current JSONL implementation,
not the replacement architecture. Source/tests establish implementation/evidence,
not product choices. [DECISIONS.md](DECISIONS.md) preserves superseded approvals.
The user and ChatGPT decide behavior and architecture; Codex implements approved
outcomes and returns material unresolved choices for adjudication.

Selected does not mean implemented. This documentation selects a clean Tkinter
rewrite, not a Qt/PySide6 frontend and not incremental JSONL compatibility work.
No SQLite runtime is delivered by this change.

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
never block Actual recording. Abnormal system-clock changes, sleep and restart
recovery policy require adjudication before affected Stage 1 code; ordinary
persistence is not permission to guess those policies.

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
| Confirmed POL-R | Latest explicitly user-confirmed absolute external task/day value. |

Export and confirmation never add Actual. No automatic POL-R synchronization or
independent backend verification is selected. User confirmation records reported
external content, not an independently verified query.

## SELECTED — Decimal-hour replacement output

Exports and POL-R fields show exactly two places. Keep underlying work exact in
integer microseconds. Round each task/day once with ROUND_HALF_UP to integer
hundredths of an hour; sum those cells for weekly/project/overall displayed
rollups. Never independently round raw aggregates for those rollups or add
project subtotals as additional work. Positive work rounding to 0.00 remains
nonzero internally and is not automatically confirmed as zero. See the
[decimal contract](EXPORT_EVIDENCE_CONTRACT.md#decimal-hour-representation).

## SELECTED — Daily reconciliation

Show Actual, Confirmed POL-R, Delta and Enter in POL-R per task/day. Unknown is
not confirmed zero. Unknown Confirmed gives **Unverified** Delta. When known,
Delta is signed displayed Actual hundredths minus confirmed hundredths; Enter
is **whole current Actual**, never Delta or an additive increment. Zero Delta
means agreement with user confirmation, not independent external verification.
Weekly summaries preserve cell-level Unknown/disagreement even when signed
differences cancel. Recording Actual is independent of reconciliation availability.

## SELECTED — Mandatory 3:00 → 5:00 contractual behavior test

Save a 3.00 export, record 2.00 more, then confirm the frozen 3.00 was entered:
**Actual 5.00 / Confirmed 3.00 / Delta +2.00 / Enter 5.00**. Confirm the external
cell at 5.00: Delta becomes 0.00. Earlier export/confirmation stays unchanged.
Correct Actual to 2.50 against Confirmed 3.00: **Delta -0.50 / Enter 2.50**.
These are mandatory, not illustrative alternatives. No Reset or extra additive
2.00 entry is needed.

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
not unapplied drafts. Save publishes exactly the reviewed candidate, without
recalculation. Later work, rename or regrouping does not change it.

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

Offer confirmation of the whole applicable saved export, checked task/day cells,
deferral with later review, and manual absolute confirmation without an export.
Propose **frozen** export values, not recalculated Actual. Do not require retyping
all cells or a free-text reason for ordinary bulk confirmation. Unchecked cells
retain prior evidence; do not automatically confirm zero. Explicit zero is valid.
Manual values may differ from Actual/export and must show resulting Delta.

## SELECTED — Confirmation evidence and batch integrity

One reviewed batch validates/commits atomically, with immutable history and current
cell references. Reject stale reviewed priors; never silently replace newer
confirmations. A source export older than a newer differing confirmation requires
cell-specific acknowledgement bound to the reviewed prior. Acknowledgement does
not bypass a changed prior. Equal proposed/current values need no extra manual
entry; even an intervening equal-value confirmation changes the prior identity.
Rejected batches change no subset. Deferral writes nothing. Confirmations never
change Actual, timers or exports. See the [technical contract](EXPORT_EVIDENCE_CONTRACT.md#absolute-confirmation-batches).

## SELECTED — Corrections and stale exports

Correcting Actual remains permitted after export/confirmation. Recalculate current
Actual/Delta/Enter, retain all older evidence and permit a new explicit absolute
confirmation after the external cell is updated. Never rewrite old export bytes
or silently roll a newer confirmation back to an old export.

## SELECTED — Incomplete current workdays

Preview/export/confirmation need no formal day closure. Distinguish running
observation from a recorded stop. Later work changes Actual/Delta, not previous
confirmation; no automatic resubmission, Reset or timer interruption occurs.

## SELECTED — Low-friction primary workflow

Show cells needing attention, copyable whole replacement amounts, signed known
Delta and visible Unknown. Support bulk/checked confirmation, defer/review and
manual correction without duplicating a second manual timesheet. Recording and
reconciliation are both core; neither allocations nor an unavailable external
system may block Actual.

## SELECTED — Reconciliation reminders

Check the previous week every local day the application is used, including
opening after absence and date rollover while running. Check current week on
Friday and Monday. Use per-task/day truth, never a weekly net that hides opposing
differences. Banner actions are Open Timesheet and explicit Dismiss for today.
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
| Frozen exports, saved-report recovery, absolute confirmation, daily/weekly reconciliation/reminders | Core Stage 3; mandatory before Stage 5 pilot. |
| Tags and other conveniences | Inventory retained; separately prioritize in Stage 6, no automatic promotion into foundation. Tags do not create exclusive or additional Actual. |
| Subtask templates | Existing legacy convenience; replacement semantics Open before any optional implementation. No silent carryover of hierarchy/duplicate-name rules. |
| Allocations / external POL-R integration | Optional Stage 6 only after their decisions/explicit approval. |

## CURRENT IMPLEMENTATION — Inspected staged and production status

The checkout remains Python/Tkinter with authoritative JSONL, replayed Python
state and derived JSON snapshots, not SQLite. Main/mini mixed Actual, read-only
modal Work History and frozen Timesheet Preview/Save/retry/confirmed Overwrite
are connected. The standalone correction dialog is not production-connected;
its replacement-interval IDs are legacy mechanics, not stable-revision design.
Date-only replay/accounting and absolute confirmation/proposal/reconciliation
services are staged; date-only production writers, confirmation/reconciliation
UI, weekly reminders, configurable weeks and complete replacement workflow are
not delivered. Legacy reset/export/evidence APIs remain independently callable,
although shipped Reset and old export UI are removed. Source-specific detail is
in [Design Notes](../DESIGN_NOTES.md). Earlier Phase 2 service acceptance is
historical JSONL evidence, not completion of a SQLite stage.

## OPEN — Reserved user/ChatGPT decisions

| Decision | First affected gate |
| --- | --- |
| Abnormal clock movement, sleep, persisted timer restart recovery | Stage 1 before affected recording/reopen code. |
| Dataset-timezone changes and historical date attribution under changes | Stage 1 dataset configuration / Stage 2 accounting, before implementation. Explicit fixed dataset zone is required; change policy is not guessed. |
| Replacement template semantics | Before optional Stage 6 template implementation. |
| Exact release paths, installation/cutover and retired-data cleanup | Before affected deployment/Stage 5 fresh pilot setup; startup deletion is unauthorized. |
| Allocation controls/recurrence/overrides/week-change effects | Before optional Stage 6 allocation work. |

These reservations do not reopen Tkinter/SQLite or defer core POL-R. Resolve only
the affected work; they do not block this authority reconciliation.

## UNVERIFIED EXTERNAL BEHAVIOR — POL-R backend

External allotment administration/enforcement and direct backend behavior are
not independently established. User-entered confirmations/allocations are not
external verification. Future external integration needs explicit approval.

## DEFERRED — Approved implementation work

All SQLite runtime implementation awaits independent architecture acceptance and
separately authorized work. The next runtime action is a bounded Stage 1 read-only
implementation plan, not another whole-application planning cycle. Only optional
expansion is deferred beyond the complete core pilot; POL-R is not deferred there.
