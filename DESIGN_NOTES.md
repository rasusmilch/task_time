# Design Notes

This document describes inspected **current implementation** and technical
limitations. The [approved replacement/POL-R contract](docs/TIMESHEET_REQUIREMENTS.md)
owns selected future product behavior, including Open architectural decisions.
Legacy behavior below remains current during staging; it is not permanent policy
for the replacement application. See [AGENTS.md](AGENTS.md) for the ownership map.
The [export evidence contract](docs/EXPORT_EVIDENCE_CONTRACT.md) owns the selected
snapshot-first, decimal-hour and confirmation architecture. Pure decimal rendering,
export-snapshot registration/verified materialization and read-only file-status
evaluation are staged. Confirmation validation/replay and dedicated batch
preparation/registration, frozen-export proposal/selection preparation and read-only
daily reconciliation calculation are staged;
confirmation/reconciliation UI, weekly reconciliation summaries and general
file-status/recovery UI are unimplemented.
The source descriptions below remain current implementation observations.

## Architecture

The app uses an event-sourced model:

1. **Append-only active event log** (`active_events.jsonl`) as authoritative current segment.
2. **Archived immutable segments** under `archives/`.
3. **Manifest/index** (`log_manifest.json`) tracking segment sequence and metadata.
4. **Derived snapshot** (`state_snapshot.json`) for fast startup only.

The complete event stream across archived + active segments is the source of truth.

`EventStorage` classifies the directory before initialization writes. Only a
nonexistent path or a genuinely empty directory (no files or subdirectories) may
receive a new journal. A nonempty directory must already contain regular files
`active_events.jsonl` and `log_manifest.json`; otherwise construction raises
`ValueError`, naming the component and refusing initialization to protect history.
Rejection leaves surviving files and directories untouched, before service setup
can create settings, backups or a derived snapshot. An existing empty active
segment is valid; absence is not equivalent to zero events.

Healthy existing root files are preserved. Strict journal loading separately
validates contents and indexed archives. Neither derived snapshots, archives nor
backups authorize reconstructing a missing root journal file. Supported backup
restoration remains an explicit operation, not initialization recovery. Interrupted
fresh initialization can leave a partial directory that is refused on reopening;
there is no automatic cleanup/repair, concurrent-process initialization guarantee
or universal startup power-loss guarantee.

## Project/task service foundation

`AppState.projects` and `AppState.tasks` are separate UUID-keyed collections.
`ProjectState` stores only `project_id`, `name`, optional notes, and creation/update
timestamps. It has no intervals, timer state, reset boundary, or elapsed counters.
`TaskState.project_id` is optional; each task continues to own its intervals and
recorded time independently. Names are display labels, not identity or matching
keys, and duplicate project or task names do not merge records.

Implemented service operations:

- `create_project(name, notes="")`, `list_projects()`.
- `update_project(project_id, *, name=None, notes=None)` and
  `rename_project(project_id, name)`.
- `create_task(name, notes, tags=None, *, project_id=None)` creates an independent
  task, optionally assigned to an existing project.
- `assign_task_to_project(task_id, project_id)` assigns or moves just that task;
  `None` removes membership. `unassign_task_from_project(task_id)` is the explicit
  unassignment operation. Unchanged updates/membership are no-ops.

Project updates affect project metadata only. Membership changes preserve task
UUIDs, intervals, running starts, tags, notes, and all earlier event evidence.
There are no persisted project roll-up totals; the separate service calculation
below derives project subtotals. Production project reporting remains future
work. Notes use the existing single-line, 160-character convention.

The existing event envelope and durable storage are reused:

| Event | Envelope `task_id` | Payload |
| --- | --- | --- |
| `project_created` | `__app__` | `project_id`, `name`, optional `notes` |
| `project_updated` | `__app__` | `project_id`, at least one of `name`/`notes` |
| `task_project_assigned` | task UUID | `project_id` (project UUID or `null`) |

New independent `task_created` events include `project_id` (possibly `null`) and
`parent_task_id: null`. Project/membership events and this new creation shape are
validated before append and again during replay: required fields, field types,
non-empty names, canonical creation UUIDs, ID collisions, and references must be
valid. Malformed events raise `ValueError`; they are not silently applied or
repaired. Legacy task events without `project_id` retain their existing replay
path. Snapshots include projects and membership, but are derived: startup and
explicit rebuild replay archived plus active events, preserving equal-timestamp
read order. Storage flush/fsync, rotation, and backup architecture are unchanged.

Task-only timer, manual-time, correction, reset, and deletion operations reject
project or unknown task IDs before mutation. Starting a task validates the target
before stopping valid running work. Bulk reset/delete selection validates all
requested IDs before touching any task. Valid task switching still enforces the
one-running-task rule. Legacy historical corrections to existing deleted task records
retain the previous behavior; deleted tasks cannot be started or reassigned.

This foundation does not change the production UI, export calculations,
submission/checkpoint semantics, report rendering, templates, or launcher path.
Legacy `parent_task_id`, `create_subtask`, and `move_task` remain for the current
workflow; project assignment uses the separate operation above and does not
implicitly move legacy descendants. No migration or conversion events exist.

Fresh-start cutover will activate a separate data directory only after project
navigation and timesheet exports are usable. Until then the launcher still uses
`~/.task_timer_data`; it must not be used to experiment with the new service
operations on existing user data. A service initialized with an isolated empty
directory does not import tasks, submissions, projects, or templates from any
other directory. No external-system integration or task numbers are introduced.
The [target contract](docs/TIMESHEET_REQUIREMENTS.md) requires installation/workflow
replacement and a fresh dataset without migration. Exact release cutover and
old-data handling remain Open; existing files are not authorized for deletion.

## Dated-duration replay foundation

`DatedDurationRecord` is distinct from `IntervalRecord` and lives in the separate
`TaskState.dated_durations` collection, keyed by stable entry UUID. Its fields are
entry/task UUIDs, a `date`-typed `work_date_local`, positive `duration_seconds`,
`reason`, creation/update audit timestamps, `revision_event_id`, and `deleted`.
It has no start/stop fields or nullable endpoint placeholders. A long duration
remains one declared amount on its selected date; no synthetic interval or second
work date is generated. Creation/update timestamps describe audit actions, not
the beginning or end of that work.

The existing event envelope, task ownership and JSONL store are reused:

| Event | Required payload |
| --- | --- |
| `dated_duration_added` | `entry_id`, `work_date_local`, `duration_seconds`, `reason` |
| `dated_duration_corrected` | same complete fields, with the existing `entry_id` |
| `dated_duration_deleted` | `entry_id`, `reason` |

The owning task UUID is the envelope's `task_id`. Creation requires an unused
work-entry UUID across all tasks, including intervals and dated-entry tombstones.
Correction updates that entry's effective date/amount/reason without allocating another
entry or changing ownership or creation time. Deletion marks the record deleted
while retaining its last date/amount. Both actions update its audit timestamp and
revision to the current event UUID. Original amounts, dates and reasons remain
recoverable from the unchanged earlier events, rather than duplicated in another
history file.

Shared internal validation runs before private append and before replay mutates
state. It requires canonical task/entry/event UUIDs, an existing task owner rather
than a project, exact payload fields, a canonical `YYYY-MM-DD` calendar date,
finite positive numeric seconds (not booleans), and a nonempty string reason.
Audit timestamps use the existing UTC `Z`, second-precision event convention.
Unexpected endpoint fields, duplicate identities, missing/deleted entry targets
and cross-task corrections/deletions raise `ValueError` without partially
changing task or record state. Existing legacy event handlers are not migrated.

Replay retains the existing `(timestamp_utc, _read_sequence)` ordering contract:
equal-second events follow their original segment read order, not their UUID
order. Events appended in memory without read metadata use their original list
position, so a same-second correction after restart stays after loaded creation
events. The latest effective record is stored once under its original entry UUID;
its `revision_event_id` identifies the latest creation/correction/deletion event.
Snapshots serialize dated records separately, with an ISO work date and audit
timestamps but no clock endpoints. Startup and snapshot rebuild derive them
again from archived plus active events. Existing backup/restore mechanisms carry
the same logs and snapshots without introducing a new persistent file.

New lifecycle events are currently
exercised through isolated fixtures and internal validation; **there is no new
public duration writer**. `add_manual_duration`, `edit_duration_interval`, legacy
synthetic records, real interval mutation, resets, checkpoints, tags, exports and
submission backend behavior remain unchanged. Independently callable interval-only
export/submission consumers still omit dated records. Main/mini calendar Actual,
Work History and production frozen Timesheet now include both supported record types. Remaining active-reader integration must be validated
before the new workflow emits production dated events. Production
reset/checkpoint consumers remain legacy. The selected
[date-scoped POL-R workflow](docs/TIMESHEET_REQUIREMENTS.md) does not use an
implicit export checkpoint or timer reset to distinguish newly worked time.
No new date-based checkpoint/reset extension is implemented. No legacy migration
or fresh-directory cutover is performed; `~/.task_timer_data` remains outside
this development workflow.

## Mixed date-window accounting

Sunday-start weeks are current source behavior. The
[selected configurable-week model](docs/TIMESHEET_REQUIREMENTS.md#selected--configurable-week-convention)
permits any weekday with Sunday as the initial default, but is not implemented.

`TaskTimerService.calculate_date_window(start_date, end_date, *, cutoff_utc,
all_tasks=False, task_ids=(), project_ids=(), include_unassigned=False,
include_deleted=False)` is an independent, read-only service API. Supply Python
`date` objects for an inclusive, ordered local-calendar window and one aware
datetime cutoff. The end boundary must be representable (not `date.max`). The
service's detected local timezone supplies the calendar boundaries.

Selection is the union of explicit task UUIDs, the current member tasks of
selected project UUIDs, and Unassigned tasks when requested. `all_tasks=True`
explicitly selects all eligible tasks. Defaults and explicit empty selections
select nothing. Duplicate selections are deduplicated by task UUID; task-only
selection never expands to siblings or legacy descendants. Unknown task/project
references are rejected before contribution calculation, even with `all_tasks`.
Deleted tasks are excluded by default, including explicit task selections.
`include_deleted=True` includes their valid historical work under the same
selection rules. This policy is recorded in the returned report.
The detached report also carries `scope` (`complete` exactly when `all_tasks=True`,
otherwise `selected`) and `local_timezone`, derived from the actual bucketing
timezone's IANA key/zone or its string label. Deleted-task inclusion is independent
of scope. Empty reports preserve their requested scope identity. These fields
are derived presentation metadata in the calculation result. Separate export
registration freezes these facts as evidence without changing accounting state.

Each included task's daily seconds combine two distinct authoritative sources:

- Nondeleted effective `IntervalRecord` versions with `entry_mode="interval"`:
  genuine endpoints are clipped to the report's local midnight boundaries and
  the single cutoff. Local day boundaries are converted to UTC, preserving
  actual elapsed seconds on 23/25-hour DST days. Separately recorded overlapping
  intervals count individually. Negative stored spans raise `ValueError`; zero
  spans contribute zero. Running work uses its existing start and the fixed
  cutoff, without appending events or changing timer state. A cutoff before the
  running start contributes zero.
- Nondeleted effective `DatedDurationRecord` entries: their full seconds belong
  entirely to `work_date_local` when that date is in scope. Audit timestamps and
  cutoff do not allocate, clip, or split dated amounts. Corrected predecessors
  and deleted entries contribute nothing. No temporary endpoints are created.

Historical actuals ignore `last_reset_utc`; resets do not erase earlier calendar
work. This API uses current effective revisions, deletion status, tags, and
membership. The cutoff caps timed work, including closed endpoints after it;
it does **not** reconstruct application state as of an earlier instant. Legacy
timestamp checkpoint consumers are unchanged; the Selected replacement removes
Reset actions and resettable counters rather than extending them to dated work.

The returned detached dictionaries contain `tasks` and `projects` keyed by UUID,
plus `unassigned`, `application`, and `tags`. Each total row has sparse
`daily_seconds` maps keyed by local `date`, `weekly_seconds` maps keyed by Sunday
`date`, and `window_seconds`. Missing date/week buckets mean zero. Weekly totals
derive from daily totals only, and partial weeks contain only requested dates.
Raw seconds are summed with `math.fsum`; no formatted hours/minutes are accounting
inputs. Task rows retain names as labels and deletion/membership metadata.
Aggregate rows list their included `task_ids`.

Project rows derive solely from included member task rows. Their `scope` is
`full_project` when all members eligible under the chosen deletion policy are
included, otherwise `selected_tasks`; `eligible_task_count` makes the distinction
explicit. Explicitly selected projects and all projects under `all_tasks` appear
even when empty. Reassignment groups the task's entire historical window under
its **current** project, preserving task amounts and application actual time.
There is no historical membership splitting or project-owned contribution.

Conservation invariants are task daily sum = task weekly sum = task window total;
sum of task totals = application actual; sum of project subtotals + Unassigned =
application actual. Project subtotals are never added to tasks again. `tags` uses
these same task rows and direct task tags, with intentionally non-exclusive
categories and no project/ancestor inheritance. The `None` key denotes untagged
tasks, distinct from a literal `"untagged"` tag. Tag totals must not be summed as
exclusive application actuals. Submission amounts, export snapshots, and frozen
submission evidence are never consulted or added.

An effective legacy `entry_mode="duration"` interval raises
`UnsupportedLegacyDurationError` if its declared work date **or** synthetic
endpoint span touches the requested window. The endpoint check detects fabricated
spillover; it never allocates seconds. An invalid legacy work date also fails
explicitly. Deleted legacy records, unselected tasks, and legacy records entirely
outside the window do not contribute. No legacy conversion or event rewriting
is performed; unsupported synthetic work fails visibly in connected readers.

This API persists nothing. Main/mini calendar Actual and frozen Timesheet preparation
consume it; independent legacy backend exports, submission/checkpoint rules and
production dated writers remain unchanged.
The event logs and their effective projections remain authoritative; snapshots
remain rebuildable. Remaining reader/writer integration and the separate
empty-directory cutover are later tasks. Tests use isolated temporary datasets.

## Production calendar Actual displays

`TaskTimerApp.refresh_live_values()` captures and validates one aware observation,
normalizes it to UTC, derives local today and its Sunday-through-Saturday week,
and calls `calculate_date_window()` once with `all_tasks=True` and
`include_deleted=True`. Each task's Today uses `daily_seconds[today]` (absent
bucket means zero); This week uses `window_seconds`. Application headlines use
the report's application totals. Parent rows retain hierarchy but display only
own work; deleted work contributes to application totals without visible task
rows. Full-week dated amounts are included even after today's cutoff date;
timed contributions remain cutoff-capped under the existing accounting contract.

The application prepares all numeric values and completed-minute text before
replacing numbers. New rows start with —. Calculation/date/formatting failure
marks all time cells and headlines —, reports the original exception through
Tk callback diagnostics and shows one inline "Time totals unavailable." message
per window. Task states and Start/Stop remain available. The normal minute tick
continues and a successful refresh clears the error; destruction prevents new
scheduled callbacks. No report is retained across refreshes.

`MiniModeWindow.refresh_live_values(*, today_seconds_by_task)` receives the same
ephemeral raw Today mapping, or `None` on failure. It renders `Today: HH:MM`, or
`Today: —`; valid no-task results retain the no-task state and `Today: 00:00`.
The mini constructor starts unavailable and performs no numeric refresh. The
application publishes the new window before coordinated refresh; opening an
existing mini also refreshes through the owner. Start/Stop uses its existing
application callback. `refresh_reminder()` changes only reminder visibility.
Mini-mode captures no accounting clock and queries no totals service.

The superseded `compute_totals`, `task_elapsed`, `task_own_elapsed` and
`task_tree_elapsed` display helpers are removed. `_all_intervals`,
`_effective_intervals` and `_windowed_intervals` retain their interval-only,
reset-sensitive export dependencies. Production dated writers, project navigation,
POL-R presentation and configurable-week settings are not activated.

## Mixed work-history service

`TaskTimerService.get_task_work_history(task_id, *, cutoff_utc,
start_date=None, end_date=None, newest_first=True)` resolves the task through
`_require_task`, including known deleted tasks, and delegates to the pure
`work_history.build_task_work_history` projection of current effective records
and the service's local timezone. It does not reread the journal, reconstruct
historical as-of state, consult resets/confirmations, install caches or capture
the clock/UUIDs. Existing interval-only readers and production callers are unchanged.

An aware cutoff is required and normalized to UTC. Both dates omitted means All
history; otherwise both must be exact `date` objects, inclusive and ordered, with
`end_date != date.max`. `newest_first` must be an actual bool. Invalid requests
raise `ValueError` without mutation. The cutoff caps timed work only; dated
amounts retain their declared dates, including dates later than the cutoff.

Each detached dictionary has exactly these fields:

`task_id`, `entry_kind`, `entry_id`, `work_date`, `segment_start_utc`,
`segment_stop_utc`, `duration_seconds`, `original_start_utc`, `original_stop_utc`,
`is_running`, `continues_before`, `continues_after`, `source`, `reason`.

`work_date` is a `date`; non-null endpoints are aware UTC datetimes. Seconds keep
raw precision without formatting or decimal rounding. Nondeleted effective
genuine intervals yield `entry_kind="interval"` rows split at local midnights,
using UTC elapsed differences and omitting nonpositive portions. Window/cutoff
clipping changes segment endpoints, not the complete original closed endpoints.
All portions share the original interval ID; that identity plus work date
distinguishes visible rows without new segment UUIDs. Continuation flags describe
other daily portions of the cutoff-limited interval even when filtered out.
An endpoint exactly at midnight creates no following zero row. Interval source
is preserved; reason is `edit_reason` or an empty string.

Running rows use `entry_id="__open__"`, `source="open"`, empty reason and
`is_running=True`; original start is the genuine running start and original stop
is `None`. Segment stops are projection boundaries through the supplied cutoff,
not recorded timer stops. A cutoff at/before the start contributes nothing.

Each nondeleted effective dated record appears once, wholly on its work date,
with its existing ID, full amount, current reason, `entry_kind="dated_duration"`
and `source="dated_duration"`. All four endpoints are `None`; running and
continuation flags are False. Audit timestamps supply neither work times nor
within-day sort positions.

Dates sort descending by default or ascending on request. Within each date,
timed segments always sort by UTC start, UTC stop and entry ID; dated rows follow
by entry ID. Changing date direction does not reverse within-day chronology.
The projection ignores deleted/replaced records and matches mixed accounting's
rejection of unsupported interval modes, naive endpoints and negative spans.
Effective synthetic `entry_mode="duration"` records raise
`UnsupportedLegacyDurationError` when their declared date or raw synthetic span
intersects the requested window; All history includes them. An invalid declared
date fails explicitly. Out-of-scope/deleted synthetic records are not converted.

The [Selected history contract](docs/TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history)
also covers current-week/custom/All UI periods, application-session date direction,
one history window per application, linked segment interaction, type-preserving
editing and audit/details. Those UI/session, edit/delete and audit capabilities,
production dated writers are not implemented by this reader; calendar Actual
displays and UI Reset removal are described separately. POL-R remains
a separate task/day service. No schema, identity or persistent state is added.

## Mixed work-history table

`work_history_view.WorkHistoryFrame(parent, *, local_timezone)` is a standalone
`ttk.Frame`/Treeview. `display_rows(rows)` consumes the complete ordered results of
the history service above; it performs no service/journal access, clock capture,
scheduling, settings management or application-state installation. Its timezone
is explicit. Complete rows are copied into UI-local metadata behind distinct
transient widget handles, without adding fields or generating segment identities.
Input order, precise seconds, original endpoints and continuation flags survive.

Columns are link marker, Date, Kind, Start, End / as of and Duration. Dates use
YYYY-MM-DD. Kind is Timed, Date only or Running; dated clock cells are blank.
Timed segment endpoints use local 24-hour HH:MM, prefixed with their actual date
when different from the row date. Repeated-minute detection reuses
`local_minute_candidates`; ambiguous endpoints include their actual UTC offset,
including non-hour offsets. Running stops are supplied observation boundaries,
not recorded stops. Durations use supplied seconds: 0:00 for zero, <1 min for
positive values below 60 seconds, otherwise completed minutes as H:MM with
unbounded hours. This formatting neither derives work from displayed clocks nor
changes accounting, raw precision, billing rounding, exports or confirmations.

Interval portions show ↔ when either continuation flag is true. A selection
callback highlights other visible portions sharing task/kind/entry identity with
a component-local bold-font tag, without global style changes or multi-selection.
Running __open__ identities remain task-scoped; dated entries do not link. Stale
handles are ignored and replacement/selection changes clear obsolete feedback.

All copied rows and display values are prepared before widget replacement.
Unsupported kinds, missing data, invalid durations and unrepresentable endpoint
conversions fail visibly and propagate, preserving the previous successful rows
and metadata. Widget-update failure invalidates metadata/selection and hides the
untrusted table where usable, with a visible error; it claims no GUI rollback.
A subsequent explicit successful render restores the table and clears the error.
Empty input is a valid empty display. No rows are silently omitted or legacy
synthetic work converted.

This render-only component delegates period/sort controls to the browser
below. Neither component schedules automatic loading. Both shipped Work History
commands compose these components through the application-owned modal path.
Correction actions, creation/deletion and audit remain pending; task Reset UI
actions are removed and main/mini calendar Actual is connected separately.
The superseded timeline dialogs/formatter/reader are removed; no new persistent
state or domain projection exists.

## Single-task history browser

`work_history_browser.WorkHistoryBrowserFrame(parent, service, task_id, *,
now_utc, week_start=6, newest_first=True, on_direction_changed=None)` composes the
existing reader/table for one fixed task. Configuration requires an explicit
callable clock, an actual integer weekday 0–6 (Monday=0), actual boolean direction and an optional callable
direction handoff; invalid configuration rejects before widget construction or
loading. It uses the service timezone. Construction attempts one
Current week load. `refresh()` reports True on successful loading/rendering and
False after inline operation failure; routine UI callback failures do not escape.

Each load observes the supplied clock once, validates/normalizes the aware cutoff
to UTC and calls the history reader once for a valid request. Current week derives
seven inclusive calendar dates from the local observation and supplied weekday;
it recalculates on refresh without fixed UTC-hour spans or changes to shared
accounting/week helpers. All omits both date bounds. The weekday argument is a
staged integration seam, not a configurable-week setting.

Custom exposes ordinary editable YYYY-MM-DD fields and owned `tkcalendar.Calendar`
popups. Drafts are not applied by typing, focus changes or picking. Apply trims
surrounding whitespace and requires canonical real ordered dates, rejecting the
reader's unsupported final-date boundary without clipping. A picker starts from
a valid draft or a previously captured valid local observation date, never a new
application clock capture; absent a seed it reports an error. Selection changes
only that draft to canonical ISO; cancellation changes nothing. Required
`tkcalendar` is imported without a silent picker fallback. Owned popups are
closed on browser destruction.

Opening, Apply, switching to Current week/All and explicit Refresh load work;
entering Custom only reveals retained drafts. Refresh uses the last successfully
applied period/Custom dates, ignoring unapplied drafts, or retries Current week
when no load has succeeded. A concise last-successful period and local as-of
label commits only after rendering; Not loaded is distinct from successful empty
history. Clock/service/validation failure preserves rows, metadata, selection,
drafts and applied information. Table preparation preservation and widget-update
invalidation remain owned by the table; failed candidate results are not installed
and no GUI rollback is claimed. A later explicit load can recover.

The browser owns the existing Date heading command. It stably sorts detached
successful rows by work_date only, preserving within-day order and every field;
no reader/clock call, draft application or cutoff change occurs. The exposed
`newest_first` property changes only after successful rendering. Both successful
loads and sorts use the table's selection clearing and related-portion behavior.
Only a successful Date-heading sort notifies `on_direction_changed`, once, after
rendering and committing its rows/direction. Construction, loads, refreshes,
picker operations, failed sorts and destruction do not notify. Notification
failure reports inability to remember the session direction inline, preserving
the completed sort and its True result; it neither rolls back nor retries.

Results, drafts and last-successful request/cutoff are temporary UI state, not an
authoritative projection or cache installed in the application.
`TaskTimerApp` initializes `_history_newest_first = True` before building controls,
independently of dataset settings. Its
`_make_history_browser(parent, service, task_id, *, now_utc, week_start=6)` imports
the browser locally and supplies that owner direction and the bound
`_remember_history_date_direction(newest_first)` assignment callback. It neither
opens a window nor changes the application's service. Sequential browsers for
different tasks/datasets share only that in-memory direction; closing a browser
does not reset it, and a new application owner starts newest-first. No preference
file, resolver, settings field or cross-process coordination is used or required.
Window ownership is provided by the modal path below; neither the Frame
nor the browser factory enforces it. Read-only production access is connected;
editing/audit and writer activation remain unimplemented. Task Reset UI actions
are removed and main/mini calendar Actual is connected separately.
The browser accesses no settings, writes no work, and schedules no refresh, retries or asynchronous loading.
Accounting, mutation services and settings ownership are unchanged.

## Owned modal history window

`history_window.HistoryWindow(parent, *, make_browser, on_closed)` creates a
withdrawn `window` Toplevel, composes the accepted browser and adds Close. The
constructor neither grabs nor waits. `show_modal()` presents it transient to its
parent, waits for visibility, rechecks the current grab immediately before
acquisition, focuses history and uses Tk's normal window wait. Acquisition permits
no grab or the originating top-level's local grab; an unrelated/global grab that
appears during visibility waiting is preserved and the conflict propagates after
history cleanup. Presentation performs no additional history load.
Normal scheduled events continue, including existing timer processing; no
automatic history refresh or work mutation is introduced. The browser remains
attached to its original task and owns its calendars, drafts and explicit loads.
Calendar mouse selection/cancellation remains usable under the ancestor grab,
Apply-only, and picker Escape does not close history or release its modality.

`TaskTimerApp` initializes `_history_window = None` and
`_history_window_opening = False` before building controls. Its lazy
`_open_history_window(service, task_id, *, now_utc, week_start=6, modal_parent=None)`
uses the root by default and sets the in-progress guard before parent validation
and context capture. An explicit parent must be a live top-level of this
application's Tk root; invalid parents reject before widgets, clock capture or
work reads. Before construction the owner captures its grab/focus, permitting no
grab or that parent's local grab only. It delegates browser composition to
`_make_history_browser`, then publishes the owned wrapper before presentation
can process modal events.
Duplicate/reentrant requests return without building, observing the clock,
reading work, refreshing or retargeting. A destroyed stale reference does not
block reopening. `_history_window_closed(window)` clears ownership only by
object identity, so an old callback cannot clear a later wrapper. Closing retains
the application's session direction; later openings use the existing handoff.
The guard remains active through construction, presentation, cleanup and return
restoration, including after the owned reference has been cleared. Duplicate
requests do not inspect their supplied arguments.

`close()` is idempotent. Close, window-manager closure, external destruction and
root shutdown dispose of the browser/calendars and release the modal wait.
Only destruction of the owned Toplevel notifies `on_closed(wrapper)`, once for a
successfully constructed wrapper; child destruction does not. Construction or
presentation/grab failure disposes partial widgets, releases only that window's
own grab and propagates the failure with cleanup context if necessary. Ownership
and the construction guard are cleared so later openings can succeed. An initial
inline browser loading failure is a usable window, recoverable through explicit
Refresh, rather than a construction failure.

The application owner restores modal context after disposal, outside Destroy
callbacks, on normal closure, external destruction and construction/presentation
failure. If the application or originating parent was destroyed, it skips return
without recreating or redirecting to an ancestor. Another live window's grab
causes an intentional skip of both grab and focus restoration. Otherwise only a
captured local parent grab is restored, without reacquiring one already held;
no prior grab means no invented return grab. A surviving saved focus widget in
the same top-level receives ordinary `focus_set()`, otherwise the surviving
parent does. Return never forces application activation. Widget survival uses
existing Tk object membership and exact Tcl command existence, including after
root destruction; a reused widget path does not revive an old object. Unexpected
inspection/restoration errors propagate rather than being classified as death.
If an earlier failure exists, it remains primary with restoration/cleanup
diagnostics retained. The guard clears in the final exit path even on failure.
No originating editor is saved, closed, reconstructed or refreshed.

Both shipped Work History commands use this one application owner. The bound
`_open_task_history(parent, service, task_id)` adapter supplies the explicit origin,
service/task, `utc_now` callable and Sunday `week_start=6`. The selected-task panel
uses the root; `EditTaskDialog` requires keyword-only `open_history`, propagates
the same bound callback to recursive subtask editors and supplies its own window.
History does not set editor changed flags, save drafts or refresh the origin.
The main command disables without a selection. Origin-local inline launch errors
start “Unable to open work history:” and clear on a new attempt; main errors also
clear when the selected task changes. Ordinary launch exceptions are reported
with their original traceback/notes through Tk's `report_callback_exception`,
without message boxes or grab/focus changes. Destroyed origins are not recreated.
Browser load failures stay inside the usable browser and are not launch errors.

`EditTimelineDialog`, `TimelineEntryDialog`/result, `get_task_timeline` and the
exclusive timeline formatter and UI-only service parsing wrappers are removed,
without compatibility aliases.
Read-only access replaces both old commands; the old creation/correction/deletion
and missed-stop controls are not retained as a parallel interface. Replacement
editing/audit remains separate. Existing shutdown/reminder choices, mutation
services, storage and settings remain unchanged. This is fresh replacement work,
not legacy-data compatibility: applicable synthetic work fails visibly under the
existing reader contract, without fallback, conversion or omission. User files
and installation/data-directory cutover are untouched. Read-only history alone
does not satisfy the Phase 3 active-reader gate. There is no window registry,
persistent identity, polling or additional mainloop.

## Replacement timed-input validation (staged)

`task_timer.work_entry_inputs` provides three pure APIs, without a service facade:

- `local_minute_candidates(work_date, time_text, local_timezone)` returns a tuple
  of distinct aware UTC datetimes in chronological order: one for ordinary local
  time, two for repeated time and none for a nonexistent time. It requires an
  exact `date`, string clock input and a valid supplied timezone object. It reuses
  `parse_flexible_time` unchanged; seconds/fractions in clock input are rejected.
- `resolve_timed_interval_input(start_date, start_time, end_date, end_time,
  local_timezone, *, start_occurrence=None, end_occurrence=None)` returns a detached
  dictionary with exactly `start_utc`, `stop_utc` and `duration_seconds`.
  Each endpoint is resolved independently. An ordinary endpoint requires `None`;
  a repeated endpoint requires `"first"` or `"second"`, referring to chronological
  UTC order. A nonexistent endpoint raises a clear `ValueError`. Invalid requests,
  occurrence selections and unrepresentable conversions also raise `ValueError`.
  Stop must be strictly after start in UTC, and elapsed seconds use UTC subtraction.
- `resolve_timed_interval_edit_input(original_start_utc, original_stop_utc,
  start_date, start_time, end_date, end_time, local_timezone, *,
  start_occurrence=None, end_occurrence=None)` validates aware original endpoints,
  positive original UTC span and local representability. It resolves proposed
  endpoints independently. Subtracting each original endpoint's local seconds
  and microseconds from its UTC instant establishes a minute candidate, which
  must occur in `local_minute_candidates` for the displayed date/clock. A matching
  proposed candidate restores the complete original endpoint. Only then are
  UTC ordering and precise duration checked. Equivalent clock text and editing
  back preserve precision; positive same-minute original spans remain valid.
  Changed occurrences are distinct candidates; no sticky dirty flag or rounding
  is used. The return shape remains exactly the same three fields.

Candidate validation tries both fold values and round-trips local → UTC → local,
requiring the complete requested wall datetime to survive. Results deduplicate
by UTC instant; different folds/offsets alone do not prove ambiguity. Standard
`ZoneInfo` and fixed-offset `timezone` objects are supported, including non-hour
transitions. No timezone detection, current date/clock capture, network lookup,
default occurrence, overnight inference or automatic gap adjustment is performed.

The [Selected minute-only behavior](docs/TIMESHEET_REQUIREMENTS.md#selected--actual-time-records)
applies to replacement entry/editing/display. These APIs interpret input only:
they do not format display, alter existing recorded work, round accounting/billing,
create identities, persist state or activate a writer/editor. Existing
`parse_flexible_time`, timezone-attaching `combine_local_date_time`, production
dialogs, service mutations, accounting, replay, exports and confirmations remain
unchanged. Those active legacy callers do not yet use this validation. Stale-edit
protection, running-work actions, audit UI, sort preferences and linked-row styling
are not delivered by this module.

## Timed-interval input form (staged)

`timed_interval_form.TimedIntervalInputFrame(parent, *, local_timezone,
start_date, end_date, start_time="", end_time="")` is a standalone `ttk.Frame`.
The caller supplies the timezone object, exact date objects and clock strings;
the frame captures no current date/time and loads no stored records. It uses only
standard tkinter/ttk controls, with separate Start date/time and End date/time
fields, initial ISO dates, a compact timezone label and inline endpoint/interval
errors. Date text must be canonical `YYYY-MM-DD` after surrounding whitespace
is trimmed for parsing; entered draft text is retained. Clock interpretation
delegates to the [accepted pure validators](#replacement-timed-input-validation-staged).

Each endpoint shows a readonly occurrence selector only for two valid UTC
candidates, in their chronological order. Labels include First/Second, local
`HH:MM` and the candidate's actual UTC offset, including non-hour offsets.
Repeated-time choices start empty. Any change to an endpoint's date or clock
text clears that endpoint's choice and recomputes its candidates without clearing
the other endpoint's still-valid selection. Ordinary, invalid and nonexistent
drafts have no active occurrence selector; invalid drafts report inline errors
without escaping widget callbacks.

`resolve_input()` revalidates current fields/selections through
`resolve_timed_interval_input` on every call, returning its fresh detached
`start_utc`, `stop_utc`, `duration_seconds` dictionary. Failure preserves entered
values, shows the affected endpoint or interval error and raises `ValueError`;
success clears obsolete errors. There is no cached successful result, inferred
overnight date, truncated second input, guessed occurrence or adjusted gap.

`resolve_edit_input(original_start_utc, original_stop_utc)` freshly delegates
current fields and choices to the precision-preserving resolver with the same
inline-error/draft retention behavior. Ordinary `resolve_input()` is unchanged.
`set_occurrence(endpoint, occurrence)` accepts start/end and None/first/second;
None clears one choice, while first/second requires a valid repeated-time draft.
Invalid requests raise without changing drafts or the other endpoint. The
standalone editor initializes only occurrences proved by stored UTC evidence;
ordinary frame construction still leaves repeated-time choices empty.

The containing editor owns confirmation/cancellation and saving. This frame has
no Save actions, mutation callbacks, duration switch, reason policy, running-stop
operation, record identity, audit interface or persistence. It is composed by the
[standalone correction dialog](#standalone-timed-interval-correction-dialog-staged),
with no production correction callers. Mixed-history browsing is connected
separately; replacement record editing and writer activation remain pending.
The retired legacy timeline input dialog is removed; mutation services remain.

## Timed-interval corrections (staged)

`prepare_timed_interval_correction(task_id, interval_id, *, start_utc=None,
stop_utc=None, comment="")` strictly reads the authoritative journal and reuses
existing work replay on a detached temporary service/state copy, without calling
the service constructor or installing state. It requires a nondeleted task and
an effective, positive, genuine closed interval. Projects, dated/synthetic work,
open intervals and superseded/deleted priors reject; a separate running interval
is preserved. No legacy checkpoint/submission restriction is consulted.

`None` preserves an endpoint exactly. Supplied endpoints are aware datetimes
normalized to UTC; a changed endpoint must be a whole local minute, while an
explicitly unchanged endpoint retains seconds/fractions. Stop must exceed start
in UTC. Comments are trimmed strings and may be empty. No endpoint change returns
`None` without a correction event, backup, snapshot or audit-clock capture; this
is not standalone comment editing.

Otherwise preparation freezes the existing `interval_edited` envelope with a
new event UUID and replacement interval UUID, unchanged schema and UTC-second
audit timestamp. `local_timezone` is offline UTF-8 metadata text with no surrounding
whitespace or C0/C1 controls, not a database-resolution requirement. Payload fields
are exactly `interval_id`, `new_interval_id`, `start_utc`, `stop_utc`, `entry_mode`,
`prior_interval_label`, `reason`; mode is `interval`. Endpoints use canonical UTC
`Z` strings preserving fractional precision. The label retains original canonical
start, ` to `, and stop. The original tombstone, replacement link/comment and event
audit time retain correction evidence. Replacement IDs cannot reuse interval or
dated-entry identities, including tombstones.

Structural validation lives in `interval_corrections.py`. Prospective replay uses
the candidate's next physical read sequence and checks exactly the intended
replacement against applying it once to the detached authoritative baseline.
Other work, task/project attributes, timers and export/confirmation projections
must agree; only the affected task's update timestamp may reflect normal replay
order. Problematic backdating rejects rather than retimestamping or changing the
shared replay policy.

`register_prepared_timed_interval_correction(prepared_event)` copies and validates
the frozen event, strictly rebuilds current authority, and checks identity before
prior effectiveness. One exact existing event may be reused; repeated occurrences,
conflicting content and cross-type identities fail closed. New events recheck
ownership, effective prior, endpoints, replacement collisions and prospective
effects, use the configured risky-operation backup hook, then repeat the gate
before one `storage.append_event` call. Generic `_append` is not used.

Ordinary successful append supplies flushing; strict reread verifies the event
and all projections. Exact reuse or recovery of a complete event after append
error requires successful `synchronize_journal`, including handle close, then
strict reread and complete replay. Healthy absence raises with retry context;
partial/unreadable/conflicting evidence fails closed without repair or another
append. Retries retain both identities and rebuild the latest complete state,
never reinstalling an older correction or confirmation.

After verified registration, state, journal and export/confirmation projections
are installed together, then the existing derived snapshot is saved. The detached
result has exactly `event_id`, `replacement_interval_id`, `projection_installed`,
`snapshot_saved`, and `warnings` (a tuple of diagnostic strings). Normal booleans
are both true. Installation failure returns both false, identifying the correction
as registered and retaining the prepared event for unchanged retry; no stale
snapshot is saved. Snapshot failure returns true/false and reports registration.
Recovery warnings preserve append-error context. Unverified or pre-registration
outcomes raise; they do not assert that no bytes were written.

`read_task_for_timed_interval_correction(task_id) -> TaskState` strictly reads
the journal, reuses the detached reconstruction helper, resolves through
`_require_task` and returns a deep copy. Known deleted tasks remain readable for
conflict presentation; missing tasks and projects reject. No constructor,
installation, synchronization, snapshot, backup or clock capture is used.

This is serialized staged service behavior, not a transaction/power-loss or
concurrent-writer guarantee. The standalone dialog consumes these APIs without
production callers. Legacy required reasons/checkpoint checks remain unchanged.

## Standalone timed-interval correction dialog (staged)

`timed_interval_editor.TimedIntervalCorrectionDialog(parent, service, task_id,
interval_id)` composes the form and correction services. It edits one complete,
effective, positive, genuine closed interval of a nondeleted task. Dated,
synthetic, open, missing and superseded work reject. Authoritative loading and
local representability checks occur before creating the modal; construction
failure destroys any partial window/grab. The explicit service timezone supplies
separate dates, minute clocks and proved original occurrences; the optional
comment starts empty. Audit timezone metadata is not resolved.

Before every new preparation, the dialog reloads authority and compares the
reviewed interval record, retaining drafts/comments on failure. Task renaming
and unrelated work do not invalidate a record. Fresh conflict information is
read-only: only an unambiguous, acyclic same-task replacement chain is followed
to a supported current successor. Deletion, missing evidence, branching, cycles
and unsupported records are reported without retargeting or replacing drafts.

Edit-aware form resolution preserves original precision. Preparation/registration
remain delegated to the accepted services; no-op/comment-only saves finish
unchanged. A prepared event is retained before registration. After an attempt,
inputs/comment are locked, Cancel becomes Close and retries invoke only the
registrar with the unchanged event, bypassing the original-prior UI gate.
Reentrant Save/retry/close callbacks are ignored while a service call is active.

An exception without a previous returned result means unverified registration:
the correction may already be recorded. Close/Escape/window-close share a brief
confirmation in that case. Any returned result establishes registration. Complete
results without warnings finish immediately; otherwise the dialog displays the
returned diagnostics. Incomplete installation/snapshot results offer Retry refresh.
A recovery warning with both completion flags true is not called an incomplete
refresh. Failed refresh retries preserve the earlier verified result and show
the new error separately.

On completion, detached `dialog.result` contains exactly `status`,
`prepared_event`, `registration_result`. Cancelled/unchanged have both other values
None; unverified retains the event; registered retains the event and latest
returned result. This is in-memory handoff only, without persistent drafts, retry
stores or restart guarantees. No production menus/timelines, creation/deletion,
dated editing, running-stop repair, audit/history UI, preferences, Reset removal
or additional recovery mechanism are activated.

## Independent-task timesheet renderer (staged)

`task_timer.exporter.build_timesheet_text(report, *, local_timezone=None, scope=None)`
returns a complete Unicode plain-text string ending in a newline. `report` is
the detached result of `calculate_date_window()`, including its authoritative
`scope` and `local_timezone`. No duplicated caller labels are required. Optional
arguments are compatibility assertions: they must match the result's exact
labels or raise `ValueError` before rendering. Missing result metadata is also
rejected. The renderer never infers completeness from names or the presence of
project rows, and never expands eligibility. Empty selected/complete reports
retain their identity, independently of deleted-task inclusion.

Each Sunday-start week intersecting the requested inclusive date range has
seven dated daily columns and a weekly-total column. Dates outside the range
say `out of scope`, while missing buckets on included dates display `00:00:00`.
Partial weeks retain only the calculated scope. Task, project, Unassigned and
application cells come directly from their supplied daily/weekly seconds;
the renderer never sums formatted values or recomputes work from endpoints.
No additional chargeable multiweek task summary is rendered.

Week layout uses bounded integer ordinals rather than unchecked date addition.
Every intersecting week retains seven physical daily columns, even at the
calendar edges. `unrepresentable` denotes a slot beyond `date.min`/`date.max`;
it has no invented date or contribution and is distinct from a representable
`out of scope` date. Final weeks stop cleanly. The latest accepted accounting
end date, `9999-12-30`, renders its last Friday as out of scope and Saturday as
unrepresentable, retaining supplied weekly totals. Zero-work reports starting
at `0001-01-01` render an unrepresentable Sunday and valid Monday–Saturday dates.
There is a separate, existing accounting limitation: nonzero work in the first
six dates of year 1 overflows when accounting constructs the preceding Sunday
week key. This repair does not alter that upstream calculation; nonzero work
from the first representable Sunday, `0001-01-07`, is supported in the tests.

Task rows contain only their own independent work, grouped by current project.
Project rows labeled `Project total — informational` use the accounting result's
`full_project` scope; `Selected tasks subtotal — informational` identifies a
partial project. Explicitly included empty projects show no eligible tasks and
their supplied zero subtotal. Unassigned tasks form a separate group when
present. Each week ends with one `Application total` or `Selected-scope total`.
Project/Unassigned subtotals are non-additive information, not task entries.
Tags and submission evidence are not additional report sections or actuals.

Names are displayed in full without truncation, whitespace normalization, or external
management numbers. Membership and lookup use UUIDs exclusively. Projects and
tasks sort by exact name, then UUID, independently of dictionary insertion order.
Duplicate task names across the included report receive a full UUID in the
`Chronicle local record reference` column, explicitly for local disambiguation.
Duplicate project headings likewise receive local project references. Deleted
historical tasks supplied by the accounting result are marked `Inactive (deleted)`;
the renderer does not independently reconstruct deletion or selection state.

Durations use `HH:MM:SS[.fraction]`, with unbounded hours and fractional seconds
retained from the supplied numeric value's round-trip decimal representation.
There is no decimal-hours rounding or truncation of nonzero subsecond work.
This describes the unchanged exact renderer. The replacement renderer uses two-decimal
task/day cells and displayed-cell rollups under the
[decimal contract](docs/EXPORT_EVIDENCE_CONTRACT.md#decimal-hour-representation);
its separate staged API is described below.
The timed-work cutoff header preserves fractional timestamp precision too.

The dedicated `_render_timesheet_table()` leaves legacy `_render_table()`
unchanged. `TIMESHEET_TASK_COLUMN_WIDTH=44` is an internal display-column limit,
not a persisted setting. Task names wrap at word boundaries when possible and
split long tokens as necessary. Wrapping carries whitespace without dropping it;
the name's text and ordering remain intact. Pipes, backslashes and control
characters use explicit reversible escapes (`\u007c`, `\\`, `\n`, `\t`, etc.)
so embedded delimiters, line breaks and tabs cannot introduce false columns or
physical rows. Project heading labels use the same escaping. Reconstructing a
label means joining its wrapped content and decoding those escapes, rather than
treating each continuation as another task.

The same escape boundary renders directional formatting instructions as visible
ASCII `\uXXXX` sequences before measuring or wrapping text: U+061C, U+200E/F,
U+202A–U+202E and U+2066–U+206F (including deprecated controls). For example,
actual U+202E displays as `\u202e`, whereas literal backslash-plus-`u202e`
displays as `\\u202e`, preserving their distinction. This applies once to task
cells and project headings; it never changes stored names or sorting. It does
not escape the entire Unicode Format category: ZWJ (U+200D), ZWNJ (U+200C),
combining sequences, accents, CJK and supported emoji remain intact. An escape
may cross a hard wrapping boundary; joining the logical cell recovers it exactly.

ASCII outer borders and row separators span every column. Continuations align
under their original cells; status, local references and time values appear only
on the first physical line. Informational subtotal labels remain explicit.
Numeric columns expand to preserve full values, including long fractional seconds;
they have no 44-column cap. A dependency-free Unicode width estimate treats
combining marks as zero columns and East Asian wide/fullwidth characters as two,
keeping ordinary accented/combining/CJK text aligned. Complex emoji sequences and
terminal-specific ambiguous-width conventions are not fully shaped; no broad
terminal framework or dependency is added. Seven daily columns and metadata
still make the report wider than a narrow terminal. No HTML, PDF, spreadsheet,
persistence, or template framework is introduced.

Rendering does not read storage, consult service state, write files/events,
operate timers, or infer submission status. The legacy `build_export_text()`
and `build_selected_tasks_export_text()` and their backend service routes remain
unchanged; their former production UI routes are removed. This renderer is not activated in the production export menu; new
duration writers, submission/checkpoint policies and the separate fresh-start
data-directory cutover remain separate implementation outcomes.

## Decimal-hour timesheet renderer (staged)

`task_timer.exporter.build_decimal_timesheet_text(report, *, local_timezone=None,
scope=None)` returns complete newline-terminated Unicode text from the same
detached accounting result. Scope/timezone arguments are matching assertions,
not independent labels. It shares the exact renderer's pure layout helpers,
Sunday-start calendar slots, grouping, selection labels, deleted-task status,
UUID disambiguation, reversible Unicode escapes and wrapped table geometry.
It does not alter `build_timesheet_text()` output or the accounting result schema.

Public `seconds_to_decimal_hundredths(seconds)` accepts finite nonnegative
`int`/`float` seconds and rejects booleans, other types, negative and nonfinite
values. Decimal arithmetic uses the input's decimal representation and an isolated
precision context to compute `ROUND_HALF_UP(seconds / 36)` as integer hundredths.
It avoids binary-float division and legacy `format_decimal_hours()` rounding.
A private formatter emits exactly two fractional digits from validated integer
hundredths. For example, 18 seconds becomes `0.01`, 12000 becomes `3.33` and
50400 becomes `14.00`.

Each included task/day's authoritative `daily_seconds` value is rounded once.
Displayed task weekly, project daily/weekly, Unassigned and application totals sum
those integer task/day hundredths, not separately rounded aggregate seconds.
Three tasks with 60 seconds each display `0.02` each and total `0.06`; underlying
Actual remains 180 seconds. Project subtotals are informational and never added
again to application totals. Raw daily/weekly aggregate fields are not decimal
rounding inputs. Selection/group membership remains supplied by the report.

Included days display decimal values such as `0.00`; valid dates outside the
window say `out of scope`, and nonexistent calendar slots say `unrepresentable`.
Positive seconds may round to `0.00` without changing their source records.
The report labels its two-place format and rounding rule. No intervals or dated
records are recalculated, and no report/state/events/files are mutated.

This renderer is independently callable and used by snapshot preparation and the
frozen preview, now composed by the modal production Timesheet. Independent
generation/save services still use the exact renderer. Export-snapshot registration
and materialization below are connected through Save; confirmation UI, general
file-status/recovery UI, configurable week starts and fresh-directory cutover remain
unimplemented. The shared Unicode-width and extreme-date accounting limitations
described above still apply.

## Frozen timesheet preview (standalone)

`TimesheetPreviewFrame(parent, service, *, now_utc, on_readiness_changed=None)`
in `timesheet_preview.py`
constructs controls without loading. `refresh_preview() -> bool` resolves This
week (default), Last week or inclusive Custom dates from one supplied aware
observation, normalized to UTC. Relative weeks use local calendar arithmetic and
Sunday starts. Typed/calendar drafts never prepare automatically. A picker uses
a valid draft or an already captured observation date; it captures no clock and
its cancellation changes nothing. The frame disposes its owned popups on destroy.

Known tasks, including marked deleted tasks and distinct UUID-backed duplicate
names, have independent checkboxes. All scope passes `all_tasks=True`; Selected
passes exactly checked IDs and rejects empty selection. Both pass
`include_deleted=True`, with no project selection or descendant expansion.

Preparation calls `prepare_timesheet_export_snapshot()` once with explicit dates,
cutoff, task scope and `preferred_destination=None`. The component deep-copies
that complete event and displays its exact `payload.report_text` in a read-only,
vertically/horizontally scrollable Text widget. It does not calculate separately
or derive cells from text. UUID and audit metadata remain the service's existing
in-memory preparation behavior; no evidence is registered or report file saved.

`get_prepared_export() -> dict | None` returns a deep copy only after complete
successful rendering while drafts remain unchanged. Period/date/scope/checkbox
writes invalidate readiness immediately, including changes back to earlier
values. Previous trusted output retains its applied range/cutoff and a refresh-
required indication. Later work or label/group changes do not mutate it; explicit
Refresh creates a new candidate. The action is Preview until first success, then
Refresh. No report is prepared during construction or on a schedule.

Preparation failure retains drafts and prior trusted output. Widget-update
failure invalidates readiness, hides untrusted output where possible and reports
the original diagnostic through Tk; explicit later success restores the report.
Valid empty All results are successful. Optional readiness notifications follow
committed transitions, never construction. An observer failure retains the actual
preview outcome and reports its original diagnostic separately. `set_locked(bool)`
disables draft/Preview/picker controls and disposes owned calendars without
invalidating a ready candidate; direct locked refresh/picker callbacks do nothing.
Programmatic draft writes still invalidate readiness. The report remains readable.
The preview itself has no Save/retry, file dialog,
modal wrapper, application route, path memory, confirmation or work mutation.
The owning Save/window components provide production routing separately; dated
writers remain inactive pending their separately approved active-reader/UI gate. The preview remains independently usable; the
[Selected target](docs/TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports)
is composed by Save and the owned modal window below. General recovery and
POL-R presentation remain separate.

## Standalone frozen-export Save/retry

`TimesheetSaveFrame(parent, service, *, now_utc)` in `timesheet_save.py` composes
`self.preview`. `save() -> bool` requires a current detached candidate before an
owned .txt destination dialog, temporarily locks preview interaction, and rechecks
that candidate after selection. Cancellation releases this temporary lock with
no durable operation. Before the first registration call it retains the exact
prepared event and explicit destination; it never changes `preferred_destination`.

From that attempt onward the preview remains locked. Every explicit Retry calls
`register_prepared_timesheet_export()` again with the unchanged event and requires
its expected identity before `materialize_timesheet_export()` at the retained
path. A registration exception means registration is not verified; publication
is prohibited even when bytes are visible. A materialization exception means the
save call did not complete; it does not imply absence and causes no deletion.
Original exceptions, traceback chains and notes are reported through Tk.
`choose_another_file() -> bool` is available after failure; cancellation keeps
retry inputs, while selection retries the same event at the new path. Existing
service gates own synchronization, complete validation, matching-copy reuse and
default no-overwrite protection. `overwrite() -> bool` and its Overwrite button
are available only after the latest materialization attempt raises
`ExportFileContentConflict`. A busy-guarded owned confirmation names the path and
defaults to cancellation. Cancel leaves inputs/eligibility unchanged with no
service calls. Confirmation re-registers the exact event, checks its identity and
calls materialization with `overwrite=True` once. New service attempts clear
eligibility; only a new content conflict re-enables it. Registration, inspection,
unsuitable-type and publication failures cannot authorize replacement. Retry and
Choose another file do not inherit permission; neither event nor handoff stores
it. Busy actions reject reentrancy without more dialogs or
service calls; retries never consult changed work or reprepare the preview.

Only successful materialization sets `saved_path` and completion, before success
presentation. Later presentation failure cannot erase that result. Completed
instances reject duplicate actions. `get_save_attempt() -> dict | None` returns
only deep-copied `prepared_event` and `destination` after the first attempt, with
no clock or I/O. This is an ephemeral current-attempt handoff, not persisted
recovery, a permanent file-status flag or an eventual Close/new-export policy.
`is_busy()` reads the existing action guard; `has_unfinished_attempt()` means an
attempt exists without known materialization completion. These are computed
queries, not another operation status. The owned Timesheet window below now
composes this same component for production. Standalone usage remains supported.
It has no general recovery UI, confirmation, submission/checkpoint, timer or
settings effects. Backend contracts are unchanged.

## Application-owned modal Timesheet

`TimesheetWindow(parent, service, *, now_utc, on_disposed)` in `timesheet_window.py`
constructs a withdrawn Toplevel with `save_frame = TimesheetSaveFrame(...)` and
Close. It performs no preparation, clock observation or durable operation.
`show_modal()` presents it transient to the root, rechecks local-grab eligibility
after visibility processing, takes a local grab and ordinary focus, then uses a
Tk variable wait ended by withdrawal or destruction. It does not use another
mainloop or scheduled data refresh. Main/mini input is blocked while timers and
normal Tk events continue. Calendars retain their own ownership/Apply-only
behavior; picker Escape does not close Timesheet.

Close/Escape/WM close ignore busy actions. Without an attempt, or after verified
completion, they dispose the window. For unfinished Save, an owned default-cancel
confirmation explains session resumption. Confirming releases only the window's
grab and withdraws the same instance, preserving event/path, report, controls and
diagnostics. Reopening does not prepare, observe, register or retry. Overwrite
eligibility is not reusable permission: each action still asks confirmation and
revalidates through existing services. Recoverable presentation failure retains
an unfinished instance; fresh/partial failures dispose widgets and report original
cleanup diagnostics. External/root destruction notifies the application exactly
once and ends the wait; it does not promise forced-destruction/crash resumption.

`TaskTimerApp.open_timesheet()` is the canonical toolbar/File/reminder opening
path. `_timesheet_window` and `_timesheet_window_opening` are initialized before
controls. Ownership is published before presentation and retained on supported
unfinished withdrawal; identity-checked disposal clears only that instance.
Duplicate/opening/busy requests do nothing. Return uses the existing bounded
parent-grab/focus restoration, leaving competing live ownership alone. Inline
launch diagnostics belong to main/banner presentation and preserve original Tk
exception diagnostics; Preview/Save errors stay in the usable component.

The normal root-close handler rejects busy/reentrant interruption. An unfinished
attempt receives an owned default-cancel exit warning before any monthly prompt;
cancel preserves it, confirm destroys root without retry/rollback/recovery writes.
The warning distinguishes lost automatic session resumption from preserved
registered evidence/files. The existing monthly close choice Open Timesheet
returns to the application afterwards. No opening or Save result handles a
reminder. Explicit Dismiss remains; weekly scheduling is Selected/pending.

This replaces all shipped full/selected export UI and checkpoint-reopening UI.
There is no parallel interface, post-export deletion, submission/checkpoint
creation, Reset or automatic reconciliation. Backend exporters/replay, file-only
save services and historical evidence remain independently available. Fresh
windows require Preview at This week/All tasks. No New export, Abandon, persisted
attempt, restart recovery, migration/cutover or dated-writer activation is added.

## Immutable export-snapshot registration (staged)

`TaskTimerService.prepare_timesheet_export_snapshot(start_date, end_date, *,
cutoff_utc, all_tasks=False, task_ids=(), project_ids=(), include_unassigned=False,
include_deleted=False, preferred_destination=None, export_id=None)` freezes one
detached calculation in memory. It uses the existing decimal converter/renderer,
includes every requested date per included task (including zero cells), and
retains the normalized original selection rather than only its expanded members.
Task/project UUIDs, original labels and membership, deletion eligibility, scope,
timezone, inclusive dates, Sunday convention (`week_start=6`), exact report text
and its UTF-8 SHA-256 are frozen. The cutoff retains microseconds; the prepared
audit timestamp uses the existing second-precision UTC convention. An optional
canonical export UUID is preserved, otherwise one is generated. A preferred
destination is a string/null metadata value: no filesystem inspection occurs.

The candidate uses the existing schema version and envelope with
`event_type=timesheet_export_snapshot_created`, `task_id="__app__"` and `event_id`
as its sole export identity. Payload fields are `start_date`, `end_date`,
`cutoff_utc`, `report_timezone`, `week_start`, `scope`, `selection`, `tasks`,
`projects`, `report_text`, `report_sha256` and `preferred_destination`.
Each task's `daily` array contains ordered `work_date`, full-precision
`actual_seconds` and integer `decimal_hundredths`; projects list frozen member
task UUIDs and full/selected scope. There are no persisted aggregate counters.
The technical authority remains the [export evidence contract](docs/EXPORT_EVIDENCE_CONTRACT.md).

`register_prepared_timesheet_export(prepared_event)` returns the export UUID only
after finding exact valid authoritative evidence. It validates schema, canonical
identities and timestamps, date coverage, selection/deletion semantics, membership,
finite nonnegative numbers, converter agreement, UTF-8 text and digest. New
uncommitted candidates must also reproduce their text from frozen layout inputs;
this does not recalculate work or consult current names/membership. An existing
identical committed candidate is reused without appending or rerendering. Different
content or collision with another event type fails. JSON content comparison
preserves numeric int/float distinctions while ignoring object-key insertion order.

Registration reads the complete journal before append and again afterward. It
uses `EventStorage.append_event()` directly to preserve the prepared identity and
existing flush/fsync/rotation behavior. Ordinary first-time append success keeps
its flush and strict post-append verification without an extra synchronization.
Exact identity reuse and recovery of a complete valid event after an append
exception require `EventStorage.synchronize_journal()`: the existing writable,
non-creating/non-truncating helper synchronizes indexed archives, active segment
and manifest and strictly rereads. Revalidate complete export and confirmation
projections and the exact export identity/content before installing evidence or
returning success. Already-registered evidence is never checked with today's
renderer. Visible complete bytes alone do not establish flushing.

Demonstrable absence after append failure preserves the original error and
unchanged-candidate retry context. Partial/malformed/conflicting/unreadable evidence
fails closed before synchronization; it is never synchronized as repair. Open,
fsync, close or revalidation failures report uncertain registration without
installation or another append, retaining the original append failure as diagnostic
context where applicable. Repeated failed synchronization cannot succeed from
visible bytes. Installation failure retains registered evidence for unchanged-event
retry; successful reuse installs the latest complete projections, including later
confirmations. No truncation, repair, new identity, calculation, Actual/timer rebuild,
derived-snapshot save or automatic backup occurs. This shares confirmation
registration's bounded recovery rule under serialized dataset ownership, not a
multi-process or universal power-loss guarantee.

`EventStorage.iter_all_events(strict=True)` checks listed archive presence and
counts, duplicate/unindexed archive paths, active-segment presence, complete JSONL
lines, duplicate JSON fields and readable event envelopes. Service startup,
restore and rebuild also use this fail-closed read mode. Valid legacy task replay
retains its existing timestamp/read-order contract; export lookup/list order uses
original journal read sequence independently of preparation audit timestamps.
Malformed exports and conflicting duplicate identities fail before export state
is installed. Identical preexisting duplicate events project to one effective
export and are not rewritten. Export projections contain detached event copies
derived solely from archived/active logs, not redundant evidence in
`state_snapshot.json`. Existing backups carry those journal files unchanged.

`get_timesheet_export_snapshot(export_id)` and `list_timesheet_export_snapshots()`
return detached committed event documents, not current calculations or file
status. Replay validates preserved schema, structured amounts and digest without
today's renderer; later work, corrections, renames, reassignment and deletion
cannot change old evidence. Original identities are checked against journal
task/project creation evidence without requiring today's labels or membership.

Preparation writes nothing. Registration changes only the journal and its normal
rotation metadata plus the in-memory evidence index/event list. Neither changes
timers, Actual, submissions, checkpoints, selection or legacy save behavior.
Registration publishes no external report or READY classification. The separate
materialization operation below verifies frozen copies; POL-R confirmation and
reconciliation UI remain future outcomes requiring
independent review. Linux fault injection covers append,
inspection and projection failures; it does not establish concurrent multi-process
writers, arbitrary journal repair, universal crash atomicity, power-loss durability
or Windows/NTFS execution.

## Verified export materialization (staged)

`TaskTimerService.materialize_timesheet_export(export_id, destination=None, *, overwrite=False) -> Path`
validates the canonical UUID and rereads the authoritative journal with strict
validation and the existing export projection validator. Missing, malformed,
conflicting or uncertain evidence fails before staging. Cached lookup results
alone cannot authorize publication. Frozen UTF-8 `report_text` and `report_sha256`
are the only content inputs; no current accounting, clock, renderer, labels or
membership are consulted. The operation does not register another event.

An explicit string/`Path` overrides the frozen `preferred_destination` without
changing that evidence. A destination is required; empty/null-containing paths
are rejected and missing parent directories are not created. Existing regular
files are read completely and reused only on full-byte and SHA-256 agreement.
No rewrite occurs for a match, including with `overwrite=True`. The flag requires
an actual boolean. Ordinary materialization rejects conflicts. Explicit
replacement accepts only fully inspected stable regular-file content conflicts;
directories, symlinks (including dangling links), other unsuitable objects and
unreadable/unstable/incomplete observations remain rejected. Verification checks
`lstat`/opened-descriptor identity and regular-file type, uses binary/no-follow/nonblocking open flags where available, then checks
the destination identity again. This detects path replacement at those checks;
it is not an arbitrary hostile-directory or concurrent-process guarantee.
The shared `export_files.py` defines `ExportFileConflict` (also imported under
the existing private service name) and its narrow `ExportFileContentConflict`
subclass. Both preserve `FileExistsError` compatibility and status classification;
only complete stable content inequality raises the narrow signal. A final
post-publication content error is chained under the broader conflict type so a
publication failure cannot enable the Save component's Overwrite control.
It also checks read length against the opened descriptor's size and compares
size/modification/change timestamps across path and descriptor observations.
Incomplete reads or detected changes raise inspection errors before byte
inequality can be treated as a conclusive conflict.

For absent destinations, the existing safe-publication approach is reused in a
separate method, leaving the exact-format file-only save method unchanged:
private same-directory `mkstemp`, binary write of all bytes, flush/fsync, successful
close, owned-staging check, then exclusive `os.link`, including when overwrite was
requested for an absent target. There is no direct-write or replacement fallback.
For an explicitly authorized stable-file replacement, resolve the path and active
dataset root before staging and reject paths inside that tree, including directory
aliases resolving into it. Immediately before `os.replace()`, recheck regular-file
type, device/inode identity, size and modification/change timestamps against the
stable initial inspection. Detected changes abort without replacing the changed
target. These bounded checks assume trusted directories and serialized ownership;
they are not atomic compare-and-replace or arbitrary concurrency protection.
`os.replace()` consumes the owned staging pathname; cleanup tolerates its absence
and never targets the final file. After either publication, complete final bytes
and SHA-256 are checked before return. Size or digest alone never establishes success. Cleanup targets
only an owned staging pathname; it never deletes the final destination.

Original failures propagate with cleanup context. An attempted/ambiguous link or
replacement is identified as unverified; a failure after known publication identifies the
published path and failed verification. Verification failure never undoes
publication. Cleanup failure after successful verification raises an error stating
that publication and verification succeeded, identifying the remaining staging
artifact. Uncertain staging ownership retains the questionable artifact. These
best-effort private-path checks retain the existing trusted-directory assumption.

Retry with the same UUID revalidates the journal and a matching existing copy
without rewriting or appending evidence. A conflicting regular copy requires
another path or explicit one-call replacement authorization. A post-replacement
failure does not establish that the old file remains or the new copy is absent.
Restart, rotation and supported backup/restore retain the snapshot needed to materialize the original bytes after later work or renderer changes.
Every call verifies anew: later external changes/deletion invalidate earlier
observations. There is no persisted completion flag, file-status history or
distinction between never-published and subsequently deleted paths. No automatic
missing-file recovery, dashboard, confirmation or cutover is added by this service.
The modal Timesheet separately composes explicit registration/materialization calls.
Linux fault injection does not establish Windows/NTFS execution, power-loss
durability, universal filesystem support or concurrent/hostile-directory safety.

## Export file-status evaluation (staged)

`TaskTimerService.evaluate_timesheet_export_file_status(export_id,
destination=None) -> str` is a standalone read-only service. It validates the
canonical UUID, strictly rereads the journal, validates the export projection
and frozen UTF-8 text/digest, then resolves explicit destination before frozen
preference. Invalid arguments, unknown exports and evidence/access failures in
the journal raise errors, including when no destination is available.

The service implements the [five selected outcomes](docs/EXPORT_EVIDENCE_CONTRACT.md#derived-pending-and-recovery-outcomes).
Without a destination it returns PENDING without path inspection. Initial
`lstat` absence, including a missing parent, returns MISSING. Otherwise the shared
read-only verifier establishes READY, its deliberate conflict signal maps to
CONFLICT, and inspection `OSError`s map to UNVERIFIABLE. An arbitrary
`FileExistsError` is not a proven conflict. Disappearance after presence was
observed, detected replacement and incomplete/unstable reads are uncertainty;
a stable shorter file read completely is a conflict. Programming and
process-control exceptions are not converted into status results.

Each call rereads evidence and inspects current contents without writes,
accounting, rendering, cached status or remembered alternative paths. Restart
reuses only the caller's destination or immutable preference. MISSING does not
establish whether the file was previously published; READY is only a current
observation. This adds no
recovery UI, automatic recovery, production integration or POL-R confirmation.
Linux fixture/fault-injection evidence does not qualify Windows/NTFS, hostile
directories, real concurrent writers or power-loss behavior.

## Immutable POL-R confirmation replay (staged)

[polr_confirmations.py](src/task_timer/polr_confirmations.py) implements
`validate_polr_confirmation_batch(event)` for exact envelope/cell types and
`collect_polr_confirmations(events)` for pure whole-journal validation and the
effective `(task_id, ISO work_date)` mapping. Each value contains only
`confirmed_hundredths` and `batch_event_id`; missing keys mean Unknown while zero
remains an entry. The [technical owner](docs/EXPORT_EVIDENCE_CONTRACT.md#confirmation-event-structure)
defines the persisted schema and relationship rules.

Confirmation envelopes use the supported schema, canonical UUID and UTC audit
seconds ending in `Z`. `local_timezone` is audit metadata: exactly a nonempty
UTF-8 string without surrounding whitespace, NUL, C0/C1 controls or DEL.
The validator preserves the label unchanged; IANA names, fixed offsets,
abbreviations and well-formed unresolvable labels are accepted without timezone
database lookup or network access. The label verifies no geographic zone or DST
rules and is not used for calculations. UTC audit timestamps and recorded local
work dates remain authoritative; existing timezone arithmetic is unchanged.
Replay follows physical read-sequence order, not audit time. Task creation and source export
must precede the batch. Export-linked amounts match frozen cells without current
accounting, rendering or external-file inspection. All cells validate against
the prior projection before any effective replacement. Per-cell prior batch IDs
and exact stale-acknowledgement truth conditions are enforced. Identical repeated
events are skipped without rolling back newer cells; changed duplicates and
cross-type identity collisions fail closed in either order.

`_rebuild_state()` validates both export and confirmation projections before
installing replacement state. Actual-work replay then skips already projected
confirmation events. `get_effective_polr_confirmations()` returns detached copies
of the in-memory projection. Nothing is added to `AppState` or
`state_snapshot.json`; restart, rotation, rebuild and supported backup restore
derive values again from the journal. Historical rename, reassignment and task
deletion do not erase earlier confirmation evidence.

`prepare_polr_confirmation_batch(cells, *, batch_id=None)` freezes a detached
nonempty list of explicitly reviewed six-field cells in caller order. It captures
one UTC audit timestamp and the offline service timezone label, preserves or
generates the batch UUID, and validates strict journal evidence plus the candidate
as the next physical occurrence. Preparation changes no projections or files and
performs no accounting, rendering, selection expansion or automatic zero selection.

`register_prepared_polr_confirmation_batch(prepared_event)` deep-copies the frozen
event and strictly rereads authoritative evidence. Exact valid existing identity
is checked before new-proposal prior validation, so retries after newer batches
cannot roll them back. Changed content and cross-type collisions fail. An absent
identity must pass whole-batch replay against current priors before append,
including equal-value prior changes and exact stale acknowledgements. No priors
or acknowledgements are refreshed; generic `_append()` directs callers here.

A successful append must be followed by strict inspection finding the exact valid
event; silent no-ops fail. An append exception with demonstrable absence retains
the original error; partial/malformed/conflicting/unreadable evidence fails closed.
Exact existing-identity reuse, including recovery of complete bytes after an append
exception, calls `EventStorage.synchronize_journal()`. It validates the manifest
and journal, opens indexed archives, active segment and manifest with existing-file
writable binary access (`r+b`), without creation, truncation or append. It writes
no content through those handles, fsyncs and closes each, then rereads strictly.
Service replay revalidates all evidence after that synchronization. Failed flush, close or
inspection cannot be treated as success just because complete bytes are visible.
No files are created, truncated, repaired or restored by synchronization.

The existing evidence-installation path computes complete export and confirmation
projections before replacing in-memory evidence. Installation failure retains the
registered batch for exact retry. It never rebuilds Actual/timers, writes the
application snapshot, creates backups or touches submissions/checkpoints/files.
Pre-append rejection leaves files and projections unchanged; operational failures
may leave partial or complete journal evidence without rollback. The API supports
synchronous serialized use through one service owning the dataset; it provides no
thread/multi-process compare-and-append guarantee. Production writer ownership
must be enforced separately. This is bounded file synchronization, not directory
sync, general recovery or universal power-loss durability.

Export-linked registration checks frozen provenance without external file
inspection or POL-R verification. Workflows relying on a report copy still need
current verification. Existing export registration, materialization and file-status
gates reject malformed confirmation evidence. Acknowledgement presentation/UI,
reconciliation presentation/weekly summaries and
production integration remain future outcomes. Isolated Linux fixtures establish
neither a complete operator workflow nor Windows/NTFS or external POL-R behavior.

## Export confirmation proposals and selected preparation (staged)

`propose_export_polr_confirmation(export_id)` reads strict journal evidence and
uses [polr_confirmation_proposals.py](src/task_timer/polr_confirmation_proposals.py)
to produce detached, canonically ordered rows for all frozen export task/days.
Rows retain original names/amounts and current evidence-derived prior amount/ID
and stale flag. Unknown pairs are `None`; known zero keeps its identity. Replay
and proposals share `requires_stale_export_acknowledgement()`; transient positions
use first physical occurrences, so backdated/equal audit times and identical
export/batch duplicates cannot change classification. Nothing is persisted or
installed, and no cached reader, Actual, renderer, file check, clock or UUID is used.

`prepare_export_polr_confirmation_batch(proposal, *, selected_cells=None,
acknowledged_cells=(), batch_id=None)` deep-copies reviewed input, validates its
exact shape/canonical rows, and freshly derives evidence. All frozen source rows,
names and amounts must match complete export coverage. Defaults select positive
proposals, including already-equal values; zero is explicit only. List/tuple
collections of two-tuple keys select exact cells; duplicates/unknown/malformed keys
and empty selection fail. Explicit input order does not alter canonical batch order.
Acknowledgement keys must exactly identify selected stale conflicts. Selected prior
ID, amount and classification must remain unchanged; unselected confirmation
changes need not invalidate the operation. Invalid review never refreshes priors
or retains a subset.

The pure selector returns only the existing six persisted fields and the service
delegates to `prepare_polr_confirmation_batch()` for fresh replay validation and
stable identity/audit/timezone capture. No append occurs. Callers explicitly
register the returned event separately; ambiguous registration retries that exact
event, not a rebuilt proposal. These APIs introduce no proposal identity, stored
draft, cache or recovery mechanism. They preserve serialized ownership and the
registration prior check after preparation. Source provenance remains independent
of report-copy readiness; file-dependent workflows still require current checks.
Deferral has no write; reopening requires renewed review. Acknowledgement dialogs,
manual-confirmation UI and production integration are not implemented.
The [technical owner](docs/EXPORT_EVIDENCE_CONTRACT.md#staged-export-proposals-and-selected-preparation)
defines the transient fields, selection and acknowledgement contract.

## Daily POL-R reconciliation calculation (staged)

`TaskTimerService.calculate_polr_reconciliation(start_date, end_date, *, cutoff_utc,
all_tasks=False, task_ids=(), project_ids=(), include_unassigned=False,
include_deleted=False)` strictly reads archived/active evidence once and derives
latest confirmations with `collect_polr_confirmations()`, without using or
refreshing `_polr_confirmations`. Invalid evidence raises even for an empty scope.
It then calls `calculate_date_window()` exactly once with the unchanged request.

[polr_reconciliation.py](src/task_timer/polr_reconciliation.py) provides the pure
`build_polr_reconciliation(report, confirmations)` projection. Its detached result
has exactly `actual` (the unchanged full-precision calculated report) and `cells`,
keyed by `(task_id, ISO work_date)`. Every included task gets a cell for every
inclusive report date, with absent sparse daily seconds treated as zero.
Each cell has `actual_hundredths`, `confirmed_hundredths`, `delta_hundredths`,
`enter_hundredths` and `batch_event_id`. The shared HALF_UP converter rounds each
task/day once. Unknown Confirmed/Delta/batch ID are `None`; confirmed zero retains
integer zero and its identity. Signed Delta subtracts confirmed hundredths from
Actual hundredths; Enter is complete Actual hundredths. Removing all work retains
a selected confirmed date with negative Delta and zero Enter. Raw seconds,
including positive amounts rounding to zero, remain unchanged in `actual`.

Selection, current labels/membership, deleted eligibility, accounting errors,
cutoff and Sunday-week metadata remain the existing accounting contract. Projects
are informational Actual metadata, never additional confirmation cells. The
service uses current Actual state under serialized dataset ownership; the cutoff
caps timed work, not confirmations or historical as-of state. Journal physical
order governs confirmations regardless of audit time. This does not synchronize
foreign Actual writers or establish an atomic multi-process snapshot.

Each call is read-only: no event append, synchronization, snapshot/backup write,
projection installation, cache refresh, implicit clock, rendering, file
materialization or timer/submission/checkpoint changes. Returned results do not
change after later work or confirmations. No Confirmed/Delta aggregate balances,
weekly reconciliation, formatting, presentation/UI or production integration is
implemented. The [technical contract](docs/EXPORT_EVIDENCE_CONTRACT.md#staged-daily-calculation)
owns the transient response and freshness boundary.

## Date-range timesheet service (staged)

`TaskTimerService.generate_date_range_timesheet(start_date, end_date, *,
cutoff_utc, all_tasks=False, task_ids=(), project_ids=(),
include_unassigned=False, include_deleted=False)` returns complete timesheet text.
It calls the existing `calculate_date_window()` and `build_timesheet_text()`;
it has no separate accounting, selection, formatting or parent-roll-up engine.
Scope/timezone labels come exclusively from the accounting result. Defaults and
explicit empty selections select nothing; `all_tasks=True` requests the complete
eligible-task report. Project/task selections form a UUID union, optionally
including Unassigned and deleted historical tasks under the existing semantics.

Start/end are inclusive local `date` objects. One explicit aware cutoff is
normalized to UTC by accounting and caps timed contributions across the report.
Dated records remain wholly on their declared work dates. Partial Sunday-start
weeks remain partial, reset boundaries do not erase historical actuals, and
current membership determines project grouping. This uses current effective
records; the cutoff is not historical as-of replay. All earlier legacy-data and
extreme-date limitations of accounting remain unchanged.

`save_date_range_timesheet(target, start_date, end_date, *, ...)` accepts the same
reporting arguments plus an explicit nonempty string/`Path` destination. It
returns the same text on successful saving. Calculation and rendering finish
before filesystem staging. Destination arguments are validated, then
`tempfile.mkstemp()` exclusively creates an unpredictable private staging file
in the destination's parent directory (0600 access on supporting POSIX systems;
Windows access follows the directory's ACL). No parent directories or implicit
report destinations are created. The complete text is written as UTF-8 without
newline translation, flushed, fsynced and successfully closed before publication.
The renderer's final newline is preserved.

`os.link(staging, destination)` atomically publishes the completed file without
overwriting existing files, directories or symlinks, including dangling symlinks
and existing storage/backup files. This operation, rather than an existence
check, enforces exclusivity even when another process creates the destination
immediately before publication. Staging and destination are on the same
filesystem. The final destination is never opened for writing and is never
deleted by this method. After publication only the staging pathname is removed;
the final hard link remains. Legacy `write_export_file()` is unchanged.

Accounting/rendering errors propagate before staging or publication. Staging
write/flush/fsync/close errors and publication errors leave the final destination
absent unless independently created. The original exception remains observable;
staging cleanup failures are attached as notes identifying the artifact. Cleanup
targets only this invocation's private staging pathname. Detected staging
identity ambiguity retains the questionable artifact and reports the problem.
These private-path checks do not eliminate all hostile-directory races; callers
should use a trusted destination directory. The hard cleanup boundary is that
the requested final destination is never deleted, including after publication.

If publication succeeds but staging cleanup fails, an `OSError` explicitly states
that the complete timesheet was published, identifies staging in `filename`, and
chains the cleanup error as its cause. Publication is not undone; the complete
destination remains. Cleanup is best effort. A crash before publication may
leave orphan staging, and no startup scavenging is implemented. The file is
fsynced before publication, but there is no directory fsync or guaranteed
power-loss durability, crash recovery, journal or staging registry.

Standard-library same-directory hard linking is compatible with ordinary
hard-link-capable Windows NTFS installations and supported Python versions.
Filesystems, network shares or restricted environments that reject hard links
fail closed with the filesystem error and attempted staging cleanup. There is
no direct-write, rename, replace or overwrite fallback. Linux publication,
existing-target protection and injected failures are tested; Windows/NTFS
execution is unavailable in this environment and is not claimed as validated.

Generating is read-only accounting; this exact-format save is file output only and does
not persist immutable export-snapshot evidence. The
[selected saved-export/confirmation requirement](docs/TIMESHEET_REQUIREMENTS.md)
requires integration with immutable evidence and future POL-R reconciliation UI. The
[approved technical contract](docs/EXPORT_EVIDENCE_CONTRACT.md) now selects
snapshot-first registration, decimal output, verified materialization, pending
recovery and confirmation batches; none is used by these file-only generation/save APIs. The
current method regenerates text on each call, rejects existing destinations even
if matching, and does not perform snapshot-linked postpublication byte verification.
A saved report is **not submission evidence**. Neither operation appends events, updates
snapshots, creates backups, changes selection/membership, operates timers, resets
counters, consults timestamp checkpoints or changes submission flags/coverage.
Legacy `export_report()`/`export_selected_tasks_report()` backend APIs remain
unchanged; their UI routes are replaced by frozen Timesheet. These exact-format
APIs activate no duration writer or production menu, and the separate empty-directory
cutover remains deferred. Tests use temporary
datasets and caller-chosen output files, leaving existing user data untouched.

## Event schema

Each event line is JSON with:

- `schema_version`
- `event_id`
- `timestamp_utc` (ISO-8601 with `Z`)
- `local_timezone`
- `task_id`
- `event_type`
- `payload`

Corrections are represented via explicit events:

- `manual_interval_added`
- `interval_edited`
- `interval_deleted`

## Reset semantics

These are retained backend/export semantics, not Selected replacement behavior
or a compatibility guarantee. Task Reset controls, Tools Reset All, and Reset
branches in both export-completion flows are removed. No replacement reset
mechanism is added. Backend reset APIs, replay, snapshots and interval-only
export clipping are unchanged. Main/mini calendar Actual and mixed work history
ignore these legacy boundaries. Production POL-R reconciliation remains pending.

`reset` creates a logical totals boundary (`last_reset_utc`) for each task:

- Retained interval-only export readers exclude or clip earlier work at this boundary.
- Historical events remain visible in exports.

## Retained export/reset backend boundary

Production export access uses the application-owned modal Timesheet above.
`TaskTimerApp.export()`/`export_selected_tasks()`, their selected-dialog/result and
post-export choices, overlap warning presentation, post-export dispatch and
checkpoint-reopening command are removed. No configured legacy pre-export or
post-delete backup hook is called by this replacement path; registration and
materialization retain their existing service behavior. Explicit deletion and
other risky-operation backup workflows outside exporting remain unchanged.

The independently callable backend `export_report(reset_after=True)` contract
still retains its report header/checkpoint flag and explicit reset behavior.
Selected backend exports still provide interval/submission semantics and overlap
calculation. Those APIs, reset/checkpoint/submission replay and historical audit
rendering are preserved, not a parallel shipped export UI or a compatibility
promise. Timesheet never calls them, confirms POL-R or marks reminders handled.

## Time handling

- Internal event timestamps are UTC-aware datetimes.
- Display/grouping uses local timezone from the running system.
- Day/week totals split intervals at local boundaries.
- Current week start is Sunday; configurable starts are selected future behavior
  in the [product contract](docs/TIMESHEET_REQUIREMENTS.md), not implemented here.

## Durability

- Every state-changing action appends + flushes + fsyncs event log.
- Snapshot and manifest writes are atomic temp-write + replace.
- UI timer refresh never writes files.

## Backups

- Managed backups are stored under `~/.task_timer_data/backups` in GFS-style buckets:
  - `sons/`
  - `fathers/`
  - `grandfathers/`
- `backup_settings.json` is auto-created with defaults on first run and is user-editable from **File → Backup Settings**.
- Retention trims each bucket to configured keep counts after backup creation.
- Restore always takes a forced safety backup before data replacement.
- Other risky-operation safety backups are controlled by `auto_backup_before_risky_operations`.
- Optional app-start auto backups are controlled by:
  - `auto_backup_on_app_start`
  - `auto_backup_min_interval_minutes`

## Window snap behavior on Windows

Windows Aero Snap behavior is owned by the operating system. The app reduces accidental top-edge maximize by making the main and mini windows non-maximizable/non-resizable while keeping normal title bars and drag behavior. If a future version needs fully resizable main windows while still blocking only top-edge snap maximize, that will require deeper Win32 style handling or custom window chrome tradeoffs.

## Main window task list behavior

- The main Chronicle window displays tasks and subtasks with a `ttk.Treeview` hierarchy (parent rows with nested child rows).
- Main window actions (`Start/Stop`, `Delete`, `Edit Task`, `Work History`) operate on the currently selected task row.
- Tree interactions support quick toggles: double-click, `Enter`, and `Space` all trigger selected task `Start/Stop`.
- Parent expansion/collapse state is tracked during runtime and parents with running subtasks are automatically kept expanded.
