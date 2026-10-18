# Chronicle development roadmap

This current-state document owns development sequencing, priorities, dependencies,
phase status and completion gates. The sequence below is user-approved; it does
not select new product behavior or architecture. The user and ChatGPT adjudicate
material decisions; Codex implements separately approved focused tasks.

The [product contract](TIMESHEET_REQUIREMENTS.md) owns Selected behavior and
Open/Unverified/Deferred boundaries. [Design Notes](../DESIGN_NOTES.md) owns current
technical contracts and limitations; source establishes what executes. See
[repository instructions](../AGENTS.md), the [overview](../README.md),
[Windows building guidance](../BUILDING.md) and the sole
[changelog](../CHANGELOG.md) for their respective scopes. This roadmap is neither
a second implementation reference nor a requirements, decision-history,
validation-ledger or task-history document.
The [testing strategy](TESTING_STRATEGY.md) owns validation applicability,
evidence requirements and release-qualification boundaries.
Historical rationale, provenance and supersessions belong in
[DECISIONS.md](DECISIONS.md), not in this current-state roadmap.
The selected technical export/confirmation architecture is owned by
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md); bounded export services
are staged, including confirmation preparation/registration/replay; confirmation
UI, reconciliation presentation/weekly summaries and production integration remain
pending; read-only daily reconciliation calculation is staged.

## Status and gate rules

| Status | Meaning |
| --- | --- |
| IMPLEMENTED / STAGED | Source-supported capability, not necessarily available in production UI. |
| APPROVED / NOT IMPLEMENTED | Selected behavior awaiting implementation or production integration. |
| BLOCKED ON ADJUDICATION | Necessary Open decision belongs to the user/ChatGPT. |
| DEFERRED | Approved work intentionally scheduled later. |
| VALIDATION PENDING | Implemented capability still lacks required integrated or platform verification. |
| COMPLETE | A bounded phase whose entire defined completion gate has actually been satisfied. |

[Phase 2](#phase-2--pol-r-evidence-and-reconciliation) is Complete for its
independently accepted bounded service gate. Its capabilities remain staged;
component tests or completed focused tasks do not establish a complete replacement
application. Integrated Windows execution, packaging and replacement-installation
validation are pending; release readiness is not established.

## Implemented foundation — staged, not production replacement

These capabilities are **IMPLEMENTED / STAGED**. Source inspection supports their
existence; their detailed contracts remain in Design Notes rather than here.

| Foundation | Implemented capability and boundary | Source / technical owner |
| --- | --- | --- |
| Project/task identity | Separate UUIDs; projects own no direct time; tasks own independent records, optional membership and reassignment preserving work. | [models.py](../src/task_timer/models.py), [project/task service](../DESIGN_NOTES.md#projecttask-service-foundation) |
| Date-only duration | Endpoint-free stable records; event-backed creation/correction/deletion replay; derived snapshots and existing backup compatibility. Production manual-duration UI still uses synthetic intervals. | [replay foundation](../DESIGN_NOTES.md#dated-duration-replay-foundation), [app.py](../src/task_timer/app.py), [backups.py](../src/task_timer/backups.py) |
| Mixed accounting | Genuine intervals and dated amounts; local-day/DST splitting; independent task totals; derived project/Unassigned/application totals; historical actuals independent of counter resets. Week start is currently Sunday only. | [accounting.py](../src/task_timer/accounting.py), [mixed service](../DESIGN_NOTES.md#mixed-date-window-accounting-service-only) |
| Mixed work history | Read-only current effective task records; linked local-day interval segments and whole dated amounts; explicit cutoff/date filtering and deterministic ordering. Standalone row rendering includes approved minute/date/offset/duration formatting and related-portion highlighting. A standalone browser adds periods, calendar/typed custom drafts, explicit Refresh and in-memory sorting, with staged application-session direction handoff. No production timeline, single-window enforcement or edit/delete integration. | [history browser](../DESIGN_NOTES.md#single-task-history-browser-staged), [history table](../DESIGN_NOTES.md#mixed-work-history-table-staged), [work_history.py](../src/task_timer/work_history.py), [history service](../DESIGN_NOTES.md#mixed-work-history-service-staged) |
| Timed input validation | Pure minute-only endpoint interpretation, separate dates, explicit repeated-time choices, gap rejection, UTC ordering and edit-aware preservation of unchanged precision; used by the form and standalone editor without production activation. | [work_entry_inputs.py](../src/task_timer/work_entry_inputs.py), [input contract](../DESIGN_NOTES.md#replacement-timed-input-validation-staged) |
| Timed corrections | Staged closed genuine-interval preparation/registration with no-op purity, preserved unchanged precision, optional comments, stale-prior rejection and journal-verified retries/warning outcomes. Consumed by the standalone correction dialog; no production callers. | [correction contract](../DESIGN_NOTES.md#timed-interval-corrections-staged) |
| Timed input form | Record-independent ttk component with separate endpoint fields, occurrence selection, edit-aware precision preservation and inline errors; composed by the standalone editor without production activation. | [timed_interval_form.py](../src/task_timer/timed_interval_form.py), [form contract](../DESIGN_NOTES.md#timed-interval-input-form-staged) |
| Standalone timed editor | Authoritative loading, precise closed-record editing through minute controls, stale conflict presentation and frozen registration/retry handoff. No production connection or dated/running editing. | [editor contract](../DESIGN_NOTES.md#standalone-timed-interval-correction-dialog-staged) |
| Timesheet presentation | Independent daily/weekly task rows, informational project subtotals, authoritative scope, duplicate-name references, multiline borders and reversible Unicode escaping protections. Exact and separate decimal renderers are staged; decimal task/day ROUND_HALF_UP cells conserve integer-hundredth rollups. | [exporter.py](../src/task_timer/exporter.py), [exact renderer](../DESIGN_NOTES.md#independent-task-timesheet-renderer-staged), [decimal renderer](../DESIGN_NOTES.md#decimal-hour-timesheet-renderer-staged) |
| Service reporting | Date-range generation; exact UTF-8 output; same-directory complete staging and atomic no-overwrite hard-link publication, destination protection and staging-only cleanup under documented assumptions. Saves files without immutable export registration. | [service workflow](../DESIGN_NOTES.md#date-range-timesheet-service-staged) |
| Export evidence | Frozen decimal snapshot preparation, strict journal-backed registration/replay, detached readers, verified materialization/retry and read-only destination-relative status evaluation. Matching files are reused; conflicting files are protected. Export APIs do not confirm POL-R; no status/recovery UI. | [snapshot registration](../DESIGN_NOTES.md#immutable-export-snapshot-registration-staged), [materialization](../DESIGN_NOTES.md#verified-export-materialization-staged), [file status](../DESIGN_NOTES.md#export-file-status-evaluation-staged) |
| Governance baseline | Root instructions, canonical approved POL-R product contract, cumulative changelog and current/target authority separation. | [AGENTS.md](../AGENTS.md), [requirements](TIMESHEET_REQUIREMENTS.md), [CHANGELOG.md](../CHANGELOG.md) |
| Confirmation evidence | Dedicated immutable batch preparation/registration/replay, prior/stale/duplicate rules, recovery synchronization, frozen-export proposals/selected preparation and an in-memory effective task/day projection. Read-only daily reconciliation is staged; no confirmation/reconciliation UI or weekly summaries. | [confirmation replay](../DESIGN_NOTES.md#immutable-pol-r-confirmation-replay-staged) |

These foundations do **not** constitute a completed production replacement.
New production date-only writers, replacement UI, production export integration,
general file-status/recovery UI,
POL-R confirmation/reconciliation UI and weekly summaries, configurable weeks, allocations and release
cutover remain pending. Existing production legacy behavior is not permanent
target policy. Platform/integrated validation remains **VALIDATION PENDING**.

## Phase 1 — Remaining governance and architecture

**Status:** approved development priority; not marked Complete. Export/evidence
architecture is selected, recorded and independently reviewed. Architectural
approval is not operational functionality and does not itself complete this phase.

**Outcome:** establish missing governance and approved technical contracts before
persistent POL-R evidence is implemented. Keep the following independently
reviewable documentation outcomes separate:

- **Testing strategy — established:** [TESTING_STRATEGY.md](TESTING_STRATEGY.md)
  defines proportional validation and evidence expectations for accounting,
  replay/correction, persistent integrity, reconciliation, backup/restore,
  filesystem failures, Windows integration, release and data safety. Establishing
  this governance does not complete Phase 1 or perform runtime qualification;
  implementation and integrated validation remain separate outcomes.
- **Architectural decision history — established:** [DECISIONS.md](DECISIONS.md)
  preserves approved choices, established rationale, provenance and genuine
  corrections/supersessions. History does not replace technical authority or
  complete Phase 1.
- **Export/evidence architecture — selected:**
  [EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md) records snapshot-first
  journal registration, decimal-hour cells, verified recoverable file copies and
  confirmation batch integrity. Pure decimal rendering is implemented/staged;
  export-snapshot registration and confirmation preparation/registration/replay are
  also staged; confirmation and file/evidence status/recovery UI remain approved
  but unimplemented. Verified file
  materialization is staged. Codex must
  follow these contracts rather than choose alternative mechanisms.

**Completion gate:** required testing governance exists; material decisions and
supersessions are traceable; persistent-evidence architecture is approved;
affected authorities agree; no necessary Open issue has been silently resolved.

## Phase 2 — POL-R evidence and reconciliation

**Status:** **COMPLETE** for the existing bounded POL-R evidence and daily
reconciliation service gate under serialized dataset ownership. Capabilities remain
**IMPLEMENTED / STAGED**: decimal rendering and immutable export
snapshot preparation/registration/replay, verified file materialization and
standalone read-only file-status evaluation, plus immutable confirmation-batch
preparation/registration/replay, effective projection and read-only daily
Actual/Confirmed/Delta/Enter calculation, plus frozen-export proposals and selected
acknowledged batch preparation. Confirmation/reconciliation presentation,
weekly summaries and general status/recovery UI remain
**APPROVED / NOT IMPLEMENTED** under their existing later-phase responsibilities.

**Accepted basis:** ChatGPT independently accepted the existing completion gate
using connected service acceptance and bounded replay/failure evidence under the
[technical contract](EXPORT_EVIDENCE_CONTRACT.md) and
[validation strategy](TESTING_STRATEGY.md#pol-r-reconciliation-evidence-and-future-workflow-acceptance).
Acceptance does not qualify native Windows/NTFS, real concurrent writers,
power-loss durability or external POL-R behavior.

**Dependencies:** follow the [approved contract](EXPORT_EVIDENCE_CONTRACT.md).
Pure decimal rendering, snapshot registration and verified materialization are
implemented/staged as separate semantic outcomes. Confirmation validation/replay
and dedicated preparation/registration, frozen-export proposal/selection
preparation and daily reconciliation calculation remain staged foundations whose
bounded gate is independently accepted. Further workflow integration requires
separately approved focused tasks and independent GO review. Phase closure does
not reorder the six development phases or activate the production UI.

**Outcome:** implement the approved distinction between Actual, Exported and
Confirmed POL-R. The [product contract](TIMESHEET_REQUIREMENTS.md) remains the
semantic authority. Required development outcomes are:

- Immutable saved-export evidence retaining task/day actuals, task UUIDs and
  historical labels, scope, cutoff, date range and original week-start convention,
  unchanged by later corrections.
- Immutable confirmation evidence for absolute daily external totals, including
  manual confirmation without an export, explicit zero, Unknown distinct from
  zero, retained earlier confirmations and validation of whole batches before
  commitment.
- Derived task/day reconciliation: Actual; latest Confirmed POL-R; signed
  Delta = Actual - Confirmed when known; Enter in POL-R = current Actual as the
  complete replacement value. Unknown confirmation yields Unverified Delta,
  not a fictitious zero-based balance. Confirmation is never additive work.
- Historical correction and stale-export handling preserving evidence,
  recalculating Delta, and preventing silent rollback of newer confirmation.
  A conflicting replacement requires the specific explicit acknowledgement
  selected in the contract.

**Required acceptance example:** save/export 3:00, work another 2:00, then confirm
the exported 3:00: Actual = 5:00; Confirmed = 3:00; Delta = +2:00;
Enter in POL-R = 5:00. After confirming the external cell at 5:00, Delta = 0:00.
The old export and earlier confirmation remain evidence; no timer reset or
additional independent 2:00 external entry is required. Also validate the
contract's correction from Actual/Confirmed 3:00 to Actual 2:30:
Delta = -0:30 and Enter in POL-R = 2:30.

**Completion gate:** deterministic evidence replay; immutable prior evidence;
no partially committed confirmation batches; export/confirmation values never
increase Actual; required examples and correction cases pass; failure handling
is validated; legacy submission/checkpoint assumptions do not enter this model.

Generate separate focused implementation tasks against the approved contract
after independent acceptance; this phase is not one broad execution authorization.
Return any newly necessary material decision for user/ChatGPT adjudication.

## Phase 3 — Time entry and project workflow

**Status:** **APPROVED / NOT IMPLEMENTED** in production; foundations
are staged, including the detached mixed work-history reader, standalone history
table/browser with related-portion highlighting, period/calendar controls,
explicit refresh and in-memory sorting, pure timed-input validation, a standalone
timed-interval form and closed-interval correction
preparation/registration connected by a standalone correction dialog. These
foundations do not activate dated writers or satisfy the active-reader/UI gate below.

**Outcome:** activate genuine date-only creation and correction/deletion, an
appropriate mixed timeline editor, project/task navigation, project creation and
reassignment, independent task displays and useful daily/weekly totals. Preserve
normal start/stop timers; eliminate fabricated endpoints from new manual entries.
Actual-work entry remains independent of POL-R confirmation and allocations.
The [Selected history behavior](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history)
requires current-week/custom/All periods, newest-first application startup with
direction remembered across task/dataset history openings only within that
session, at most one history window per application,
linked daily portions that edit/delete the full interval, type-preserving editing
and audit/details. Replacement Reset actions/counters are removed from the target;
their production removal and production browser/editing integrations remain pending.
The standalone browser's caller-supplied week start and application-owned direction
handoff are staged seams; production window ownership/enforcement and
configurable-week settings remain pending. No cross-restart preference is required.
The [Selected timed-input behavior](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records)
requires minute-only entry/editing/display, separate endpoint dates/times,
explicit repeated-time occurrence choices and rejection of nonexistent local
times. Input interpretation, the standalone form and closed timed-correction
services are staged. The correction path preserves unchanged endpoints, allows
optional comments and rejects stale saves; unchanged saves create no event.
Standalone closed-record editing and mixed-history rendering are staged;
production editor/history integration and activation remain pending.

**Dependency:** do not activate a production dated-duration writer while any
required active reader omits that work. Integrate mixed accounting/readers with
the writer safely; backend availability alone does not satisfy this boundary.

**Completion gate:** new manual amounts have no artificial timestamps; every
active reader includes both supported types; task/project/application totals
reconcile; corrections remain auditable; timers and manual entries agree with
accounting; representative operator UI workflows are validated.

## Phase 4 — Configurable weeks and timesheet UI

**Status:** **APPROVED / NOT IMPLEMENTED**; staged text reporting is a foundation.

**Outcome:** make the approved reporting and reconciliation workflow usable:

- Select any weekday as week start, initially Sunday. Apply it consistently to
  weekly reporting and reconciliation without changing work dates or amounts;
  saved evidence retains its original convention.
- Present project/task grouping, daily values, independent weekly task totals
  and informational project subtotals, with clear incomplete/current-day status.
- Display Actual, Confirmed POL-R, Delta and Enter in POL-R, prioritizing the
  absolute replacement value and making Unknown visible.
- Provide confirm-entire-applicable-export, checked-cell confirmation, defer,
  manual external-total confirmation, access to frozen evidence, stale-export
  warnings and minimal repeated typing. Propose frozen amounts; unchecked
  values remain unchanged. Do not automatically confirm zero-hour export cells.
- Provide preview, save, reopen evidence and explicit confirmation controls;
  enable easy copying and multiple-cell selection without requiring a reason
  for every ordinary bulk confirmation. No export-driven timer reset or stop.

**Dependencies:** validated Phase 2 evidence/reconciliation and corresponding
production readers; correct date-based contributions for configurable weeks.
POL-R-facing formatting follows the selected two-decimal-hour representation
and displayed-cell rollups in the [technical contract](EXPORT_EVIDENCE_CONTRACT.md).

**Completion gate:** a normal reporting week can be managed through the UI;
whole-export confirmation needs minimal interaction; partial confirmation leaves
unchecked cells intact; stale exports cannot silently undo newer confirmation;
Actual/Confirmed/Delta/Enter stay correct during further work; week-start changes
preserve daily work and old evidence; user-facing workflow tests pass. Export
and confirmation are allowed during an incomplete day without timer resets.

Use several independently reviewed focused tasks as needed, not one execution
whose scope is the entire phase.

## Phase 5 — Optional weekly allocations

**Status:** selected functionality; **DEFERRED**. Configuration details remain
**BLOCKED ON ADJUDICATION**.

**Outcome when implemented:** support Unknown, explicit zero, task-specific weekly
allotments, recurring defaults, week overrides and manual adjustments. Show both
allocation minus confirmed external time and projected remaining after all
recorded actual work as estimates, separate from outstanding unconfirmed time.
Insufficient allowance may warn; it never prevents recording or discards Actual.

**Dependencies and boundaries:** recurring/override configuration and treatment
of existing overrides after week-start changes require user/ChatGPT adjudication.
POL-R backend administration/enforcement remains Unverified. Allocations must not
block actual-time development or basic confirmation. Whether allocations are
required for the first replacement release remains a release-scope decision
reserved for the user/ChatGPT; this roadmap does not decide it.

**Completion gate when implemented:** Unknown and zero remain distinct; recurrence
and overrides follow approved behavior; estimates never change Actual; warnings
do not interrupt timers; no external POL-R authorization is falsely implied.

## Phase 6 — Replacement release and integration

**Status:** not complete; replacement work is **APPROVED / NOT IMPLEMENTED**,
integrated/platform verification is **VALIDATION PENDING**, and cutover is
**BLOCKED ON ADJUDICATION**.

**Outcome:** deliver the selected replacement rather than a permanent parallel
legacy interface, with four bounded areas:

- **Legacy reconciliation:** remove or retire superseded UI and parent/subtask
  reporting assumptions. Reconcile mini-mode, templates and related functionality
  against the selected contract; do not invent their future disposition.
- **Data/installation:** start fresh, without historical migration; protect old
  user files. Adjudicate exact installation/data cutover before implementing it.
  Replacement is not permission to delete existing data.
- **Integrated validation:** exercise complete timesheet operation, timer/manual
  interaction, export/confirmation/correction together, replay, archive rotation,
  snapshots, backup/restore and file-output/persistence failures. Perform
  representative Windows execution, packaging and installation checks; verify
  old data protection.
- **Governance closure:** reconcile affected current-state owners and cumulative
  Unreleased changes; remove or explicitly track material blockers; obtain
  independent integrated review before release or merge authorization.

**Completion gate:** the actual user workflow operates end to end; required
Windows checks are performed; no critical data-integrity failure remains;
installation matches approved cutover policy; documentation describes the
implemented product; independent integrated review supports release readiness.
A passing backend suite alone does not meet this gate. The optional allocation
release-scope decision remains outside Codex's authority.

## Dependency constraints and adjudication

The phase order is the approved development priority. Dependencies apply to the
affected outcome; they do not require an entire preceding phase to finish before
independent work elsewhere can begin. Safe parallel conceptual planning is
allowed, but it does not authorize premature implementation.

| Development outcome | Prerequisite or reserved decision |
| --- | --- |
| Persistent export/confirmation events | Selected technical contract and validated decimal replacement rendering before export-snapshot integration. |
| POL-R reconciliation | Reliable confirmation evidence; Unknown/zero and replacement semantics. |
| Confirmation from saved exports | Frozen export evidence, not a recalculation of current Actual. |
| Production date-only entry | Corresponding mixed-accounting and active-reader integration. |
| Production reconciliation UI | Validated evidence/calculations and the selected decimal representation. |
| Configurable weekly presentation | Correct date-based contributions and preservation of old evidence conventions. |
| Allocation configuration | Approved remaining recurrence/override/week-change behavior. |
| Release cutover | Separately approved installation/old-data handling contract. |
| Final release readiness | Integrated workflow and actual Windows validation plus independent review. |

Allocation configuration, week-change interactions, replacement cutover and
first-release allocation inclusion remain Open. POL-R backend allotment
administration/enforcement remains Unverified. Export event/confirmation contracts,
snapshot-first consistency/recovery and decimal representation are selected in
their technical owner; this roadmap neither duplicates nor replaces that contract.

## Maintenance

Update phase status from verified implementation evidence, dependencies and gates
when their approved basis changes. Preserve accurate foundation statements; keep
Open matters visible; remove stale current-state claims in place. Claim Complete
only after the bounded gate is satisfied, not after a component task or test run.

Do not append receipt/commit history, estimates, percentages, delivery dates or
fixed task counts. Requirements remain in the product contract, implementation
details in Design Notes, decisions in their appropriate approved authority and
historical changes in CHANGELOG.md. This document is not an automated task tracker
or validation ledger. Return any newly necessary product/architecture decision
to the user/ChatGPT before dependent execution.
