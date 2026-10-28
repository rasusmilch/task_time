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
functional acceptance. The later Stage 4B GO independently accepts backup/cold
restore. The later Stage 4C GO independently accepts Stage 4B portable reliability.
Stage 4C cold compatibility inspection, protected refusal and bounded owned
SQLite-native rollback recovery are independently accepted for functional
development. Stage 4 remains IN PROGRESS; native Windows qualification is incomplete
and Stage 5 is NOT STARTED.

## SELECTED — Replacement installation and data boundary

One local desktop application operates one selected dataset with one serialized
application writer. The replacement starts with fresh data. No historical import,
migration, old schema/API support, automatic old-data discovery, dual-write or
parallel legacy runtime is required. Direct Python source execution selects one runtime.
Temporary old source during development creates no compatibility obligation.

Existing files must remain protected during development. Absence of a release
preservation obligation for the retired dataset does not authorize arbitrary
startup deletion. Exact release paths, installation/cutover and cleanup remain
Open. Protect new-runtime audit history; the approved hierarchy target starts
fresh rather than transforming existing datasets.

## SELECTED — Source-mode first-run and remembered startup

Zero-argument `python run_chronicle.py` and the optional PowerShell source launcher
show first-run setup or normally open the remembered dataset. Setup offers local
folder choice, readable explicitly confirmed timezone, Advanced / Other IANA input,
Create and Open, Open Existing Dataset and Cancel. Only exact approved Windows
zone-key mappings may suggest a timezone; offsets, abbreviations and network
inference are not timezone authority. Existing dataset timezones never change.

Windows may suggest `%LOCALAPPDATA%\Chronicle\Data` for source-mode opt-in;
non-Windows uses a suitable per-user local-data suggestion or requires selection.
This does not settle Open installation/cutover paths. No creation occurs on setup
display/cancel, and accepted creation keeps the existing exclusive worker/store
checks for a new/empty folder, unknown contents, races and ownership.

A separate bounded version-1 launcher record contains only the absolute dataset
path. Remember only after readiness. Explicit CLI/recovery never changes it.
Unreadable/corrupt/unsupported preferences and incompatible/missing/busy datasets
produce diagnostics, never recreation or repair. Preserve unexpected preference
objects; a remembering failure leaves a successfully opened dataset usable with a
warning. Without a record, discover only the new suggested source-mode folder:
apparent existing database opens normally, absent/empty shows setup, unknown or
incomplete content requires explicit action. No legacy search/import occurs.

One root/mainloop hands off to the ordinary app only after existing worker
readiness; startup failure/cleanup cannot install a second authority. Cold
inspection is not a prerequisite to ordinary recovery. Schema 1, evidence,
transactions and all recovery contracts stay unchanged. Native first-run evidence
and independent acceptance remain outstanding; Stage 4 remains IN PROGRESS.

## SELECTED — Independent projects and tasks

Tasks have stable UUIDs and own independent work. Duplicate names are valid;
POL-R uses names rather than invented external task numbers. A task may belong
to one optional organizational project or be Unassigned. Projects have stable
UUIDs, names and optional descriptions but own no time or timer.

Moving or renaming a task preserves its identity/work. Reports group all its
historical work by **current** project membership. Derived project subtotals are
informational; never add them again to their tasks. Parent/descendant display
must not turn another task's work into a task's own Actual.

### Approved hierarchy target and fresh-data boundary

The later explicit hierarchy-design instruction selects the following target;
it is **not implemented** in the current flat SQLite runtime. It supersedes the
former Open/optional placement of replacement templates and the assumption that
this hierarchy change would transform existing version-1 data. Exact fresh DDL
and its distinct supported schema identity remain PROPOSED pending separate review.

Maximum structure is Project → Task → Subtask → Sub-subtask: three task levels
below a project. Each task has an independent UUID, optional project membership
and optional parent task. Projects have independent identities but never own work
or timers. Task names need not be globally unique. Cycles, duplicate identities,
cross-dataset relationships and depth overflow reject. Branch moves preserve all
task UUIDs and work; project membership determines current reporting grouping.
Unassigned is a virtual project group, not an additional persisted project or work
owner. It has the same three-task-level limit as real projects: root Task,
Subtask, Sub-subtask. Duplicate task names remain valid at every level.

Only leaf tasks may accept **new time**: Start, Switch destination, Add timed work
and Add date-only work. A task becomes a parent when it gains children. Its
previous direct work remains its Individual Actual, independently readable and
correctable through its own Work History; it is not transferred to children,
discarded or duplicated. Correcting/deleting existing work is not creating new
work. A parent's History stays direct-task history, not an implicit descendant
browser. Descendant work remains accessible by selecting each descendant UUID.

A running task cannot become a parent or be moved into an ineligible state.
Adding a child, reparenting or applying a template cannot bypass this rule.
Archiving any branch containing the running task refuses until an explicit prior
Stop/Switch; an active timer also blocks Delete's unused-only eligibility. No
hierarchy operation silently stops, switches or restarts a timer. Archived or
effectively archived leaves accept no new time; their history remains retained.

The new hierarchy runtime will require fresh data: no version-1 migration,
backward-compatible mode, conversion engine, compatibility shim, JSONL import or
old-runtime fallback. Its schema must identify itself distinctly so an old dataset
cannot be mistaken for supported new data. Incompatible datasets may refuse.
Creation still requires exclusive ownership and a new/empty destination; never
delete, truncate, replace or reuse an old database automatically. Retention of old
filesystem objects is protection, not a requirement to make them compatible.

### Project/task management and branch lifecycle

Provide discoverable project and task management entry points in the main UI,
including a visible project-management route rather than only an unrelated
dropdown. Create project with its own identity. With no selection, New Task creates
an Unassigned root. Otherwise it inserts immediately beneath the selected real or
virtual project group or eligible task, with destination shown before submission.
Refuse a child beyond the depth bound. Rename preserves UUID/work. Move/reparent
reviews source and destination, then atomically moves the entire subtree without
cycles, cross-dataset references, identity changes or partial project reassignment.
Assigning/moving between projects uses this same branch invariant. A selected
effectively archived branch cannot move until it is unarchived, including clearing
inherited hiding through its ancestor path. An allowed move preserves independently
archived descendant states; it must not clear flags to make a move possible.

Exactly two primary lifecycle actions exist: **Archive**, reversible preservation,
and **Delete**, irreversible removal of unused structure. Unarchive reverses Archive;
it is not a deletion tier. No user-facing soft deletion, Deleted Items manager,
separate Permanent Delete, Trash or recoverable Delete belongs to this target.

Archive changes only the selected project/task's explicit archived state and
stores its exact accepted UTC action instant as the current archive timestamp.
Descendants become effectively archived by inheritance; do not rewrite their
independent flags. Preserve identities, relationships, work, history, current
project grouping, frozen reports and POL-R evidence. A running descendant blocks
Archive; never perform an implicit Stop/Switch. Unarchive clears only the selected
node's flag and current archived-at value, preserving independent child flags.
An archived ancestor still hides an unarchived descendant. Unarchive does not
move, rename, restore, recreate or change work. Archiving again later establishes
a new current timestamp; no historical archive-date journal is required merely
to view/sort abandoned unused items.

Project/task management offers Create, Rename, Move, Archive/Unarchive, Delete and
direct Work History using reviewed UUIDs/versions, cancellation without writes,
stale diagnostics and authoritative completion. These remain unimplemented target
operations; current schema-1 functionality is not being relabeled as delivered.

### Unused-only Delete

Delete physically removes selected project/task rows and their complete selected
subtrees from the logical database. It is irreversible and available from
appropriate management surfaces, including Archived Items. Archive is **not** a
prerequisite. It never means deleting a dataset file or deleting work history.

Evaluate the full scope and typed dependency closure. Refuse if any affected entity
has timed work, date-only work, any work revision including deleted work, an active
timer or active-start correction, any frozen Timesheet reference (even zero-valued
scope/basis/task/project references), any POL-R confirmation including confirmed
zero, any current/retained reporting dependency, any protected relationship to
surviving evidence, any unresolved administrative dependency, or an ineligible
descendant. Current Actual = 00:00 is not evidence of unused status. One protected
descendant blocks a whole project deletion. Do not prune protected descendants,
expand the confirmed scope or rewrite history to manufacture eligibility.
A separately selected unused child may be eligible despite its parent's work,
only when its complete dependency closure is independently removable.

Before Delete show the exact scope, affected project/task counts and an explicit
cannot-be-undone warning. Require confirmation, **typed DELETE for branch
deletion**, followed by final transactional validation against the reviewed scope.
Reject stale/racing decisions and require fresh review. Remove all or none of the
eligible entity rows, parent-child relationships, exclusively owned administrative
facts and safely proven exclusively associated administrative request records.
Preserve unrelated survivors and every protected work/report/confirmation record.
Do not retain a recoverable identity, names/notes in tombstones, an anti-replay
registry or a permanent unused-project audit/purge-proof ledger.

Projects/tasks have UUID identity, not name identity. A new item may use the name
of an existing, archived or deleted item, but normal creation always generates a
fresh UUID. Duplicate names never authorize reuse, restoration, merging or
overwriting. Active-template name uniqueness does not apply to projects/tasks.

There is no automatic, age-based, scheduled or background deletion. Existing
backups and filesystem copies remain unchanged. SQLite logical deletion does not
promise secure physical erasure of old pages or external copies.

Surviving requests and all protected evidence retain normal exact committed-request
behavior. **Fully erased administrative requests no longer promise exact historical
retry/result recovery.** Without persistent identity records, a later resubmission
of an erased old request cannot necessarily be recognized or prevented from
reintroducing its old UUID. Normal creation uses fresh IDs; stale queued/concurrent
operations must still pass final transactional dependency checks. Do not claim
permanent replay protection or silently reinstate a registry.

If Delete committed but acknowledgement was lost and its own receipt was erased,
present existence checks can establish current state, not prove that request's
historical outcome. Report failure/uncertainty truthfully; do not automatically
reexecute or invent a retained deletion journal to conceal this limit. The
[proposed deletion/receipt boundary](ARCHITECTURE.md#proposed-unused-entity-deletion-and-receipt-boundary)
requires separate engineering adjudication of its finite allowlist, closure,
cross-entity/survivor dependencies, transaction order, stale/uncertain handling,
independent verification and fresh DDL. Unsafe/unprovable scopes refuse.
Current version-1 receipts and immutable evidence guards remain unchanged.

A task/project with protected history must be archived instead of deleted. Its
retained history stays available to History, Timesheet and POL-R/reconciliation.
The existing work-entry History Delete remains a separate use case: it appends
retained deleted-revision evidence and removes effective work from current Actual;
it does not physically delete the task/work identity.

### Archived Items tree, archive dates and sorting

Provide a discoverable Archived Items window/view with archived projects,
independently archived task branches and descendants hidden by archived ancestors.
Preserve Project → Task → Subtask → Sub-subtask relationships and support full
expand/collapse at every available level, historical Individual/Cumulative values,
direct-task Work History, selected explicit-node Unarchive and eligible-branch
Delete. Explain ineligible Delete/Unarchive. The view is read-only for recording:
no Start, Switch into archived tasks or new manual work beneath archived parents.
Selection, sorting and expansion never make an archived leaf eligible for time.

An independently archived child with active ancestors is an archived entry with
sufficient project/parent context, not a reparented task. An ancestry-hidden child
appears under its archived parent when expanded. Do not flatten relationships or
present one UUID as multiple independent archived records. Unarchive can only
clear an explicit flag; explain inherited hiding without clearing an ancestor.

Display current archive timestamps in the dataset IANA timezone using real DST/
timezone conversion, never creation/modification time or a fixed offset. An
independently archived child has its own accepted timestamp; a descendant hidden
only through ancestry displays its nearest effective archived ancestor's timestamp.
The exact column names/DDL remain proposals, not executing schema changes.

Offer exactly four primary sorting choices:

- Name — A to Z.
- Name — Z to A.
- Date Archived — Newest first (default).
- Date Archived — Oldest first.

Sort among siblings and top-level archived entries while keeping the tree intact.
Use a deterministic stable secondary order such as UUID for equal names/timestamps.
Preserve expansion/collapse throughout the open view, including sorting and normal
refresh; preserve selected identity where still visible. Sort state may initially
be session-local. Do not persist settings without approval, change authoritative
accounting order/UUIDs/membership/work, or unnecessarily rebuild unchanged rows.
Archive/Unarchive trigger targeted structural refresh in main and archived views;
shared exact totals and main/mini observation remain unchanged by visibility.

### Reusable nested templates

Templates have their own UUID/name and a collection of named task nodes with
parent relationships fitting the depth limit. They contain **no Actual, active
timer, confirmations, committed operation receipts or work revisions copied from
tasks**. Template-management operations still have their own ordinary request
receipts. Template edits do not modify previously applied instances.

Provide Create, Edit, Duplicate, Archive/Unarchive, Delete and Apply in a
discoverable Templates manager. Archive/Unarchive makes a definition unavailable/
available. Delete is intended as actual definition removal, not a hidden
recoverable state. Exact eligibility for an already applied/referenced template
is an Open technical dependency question before Package E; never silently discard
retained request/evidence references or introduce tombstones. Task/project unused-
only Delete does not authorize a broad template/history purge. Active template
names remain unique after trim/casefold; Create/Duplicate/Rename/Unarchive must
respect this without overwriting another definition. Applied instances remain
independent and unchanged; project/task names remain duplicable. Apply
fixes the selected project/parent task, shows the structure/destination for review,
and inserts template roots immediately
beneath it. Every inserted task receives a fresh UUID, preserving nested
relationships; the entire insertion and receipt commit atomically. Refuse depth
overflow, stale/ineligible destination and attempts to make a running task a
parent; never overwrite unrelated tasks or leave partial insertion. Duplicate
names do not authorize merging. No recurrence, scheduling or automatic external
task creation is selected.

### Target main and mini presentation

Restore a practical tree layout with distinct project and task rows, expandable
branches, preserved task selection by UUID and running/stopped indicators. Use
green Running and red Stopped with text/symbols so color is not the sole cue.
Ancestors indicate a running descendant without claiming their own timer; expand
the active task's ancestors automatically. Collapse never excludes descendant
work from totals. Sort A-Z must preserve parentage and identity, not flatten or
merge equal names. Sort A-Z is initially session-local. Navigation provides
context-sensitive New Task, task History and metadata editing, visible
project/task management and Archived Items. Starting a project or nonleaf is
unavailable; Stop still targets the sole actual timer, and Switch requires an
eligible distinct leaf. Existing modal and uncertain-request blocking applies to
main and mini actions alike.

Main task columns are **Individual** and **Cumulative**, controlled together by
**Today / This Week**. Individual is exact-task work for that period; Cumulative
is that Individual plus every descendant's Individual exactly once. Project rows
show only derived cumulative totals. A parent with older direct work displays it
in Individual and includes it once in Cumulative; its History opens only that
direct work. Application totals sum underlying task Actual once, never both
columns or project subtotals. Archived history and retained effective work continue
to contribute where applicable even when navigation hides its rows. Main/mini/report daily
facts share the existing exact accounting and one coordinated cutoff.

Mini restores a clear green/red state bar, task name, **Today**, Start/Stop,
Show Main and Keep Mini Open, with appropriate always-on-top behavior. It keeps
the existing active-task/otherwise-selected-task rule and displays that task's
Individual Today; it is never a second timer or a cumulative POL-R source.
Keep Mini Open defaults Off and is session-local. Show Main leaves mini visible
only when that option is On. Mini must not steal focus or grabs from owned modals;
topmost behavior must respect that existing modal owner.

Use minute-boundary presentation updates and immediate post-operation refresh,
updating changed row values/structure rather than rebuilding unchanged rows.
No continuously changing started-at timestamp is required in main. Redraw cadence
is separate from observation: clock movement, date rollover and unavailable
calculations must still be detected accurately, and actions keep exact accepted
instants. No per-minute persistence, rounded work or sleeping UI loop is selected.

These display rollups do not alter reporting scope: POL-R and frozen Timesheets
remain independent task/day identities with existing exact allocation, Unknown/
confirmed-zero, immutable labels and evidence. Parent Cumulative values are never
additional Actual or confirmation cells. Selecting a parent UUID in Timesheet
still selects only that task, not descendants.

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

The current flat runtime shows **Today** and **This week** for each task's own
work. The approved hierarchy target replaces those main columns with shared-period
Individual/Cumulative as specified above. Mini-mode retains Individual **Today**
for its displayed task and Start/Stop.
Application totals retain archived-task work when navigation hides it. Current
schema-1 readers also preserve their existing retained-deleted task identities;
that representation is not a new-target soft-delete tier. One coordinated refresh
uses one aware UTC cutoff and local observation date for main/mini. This week is the complete containing calendar
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
Do not expand descendants. Duplicate names remain separate; archived-task work
stays reportable. Existing schema-1 retained-deleted task inclusion is unchanged,
not a target recoverable-Delete workflow. Calendar selection only edits drafts;
cancellation preserves them and invalid drafts remain correctable. Resolve relative periods at explicit
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
| Hierarchy, branch lifecycle, tree main/mini and nested templates | Approved target packages A–F in the roadmap; not implemented, not silently inherited from JSONL and not authorized for execution by this design task. |
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
validation and cold restore to new directories, independently accepted by the later
Stage 4B GO; the later Stage 4C GO independently accepts Stage 4B. Stage 4B adds
portable transaction/file/backup interruption and queued
shutdown evidence, retains failed-probe cleanup ownership and guards authoritative
outcome delivery against UI faults and mismatched replies. It does not complete
Stage 4.
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
reminder. Stage 4A is independently accepted under the later Stage 4B GO; Stage 4B
portable operational reliability is independently accepted under the later Stage 4C
GO. Native qualification and the remaining Stage 4 gate precede complete pilot.

## SELECTED — Schema compatibility and future upgrade safety

Current production schema remains version 1 with the same application identity.
A healthy complete current dataset permits ordinary work; older/newer markers,
same-version differing schema, foreign identity, unsupported profile and damaged or
unavailable inspection refuse without conversion, recreation or automatic repair.
A lower marker does not establish an authentic older Chronicle schema.

`--inspect-dataset DATA_DIR` is an explicit cold read-only diagnostic, not an upgrade
command. Close other sessions first; inspection creates no lock, Tk root, worker,
backup, receipt or persisted status. It returns detached compatibility diagnostics,
with trustworthy observations only. Supported current results require complete
independent integrity, schema, metadata, audit, work, frozen export, confirmation
and receipt validation plus successful cleanup and final source-stability checks.
Detected changes, unsafe paths or outstanding journals/sidecars make inspection
unavailable rather than authorizing recovery. Existing files are never removed or
repaired to force acceptance. Backup/restore retain their complete current-schema
validation and protected destination contracts.

The later hierarchy approval selects fresh creation rather than a version-1
transformation. No migration/backward compatibility obligation belongs to that
plan; old files remain protected and incompatible data refuses. The current
runtime still supports only its exact version-1 schema. A hypothetical later
data-preserving transition would require a separate explicit approval and complete
source/target, evidence, ownership, installation/failure and recovery contract;
Stage 4C's historical safety contract is not permission or an implementation
requirement to build one for hierarchy. No target version or DDL is activated here.
The [technical boundary](ARCHITECTURE.md#cold-compatibility-inspection-and-future-transition-boundary)
remains strict. Stage 4C is independently accepted for functional development;
Stage 4 remains IN PROGRESS and no pilot is authorized.

## OPEN — Reserved user/ChatGPT decisions

| Decision | First affected gate |
| --- | --- |
| Dataset-timezone changes and historical date attribution under changes | Stage 1 dataset configuration / Stage 2 accounting, before implementation. Explicit fixed dataset zone is required; change policy is not guessed. |
| Unused-only Delete engineering | Before affected B/C implementation: finite administrative allowlist, complete closure/cross-entity survivor proof, transaction/constraint design, stale/uncertain handling and complete independent verification. The owner approves retiring exclusively owned administrative requests without historical retry guarantees; no tombstones/registry/ledger or executable DDL is selected. |
| Referenced template deletion | Before Package E: exact eligibility and retained administrative/request/evidence dependency handling for already applied/referenced definitions. Archive/Unarchive and actual Delete intent are selected; no silent reference removal or tombstones. |
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
