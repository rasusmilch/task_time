# Chronicle replacement application and POL-R product contract

This document is the canonical current-state authority for the user-approved
**target product behavior**. It is not a claim that the target is implemented.
The user and ChatGPT approve requirements and architecture; Codex implements
approved tasks without resolving the Open matters below. Repository instructions
are in [AGENTS.md](../AGENTS.md), inspected technical behavior in
[DESIGN_NOTES.md](../DESIGN_NOTES.md), and implementation status/navigation in
[README.md](../README.md). Historical material changes belong to
[CHANGELOG.md](../CHANGELOG.md).

## Authority and status

- **SELECTED**: user-approved desired behavior to preserve and implement. A
  requirement can be Selected and not yet implemented.
- **CURRENT IMPLEMENTATION**: behavior established by inspected source. Existing
  execution does not automatically establish selected target policy.
- **OPEN**: a material decision reserved for the user and ChatGPT. Codex must
  return it for adjudication, not close it through code, examples or assumptions.
- **UNVERIFIED EXTERNAL BEHAVIOR**: a POL-R fact not established by direct evidence.
- **DEFERRED**: approved functionality belonging to a later phase. Deferral does
  not withdraw approval or imply implementation.

The behavioral requirements below are Selected. The approved export-evidence,
decimal-hour, recovery and confirmation technical contracts are owned by
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md). Pure decimal rendering,
immutable export-snapshot registration/verified materialization and read-only
destination-relative status evaluation are implemented/staged. Confirmation-batch
validation/replay, dedicated preparation/registration and effective projection are
staged service capabilities; production export integration, general status/recovery
UI, automatic missing-file recovery, confirmation/reconciliation UI and weekly
reconciliation summaries are not implemented. Read-only daily reconciliation
calculation is staged. Unrelated Open matters
remain reserved for user/ChatGPT adjudication.

## SELECTED — Replacement, installation and data boundary

Chronicle is a local, Windows-friendly task timekeeping application. The
redesigned product replaces the legacy installation and user workflow; it is not
intended to retain a permanent parallel legacy interface.

The redesigned installation begins with a fresh timekeeping dataset. Historical
task, interval, submission and template migration is not required. During staged
development, existing user data must not be modified or imported unintentionally.
Installation replacement is not permission to delete user files. Exact release
cutover and handling of the old data directory remain Open.

## SELECTED — Independent projects and tasks

Projects are user-created organizational containers with stable internal UUIDs,
names and optional descriptive information. They own no direct time and have no
independent running timer. Their displayed subtotals derive from member tasks.

Tasks are independent time-bearing assignments with stable internal UUIDs. POL-R
identifies them by their names, not invented external task numbers. Duplicate
names are valid. Each task may belong to one project or remain Unassigned, and
retains its own daily and weekly totals.

Moving a task preserves its identity and recorded time. Reports group all its
historical work by its **current** project; time is not divided among former
projects. Task time and project subtotals must never be added together as separate
actual work.

## SELECTED — Actual-time records

Actual work derives from two distinct types:

- **Real timed interval**: genuine start/stop timestamps, actual elapsed time
  assigned to local work dates, correct splitting at midnight, week boundaries
  and daylight-saving transitions, with correction and deletion support.
- **Date-only manual duration**: task identity, local work date and duration,
  without fabricated start/stop timestamps. Its entire amount belongs to the
  declared date, with correction/deletion and retained audit evidence.

A 14-hour dated duration on Saturday remains entirely on Saturday. Corrections
and deletions change current actual totals without erasing authoritative earlier
events. Replacement Reset actions and resettable counters are removed from the
Selected workflow; normal history and calendar Actual are independent of legacy
reset boundaries. This target does not remove currently active legacy controls.
Real work must remain recordable when allocations are exhausted or unknown.

Replacement timed-work entry, editing and work-history display use minute-only
clock precision, with separate start/end dates and times. Repeated local times
require explicit first/second occurrence selection, ordered by their UTC instants;
nonexistent local times are rejected. Endpoint ordering and elapsed duration use
UTC, so valid work may cross midnight or have an earlier-looking stop clock
during a fallback. No overnight rollover, gap adjustment or occurrence is guessed.
This selects input/display behavior, not billing rounding or changes to existing
recorded precision, raw accounting or export representations.

Ordinary timed editing applies to closed genuine intervals. Saving unchanged
work writes no event, including when only a comment is entered. Changing one
endpoint preserves the other exactly; recorded seconds/fractions are not
automatically rounded. A genuinely changed endpoint must be a whole local minute.
Correction comments are optional. Original/replacement values and the correction
audit timestamp remain available, and changes to the reviewed entry reject the
save. A separate running interval does not prevent correcting older closed work.
Minute drafts denoting the original local minute and UTC occurrence preserve the
stored endpoint exactly, even after editing back or using equivalent clock text.
Restore that precision before checking UTC order, including positive intervals
whose endpoints display the same minute. A stored repeated-time occurrence may
be initialized from its actual instant; subsequent changed repeated times still
require an explicit choice. No gap adjustment or rounding is authorized.

## SELECTED — Mixed work history

Normal task history contains genuine timed intervals and date-only entries
together, showing their latest effective versions independently of resets.
Earlier revisions and deletions remain available through audit/details. Editing
preserves entry type; a dated amount must not acquire fabricated endpoints.

The default UI period is the current week, with custom inclusive dates and All
history available. The date-column header switches oldest/newest date order.
Every application startup begins newest-first. A successful direction change is
remembered across subsequent history openings for any task or dataset during that
application session; closing and reopening the application resets newest-first.
No preference file, settings field or cross-process coordination is required.
At most one history window may be open per application. History is modal: close
it before using the main application or choosing another task. It stays attached
to its original task and provides browsing controls and Close, without Start/Stop
or other main-window functions. Duplicate or reentrant opening requests have no
effect; they do not replace, retarget or refresh the existing window. Timers
continue running, unchanged by opening or closing history. Within each date,
timed portions stay chronological and date-only entries follow them without
invented clock positions.

History loads on opening, Apply, switching to Current week or All, and explicit
Refresh. Date-header sorting reorders the displayed results without loading newer
records or advancing the cutoff. Successful loads and sorts clear selection.
Current week covers seven local calendar dates from the supplied week start,
initially Sunday, and rolls over on refresh rather than through scheduled loading.
This staged caller input is not delivery of the configurable-week setting.

Custom dates support typing and owned calendar pickers; Apply is required.
Entering Custom, typing, focus changes and calendar selection do not load work.
After surrounding whitespace is trimmed, Apply requires canonical YYYY-MM-DD,
real ordered inclusive dates and the reader's representable boundary. Drafts are
retained on failure and across period switches. Refresh reloads the last
successfully applied period, reusing its Custom dates rather than unapplied
drafts; before any success it retries Current week. Failed loading must leave
last-successful period/as-of information truthful and distinguish unestablished
history from a valid empty result. Rendering retains the table's failure rules.

Intervals crossing local midnight appear as linked daily segments of one
underlying interval. Editing or deleting a segment acts on that complete
interval; deletion warns about affected dates. POL-R reconciliation stays per
task/day, without per-entry confirmation or Delta state.

The history table presents a compact link column, Date, Kind, Start, End / as of
and Duration. Dates use YYYY-MM-DD; Kind distinguishes Timed, Date only and
Running. Dated entries have blank clock cells; running endpoints are observation
boundaries, not recorded stops. The approved presentation rules are:

- Segment clocks use 24-hour HH:MM. An endpoint on a different local date from
  the row includes its actual YYYY-MM-DD date, including next-date midnight.
- Repeated local minutes include the endpoint's actual UTC offset, preserving
  non-hour offsets. Ambiguity comes from valid local-minute candidates, not a
  timezone name or abbreviation.
- Durations use supplied seconds: zero displays 0:00, positive sub-minute work
  displays <1 min, and other amounts display completed whole minutes as H:MM
  with unbounded hours. These display rules change no stored precision,
  accounting, billing rounding, exports or POL-R values.
- Linked interval portions show ↔ when either continuation flag is true.
  Selecting one portion visually highlights its other visible portions by
  task/kind/entry identity, including task-scoped running portions. Selection
  stays on the chosen row; dated entries do not link. No routine extra text is
  added. This later approval resolves the earlier undecided link styling.

The detached [work-history service](../DESIGN_NOTES.md#mixed-work-history-service-staged)
and pure [timed-input validation](../DESIGN_NOTES.md#replacement-timed-input-validation-staged)
are staged, together with a standalone
[timed-interval form](../DESIGN_NOTES.md#timed-interval-input-form-staged) and
[closed-interval correction preparation/registration](../DESIGN_NOTES.md#timed-interval-corrections-staged).
A [standalone correction dialog](../DESIGN_NOTES.md#standalone-timed-interval-correction-dialog-staged)
now connects those components without production callers.
A standalone [work-history table](../DESIGN_NOTES.md#mixed-work-history-table-staged)
now renders supplied rows and related-portion feedback without service access.
The standalone [history browser](../DESIGN_NOTES.md#single-task-history-browser-staged)
now composes that reader/table with periods, typed/calendar drafts, explicit
refresh and in-memory sorting. A staged application-owned boolean and unrouted
composition helper now hand off successfully rendered direction across sequential
browser openings, without persistence or production activation.
A staged [owned modal window](../DESIGN_NOTES.md#owned-modal-history-window-staged)
now composes the browser through an unrouted application opening path, with
single-window ownership and lifecycle cleanup limited to that path.
Production record-editor/history integration, application-wide window enforcement,
audit presentation,
segment editing/deletion handlers, dated writer activation and production Reset
removal remain subsequent work.

## SELECTED — Configurable week convention

The user can select **any weekday** as the beginning of a week; Sunday is the
initial default. The selected day controls timesheet weekly columns/periods,
weekly task totals, weekly project subtotals, weekly reconciliation summaries
and weekly allocation periods when allocation tracking is active.

Changing this setting must not change recorded work dates, individual amounts,
POL-R daily confirmations, original export snapshots or actual historical events.
An export retains the convention used at its creation; old exports must not be
silently rewritten. Current Sunday-only code is a staged limitation, not a
permanent product requirement. Configurable-week support remains approved but
is not yet implemented.

## SELECTED — Actual, Exported and Confirmed POL-R are distinct

| Concept | Meaning |
| --- | --- |
| Actual | Current calculated work by task UUID and local work date. |
| Exported | Frozen evidence of the work contained in a particular saved timesheet at generation. |
| Confirmed POL-R | Latest user-confirmed absolute total believed to be in an external task/day cell. |

Exported and confirmed amounts are never additional actual work. They must not
be added to elapsed totals. There is no automatic POL-R connection or
synchronization: the user enters and corrects external values.

## SELECTED — Decimal-hour replacement output

Replacement exports and POL-R-facing reconciliation use decimal hours with exactly
two places. Keep full-precision accounting seconds unchanged; round each task/day
cell once using deterministic ROUND_HALF_UP to integer hundredths. Displayed
weekly, project and overall totals sum displayed task/day cells, not independently
rounded raw aggregates. This presentation does not create additional Actual.
Nonzero work rounding to 0.00 stays nonzero internally and is not automatically
confirmed as zero. The technical rules are in the
[decimal contract](EXPORT_EVIDENCE_CONTRACT.md#decimal-hour-representation).

## SELECTED — Daily reconciliation

Every task/day reconciliation record supports **Actual**, **Confirmed POL-R**,
**Delta**, and **Enter in POL-R**:

- Actual is the current independent Chronicle task/day total.
- Confirmed POL-R is the latest explicitly confirmed **absolute daily total**
  for that task/date.
- When the confirmed amount is known, Delta = Actual minus Confirmed POL-R.
  Positive means POL-R needs additional hours; negative means its known amount
  exceeds Chronicle's corrected actual. Zero means reconciliation with the last
  confirmation, not independent verification of POL-R.
- Enter in POL-R is the complete absolute daily replacement value, equal to the
  current Actual. It is **not the Delta** or a separate incremental entry.

Unknown is different from zero. If no external amount has ever been confirmed:

| Field | Required value |
| --- | --- |
| Confirmed POL-R | Unknown |
| Delta | Unverified |
| Enter in POL-R | Current Actual |

Do not assume an unconfirmed cell contains zero or calculate a fictitious exact
outstanding amount from an unknown previous external value.

POL-R-facing Delta uses displayed Actual hundredths minus confirmed hundredths;
Enter uses current displayed Actual. Underlying Actual retains exact seconds.
The mandatory HH:MM examples below preserve work semantics; their selected
decimal representations are specified in the
[reconciliation contract](EXPORT_EVIDENCE_CONTRACT.md#displayed-reconciliation).

**CURRENT IMPLEMENTATION:** a staged read-only service returns detached raw Actual
and task/day hundredths for Actual/Confirmed/Delta/Enter, with `None` for
Unknown/Unverified and batch identity for known confirmation. It validates current
journal evidence and uses existing current-state accounting without writes or
cache installation. Reconciliation presentation, weekly summaries and production
integration remain unimplemented.

## SELECTED — Mandatory 3:00 → 5:00 contractual behavior test

Task A, Monday:

1. Actual = **3:00**. The user saves an export containing **3:00**. POL-R remains
   **Unknown** until explicitly confirmed.
2. The user works another **2:00**. Actual = **5:00**. The earlier saved export
   remains frozen at **3:00**.
3. The user confirms that **3:00** from that earlier export was entered into
   POL-R: **Actual = 5:00; Confirmed POL-R = 3:00; Delta = +2:00;
   Enter in POL-R = 5:00**.
4. The user changes Monday's POL-R cell from **3:00** to **5:00** and confirms
   the new absolute daily total: **Actual = 5:00; Confirmed POL-R = 5:00;
   Delta = 0:00**. No further cell update is required.

The earlier 3:00 confirmation remains historical evidence. No timer reset is
required to distinguish new work from already-confirmed time. The external cell
must become **5:00**, not an additional independent **2:00** entry. This example
is mandatory acceptance behavior, not optional illustration.

## SELECTED — Preview and saved exports

**Preview timesheet** displays current calculated actual work without persistence,
submission, timer resets or checkpoints.

**Save/export timesheet** must save a complete readable report and record immutable
evidence of that export's work-date amounts. It preserves the selected date
range, week-start convention, calculation cutoff, reporting scope, task UUIDs
and historical display labels. The export can be reviewed and confirmed later.
Saving never automatically marks work as entered into POL-R.

Saved exports remain unchanged after later work, corrections, project movement
or task renaming. Repeated exports never add their hours to actual work.

One immutable journal-backed snapshot is authoritative; external files are
reproducible copies. Register and verify that snapshot before file publication,
then verify complete file bytes before reporting successful export. A failed
materialization leaves recoverable registered evidence. Retry the same snapshot
without recalculating work or overwriting existing files; a conflicting destination
requires another user-selected path. Matching existing bytes may be recognized.
File availability is derived from valid committed evidence and the selected
destination: an explicit path, otherwise the original preferred path if present.
No available destination differs from a selected destination with no file. An
absent selected file establishes no publication history, including whether it
ever existed. Reverify current status rather than assuming it remains correct;
do not persist publication-history or completion state.
The [technical contract](EXPORT_EVIDENCE_CONTRACT.md) owns identity, contents,
registration uncertainty, materialization and recovery rules.

**CURRENT IMPLEMENTATION distinction:** the staged save service publishes a
report file but does not register an immutable export-snapshot event. It still
uses exact HH:MM:SS output and lacks snapshot-linked byte verification/recovery.
The separate pure decimal renderer and immutable snapshot-registration APIs are
implemented/staged but are not used by these generation/save APIs. Registration
alone publishes no file. A separate materialization API verifies journal evidence
and exact destination bytes, reuses matching files and refuses overwrite. It does
not recalculate work or create another event. Standalone status evaluation also
strictly validates committed evidence and derives the five current file outcomes
without writes, retained status or remembered alternative paths. Production export
integration, general status/recovery UI and confirmation UI remain Selected
and not yet implemented.

## SELECTED — Explicit POL-R confirmation workflow

After saving, offer a quick workflow to:

1. Confirm the entire applicable export as entered.
2. Confirm only checked task/day cells.
3. Defer confirmation and return to that export later.
4. Manually confirm the absolute amount currently in one POL-R task/day cell.

The common workflow requires no retyping of exported amounts. Propose each
applicable cell's **frozen export amount**, not its later recalculated actual.
Several entries can be confirmed together, always explicitly; saving alone is
never confirmation.

Partial confirmation changes checked entries only. Unchecked entries, including
previous confirmations, must not be cleared or reset. Zero-hour export cells are
not automatically confirmed. A user may explicitly confirm zero after clearing
or setting the actual external cell to zero.

Manual confirmation may differ from current Actual or the previous export.
Retain that distinction and show the resulting reconciliation Delta.

**CURRENT IMPLEMENTATION:** staged service APIs propose frozen export cells,
apply positive-only default or explicit checked/zero selection, validate
cell-specific acknowledgements against unchanged reviewed priors, and prepare an
existing-format batch without registration. Registration is a separate explicit
call. Deferral writes nothing; reopening requires renewed review. Acknowledgement
presentation, dialogs, manual-confirmation UI and production integration remain
unimplemented; these services do not verify external POL-R or report-file readiness.

## SELECTED — Confirmation evidence and batch integrity

The approved design uses two new event-backed concepts: **immutable saved export
snapshot** and **immutable POL-R confirmation**. A confirmation identifies task/day
cells and their new absolute external totals. Each cell's latest confirmed value
is derived from authoritative evidence.

Confirmations replace the known external cell total; they are not additive
increments. Prior evidence is not rewritten or deleted. A batch validates every
selected entry before committing; a rejected batch must not partially confirm
entries. Latest confirmed amounts, Delta and outstanding status are derived,
without independent additive project totals, outstanding balances or Delta
counters.

Confirmations may reference an export. Manual confirmation must also work without
a saved export. The approved
[confirmation technical contract](EXPORT_EVIDENCE_CONTRACT.md#confirmation-event-structure)
defines one validated batch event, expected prior identities and conflict-specific
acknowledgement. Strict immutable batch validation/replay, dedicated batch
preparation/registration and a derived in-memory effective-confirmation mapping
are implemented/staged. The low-level writer accepts explicitly reviewed cells;
it does not present proposals, infer acknowledgements or verify report copies.
Separate frozen-export proposal and selected preparation services are staged;
user acknowledgement presentation and confirmation UI remain unimplemented.
Staged service APIs do not make the production POL-R workflow operational.

## SELECTED — Corrections and stale exports

Corrections remain permitted after POL-R confirmation. When Actual changes,
recalculate it, preserve confirmed evidence, recalculate Delta, and show the new
absolute replacement total. When the user updates POL-R, record a new absolute
confirmation, retain earlier evidence and recalculate Delta.

Mandatory correction behavior: Actual originally **3:00**, Confirmed POL-R
**3:00**, Actual corrected to **2:30** produces **Delta = -0:30** and
**Enter in POL-R = 2:30**.

An export can be older than both current Actual and the latest confirmation. If
confirming an older export would replace a newer confirmed value with a different
amount, identify that specific conflict and require explicit user acknowledgement
before recording the replacement. Ordinary bulk confirmation must not silently
roll back newer confirmations. If the proposal already equals the latest known
value, no extra manual entry should be necessary. Confirmation errors and
corrections remain auditable.

## SELECTED — Incomplete current workdays

Export and confirmation are permitted during an incomplete workday; formal day
closure is not required. Where appropriate, clearly distinguish ongoing work
from a finalized historical reporting period. More work after confirmation
increases Actual and Delta while Confirmed POL-R stays unchanged; Enter in POL-R
shows the new complete daily total. Unknown prior values still follow the
Unknown/Unverified rule, rather than an invented signed Delta.

No automatic resubmission occurs. Exporting or confirming does not stop a timer
or reset actual-work counters.

## SELECTED — Low-friction primary workflow

Prioritize quick, clear actions. The user can see task/day cells needing attention,
read and easily copy the absolute replacement value, read signed Delta when the
prior value is known, select multiple cells, confirm all applicable export
entries or checked entries, defer, and manually correct a confirmed amount.
Unknown external values are visibly identifiable.

Ordinary bulk confirmation must not require a reason or free-text explanation
for every entry. Accidental or exceptional correction of prior evidence remains
traceable. Do not force reconstruction of a saved export cell by cell, or create
an additional timesheet requiring duplication of every manual entry already made
into POL-R.

## SELECTED — Optional weekly allocations; implementation DEFERRED

Allocations are optional informational, user-supplied data, not automatically
verified against POL-R. Do not assume one fixed lifetime allocation. Future
tracking supports Unknown allocation, explicit zero, task-specific weekly
allocation, a recurring weekly default, a specific weekly override, and manual
correction when project management changes an allotment.

Remaining allocation differs from outstanding unconfirmed time. For known
allocation, provide both **allocation minus confirmed external time** and
**projected remaining allocation after all current recorded actual work** as
estimates based on available information. Unknown allocation is not zero.
Negative remaining allocation may warn, but limits must never stop recording
or discard actual work.

Exact allocation-edit controls and treatment of existing weekly overrides after
week-start changes are Deferred for later adjudication, not choices made here.
POL-R's administration and enforcement of allotments remain Unverified.

## CURRENT IMPLEMENTATION — Inspected staged and production status

Source describes what executes, not an alternative product contract. See
[DESIGN_NOTES.md](../DESIGN_NOTES.md) for the technical contracts and limitations.

| Area | Inspected current behavior |
| --- | --- |
| Project/task foundation | Separate UUID-based service records, optional current project membership and independent task-owned time. |
| Date-only duration foundation | Separate endpoint-free records with append-only creation/correction/deletion replay and snapshots; new production duration writers are inactive. |
| Mixed accounting | Read-only explicit local-date windows, real intervals plus effective dated records, derived project/Unassigned/application totals, and fixed Sunday-start weeks. |
| Mixed work history | Detached task-owned interval/day segments and date-only rows, explicit cutoff, All history or inclusive dates, deterministic date direction and within-day chronology. Known deleted tasks are readable. A standalone table renders ordered rows with minute clocks, completed-minute durations and related-portion highlighting. A standalone browser adds Current week/Custom/All, Apply-only calendar/typed dates, explicit Refresh and local date sorting, with staged application-session direction handoff. An owned modal wrapper enforces single-window ownership through its unrouted opening path. Production integration and application-wide enforcement remain pending; production timeline, editing and reset controls are unchanged. |
| Timed input validation | Pure minute-clock candidate/resolution APIs with separate endpoint dates, explicit repeated-time occurrences, gap rejection, UTC ordering and edit-aware restoration of unchanged precision. Consumed by the form and standalone editor; production callers remain unchanged. |
| Timed input form | Standalone minute-only endpoint fields, canonical dates, timezone/occurrence choices and inline errors using the accepted validators. No stored-record loading, saving or production connection; legacy TimelineEntryDialog is unchanged. |
| Timed corrections | Separate staged preparation/registration of one effective closed genuine interval replacement, preserving unchanged precision, optional comments and retry identities. No-op saves write nothing; stale priors reject. Consumed by the standalone dialog; production editing remains inactive. |
| Standalone timed editor | Authoritative detached loading, minute controls preserving unchanged precision, stale conflict presentation, optional comments and frozen correction registration/retry. No production callers, creation/deletion or dated/running editing. |
| Timesheet rendering/generation | Staged independent-task exact and decimal renderers with authoritative scope/timezone metadata, safe calendar slots, reversible escaping and wrapped borders. Decimal output rounds task/day cells once and sums displayed hundredths; service generation still uses exact durations. |
| Timesheet file saving | Complete same-directory staging and atomic no-overwrite hard-link publication on supported filesystems; no new export event, submission, checkpoint or reset. |
| Production application | Legacy parent/subtask UI, exports, timestamp checkpoints and legacy submission markers still active; current duration UI still uses synthetic intervals. |
| Export evidence | Separate frozen decimal snapshot preparation, validated journal registration/readers/replay, verified materialization and read-only destination-relative five-status evaluation. Exact copies, matching-file reuse and no-overwrite publication are staged; materialization/evaluation create no new events or persistent file-status flags. |
| POL-R target workflow | Immutable confirmation-batch preparation/registration/replay, frozen-export proposals/selected preparation and latest absolute task/day projection are staged. Read-only daily Actual/Confirmed/Delta/Enter calculation is staged; confirmation/reconciliation UI, weekly summaries and production integration remain unimplemented. Legacy markers are not this contract; export registration is not confirmation or successful file export. |
| Week configuration and allocations | No selectable week-start setting or selected weekly-allocation management. |
| Data/installation | Launcher still uses the existing data path; fresh-directory release cutover is inactive. No historical migration implemented. |

Current text `HH:MM:SS[.fraction]` reporting remains available and unchanged;
two-decimal replacement rendering, separate persistent snapshot registration,
verified materialization and status evaluation are independently callable and
staged, without production export integration or a general file-status/recovery UI. Current source
Sunday-start handling is not a fixed future policy.
Backend foundations do not make the redesigned production workflow operational.

## OPEN — Reserved user/ChatGPT decisions

- **Allocation configuration details:** recurring defaults, overrides,
  allocation-edit controls and existing allocations/overrides after week-start
  changes.
- **First-release allocation scope:** whether allocation management is required
  for the first replacement release.
- **Replacement cutover:** exact release installation and old-data handling.
  Migration is not required; automatic deletion is not authorized.

## UNVERIFIED EXTERNAL BEHAVIOR — POL-R backend

The user's description suggests allotted-hour limits, but how allotments are
administered/changed and automatically enforced across recurring weeks is not
established by direct evidence. User-entered allocations and confirmations are
not independent external verification. Do not turn these assumptions into policy.

## DEFERRED — Approved implementation work

Future implementation includes configurable week starts, production export
integration and general file-status/recovery UI, explicit POL-R confirmation/reconciliation UI and weekly summaries,
the low-friction UI, weekly allocation tracking and replacement installation/cutover. Their Selected
behavior remains binding. Export/confirmation development follows the approved
technical contract through separately reviewed outcomes; unrelated Open allocation
and cutover decisions still require adjudication. No production workflow is active
merely because its contract is documented.
