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
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md); implementation is pending.

## Status and gate rules

| Status | Meaning |
| --- | --- |
| IMPLEMENTED / STAGED | Source-supported capability, not necessarily available in production UI. |
| APPROVED / NOT IMPLEMENTED | Selected behavior awaiting implementation or production integration. |
| BLOCKED ON ADJUDICATION | Necessary Open decision belongs to the user/ChatGPT. |
| DEFERRED | Approved work intentionally scheduled later. |
| VALIDATION PENDING | Implemented capability still lacks required integrated or platform verification. |
| COMPLETE | A bounded phase whose entire defined completion gate has actually been satisfied. |

No phase below is marked Complete. Component tests or completed focused tasks do
not establish a complete replacement application. Integrated Windows execution,
packaging and replacement-installation validation are pending; release readiness
is not established.

## Implemented foundation — staged, not production replacement

These capabilities are **IMPLEMENTED / STAGED**. Source inspection supports their
existence; their detailed contracts remain in Design Notes rather than here.

| Foundation | Implemented capability and boundary | Source / technical owner |
| --- | --- | --- |
| Project/task identity | Separate UUIDs; projects own no direct time; tasks own independent records, optional membership and reassignment preserving work. | [models.py](../src/task_timer/models.py), [project/task service](../DESIGN_NOTES.md#projecttask-service-foundation) |
| Date-only duration | Endpoint-free stable records; event-backed creation/correction/deletion replay; derived snapshots and existing backup compatibility. Production manual-duration UI still uses synthetic intervals. | [replay foundation](../DESIGN_NOTES.md#dated-duration-replay-foundation), [app.py](../src/task_timer/app.py), [backups.py](../src/task_timer/backups.py) |
| Mixed accounting | Genuine intervals and dated amounts; local-day/DST splitting; independent task totals; derived project/Unassigned/application totals; historical actuals independent of counter resets. Week start is currently Sunday only. | [accounting.py](../src/task_timer/accounting.py), [mixed service](../DESIGN_NOTES.md#mixed-date-window-accounting-service-only) |
| Timesheet presentation | Independent daily/weekly task rows, informational project subtotals, authoritative scope, duplicate-name references, multiline borders and reversible Unicode escaping protections. | [exporter.py](../src/task_timer/exporter.py), [renderer](../DESIGN_NOTES.md#independent-task-timesheet-renderer-staged) |
| Service reporting | Date-range generation; exact UTF-8 output; same-directory complete staging and atomic no-overwrite hard-link publication, destination protection and staging-only cleanup under documented assumptions. Saves files without immutable export registration. | [service workflow](../DESIGN_NOTES.md#date-range-timesheet-service-staged) |
| Governance baseline | Root instructions, canonical approved POL-R product contract, cumulative changelog and current/target authority separation. | [AGENTS.md](../AGENTS.md), [requirements](TIMESHEET_REQUIREMENTS.md), [CHANGELOG.md](../CHANGELOG.md) |

These foundations do **not** constitute a completed production replacement.
New production date-only writers, replacement UI, immutable export registration,
POL-R confirmation/reconciliation, configurable weeks, allocations and release
cutover remain pending. Existing production legacy behavior is not permanent
target policy. Platform/integrated validation remains **VALIDATION PENDING**.

## Phase 1 — Remaining governance and architecture

**Status:** approved development priority; not marked Complete. Export/evidence
architecture is selected and recorded; independent review of the reconciled
contract remains pending. Architectural approval is not operational functionality.

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
  confirmation batch integrity. These formerly Open contracts are approved, not
  implemented. Codex must follow them rather than choose alternative mechanisms.

**Completion gate:** required testing governance exists; material decisions and
supersessions are traceable; persistent-evidence architecture is approved;
affected authorities agree; no necessary Open issue has been silently resolved.

## Phase 2 — POL-R evidence and reconciliation

**Status:** **APPROVED / NOT IMPLEMENTED**. Relevant technical contracts are
selected; independently accepted documentation and focused implementation are
still required.

**Dependencies:** follow the [approved contract](EXPORT_EVIDENCE_CONTRACT.md).
First implement and validate decimal-hour replacement rendering as a separate
semantic outcome, before persistent export-snapshot integration. This dependency
does not reorder the six development phases or activate the production UI.

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

**Status:** **APPROVED / NOT IMPLEMENTED** in production; backend foundations
are staged.

**Outcome:** activate genuine date-only creation and correction/deletion, an
appropriate mixed timeline editor, project/task navigation, project creation and
reassignment, independent task displays and useful daily/weekly totals. Preserve
normal start/stop timers; eliminate fabricated endpoints from new manual entries.
Actual-work entry remains independent of POL-R confirmation and allocations.

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
