# Chronicle current requirements

## Authority and scope

The latest user/ChatGPT single-schema replacement instruction supersedes the
multi-version development and compatibility workstreams. Chronicle has one current
schema-5 application. Earlier implementations and decisions remain available in
Git history; they are not supported runtime or test obligations. No migration,
upgrade, import, compatibility mode, legacy application, backup/restore feature or
historical qualification infrastructure is selected. No automatic weekly database
creation or automatic deletion is selected. Personal databases are not test data.

## Projects, tasks and creation

Every task has one valid real-project UUID. No virtual Unassigned group, default
project or implicit project assignment exists. Projects have unlimited nesting and
may contain both direct tasks and child projects. Tasks have at most three levels;
project depth consumes no task level. Project containers never own recorded time.
Real empty projects remain visible. Duplicate names remain distinct UUID identities.

One owned New Task dialog reviews editable name, real project tree, complete path,
UUID and root/child context. A selected project prefills its identity but permits
changing a root-task destination. With no selection, the project is initially empty.
A selected eligible task creates its immediate child and inherits the real project
read-only. A running, effectively archived or level-three parent refuses. There is
no first/recent/default project choice. If no eligible project exists, provide an
explicit Create Project route that closes this dialog first; never create/retry a
task automatically. Cancel/X/Escape creates no Request or mutation. Submission
freezes current versions and ancestry; the service revalidates them atomically.

## Hierarchy and lifecycle

Rename preserves UUID and work. Task Move reviews source, destination and the full
branch, enforces task depth, archive and running-parent restrictions, and installs
one atomic move between real projects or eligible parent tasks. It cannot unassign.
Project Move reviews the full project subtree; its organizational Root means nullable
parent_project_id, never a projectless task. No-op movement writes no receipt.

Archive/Unarchive changes only the selected explicit flag/timestamp. Descendants
inherit effective archive state; independent child flags survive ancestor Unarchive.
A running descendant blocks Archive. Archived Items preserves complete hierarchy
context with read-only ancestors and existing sorting. No soft Delete/Trash exists.
Unused-only Delete requires exact reviewed scope, version and typed DELETE. Protected
work, exports, confirmations and dependent retained evidence block it. Whole-Apply
dependencies cannot partially retire. Delete has no receipt and an uncertain attempted
commit never retries or infers history from current absence. Templates are independent
blueprints with at most two task levels; Apply must fit the three-level task limit,
review a real destination, create fresh UUIDs and copy no work. Definition changes
never rewrite applied tasks or frozen Apply evidence.

## Recording and timer operation

New recording is permitted only on eligible leaf tasks. One active timer exists.
Start accepts one UTC action instant; Stop must be later than effective start.
Switch closes the current timer and starts the selected different leaf atomically.
Corrections retain active-start evidence and immutable work revisions. A backwards
observation is a visible clock error, not an automatic timer adjustment. No implicit
Stop/Switch, synthetic work or clock manipulation occurs. Date-only work has a civil
date and positive amount without invented endpoints. Closed timed work uses genuine
UTC endpoints, with explicit DST occurrence review. History shows one task's direct
work, full chronological ordering, exact UUID/revision identity, local allocation
and date-only entries without fabricated instants. Mini uses the Main owner.

## Accounting and week configuration

Retain integer-microsecond Actual and dataset-local calendar attribution. Task
Individual is direct work; Task Cumulative adds descendants once. Project Direct
sums direct task contributions assigned there; Project Cumulative includes descendant
projects without duplication. Application Actual sums task Individual once per task.
Project totals are never additional work. Preserve work through movement and archive.
Week start is explicit persisted configuration, Sunday by default, Monday=0 through
Sunday=6, with reviewed-prior mutation. It never rewrites work or frozen reports.

## Timesheet navigation and report evidence

One TimesheetWindow has four primary sections: Timesheet, Reconciliation, Saved
Reports and Confirmation History. One exclusive growing content host and permanent
Close footer use 980x740 default and 800x620 minimum geometry. Tables grow, and
adjacent vertical/horizontal scrollbars keep UUIDs, dates, actions and status reachable.
Fresh opening shows This week/All tasks with explicit Preview. Reconciliation and
Manual confirmation need no Preview or saved report. Navigation performs worker-owned
read snapshots without mutation Requests or a second writer.

A frozen report is distinct from a fresh Preview. Save registers exact dates,
cutoff, task/project UUID/name snapshots, full-week basis, values and UTF-8 bytes
before external file publication. Saved Reports loads that immutable registered
identity exclusively into Timesheet without recalculation, registration or another
Save, including after restart and when its external copy is absent. Existing save
attempts are not detached by primary navigation. Replacing a report, New Preview
and Close retain explicit unfinished/unverified attempt safeguards. Protected file
publication, conflicts, explicit overwrite, retry and fresh status remain separate
from evidence registration. See [the technical contract](EXPORT_EVIDENCE_CONTRACT.md).

## POL-R allocation and absolute confirmation

Actual, Exported and Confirmed are distinct facts. Exact Actual is not quarter-rounded.
For every task/full week independently, ceil exact work to a quarter-hour target,
then distribute by largest exact daily remainder with earlier-date ties. Zero-work
days receive nothing. Partial views retain the full seven-day allocation basis.
No cross-task/week transfer or accounting arithmetic change is selected. The sole
normative algorithm and independent examples are in the
[allocation contract](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation).

Source confirmation uses only a registered frozen source. Positive frozen suggestions
are checked by default, including already-equal values; zeros are unchecked but may
be explicitly selected. Empty selection is not All. Unchecked cells retain prior
values. Selected stale conflicts need exact cell-specific acknowledgements; changed
priors require fresh review. One authoritative transaction commits the whole batch.
Manual confirmation reviews the current prior and accepts a nonnegative absolute
quarter-hour total, replacing the total rather than adding a delta. Unknown is not
confirmed zero. No automatic confirmation or external POL-R submission exists.

Daily Delta is Actual minus Confirmed; suggested-entry gap is Suggested minus
Confirmed. Opposing daily mismatches cannot net into complete coverage. Current
correction/reconciliation never rewrites frozen evidence. Successful confirmation
keeps its batch UUID and known committed outcome visible until explicit Return,
even if a follow-up read/render fails. A second batch requires renewed explicit
review. Confirmation History shows immutable batches, source/Manual, audit UTC,
task/date, absolute amount, prior identity/amount and stale acknowledgements.

## Review ownership and return

Source/manual reviews are temporary subviews in the same modal. Disable conflicting
navigation and reject direct conflicting calls. Close/X/Escape cannot silently
abandon editable reviews; Cancel/Defer is explicit. Pending/unverified operations
retain exact Request ownership. Retry/Reconcile reuses the original Request.
Return from Reconciliation refreshes its last applied period/task scope, preserves
unapplied drafts, restores task UUID/date selection semantically and clears a row
that no longer exists. Draft changes are never silently applied. Return from
Timesheet goes to Timesheet. A late read cannot overwrite another view or identity.
Failed reads/rendering must not manufacture current data or erase a known commit.

## Reminders

Read previous-week reconciliation each local day used, and current-week coverage
on Friday/Monday. Opening/Save does not dismiss or confirm. Explicit Dismiss for
today persists the local date across restart, without confirmation or cleanup writes.
A new date expires suppression by comparison. Numeric timer ticks do not query
reconciliation every second. Read failure is unavailable, never proof of coverage.

## Startup, persistence and limits

One StartupWindow, Tk root, ChronicleApp, serialized DatabaseWorker, worker-owned
SQLiteStore and transaction authority. Fresh creation installs exact schema 5 with
integrity/FK constraints. Complete current semantic verification precedes ready.
One dataset owner excludes a second writer. Existing unsupported files are not
migrated or automatically replaced. Folder/explicit timezone selection and remembered
startup are shared by zero-argument and explicit source launch. No public schema
selector or old-data recovery interface exists. Use standard SQLite transactions.

## Reserved decisions

Dataset-timezone changes, external employer/customer policy, release/cutover and
pilot deployment remain with the user/ChatGPT. No native Windows qualification,
merge, release or pilot permission follows from implementation or portable tests.
Stage 4 remains IN PROGRESS; Stage 5 remains NOT STARTED.
