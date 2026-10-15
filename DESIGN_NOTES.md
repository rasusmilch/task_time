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
preparation/registration are staged; confirmation UI, reconciliation and general
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
one-running-task rule. Historical corrections to existing deleted task records
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
synthetic records, real interval handling, resets, checkpoints, timeline UI,
mini-mode, totals, tags, exports and submission behavior remain unchanged.
Those production consumers do not include the new records yet. The separate
mixed calculation below is available for service use; reader integration must
be validated before the new workflow emits these events. Production
reset/checkpoint consumers remain legacy. The selected
[date-scoped POL-R workflow](docs/TIMESHEET_REQUIREMENTS.md) does not use an
implicit export checkpoint or timer reset to distinguish newly worked time.
No new date-based checkpoint/reset extension is implemented. No legacy migration
or fresh-directory cutover is performed; `~/.task_timer_data` remains outside
this development workflow.

## Mixed date-window accounting (service only)

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
it does **not** reconstruct application state as of an earlier instant. It does
not decide eligibility for timestamp checkpoints or reset-based dated counters.

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
is performed; the old production reporting path continues unchanged.

This API persists nothing and activates no writer, UI, export, submission,
checkpoint, reset-counter, or mini-mode consumer. The event logs and their
effective projections remain authoritative; snapshots remain rebuildable. New
reader/writer integration and the separate empty-directory cutover are later
tasks. Tests use isolated temporary datasets and leave existing user data alone.

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
and `build_selected_tasks_export_text()` and their service/UI routes remain
unchanged. This renderer is not activated in the production export menu; new
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

This renderer is independently callable only: existing generation/save services
still use the exact renderer. Separate export-snapshot registration is staged
below; confirmation UI, file-status/recovery UI, production export/UI
integration, configurable week starts and fresh-directory cutover remain
unimplemented. The shared Unicode-width and extreme-date accounting limitations
described above still apply.

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
existing flush/fsync/rotation behavior. If append raises, a complete valid matching
event found on strict inspection is reused. Demonstrable absence preserves the
original error for same-candidate retry; unreadable or ambiguous evidence fails
closed with inspection context. This inherited export path does not resynchronize
the journal before reusing visible complete evidence after an append exception;
the stronger confirmation recovery synchronization below does not repair or
qualify export-registration flushing. No truncation, automatic repair, new identity
or new calculation occurs. Registration neither saves a derived state snapshot nor
creates an automatic backup, since Actual state did not change.

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
materialization operation below verifies frozen copies; POL-R confirmation UI,
reconciliation and production integration remain future outcomes requiring
independent review. Linux fault injection covers append,
inspection and projection failures; it does not establish concurrent multi-process
writers, arbitrary journal repair, universal crash atomicity, power-loss durability
or Windows/NTFS execution.

## Verified export materialization (staged)

`TaskTimerService.materialize_timesheet_export(export_id, destination=None) -> Path`
validates the canonical UUID and rereads the authoritative journal with strict
validation and the existing export projection validator. Missing, malformed,
conflicting or uncertain evidence fails before staging. Cached lookup results
alone cannot authorize publication. Frozen UTF-8 `report_text` and `report_sha256`
are the only content inputs; no current accounting, clock, renderer, labels or
membership are consulted. The operation does not register another event.

An explicit string/`Path` overrides the frozen `preferred_destination` without
changing that evidence. A destination is required; empty/null-containing paths
are rejected and missing parent directories are not created. Existing regular
files are read completely and accepted only on full-byte and SHA-256 agreement.
No rewrite occurs for a match. Conflicting files, directories, symlinks (including
dangling links) and other unsuitable objects are rejected; unreadable files are
not matches. Verification checks `lstat`/opened-descriptor identity and regular-file
type, uses binary/no-follow/nonblocking open flags where available, then checks
the destination identity again. This detects path replacement at those checks;
it is not an arbitrary hostile-directory or concurrent-process guarantee.
The shared verifier uses a private `FileExistsError` subclass for deliberate
content/type conflicts, preserving existing messages and exception compatibility.
It also checks read length against the opened descriptor's size and compares
size/modification/change timestamps across path and descriptor observations.
Incomplete reads or detected changes raise inspection errors before byte
inequality can be treated as a conclusive conflict.

For absent destinations, the existing safe-publication approach is reused in a
separate method, leaving the exact-format file-only save method unchanged:
private same-directory `mkstemp`, binary write of all bytes, flush/fsync, successful
close, owned-staging check, then exclusive `os.link`. There is no overwrite or
direct-write fallback. After linking, complete final bytes and SHA-256 are checked
before return. Size or digest alone never establishes success. Cleanup targets
only an owned staging pathname; it never deletes the final destination.

Original failures propagate with cleanup context. An attempted/ambiguous link
is identified as unverified; a failure after known publication identifies the
published path and failed verification. Verification failure never undoes
publication. Cleanup failure after successful verification raises an error stating
that publication and verification succeeded, identifying the remaining staging
artifact. Uncertain staging ownership retains the questionable artifact. These
best-effort private-path checks retain the existing trusted-directory assumption.

Retry with the same UUID revalidates the journal and a matching existing copy
without rewriting or appending evidence. A conflicting copy requires another
explicit path. Restart, rotation and supported backup/restore retain the snapshot
needed to materialize the original bytes after later work or renderer changes.
Every call verifies anew: later external changes/deletion invalidate earlier
observations. There is no persisted completion flag, file-status history or
distinction between never-published and subsequently deleted paths. No automatic
missing-file recovery, dashboard, confirmation, UI integration or cutover is added.
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
and journal, opens indexed archives, active segment and manifest in existing-file
binary read mode, fsyncs and closes each, then rereads strictly. Service replay
revalidates all evidence after that synchronization. Failed flush, close or
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
gates reject malformed confirmation evidence. Acknowledgement proposals/UI,
automatic full-export selection, reconciliation calculations/presentation and
production integration remain future outcomes. Isolated Linux fixtures establish
neither a complete operator workflow nor Windows/NTFS or external POL-R behavior.

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

Generating is read-only accounting; current saving is file output only and does
not persist immutable export-snapshot evidence. The
[selected saved-export/confirmation requirement](docs/TIMESHEET_REQUIREMENTS.md)
requires integration with immutable evidence and future POL-R reconciliation. The
[approved technical contract](docs/EXPORT_EVIDENCE_CONTRACT.md) now selects
snapshot-first registration, decimal output, verified materialization, pending
recovery and confirmation batches; none is used by these file-only generation/save APIs. The
current method regenerates text on each call, rejects existing destinations even
if matching, and does not perform snapshot-linked postpublication byte verification.
A saved report is **not submission evidence**. Neither operation appends events, updates
snapshots, creates backups, changes selection/membership, operates timers, resets
counters, consults timestamp checkpoints or changes submission flags/coverage.
Legacy `export_report()`/`export_selected_tasks_report()` and their UI routes
remain unchanged. No new duration writer or production menu is activated, and
the separate empty-directory cutover remains deferred. Tests use temporary
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

These are current legacy counter semantics, not a rule for erasing historical
date-based actuals in the selected replacement workflow.

`reset` creates a logical totals boundary (`last_reset_utc`) for each task:

- Current elapsed/day/week totals ignore prior intervals.
- Historical events remain visible in exports.

## Export + reset flow

This is the active legacy export flow. The
[selected replacement workflow](docs/TIMESHEET_REQUIREMENTS.md) separates preview,
saved export evidence and explicit POL-R confirmation without export-triggered
timer stops, resets or implicit checkpoints.

- Export file is generated first.
- The service records an `export_checkpoint` after successful file writing.
- If reset was not requested, this operation records no reset events.
- If reset was requested, it then resets all non-deleted tasks; running tasks
  are stopped through the existing reset path before their reset event.

Default reset scope is all non-deleted tasks.

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
- Main window actions (`Start/Stop`, `Reset`, `Delete`, `Edit Task`, `Edit Timeline`) operate on the currently selected task row.
- Tree interactions support quick toggles: double-click, `Enter`, and `Space` all trigger selected task `Start/Stop`.
- Parent expansion/collapse state is tracked during runtime and parents with running subtasks are automatically kept expanded.
