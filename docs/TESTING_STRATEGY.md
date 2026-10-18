# Chronicle testing strategy

This document owns validation expectations, applicability, evidence requirements
and release-validation boundaries. It does not select product behavior,
architecture, persistence/recovery mechanisms or a new release policy.

The [product contract](TIMESHEET_REQUIREMENTS.md) owns acceptance semantics;
the [roadmap](ROADMAP.md) owns sequencing and completion gates;
[Design Notes](../DESIGN_NOTES.md) owns current technical implementation and
limitations. [AGENTS.md](../AGENTS.md) routes repository work;
[README.md](../README.md) describes status; [BUILDING.md](../BUILDING.md) owns
Windows packaging instructions; [CHANGELOG.md](../CHANGELOG.md) is the sole
historical change record. Tests are evidence, not independent product authority.
An expectation below does not establish an existing test or a passing result.
Export/confirmation tests follow the selected
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md), the sole technical
owner of event, decimal, verification/recovery and batch semantics.

## Principles and applicability

Evidence must match the claim. Passing tests demonstrate the behavior exercised,
not architectural correctness, a working desktop workflow or release readiness.
Choose meaningful tests for the changed guarantees, credible failures and actual
dependencies. Focused implementation requires behavioral evidence for its new
semantic outcome, invariants, invalid inputs and affected existing behavior.
Avoid tests that merely mirror implementation or ceremony unrelated to risk.

Selection is proportional: an isolated change need not run every category.
Shared accounting, event persistence, recovery, application state and significant
cross-component changes justify broader regression. Known commands are not
mandatory for every change. Markdown-only changes normally need source/status
review, link checks and diff checks, without Python regression; an unexpected
executable delta or applicable authority can change that scope.

Use isolated data. Never weaken tests to hide regressions, relabel a failing
requirement as an implementation preference, or change approved behavior to make
tests pass. If an expected result requires an Open product/architecture decision,
return it to the user/ChatGPT before dependent implementation or test assertions.
Report unavailable platforms and checks not run; do not present historical
results as present execution.

## Validation levels

These levels describe applicability, not a compulsory sequence for every task.

| Level | Purpose and applicability |
| --- | --- |
| A — Focused behavioral | One implementation outcome: new behavior, important invariants, meaningful invalid inputs, credible failure paths and directly affected old behavior. |
| B — Affected regression | Required where neighboring behavior can change. Select existing tests from source dependencies, not a repeated unrelated checklist. |
| C — Full Python regression | Required for significant integration boundaries and shared accounting, persistence, recovery, application-state or cross-component changes where focused tests cannot establish regression safety; also required for final integrated validation. |
| D — Application integration | Exercise interacting components and applicable operator workflows: timers, manual work, projects, exports, confirmations and restoration. Mocked service/UI tests alone do not prove real desktop interaction. |
| E — Windows/platform | Exercise actual Windows UI, filesystem, PowerShell, packaging and installation guarantees where applicable. Linux results cannot establish them independently. |
| F — Release qualification | Apply the roadmap's final gates: integrated workflow evidence, actual Windows execution, packaging, approved installation/data protection and independent integrated review. Unit tests alone do not qualify a release. |

For Levels A–C, state which suite ran and its actual result; a focused run is not
a full regression. Levels D–F require evidence of interactions/platforms actually
exercised, with material omissions explicit. Implementation tests and integrated
qualification remain distinct.

## Current test evidence and limits

The following inventory describes existing test cases and their scope, not
exhaustive coverage or passing results. Use it to find affected tests and inspect
their assertions before selecting a run.

| Area | Existing test sources and observed scope |
| --- | --- |
| Project/task identity | [test_projects.py](../tests/test_projects.py): independent identities, membership/reassignment, invalid targets, replay and data isolation. |
| Date-only replay | [test_dated_durations.py](../tests/test_dated_durations.py): endpoint-free records, correction/deletion, ownership/payload rejection, equal-second replay, archives, rebuild and backup/restore. Uses isolated private event fixtures; it does not activate production writers. |
| Accounting and time boundaries | [test_mixed_accounting.py](../tests/test_mixed_accounting.py), [test_time_utils.py](../tests/test_time_utils.py): conservation, selection, cutoffs, midnight/DST, corrections, resets, fractional amounts and fixed Sunday weeks. |
| Replacement timed inputs | [test_work_entry_inputs.py](../tests/test_work_entry_inputs.py): accepted minute formats, strict date/clock/timezone/occurrence validation, second/fraction rejection, round-trip candidates, ordinary deduplication, Chicago gap/repeat, UTC ordering despite reversed wall clocks, overnight/fixed offsets, Lord Howe non-hour transitions, representability limits, detached results, prohibited external operations and fresh import/evaluation without service/storage dependencies. Also covers edit-aware restoration of unchanged seconds/fractions, same-minute positive spans, equivalent text and changed occurrences. Pure input interpretation only; editor integration is covered separately below. |
| Timed input form | [test_timed_interval_form.py](../tests/test_timed_interval_form.py): actual component construction with widget doubles, variable/event wiring, separate dates, minute formats, canonical date rejection, gaps/repeats/offset labels, independent choice clearing, draft retention/error correction, fresh validator delegation and absence of external writes/clock detection. Separate real-Tk smoke cases exercise construction, field callbacks, choice selection and resolution when a display is available; otherwise they skip with a reason. Edit-aware resolution and the validated occurrence setter have separate draft/error/fresh-delegation assertions. Neither doubles nor Linux Tk smoke establish production activation or native Windows interaction. |
| Timed corrections | [test_timed_interval_corrections.py](../tests/test_timed_interval_corrections.py): authoritative detached preparation, optional comments, unchanged fractional endpoints, no-op purity, effective-prior/identity/schema rejection, prospective equal/backdated replay, stale caches and backup-hook rechecks, configured backups, append absence/no-op/partial/complete-error and rotation-manifest faults, synchronization open/fsync/close/inspection/validation failures, installation/snapshot warnings, exact retry after newer work/confirmations, midnight/DST agreement, restart/rotation/rebuild/restore. The authoritative correction reader also covers stale caches, detached/deleted task reads, owner rejection and write-prohibited journal failures. Earlier evidence and prepared identities remain detached; no production editor or universal durability qualification. |
| Standalone timed editor | [test_timed_interval_editor.py](../tests/test_timed_interval_editor.py): actual construction/callbacks with widget doubles and real isolated services, precise/no-op editing, stale conflict and replacement-chain presentation, locked frozen retries, registration uncertainty versus refresh/recovery warnings, earlier verified-result retention, reentry, Close/Cancel handoffs and unrelated-work/evidence preservation. Real-Tk cases exercise construction, occurrence selection, Save/retry and unverified close when a display is available. No production or platform qualification. |
| Mixed work history | [test_work_history.py](../tests/test_work_history.py): real isolated service/model projection, exact detached row shape, mixed entries, known deleted-task lookup, inclusive/All dates, date direction with stable within-day chronology, linked daily identity/continuations, midnight/DST/fixed offsets, running cutoffs, whole dated amounts, correction/redating/deletion/restart, reset/confirmation independence, synthetic refusal and per-day accounting agreement. State/event/snapshot/file comparisons and prohibited journal/write/clock/UUID calls cover purity on success and rejection. No production timeline, edit/delete handler, sort-preference or audit UI qualification. |
| Mixed-history table | [test_work_history_view.py](../tests/test_work_history_view.py): actual constructor/callbacks with widget doubles and real isolated service rows, exact order and detached complete metadata, midnight dates, DST/repeated-hour offsets, fixed/non-hour zones, running boundaries, precise retained amounts and completed-minute display, task-scoped related highlighting, stale handles, replacement/empty results, preparation failure preservation and widget-update invalidation/explicit recovery. Prohibited service/file/settings/clock/scheduling calls and dataset/state comparisons cover purity. Separate real-Tk smoke exercises construction, mapping, selection/highlighting, replacement and failures when a display is available; otherwise it skips with a reason. No production browser or native Windows qualification. |
| Single-task history browser | [test_work_history_browser.py](../tests/test_work_history_browser.py): real isolated reader/table composition with constructor/callback doubles, exact load arguments and clock counts, seven week starts, rollover/UTC-local/DST boundaries, mixed and future dated work, inclusive Custom/All, running cutoffs, Apply-only typed/calendar drafts, seed/cancel/disposal, stable local sorting without newer records, committed Custom refresh, initial failure versus valid empty history, clock/service/preparation/widget faults, recovery and state/file/settings/timer/scheduling purity. Separate real-Tk smoke uses actual Calendar selection/cancellation, focus changes, Apply, Date-heading invocation, Refresh, errors and replacement. These tests do not qualify production window ownership, workflows or native Windows. |
| History session direction | [test_history_session_direction.py](../tests/test_history_session_direction.py): actual application constructor with unrelated startup isolated, newest-first initialization before controls independently of settings, unrouted factory using explicit task/service, post-render single notification, sequential task/dataset handoff, closure retention and new-owner reset. Actual browser/table doubles exercise preparation/widget failures, callback rejection before construction/loading, completed-sort notification failure, and unchanged cutoff/drafts/domain/files with no sort-time reader/clock/settings writes. Separate real-Tk smoke covers sequential construct/sort/destroy/reopen; it does not qualify production routing or enforce the Selected single-history-window rule. No cross-restart persistence is Selected. |
| Rendering | [test_timesheet_renderer.py](../tests/test_timesheet_renderer.py): scope, partial/multiple weeks, calendar boundaries, exact durations, duplicate identity, wrapping/geometry and Unicode escaping. |
| Decimal rendering | [test_decimal_timesheet_renderer.py](../tests/test_decimal_timesheet_renderer.py): ROUND_HALF_UP conversion/boundaries, invalid numbers, task/day rounding and displayed-rollup conservation, selection/identity, partial/multiple weeks, calendar edges, Unicode wrapping, purity and exact/legacy byte compatibility. This is a pure staged renderer, not export-evidence persistence. |
| Export registration | [test_export_snapshot_registration.py](../tests/test_export_snapshot_registration.py): frozen request/cells/text/digest, strict validation, stable identity/retry, journal health, synchronized recovery/reuse, ambiguous append and projection failures, immutable replay order, restart/rotation/rebuild/backup restore and no report publication or confirmation creation by registration. Includes reuse checks for preservation of existing materialized bytes and installation of the latest valid confirmation projection. Dedicated materialization and confirmation suites provide broader feature coverage. |
| Verified materialization | [test_export_materialization.py](../tests/test_export_materialization.py): authoritative journal gate, exact frozen UTF-8 bytes and SHA-256, existing-file reuse/conflicts, symlinks, staging/publication/verification/cleanup failures, concurrent replacement injection, retry, restored evidence and state/journal purity. No production UI or permanent file-status guarantee. |
| File-status evaluation | [test_export_file_status.py](../tests/test_export_file_status.py): strict evidence gate even without a destination, precedence, five current outcomes, conclusive conflict versus inspection uncertainty, complete short files versus incomplete reads, disappearance/replacement, reevaluation/restart and write-prohibited purity. Service-only coverage, not recovery UI or platform qualification. |
| Confirmation replay | [test_polr_confirmation_replay.py](../tests/test_polr_confirmation_replay.py): exact event/cell validation, manual/export-linked values, Unknown/zero, prior/stale truth conditions, atomic rejection, physical ordering, duplicates/collisions, startup failure, history/rotation/rebuild/restore and Actual/timer/export purity. Isolated replay fixtures; writer coverage is separate below. |
| Confirmation writer | [test_polr_confirmation_writer.py](../tests/test_polr_confirmation_writer.py): pure explicit-cell preparation, strict pre-append validation, superseded priors, exact identity recovery after newer batches, append/flush/sync/close/inspection/installation faults, rotation/restart/restore and Actual/export purity. Serialized one-service fixtures do not qualify multi-process writers or production workflows. |
| Export confirmation proposals | [test_polr_confirmation_proposals.py](../tests/test_polr_confirmation_proposals.py): frozen values/names/coverage, positive-only defaults and explicit zeros, canonical checked selection, first-occurrence stale truth table, exact acknowledgements, selected-prior changes, tampering, fresh evidence, purity and explicit registration/retry. Service preparation only; no dialogs or production interaction. |
| Daily reconciliation | [test_polr_reconciliation.py](../tests/test_polr_reconciliation.py): Unknown/zero, mandatory frozen-export and correction examples, precise cell rounding, scope/identity, sparse zero-work dates, physical-order confirmation freshness, one strict read/one Actual call, detached results, evidence/accounting rejection and write-prohibited purity. Daily service calculation only; no weekly balance, UI or production workflow qualification. |
| Connected POL-R services | [test_polr_service_workflow.py](../tests/test_polr_service_workflow.py): real export preparation/registration, exact-byte/digest materialization, frozen proposals, default/checked selection, separate explicit registration, daily reconciliation and replay/restore. Covers 3.00-to-5.00 absolute replacement, negative correction, explicit zero/Unknown, stale rejection and exact retries without duplicate append or rollback, with state/file purity and detached evidence. POSIX/Windows path-representation cases exercise the registration guard's journal exclusions and unrelated-file mutation detection. Disposable serialized service scenarios and path-flavour coverage, not production, native Windows, concurrent-writer or power-loss qualification. |
| Reporting/file publication | [test_timesheet_service.py](../tests/test_timesheet_service.py): real service orchestration, UTF-8 bytes, no-clobber publication, concurrent targets, injected staging/publication/cleanup failures and state/file purity. |
| Existing storage and backups | [test_storage.py](../tests/test_storage.py), [test_backups.py](../tests/test_backups.py), plus project/dated/accounting/export fixtures: fresh/empty initialization, missing-component constructor rejection without mutation, healthy restart, rotation, snapshots, backup contents, retention and restore behavior. |
| Legacy compatibility | [test_exporter.py](../tests/test_exporter.py), [test_timeline_corrections.py](../tests/test_timeline_corrections.py), and neighboring tags/subtask/template/selected-export tests protect current behavior during staging. Legacy submission/checkpoint tests are not proof of replacement POL-R semantics. |
| UI and launch routing | [test_app_ui.py](../tests/test_app_ui.py), dialog/window tests and [test_root_launcher.py](../tests/test_root_launcher.py): callbacks, formatting and routing; some construct fake roots, SimpleNamespace widgets or instances without real GUI initialization. They do not establish real Windows desktop usability or packaged execution. |

Existing fixtures use pytest `tmp_path` and `monkeypatch`, including fixed clocks
and America/Chicago timezone examples. File/state snapshots make purity and
invalid-operation assertions meaningful.

Currently, mixed accounting is staged and Sunday-only, mixed work-history
projection is service-only with a separate standalone rendering/selection-feedback
component and staged standalone browser with periods/explicit refresh/local sorting,
production date-only writers are inactive, and saving publishes a file
without immutable export-event registration. Confirmation preparation/registration/replay and daily reconciliation
calculation are staged; configurable weeks, POL-R confirmation/reconciliation UI,
weekly reconciliation summaries and
replacement installation are not implemented or validated by existing foundation
tests. Future acceptance obligations below are explicitly conditional on approved
implementation; test names or prior receipts do not change that status.

Future history integration must validate the
[Selected UI behavior](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history):
production current-week/custom/All workflows, application-session direction
handoff across task/dataset openings with newest-first startup and single-history-window
ownership/enforcement, linked
segment edit/delete acting on the complete interval with affected-date warnings,
entry-type preservation, effective-only normal history and audit/details access.
Pure timed-input tests separately cover the Selected minute-only and daylight-saving
interpretation rules. The standalone form has field/occurrence/inline-error
coverage, including edit-aware precision preservation. The standalone correction
dialog connects these to real correction services, with its own callback,
registration/retry and real-Tk cases. Future production integration must retain
these guarantees and validate the operator workflow. Those input/editor tests do
not establish work-history rendering; the separate table suite covers standalone
rendering and related-portion feedback. The browser suite separately covers
standalone reader/table integration and explicit interactions, not production
integration, application-wide window enforcement, native Windows or production readiness.
The separate session-direction suite covers the staged application-owned handoff,
not production routing; it requires no preference file or settings persistence.
Production Reset removal is separate from proving that staged history ignores
legacy reset boundaries. Service projection tests do not establish those UI or
application-window capabilities, native Windows interaction or production qualification.

## Accounting guarantees to validate when changed

Use exact recorded seconds, including supported fractions, as accounting inputs;
do not establish correctness from rounded report text alone. Test:

- Independent UUID-keyed task totals, duplicate names, Unassigned tasks and
  historical deleted-task inclusion under explicit selection rules.
- Derived non-additive project subtotals and application conservation:
  **sum of included task Actual = application Actual**;
  project subtotals plus Unassigned equal the same application amount.
  Never add a project subtotal to its constituent task work again.
- Genuine interval start/stop elapsed time, local-midnight and week-boundary
  splits, spring-forward/fall-back DST, and one fixed cutoff for running work.
  Calculation must not interrupt timers or append events.
- Whole-date attribution of dated durations with no fabricated endpoints or
  clock-overlap inference: 12,600 seconds stays on its selected date; 50,400
  seconds on Saturday remains entirely Saturday, not Sunday.
- Effective corrections, work-date movement and deletion without double counting
  prior revisions or losing audit evidence; fractional seconds remain intact.
- Reassignment changes grouping under the current project, not UUID or work;
  selected project/task unions deduplicate by UUID and an empty selection stays
  empty. Partial date windows contain no unrequested work.
- Task daily/weekly/window totals reconcile. Counter resets do not erase
  historical date-based Actual; test current counters separately under their
  existing contract. Unsupported legacy synthetic records must not silently
  become genuine work in the new accounting path.

**Future configurable-week acceptance:** test every selectable weekday with
Sunday as the initial default, consistent weekly reporting/reconciliation, and
preservation of task/day amounts, original events, daily confirmations and saved
export conventions across setting changes. Existing Sunday tests do not establish
this requirement. Allocation-period tests follow adjudicated allocation behavior
when that deferred feature is implemented; limits must never prevent recording.

For current exact renderer/service changes, assert output against supplied seconds.
For replacement decimal rendering, assert the selected displayed-cell sums while
preserving full-precision accounting. Both need authoritative scope/timezone,
partial weeks, Unicode escape reversibility, complete wrapped names, aligned
borders and no repeated chargeable values on continuation rows. Pure generation
and rendering must not mutate inputs/state/files. Evidence registration changes
its intended evidence only, never Actual records, timers or export checkpoints.

## Decimal rendering, export registration and future integration validation

The pure decimal renderer/converter, immutable export-snapshot registration and
verified materialization and read-only file-status evaluation are implemented/staged,
with coverage above. Confirmation preparation/registration/replay is also staged,
while confirmation UI, general file-status/recovery UI and production
integration remain unimplemented.
Apply the selected technical contract to current export services and future integration:

- Exactly two decimal places, integer hundredths and deterministic ROUND_HALF_UP
  conversion without binary-float presentation artifacts. Check the supplied
  3.00, 3.25, 3.33, 1.50, 0.75 and 0.02 examples, halfway boundaries and supported
  fractional seconds; nonzero work rounding to 0.00 retains its Actual and is not
  auto-confirmed as zero.
- Rollups sum rounded task/day cells: three distinct 60-second task/day cells
  display 0.02 each, totaling 0.06, while Actual remains 180 seconds. Project and
  application display both conserve that 0.06, never 0.12 through double counting.
- One calculation/cutoff produces consistent structured cells, frozen labels,
  metadata, exact UTF-8 text and digest before registration. Renderer changes,
  work corrections, renames, regrouping and week changes never alter old evidence.
- Successful durable registration and authoritative verification precede any
  external publication. A snapshot-linked copy contains frozen bytes, not a
  recalculation. Full-byte comparison and digest integrity agree; no success is
  reported for a mismatching file.
- Status-evaluation tests require valid committed journal evidence first;
  unhealthy or uncertain evidence must not become a file-status result. Distinguish
  PENDING (neither explicit nor preferred destination available) from MISSING
  (a destination is selected but no file exists). Neither establishes prior
  publication or an attempted write. READY requires current full-byte/digest
  verification of a suitable regular file; incompatible bytes, digest or object
  type produce CONFLICT, while unsafe or inconclusive inspection produces
  UNVERIFIABLE. An unreadable file cannot retain an earlier READY result.
- Evaluate status per selected destination, preferring an explicit path over the
  frozen preference. After restart, reevaluate without remembering prior
  alternative paths or inferring whether an absent file ever existed. Test these
  semantics without adding persisted completion, publication-history or status
  state. Recoverable registered evidence is broader than PENDING. Matching files
  may be reused, conflicts are never overwritten, and retry at another path
  retains the original snapshot/identity without another export event.
- Ambiguous registration reuses a valid journal event, retries a demonstrably
  absent event only with a healthy journal and the same identity, and fails closed
  on malformed/partial/unknown registration. Derived-snapshot failure does not
  undo valid evidence; restart, archive replay, rebuild and backup/restore retain
  registered exports. Duplicate identities cannot duplicate effective evidence.

Decimal conversion/displayed rollups, journal registration/replay and bounded
materialization/retry and five-status service evaluation have focused coverage.
General file-status/recovery UI, confirmation/reconciliation UI and weekly-summary
assertions remain future expectations, not passing coverage or a mechanism selected by tests.
Preserve exact renderer and legacy assertions. Each foundation requires independent
review before subsequent workflow integration.
Linux fault injection is not power-loss, concurrent-process or Windows qualification.

## Immutable confirmation validation/replay evidence

The staged validator and pure projection implement the exact
[confirmation contract](EXPORT_EVIDENCE_CONTRACT.md#confirmation-event-structure).
Test manual and frozen export-linked absolute cells, canonical identities/dates,
integer amounts, exact fields, preceding task/export evidence and whole-batch
rejection. Expected prior IDs and stale acknowledgements are checked per cell,
including required and forbidden acknowledgement cases. Physical journal order
must prevail over equal or backdated audit timestamps. Exact duplicate identities
cannot reapply earlier values; changed duplicates and cross-type collisions fail
closed. Rejected replay cannot install a partial projection.

Timezone audit metadata tests accept IANA names, fixed offsets, abbreviations and
opaque labels without resolution. Reject invalid types, empty/edge-whitespace
text, NUL/C0/C1 controls and invalid UTF-8. Forbid timezone lookup and network calls;
verify unchanged labels and amounts through replay, archive restart and supported
backup restore. These checks do not qualify timezone arithmetic or offline Windows
timezone-data packaging.

Use isolated persisted fixtures to exercise real startup, archive rotation,
snapshot rebuild and supported backup restoration, retaining immutable earlier
evidence after rename, reassignment or task deletion. Assert detached readers,
Unknown versus zero, unchanged Actual/timers/submissions/exports/file copies and
absence of confirmation data in derived state snapshots. Generic service append
must reject confirmation creation in favor of dedicated registration. Replay tests
alone establish no writer, dialog, concurrency guarantee or reconciliation UI.

The dedicated writer tests cover detached, write-free explicit-cell preparation;
stable UUID/audit/timezone metadata; manual/export-linked absolute amounts and
explicit zero without selection expansion. Check the authoritative journal, not
cached state, on preparation and registration. Reject the entire new proposal for
invalid cells or changed prior identity, including equal amounts. Unrelated-cell
changes may leave a proposal valid. Test exact acknowledgement truth conditions
and deliberate manual amounts without claiming export provenance.

Inject before-write, silent no-op, partial JSONL, complete-write-then-error,
transient/persistent fsync, synchronization/close, rotation-manifest,
post-append inspection and installation failures. Exact identity retry after newer
batches must neither append nor roll back the latest projection. Successful reuse
requires successful fsync/close of all indexed journal segments, active segment
and manifest followed by strict revalidation. Repeated failed synchronization
cannot report success. Model Windows flush access by rejecting actual non-writable
file objects while retaining real opens and fsync; this is portable fault injection,
not native Windows qualification. Verify existing-file writable, non-truncating
access preserves bytes, missing files are not recreated, writable-open denial
propagates, and the close-failure injection is reached before installation.
An unchanged candidate remains retryable once transient failures clear.
Compare surviving bytes, event counts, unchanged prepared inputs and effective
state, including no partial installation. Logical batch
integrity is not filesystem rollback after operational failure.

Exercise writer-created evidence through restart, rotation, rebuild and supported
restore; assert unchanged Actual/timers/export evidence/files/submissions/checkpoints,
no automatic backups and no confirmation state in derived snapshots. Source export
IDs prove frozen provenance, not file readiness; later file-dependent workflows
retain current verification obligations. These fixtures support serialized
single-service use only, not a thread/multi-process transaction claim.

## Export confirmation proposal and selection evidence

Test proposals against real registered exports and fresh strict journal evidence,
including Unknown/zero, frozen duplicate-name identities after later work and
lifecycle changes, complete coverage and canonical row order. Share the replay
stale predicate; exercise first physical occurrences, backdated/equal audit times
and repeated identical export/batch events. Proposal creation must use no clock,
UUID, accounting, rendering, cached readers or external-file inspection.

Test positive-only defaults including already-equal cells; never auto-select zero
or nonzero work rounded to zero. Explicit keys may select zero. Reject malformed,
duplicate/absent selection keys, empty effective selection, invalid proposal shape,
tampered source/name/amount/coverage and selected prior identity/amount/stale changes.
Unselected confirmation changes must remain permissible. Acknowledgements must
exactly match selected stale conflicts; reject missing/extra/duplicate/unselected
or nonconflicting keys and blanket booleans. No inferred acknowledgement or silently
retained subset is valid.

Capture unchanged inputs, service projections and complete dataset bytes for both
APIs on success/rejection. Prohibit writes, sync, backups, projection installation
and file materialization; only final delegation may capture event identity/audit
metadata. Exercise propose/select/acknowledge/prepare followed by separate explicit
registration, checked-only effects, exact six-field cells and unchanged-event retry
after newer confirmations without duplicate append or rollback. Registration must
still reject an intervening selected prior change after preparation. Existing writer
recovery tests retain their scope. These service fixtures do not qualify UI,
production integration, real concurrent writers or Windows interaction.

## POL-R reconciliation evidence and future workflow acceptance

Read-only daily calculation is implemented/staged in
[test_polr_reconciliation.py](../tests/test_polr_reconciliation.py). Validate one
strict journal read and one unchanged accounting request per call, current
confirmation evidence rather than cache, and `None` versus confirmed zero.
Keep every included task/date, including sparse zero-Actual cells with negative
Delta, without widening selection to other confirmations or counting project rows.
Check HALF_UP boundaries and unchanged fractional seconds, selected/deleted and
duplicate identities, fixed running cutoffs, physical confirmation order regardless
of audit time, detached earlier results and errors for invalid evidence/requests.
Capture all dataset bytes and service state; prohibit append, sync, backup,
snapshot writes, rendering and state/cache installation during each calculation.

The connected scenarios in
[test_polr_service_workflow.py](../tests/test_polr_service_workflow.py) exercise
these calculations after real frozen export registration/materialization,
proposal/selection and separate explicit confirmation registration. Default
positive selection leads to 5.00/3.00/+2.00/5.00, then a manual absolute 5.00
confirmation and zero Delta; rotation/restart retains identities, and old-event
retries cannot roll back that value. Checked selection includes explicit zero,
leaves unchecked cells Unknown and yields 2.50/3.00/-0.50/2.50 after correction.
Backup/restore, fresh startup and snapshot rebuild retain the corrected state,
discard subsequent work/confirmation changes and permit rematerialization of
the original frozen bytes. Equal proposed/confirmed 3.00 requires no stale
acknowledgement even when current Actual is 2.50. Captured journal, dataset bytes,
Actual/timer/legacy state and detached inputs/results establish nonpersistent
proposal, preparation and calculation behavior. The registration guard converts
native captured names to relative paths and excludes only the root active journal,
root manifest and paths beginning with the archives component. PurePosixPath and
PureWindowsPath cases exercise this same filter: legitimate journal rotation is
ignored while snapshots, backups, similarly named directories, nested journal
filenames and unrelated additions/removals/changes remain observable. These cases
run on either host and do not establish native Windows execution. Existing fault
suites remain responsible for failure injection; these two service scenarios do
not qualify production interaction, Windows/NTFS, real concurrency or power-loss
durability.

The obligations below come from the product contract. Daily numeric semantics
have staged service coverage; full operator workflows, weekly reconciliation and
presentation remain future acceptance, **not an implemented production workflow**.
Validate Actual, immutable Exported and latest Confirmed POL-R independently:

- Preview has no persistence effect; saving does not confirm external entry.
  Export or confirmation amounts never increase Actual.
- Confirmed values are absolute daily replacements, not additive increments.
  Unknown differs from zero: without confirmation, Delta is Unverified and
  Enter is current Actual. With confirmation, Delta is signed Actual minus
  Confirmed; Enter is the complete current Actual, never the Delta.
- Prior export/confirmation evidence remains immutable after later work,
  corrections, renaming or regrouping. Corrections recalculate Delta without
  rewriting confirmation evidence.
- A stale export cannot silently roll back a newer differing confirmation;
  validate the specific acknowledgement and unchanged values on rejection.
- Full applicable export, checked-cell partial confirmation, defer/reopen and
  manual confirmation without an export work as selected. Unchecked cells
  retain prior values; zero export cells are not automatically confirmed;
  explicit zero is allowed. Frozen export amounts are proposed without retyping.
- Rejected batches do not partially confirm. Audit earlier confirmations and
  exceptional corrections. Export/confirmation never resets or interrupts
  timers; further current-day work remains reportable without day closure.

**Mandatory acceptance sequence:** Actual 3:00; saved export 3:00; additional
work 2:00. Confirm that the earlier exported 3:00 was entered:

| Field | Expected |
| --- | --- |
| Actual | 5:00 |
| Confirmed POL-R | 3:00 |
| Delta | +2:00 |
| Enter in POL-R | 5:00 |

Then confirm the external cell at 5:00: Confirmed POL-R = 5:00, Delta = 0:00.
Keep prior evidence. No timer reset or separate additive 2:00 entry is required.
Also test Actual 3:00 confirmed at 3:00, then corrected to 2:30:
**Delta = -0:30; Enter in POL-R = 2:30**.

No automatic POL-R connection or independent external verification is implied.
POL-R-facing values use the selected two-place decimal contract: displayed Actual
hundredths minus confirmed hundredths gives Delta; Enter is current displayed
Actual. Test 5.00/3.00/+2.00/5.00 and the 2.50/3.00/-0.50/2.50 correction alongside
the original work-time semantics. Unknown still gives Unverified Delta.

Validate whole-batch rejection, duplicate cell keys, invalid references/amounts,
explicit zero and export-linked frozen values. One valid operation appends one
whole batch event. Check optimistic prior-identity changes between proposal and
commit, stale acknowledgements bound to the observed identity and cell-specific
conflict, full/checked-cell parity, deterministic replay and immutable earlier
evidence. No batch changes Actual, exported snapshots or timers.

## Persistence, replay and recovery evidence

For event-backed changes, validate before mutation and compare state, event count
and authoritative file bytes on rejection. Test stable UUIDs, append-only history,
deterministic replay including equal-timestamp read order, effective corrections
and deletions, restart, archive rotation, derived snapshots and reconstruction.
Compare rebuilt projections with authoritative archived and active events.

Exercise initialization through `TaskTimerService(EventStorage(data_dir))`, not
only reads from an already-created storage instance. Test nonexistent/empty
directories, healthy zero-event journals and existing datasets missing either
root journal file, including archived work and registered exports. Capture the
surviving directory entries (including empty directories) and file bytes before
rejected construction; prove no replacements or other mutations occur. Derived
snapshots and unrelated content cannot justify a fabricated fresh journal.
Keep valid explicit backup/restore and subsequent restart coverage separate from
these refusal tests; no automatic recovery or power-loss guarantee is implied.

Validate backup creation and restoration with representative records and audit
history, malformed event envelopes/payloads, partial event writes and meaningful
append/interruption failures. Earlier valid work must not be silently lost.
Assertions must follow approved failure semantics, not invent repair or rollback
behavior. Existing happy-path restart/restore tests do not prove every
interrupted-recovery scenario.

[storage.py](../src/task_timer/storage.py) appends JSONL, flushes/fsyncs,
orders archived/active reads and replaces derived JSON files. The service validates
new project/dated lifecycle and export-snapshot events before append and replay.
The separate staged timed-correction path structurally validates frozen
`interval_edited` candidates and checks prospective effects using existing detached
work replay; legacy interval mutators and replay ordering remain unchanged.
These mechanisms do not establish universal transactional or power-loss guarantees.

Export snapshots and confirmation batches have bounded replay/fault coverage
above, including dedicated confirmation append/interruption, proposal/commit and
recovery synchronization coverage against the
[selected technical contract](EXPORT_EVIDENCE_CONTRACT.md). Export registration
uses the same synchronization requirement for existing-identity reuse and recovery
after append exceptions. Test transient failed append fsync followed by successful
synchronization, persistent failures across unchanged retries, and complete appends
followed by errors. Successful ordinary new appends must not add unconditional sync.
Use actual writable handles and real synchronization where available; assert indexed
archives, active segment and manifest are synchronized without byte changes.
Inject open/fsync/close/inspection and export/confirmation-validation failures;
require no success or installation and preserve original append diagnostics.
Malformed evidence must fail before synchronization-as-repair. Exact reuse must
remain renderer-independent and install the latest complete confirmation projection.
Test installation-failure recovery without another append; compare prepared inputs,
event counts, dataset bytes, Actual/timers, snapshots and external copies. Operational
failure may retain complete/partial evidence; logical integrity is not filesystem
rollback. Timed-correction recovery/reuse also requires synchronization and full
work/export/confirmation reconstruction before installation. Exercise unchanged
endpoints, no-op saves, stale priors, backup gates and prospective replay ordering;
returned registered-but-not-installed/saved warnings must differ from uncertain
outcomes that raise. Historical retries must install current work, not roll it
back, and must not save stale snapshots after installation failure.
Preserve one-event confirmation batch integrity and authoritative journal
precedence over derived snapshots. This strategy defines tests, not another event/schema/recovery owner.

## File publication and cross-resource failures

Current timesheet saving uses complete same-directory staging followed by
no-overwrite hard-link publication; its detailed guarantees and limitations are
in [Design Notes](../DESIGN_NOTES.md#date-range-timesheet-service-staged).
Existing service tests exercise several failures, including write/flush/fsync/
close, publication, concurrent targets and cleanup. They are not a claim of
universal filesystem/platform coverage.

For affected changes, test generation errors before file creation, exact Unicode
UTF-8 bytes and final newline, staging completeness, flush/fsync/close failures,
atomic no-clobber publication, existing files/directories/symlinks (including
dangling links), concurrent destination creation and unsupported operations.
Test original-error propagation and staging-only cleanup before publication;
after publication, cleanup failure must not remove the complete final report or
a concurrent replacement. Capture unrelated files and timekeeping state.

Materializing committed immutable export evidence now exercises the bounded
cross-resource boundary governed by the approved snapshot-first contract. Inject failures
before/during registration, after durable registration but before publication, during derived-snapshot writes,
through staging/publication and during final verification. Validate no external
publication without established registration, retained immutable evidence, stable
retry identity, no overwrite and no false success for byte disagreement. Recheck
externally changed files before status/confirmation use. Backup/restore
interruptions require corresponding recovery evidence where applicable.
The strategy adds no alternate transaction or recovery policy. Staging fsync is
not directory fsync or guaranteed power-loss durability; no such claim follows
from architecture approval or simulated interruption tests.

## Windows desktop and release qualification

Linux service results and mocked UI callbacks cannot independently establish
Windows tkinter interaction, NTFS behavior, PowerShell or PyInstaller correctness.
Use an approved isolated test area for representative real Windows checks:

- Source launch and main-window operation; project/task navigation; timer start,
  stop and switching; real date-only creation/edit/delete when activated.
- Timesheet display/scrolling, keyboard/mouse actions, confirmation dialogs and
  checkboxes, long names, Unicode, errors and cancellation without side effects.
  Check mini-mode where retained by the approved replacement contract.
- Same-directory no-clobber publication on a supported Windows filesystem,
  existing-target protection, meaningful failures and backup/restore.
- Packaged executable launch and operation separately from source launch;
  fresh-data installation and old-data protection under approved cutover policy.

Follow [BUILDING.md](../BUILDING.md) and inspect [build.ps1](../scripts/build.ps1)
and [run.ps1](../scripts/run.ps1). Source launch uses the root launcher; default
packaging produces the full onedir distribution, with optional onefile output.
The build script installs dependencies and removes existing build/dist outputs
(and may recreate a broken venv). Do not run it as a harmless documentation check.

Release qualification follows [Phase 6](ROADMAP.md#phase-6--replacement-release-and-integration):
full Python regression plus end-to-end timer/manual/project/export/confirmation/
correction workflows, persistence/recovery, actual Windows packaging/installation
and protected old data. No critical data-integrity failure may remain; current
documentation and cumulative changelog must agree with the product, and independent
integrated review must support readiness. Tests alone do not authorize release
or merge. No new release scope or allocation requirement is selected here.

## User-data protection

Routine automated tests use disposable temporary directories. They must not
modify `~/.task_timer_data`, delete real records, import old history into the
replacement dataset, change user backups or alter installations outside an
approved test area. Use constructed fixtures or disposable copies for old-data
tests; inspect launcher/data paths before any manual execution.

EventStorage and service construction can create files; do not initialize them
against real data merely to investigate source. Eventual replacement validation
must cover fresh initialization, the approved selected path, old-data protection,
no unauthorized migration, backup/recovery and replacement failures. Exact
installation cutover remains Open; this document does not choose it.

## Commands and evidence classification

[pyproject.toml](../pyproject.toml) requires Python 3.11+, configures pytest's `src`
import path and quiet output. Existing tests establish the paths below.
Use the appropriate existing interpreter and dependencies. Commands are examples
to select by applicability, not a universal per-task checklist.

**Source-grounded command examples:**

These examples are supported by repository configuration and existing test paths;
their presence does not imply that they have passed.

```bash
.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts=''
.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/test_mixed_accounting.py tests/test_time_utils.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/test_timesheet_service.py
```

The first is full regression; the others are focused examples, not coverage of
every affected dependency. Select additional existing paths for the actual change.
Applicable Python syntax validation can compile changed source/test bytes in
memory without importing the application or writing bytecode, for example:

```bash
.venv/bin/python -B - <<'PY'
from pathlib import Path
for filename in ("src/task_timer/accounting.py", "tests/test_mixed_accounting.py"):
    compile(Path(filename).read_bytes(), filename, "exec")
PY
```

This example checks syntax only; it does not execute application behavior.
Use it when syntax validation is applicable and select paths according to the
changed files; no new runner or fixture is required.

**Documentation validation:** applicable checks may include reviewing the actual
Markdown diff, checking whitespace and formatting, verifying relative links and
anchors, confirming changed-file scope and current-state consistency, and
confirming executable content remains unchanged. Select checks proportionally;
no fixed command checklist is required. Report actual results in the task receipt,
not an accumulating validation ledger.

**Windows-specific applicability:** Windows launch and build procedures are
documented in BUILDING. PowerShell packaging requires an appropriate Windows
build environment. Assess availability for each actual execution; Linux results
do not establish Windows compatibility. Source launch is not packaged executable
validation, and a successful build alone does not prove installation or GUI
workflow correctness.

**Historical test evidence:** an earlier passing result may be cited as historical
or carried-forward evidence only with an appropriate applicability judgment.
It must not be reported as a newly executed test. Do not invent CI commands,
numeric coverage thresholds or Windows results.

## Reporting and maintenance

For applicable validation, report the behavior/guarantee, exact commands actually
executed, results, relevant environment, material failures, checks not run with
reasons and remaining unsupported claims. Environment detail should explain the
claim's limits (for example OS, timezone/cutoff or filesystem when relevant).

Distinguish **Current execution**, **Historical evidence**, **Carried-forward
evidence** (earlier results whose applicability to unchanged behavior was assessed)
and **Not run / Unavailable**. Carrying evidence forward is not running it again.
No new standalone ledger is required: receipts, inspected existing tests and
targeted review are acceptable evidence sources.

Reconcile this strategy and related owners when approved behavior or actual
validation capability changes. Keep expectations separate from implemented
coverage and results. Export/confirmation, consistency/recovery and decimal rules
are selected in their technical owner, not implemented by this strategy.
Allocation details, first-release inclusion and replacement cutover remain with
user/ChatGPT adjudication; POL-R backend facts remain Unverified. Testing governance
alone does not complete roadmap Phase 1 or qualify the release.
