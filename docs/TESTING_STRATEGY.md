# Chronicle testing strategy

This document owns validation expectations, applicability, evidence requirements
and release-validation boundaries. It does not select product behavior,
architecture, persistence/recovery mechanisms or a new release policy.

The [product contract](TIMESHEET_REQUIREMENTS.md) owns acceptance semantics;
the [roadmap](ROADMAP.md) owns sequencing and completion gates;
[ARCHITECTURE.md](ARCHITECTURE.md) owns the selected Tkinter/SQLite target;
[Design Notes](../DESIGN_NOTES.md) owns retained unshipped JSONL source/limitations. [AGENTS.md](../AGENTS.md) routes repository work;
[README.md](../README.md) describes status; [BUILDING.md](../BUILDING.md) owns
Windows packaging instructions; [CHANGELOG.md](../CHANGELOG.md) is the sole
historical change record. Tests are evidence, not independent product authority.
An expectation below does not establish an existing test or a passing result.
Export/confirmation tests follow the selected
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md), the sole technical
owner of frozen evidence, decimal, verification/recovery and batch semantics.
SQLite transaction mechanisms belong to ARCHITECTURE, not legacy JSONL replay.

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

## Connected SQLite timer evidence

The Stage 1A suites below exercise the shipped `chronicle` source with disposable
SQLite datasets. This inventory describes assertions, not an automatic passing
result or native qualification; current command outcomes belong in receipts.

| Suite | Exercised boundary |
| --- | --- |
| [test_schema.py](../tests/rewrite/test_schema.py) | Real STRICT/FK/CHECK/UUID constraints, profile/version gates, fresh/reopen/refusal, immutable evidence, active/closed guards and pre-COMMIT orphan postcondition. No hostile database guarantee. |
| [test_services.py](../tests/rewrite/test_services.py) | Independent UUID task/project operations, atomic same-instant Switch/rollback, exact receipt reuse before stale checks, changed-content rejection, bounded busy, failed COMMIT with open transaction, failed rollback/close, independent committed lookup, lost acknowledgement, unverified retry and immutable active-start audit/precision/DST behavior. Injected failures are not universal power-loss evidence. |
| [test_timekeeping.py](../tests/rewrite/test_timekeeping.py) / [test_accounting.py](../tests/rewrite/test_accounting.py) | Integer microseconds, range/type/canonical-date rejection, bundled IANA rules, gaps/repeats/non-hour transitions, local midnight/week, running cutoff, own/deleted work conservation, sleep/forward elapsed and impossible-observation warnings without refresh writes. No dated writer or quarter-hour implementation. |
| [test_worker.py](../tests/rewrite/test_worker.py) / [test_bootstrap.py](../tests/rewrite/test_bootstrap.py) | Worker-thread connection lifecycle, exact reconciliation, startup failure, actual separate-process exclusion/ordinary directory aliases, committed active restart and abrupt process exit. Native alias cases skip narrowly where unsupported. Process tests are bounded examples, not hostile/multiwriter qualification. |
| [test_app.py](../tests/rewrite/test_app.py) | Actual main/mini construction and callbacks with real services/worker; server-delivered X11 task selection/buttons, Start/Switch/Stop, active-start correction, shared totals, slow-worker event delivery, duplicate guards and queued shutdown. Correction cases retain exact drafts/occurrences across real service validation, stale conflict, injected COMMIT rollback and pre-execution unavailability; queued work locks Close/fields, unchanged writes nothing, and unverified editor-local retries retain the same Request through absence/committed lookup. Dispatch tokens reject duplicate completions; unexpected view destruction retains owner evidence. Server-delivered keyboard/mouse cases cover rejection-to-success, repeated selection, blocked main/mini, Escape, editor Retry and the actual toolkit default-No exceptional-exit warning. WM Close is separately exercised through its registered handler. Known completion survives numeric/cleanup failure; cancellation/confirmed exit, read purity and late-result handling remain covered. Repeated-interpreter test cleanup is UI-thread-owned; doubles alone do not establish desktop interaction. |
| [test_packaging.py](../tests/rewrite/test_packaging.py), [test_root_launcher.py](../tests/test_root_launcher.py) | Replacement-only root import, package selection/exclusion and spec tzdata collection. Static/import checks are not a native executable build. |

A usable display is required for `real_tk` cases. Linux Xorg/XTest evidence does
not establish native Windows, NTFS, suspend/resume or package usability. SQLite
feature floor 3.37 is distinct from the supported WAL-reset-fixed runtime floor
3.51.3 (excluding withdrawn 3.52.0); source tests record the actual linked build.
Operational interruption and native Windows source/onedir evidence remain the
next Stage 1 slice. Core History, dated writers and Timesheet/POL-R are later work.

## Retained legacy test inventory and limits

The following inventory describes existing test cases and their scope, not
exhaustive coverage or passing results. These are tests of retained, unshipped
Tkinter/JSONL source, not SQLite transaction/worker/inline-editor evidence.
Old names containing “replacement” or “staged” do not make them rewrite delivery.
Retain useful semantic cases, but do not require JSONL replay/synchronization,
constructor waits or widget-retained retries in the new architecture. Use it to find affected tests and inspect
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
| Production Actual displays | [test_actual_readers.py](../tests/test_actual_readers.py): real isolated services through application/mini refresh, own task values, deleted work in application totals, full Sunday calendar weeks, future dated amounts, cutoff-capped timed work, fractional seconds, DST/midnight rollover, effective corrections/redating/deletion, reset/confirmation independence and single-observation handoff. Faults cover clock/date/accounting/malformed numeric/formatting/synthetic failures, unavailable presentation, original diagnostics, continued cadence and recovery with Start/Stop. Captures and prohibited writes protect domain/settings purity. Separate real-Tk construction and server mouse input cover minimum-size columns, headlines, mini opening, Start/Stop and failure recovery; Linux Tk is not native Windows or full writer/export workflow qualification. |
| Mixed work history | [test_work_history.py](../tests/test_work_history.py): real isolated service/model projection, exact detached row shape, mixed entries, known deleted-task lookup, inclusive/All dates, date direction with stable within-day chronology, linked daily identity/continuations, midnight/DST/fixed offsets, running cutoffs, whole dated amounts, correction/redating/deletion/restart, reset/confirmation independence, synthetic refusal and per-day accounting agreement. State/event/snapshot/file comparisons and prohibited journal/write/clock/UUID calls cover purity on success and rejection. No production timeline, edit/delete handler, sort-preference or audit UI qualification. |
| Mixed-history table | [test_work_history_view.py](../tests/test_work_history_view.py): actual constructor/callbacks with widget doubles and real isolated service rows, exact order and detached complete metadata, midnight dates, DST/repeated-hour offsets, fixed/non-hour zones, running boundaries, precise retained amounts and completed-minute display, task-scoped related highlighting, stale handles, replacement/empty results, preparation failure preservation and widget-update invalidation/explicit recovery. Prohibited service/file/settings/clock/scheduling calls and dataset/state comparisons cover purity. Separate real-Tk smoke exercises construction, mapping, selection/highlighting, replacement and failures when a display is available; otherwise it skips with a reason. Component coverage alone does not qualify production routing or native Windows. |
| Single-task history browser | [test_work_history_browser.py](../tests/test_work_history_browser.py): real isolated reader/table composition with constructor/callback doubles, exact load arguments and clock counts, seven week starts, rollover/UTC-local/DST boundaries, mixed and future dated work, inclusive Custom/All, running cutoffs, Apply-only typed/calendar drafts, seed/cancel/disposal, stable local sorting without newer records, committed Custom refresh, initial failure versus valid empty history, clock/service/preparation/widget faults, recovery and state/file/settings/timer/scheduling purity. Separate real-Tk smoke uses actual Calendar selection/cancellation, focus changes, Apply, Date-heading invocation, Refresh, errors and replacement. These tests do not qualify production window ownership, workflows or native Windows. |
| History session direction | [test_history_session_direction.py](../tests/test_history_session_direction.py): actual application constructor with unrelated startup isolated, newest-first initialization before controls independently of settings, factory using explicit task/service, post-render single notification, sequential task/dataset handoff, closure retention and new-owner reset. Actual browser/table doubles exercise preparation/widget failures, callback rejection before construction/loading, completed-sort notification failure, and unchanged cutoff/drafts/domain/files with no sort-time reader/clock/settings writes. Separate real-Tk smoke covers sequential construct/sort/destroy/reopen; it does not qualify production routing or enforce the Selected single-history-window rule. No cross-restart persistence is Selected. |
| Owned modal history window | [test_history_window.py](../tests/test_history_window.py): actual wrapper/browser composition with isolated services, initialization before controls, withdrawn construction, ownership before waiting, same/different-task duplicate and reentrant rejection, construction/presentation/grab cleanup, inline initial-load recovery, stale/child callbacks, idempotent close, external/root destruction, calendar disposal and sequential task/dataset session handoff. Prohibited domain/settings writes and captured dataset/timer state cover purity. Separate real-Tk cases exercise local modal wait/grab, server-delivered X11 mouse input blocked at the main window while history/calendar controls remain usable, Apply-only mouse selection/cancellation and picker Escape, normal scheduled event processing, open-calendar Close/root shutdown, actual-widget failure cleanup and reopening. These cases require a usable test display; widget doubles do not substitute for missing real-Tk evidence. This shell suite alone establishes neither native Windows interaction nor shipped command wiring; the access suite covers the latter. |
| History modal return | [test_history_modal_return.py](../tests/test_history_modal_return.py): root-default/explicit parent identity, rejection before loading of invalid parents and unrelated/global grabs, guard protection through restoration after ownership cleanup, captured-grab/focus return, no invented/redundant grab, dead/outside focus fallback, competing grab preservation, visibility-time conflicts, destroyed origins and primary/cleanup/restoration diagnostics. Actual helper/shell/browser composition uses isolated datasets. Real-Tk cases drive the helper from actual task and recursive subtask editors, preserve unsaved name/note/tag drafts, selection/flags and work/timer state, exercise server-delivered ancestor-input blocking, calendars, ordinary focus/local-grab return, destruction and session sorting. Reused Tcl paths do not revive destroyed focus widgets. Desktop focus-return evidence requires a working window manager as well as a display; bare Xorg is not equivalent. The separate access suite covers production control wiring. No legacy-data compatibility or native Windows qualification. |
| Work History access | [test_history_access.py](../tests/test_history_access.py): constructed selected-task control/enablement, exact application adapter and required recursive editor callback, origin-local inline launch diagnostics with original exception/traceback/notes, selection-change clearing and destroyed origins. Real-Tk cases drive actual main/editor/nested controls with server-delivered input, one shared owner, session sorting, linked mixed rows/precision, calendars, Apply/Refresh and error recovery, blocked ancestors, modal return, retained drafts/flags/selections, timers and dataset purity. Unsupported synthetic evidence stays a visible browser failure without fallback. Real-Tk evidence needs a display/window manager and does not qualify native Windows, installation/cutover or the remaining replacement writer/editor workflow. |
| Reset UI removal | [test_reset_ui_removal.py](../tests/test_reset_ui_removal.py): constructed task controls/menus expose no Reset commands; real-Tk server-input coverage preserves Start/Stop and Work History. Superseded full/selected-export post-action assertions are retired with that UI. Connected frozen export/no-Reset evidence now belongs to the Timesheet access suite. Backend reset, replay, accounting and audit coverage remains applicable; no production POL-R or native Windows qualification. |
| Rendering | [test_timesheet_renderer.py](../tests/test_timesheet_renderer.py): scope, partial/multiple weeks, calendar boundaries, exact durations, duplicate identity, wrapping/geometry and Unicode escaping. |
| Decimal rendering | [test_decimal_timesheet_renderer.py](../tests/test_decimal_timesheet_renderer.py): ROUND_HALF_UP conversion/boundaries, invalid numbers, task/day rounding and displayed-rollup conservation, selection/identity, partial/multiple weeks, calendar edges, Unicode wrapping, purity and exact/legacy byte compatibility. This is a pure staged renderer, not export-evidence persistence. |
| Frozen timesheet preview | [test_timesheet_preview.py](../tests/test_timesheet_preview.py): actual frame/callbacks with widget doubles and real isolated snapshot preparation, one explicit cutoff/calculation, This week/Last week boundaries and inclusive Custom, independent UUID selection/duplicate names/deleted work, mixed/fractional/decimal cells, exact frozen text/digest, detached getter and later-work/correction/rename/group changes. Covers immediate draft invalidation/backtracking, empty All versus empty Selected, invalid dates/clocks, preparation/synthetic/render failures, original diagnostics and explicit recovery, picker seeds/cancel/disposal and prohibited durable operations with dataset/state comparison. Separate real-Tk mouse/widget cases exercise checkboxes, typed drafts, Calendar selection/cancellation, read-only report, readiness and failure recovery. Readiness transition/observer-failure and locking evidence is extended by the Save suite; the preview itself has no registration/file effects. No production routing, native Windows or dated-writer qualification. |
| Standalone frozen Save/retry | [test_timesheet_save.py](../tests/test_timesheet_save.py): real isolated preparation/registration/materialization through actual components, readiness/dialog gates, exact frozen bytes/digest/event/cells, unchanged explicit-destination handoff, same-identity retry after absent/ambiguous registration and persistent synchronization failure, no publication before verified registration, conflicts/alternate destinations, matching-copy reuse and post-publication failure. Covers newer work/confirmation preservation, reentry, preview locks/readiness notifications, detached handoff, cancellation, completion/presentation failure and no incidental work/settings/snapshot/submission/checkpoint changes. Separate real-Tk server-input cases exercise enablement, draft invalidation, cancellation, locked retry and completion; dialogs are doubled. This is one ephemeral operation per instance, not by itself production routing, general recovery UI, restart/power-loss or native Windows qualification. |
| Explicit frozen overwrite | [test_timesheet_overwrite.py](../tests/test_timesheet_overwrite.py): real materialization and Save callbacks, typed stable-content eligibility versus unsuitable/inconclusive inspection, default-cancel owned confirmation and reentry, one-call authorization, ordinary Retry/alternate-path protection, exact frozen bytes/digest and registration-before-publication. Covers matching reuse, absent-target exclusive creation/races, direct dataset protection and capability-dependent symlink aliases, real target changes and deterministic same-size/restored-mtime rejection using injected change time at the final target recheck, staging/write/flush/fsync/close/replace faults, consumed/foreign staging cleanup, ambiguous/known post-replacement failures and unchanged-input retry with newer work/confirmations. Native FIFO/symlink setup skips only absent APIs or recognized permission/unsupported-operation restrictions; portability regressions retain unexpected failures and verify symlink setup precedes materialization. Separate real-Tk server-input cases exercise Overwrite/Retry/alternate controls and completion; confirmation/file-dialog decisions are doubled. No native Windows, hostile-directory, concurrent-process, power-loss or production-routing qualification. |
| Owned production Timesheet | [test_timesheet_window.py](../tests/test_timesheet_window.py) and [test_timesheet_access.py](../tests/test_timesheet_access.py): actual application ownership and accepted component composition with isolated services, no preparation on opening/reopening, single ownership/reentry, frozen registration/publication, exact same-instance unfinished-attempt retention, cancellation, registration uncertainty, file conflict/Overwrite, post-publication failure and completion despite presentation failure. Covers retained presentation failure, stale/child destruction callbacks, cleanup diagnostics, explicit recovery, exit warning precedence/default cancellation/busy guards, unchanged work/timers/earlier evidence and no automatic reminder/settings/submission/checkpoint/delete/reset effects. Constructed toolbar/File/banner/close-reminder wiring replaces the retired dialogs and dispatch. Actual monthly reminder controls exercise already-presented Return/Open/Close before Save and after verified Save, unchanged frozen data/files, reentrant callbacks, cancelled unfinished-exit grab return, local/global competitors, destroyed/stale widgets, focus fallback and original/secondary restoration diagnostics. Separate real-Tk server-input cases exercise production controls, main/mini blocking, calendars/picker Escape, normal scheduled events, withdrawal-aware modal wait, retained reopening, Overwrite and root shutdown. Already-presented monthly round trips use the actual reminder, root-close protocol and server-delivered Return/Open/Close controls before/after successful Save, checking restored local ownership, main/mini input blocking and ordinary Timesheet interaction. Focus assertions depend on the available window manager separately from grab/input evidence; doubles cover represented global grabs and fault injection. File/confirmation decisions may be doubled. Session resumption is not crash/restart recovery, and Linux Tk is not native Windows/NTFS or release qualification. |
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
| Retained service regression | [test_exporter.py](../tests/test_exporter.py), [test_timeline_corrections.py](../tests/test_timeline_corrections.py), and neighboring tags/subtask/template/selected-export tests protect unchanged service/accounting and export behavior during staging, not a replacement compatibility commitment. Legacy submission/checkpoint tests are not proof of replacement POL-R semantics. |
| UI and launch routing | [test_app_ui.py](../tests/test_app_ui.py), dialog/window tests and [test_root_launcher.py](../tests/test_root_launcher.py): callbacks, formatting and routing; some construct fake roots, SimpleNamespace widgets or instances without real GUI initialization. They do not establish real Windows desktop usability or packaged execution. |

Existing fixtures use disposable `tmp_path`, fixed clocks and real service
composition where applicable. The accepted historical Phase 2 service gate is
JSONL-only; no test in this inventory completes a SQLite stage. Retained JSONL source
has main/mini Actual, read-only History and frozen Timesheet; dated writers,
confirmation/reconciliation UI, weekly reminders and selected week settings are
not active. Retained nested-editor modal tests protect that old source,
not a requirement to reproduce that navigation in the rewrite. Existing JSONL
confirmation/proposal/reconciliation suites use arbitrary integer hundredths and
Actual-as-Enter, not the new quarter-hour policy. Their integrity assertions are
useful predecessor evidence; they do not establish SQLite or weekly-allocation
implementation. Task 1b adds future obligations below, not passing runtime tests.

## Rewrite evidence by stage

Stage 0's documentation gate is independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`; this supplies no SQLite/runtime evidence.
The rows below are stage acceptance obligations, not automatic passing results.
Stage 1A implements and tests the connected timer on `feature/chronicle-rewrite`;
operational/native Windows qualification remains pending, so Stage 1 is not Complete.
Tests follow the user-selected [architecture](ARCHITECTURE.md) and
[semantic contract](EXPORT_EVIDENCE_CONTRACT.md); they do not choose stronger
recovery/platform policy. Integrity tests begin in each slice, not only Stage 4.

| Stage | Applicable evidence |
| --- | --- |
| 0 authority | Review complete affected Markdown/current source, all material decisions, current/target separation, incoming relative links/anchors and executable scope. No runtime delivery from documentation. |
| 1 foundation | Real SQLite recording/reopen, stable task/project IDs, one active timer, atomic Switch at one accepted time, rollback on rejected use cases, exact request reuse before stale checks and changed-content rejection. Verify actual WAL/FULL/foreign-key/constraint behavior, bounded lock failure and truthful commit uncertainty. Early native Windows onedir smoke includes SQLite runtime and offline zone availability. Approved continuous sleep/restart, explicit active-start recovery and uncertain-exit rules now have Stage 1A assertions; native operational qualification remains pending. |
| 2 recording | Integer-unit mixed accounting, genuine/date-only shape integrity, stable work UUID/revision/current references, correction/deletion history, no-op purity, stale drafts, whole-entry segment editing, precise unchanged endpoints, minute changes, DST/UTC, all week starts, applied periods/unapplied drafts/session sorting and all-reader gate before exposed writers. |
| 3 Timesheet AND POL-R | Connected frozen preview/full-week quarter-hour suggestions and saved-report recovery; explicit whole/checked/manual absolute quarter confirmations, complete reviewed source, exact acknowledgements, Unknown/zero, stale priors, daily gaps/adjustments/coverage and reminders. External reporting/zero-entry validation before affected official use. No pilot without these. |
| 4 stabilization | Integrated interruption/commit ambiguity, second-instance refusal, queued shutdown/restore invalidation, real backup/restore, upgrades, storage faults, native Tk and packaged Windows. Earlier slices already test their integrity boundaries. |
| 5 complete core pilot | Fresh representative reporting week: timer/manual/correction, full/partial frozen quarter-hour exports, whole/checked/manual/zero/Unknown confirmation, explained rounding, daily allocation agreement/coverage, reminders and restore without workarounds. External redistribution and zero-entry treatment validated; independent review/native evidence, not a timer-only pilot. |
| 6 optional | Only adjudicated allocation/convenience/external integration outcomes. No optional limit blocks Actual; core POL-R is already complete. |

## Accounting and revision guarantees

Compare integer microseconds, not formatted values or float sums. Exercise:

- Independent task UUIDs and duplicate names, current-project/Unassigned grouping,
  retained deleted-task amounts and task/application conservation without double
  counting project subtotals or descendants.
- Midnight, month/year/week boundaries, spring/fall DST, non-hour transitions,
  explicit IANA/offline zones, range limits and a shared main/mini running cutoff.
- Whole-date amounts, including a 14-hour Saturday and later dates within the
  containing week, with no fabricated clock overlap or audit-date attribution.
- All seven week starts, Sunday default and setting changes preserving work dates,
  daily confirmations and original saved export conventions.
- Stable work UUID across edits, expected-revision conflicts, exact preserved
  unchanged seconds/fractions, no-op/comment-only purity, positive same-minute
  spans, explicit repeated occurrences and nonexistent-time rejection.
- Correction/redating/deletion changes effective work and current totals while
  older revisions, exports and confirmations remain immutable.
- Read/render purity and one observation for main/mini; errors display unavailable
  values without disabling normal Start/Stop or creating synthetic zero work.

Do not reproduce replay/accounting in tests. Use independent expected examples
and real use cases/transactions, with snapshots of authoritative facts before
and after rejected or read-only operations.

## SQLite, requests and recovery evidence

Use disposable real databases, actual transactions and independent reopen reads.
Test current rows, immutable revision/batch cells, current references and receipt
committing together or not at all; constraints/foreign keys must actually reject
invalid shapes. Do not infer transaction integrity from mocked adapter calls.

Inject failures before commit, uncertain commit/response delivery, and after
commit before UI refresh. Reconcile the same request ID/content authoritatively;
exact old retries after newer work/confirmations return the original result
without rolling back current state. Changed content under the same ID rejects.
Unchanged edits create no revision/artificial receipt. A committed mutation remains
committed when rendering fails or its view closes. Do not use a global pending
slot, new request ID or visible widget/file as authority for uncertain results.

Verify one worker owns its connection and database/file I/O, no arbitrary sharing
or `check_same_thread=False`, and bounded lock handling. Test supported SQLite
backup captures committed WAL contents, independently validates, restores and
reopens all work/export/confirmation history. Do not test a live main-file copy
as a valid backup. Protect future rewritten-data schema upgrades and reject
unsupported versions truthfully. No legacy import/compatibility fixture obligation.
Linux fault injection does not prove arbitrary concurrent-writer, power-loss or
native Windows/NTFS safety.

## Tk thread, interaction and lifecycle evidence

Construct actual controls and exercise completion wiring as well as doubles.
Instrument **all** Tk calls, including Variable access, `after`, focus and destroy,
to remain on the UI thread; worker results travel only through queues. Exercise
the single bounded UI result drain, stale refresh coalescing, delayed/out-of-order
responses, session invalidation after restore and owner reconciliation after view
closure. Slow I/O must not prevent timer display/event processing. The drain must
not create work, replay journals or become another projection authority.

Constructors must construct only; explicit presentation/completion callbacks must
not use app-authored nested mainloops, `update` loops or blocking modal sequencing.
Test normal local modal ownership with timers continuing and main/mini input
blocked; inline History editing returns to the same task/period/drafts/direction.
Cancel/no-op writes nothing; validation/conflict preserves drafts. No selection
or unsupported row can authorize a write from text/temporary widget handles.

Separate real-Tk server-delivered mouse/keyboard evidence from doubles/direct
`invoke()` calls. Exercise History inline fields, calendar select/cancel/Escape,
Timesheet Preview/Save/overwrite/confirmation, modal input blocking and legitimate
focus/grab return. Short toolkit/native dialogs may internally wait; test explicit
parents, reentry guards, destruction and competing local/global ownership without
stealing it. Focus claims requiring a window manager differ from local-grab checks.
No global modal registry or polling workaround is selected.

Shutdown rejects submissions while queued work drains/reconciles, keeps UI event
processing alive, and closes connection/worker without UI-thread joining a
running worker or silently killing it. Root/view destruction and later results
must neither hang nor install stale state. Tests cannot choose still-Open abnormal
clock/restart or dataset-timezone-change behavior.

## Frozen exports and core POL-R workflow

These are **future tests**, not tests written/run by this documentation task.
Follow the single [precision/allocation owner](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation)
without duplicating accounting or approving policy through assertions.

### Exact weekly submission and scoped evidence

- Keep integer-microsecond Actual, displayed Actual hundredths and suggested/
  confirmed quarter counts distinct. Verify Actual HALF_UP ties and cell-summed
  displayed rollups independently of weekly submission. No floats or daily decimal
  rounding feed the target. Invalid negative/bool/float/overflow inputs reject;
  manual non-quarter decimals cannot silently become valid confirmation.
- Exercise mandatory C–G with independent expected outputs: exact weekly total,
  upward +14-minute adjustment, no carryover, small equal remainder with earlier
  date winning, and exact quarters. Zero week yields zero; positive sub-minute
  work can yield one quarter, but zero-work dates never receive it. Check allocation
  conservation, no more than one remainder extra per date, deterministic ties and
  integer precision/range boundaries, including target/converted-unit bounds.
- Check all seven week starts, UTC/local date differences, midnight/DST and non-hour
  transitions using existing work attribution. Validate one explicit observation,
  running cutoff and existing future-dated amounts without predicting a stop.
- Multiple tasks receive independent ceilings; project membership/other tasks
  cannot change a task's distribution. No cross-week transfer or retained residual.
- This week/Last week and inclusive Custom always use full intersecting weeks.
  Tuesday-only case C still shows 1.00, not a Tuesday-only ceiling. A Custom range
  crossing two weeks computes them independently; visible subsets need not sum
  to full targets. Never publish/confirm out-of-scope cells, even though frozen
  proof retains their contextual basis. Reject unrepresentable expanded boundaries.
- More work in an incomplete week may change suggestions. Correction/deletion may
  reorder remainders and change other dates of that task/week. Fresh preview updates
  current suggestions; old export context/cells/text/digest and all prior confirmed
  values/identities remain unchanged. Show resulting mismatches, not automatic
  confirmation redistribution, new work or cross-week carryover.

Check complete exact/displayed Actual, suggested quarters, full-week source basis,
cutoff, timezone/week convention, scope and historical labels from the reviewed
candidate. Display Actual and suggestion separately. Save never recalculates;
commit snapshot/cells/receipt before publication; reconcile uncertain commitment
before publishing. Recover a saved report without its old widget or current Actual.
Retain readable names, duplicate UUIDs, Unicode escaping, safe partial-week layout,
draft invalidation/backtracking, valid empty All versus invalid empty Selected.

### Restored confirmation integrity

Use actual SQLite services/transactions when implemented, not independent mock
selection logic. Inspect useful predecessor cases in
[test_polr_confirmation_proposals.py](../tests/test_polr_confirmation_proposals.py),
without inheriting JSONL mechanics or arbitrary hundredth inputs as target policy.

- Whole-report default is every positive **frozen suggestion**, including already-
  equal confirmed values. Positive Actual with zero suggestion is not default-
  selected. Explicit checked zero is allowed; explicit empty never means All.
  Unchecked cells retain Unknown or prior absolute confirmation unchanged.
- Validate complete canonical source identity/scope/association and every frozen
  task UUID/date/name/suggested-quarter row, **including unchecked rows**. Reject
  missing, extra, duplicate, substituted, reordered or tampered coverage. Context
  outside report scope is not selectable. Reject malformed/foreign/duplicate keys.
- Acknowledgements must be exactly the selected newer-differing-source conflicts.
  Reject missing, extra, duplicate, unselected, nonconflicting and blanket consent,
  including malformed types. Bind consent to task/day, frozen count and reviewed
  prior identity; no automatic consent from a proposal flag. Manual confirmation
  requires no source-export acknowledgement but checks current prior.
- Revalidate selected prior identity/amount/stale classification in the committing
  transaction. An intervening equal-value confirmation is stale review. Reject the
  entire batch, not a subset. Unrelated newer **unchecked** confirmations need not
  invalidate checked selection when complete immutable source remains exact.
- Confirm older exports from frozen **suggested quarters**, not current Actual or
  legacy Actual decimals. Test source precedence by committed SQLite ordering,
  not audit timestamps/UUID/physical JSONL order. Deferral/later review writes
  nothing until explicit confirmation and renews prior review.
- Batch/cells/current references/receipt commit atomically. Exact old-request reuse
  returns its committed result before stale checks without reapplying old values
  after newer confirmations; changed contents under one identity fail closed.
  Unknown commit retains the exact request. No immutable export/work/timer/file
  changes result from confirmation; no added work or automatic external update.

### Reconciliation, coverage and operator evidence

Retain compatible cases A/B: 5.00 Actual / 3.00 Confirmed / Daily Delta +2.00 /
Suggested 5.00, then explicitly confirm 5.00 for suggested-entry gap 0.00; correct
Actual to 2.50 against 3.00 for Daily Delta -0.50 / Suggested 2.50. These do not
validate arbitrary decimal POL-R entries. Unknown gives Unverified Daily Delta
and unresolved gap, never zero. Explicit zero retains identity.

Test expected nonzero Actual-minus-Confirmed differences when quarter allocation
matches confirmation, known allocation mismatch despite equal weekly totals,
incomplete review/confirmation coverage, explained exact weekly adjustment and
stale current proposals. Full-week adjustment must not be inferred from partial
visible totals. No persisted Delta/rounding balance. Case F's worked Tuesday with
0.00 suggestion stays Unknown until explicit valid review; no automatic zero or
claim of complete reconciliation. External zero/omitted-entry behavior needs
validation before affected Stage 3 official workflow and pilot. Simulated external
interaction/math tests do not establish employer/customer redistribution approval.

Real-Tk future workflow evidence must distinguish Actual/Suggested/Confirmed,
Daily Delta/gap/adjustment/coverage and frozen versus current proposals. Exercise
whole/checked/manual confirmation, zero, defer/review, stale errors, fresh preview
and correction-induced changes through actual controls, with exact retry/no false
success. Doubles do not establish native operator interaction. Required reminders
check previous week every used local day including restart/rollover/absence and
current week Friday/Monday; don't hide daily mismatch/Unknown in a weekly net.
Open/Save never confirms/dismisses; external unavailability does not block Actual.
These are mandatory Stage 3/core pilot gates, not optional allocation budgets.

## File publication and cross-resource failures

Validate the selected file contract with committed SQLite evidence: matching-copy
reuse without rewrite, absent-target exclusive publication, complete same-directory
write/flush/fsync/close/ownership, final byte/digest verification and staging-only
cleanup. File failures cannot undo a database commit or falsely claim no file
exists. Exact saved-report retries remain independent of later Actual/labels.

Ordinary Save/Retry cannot overwrite. A typed stable regular-file content conflict
alone offers explicit one-call default-cancel overwrite. Test cancellation/reentry,
dataset tree/alias protection, final target metadata/identity checks, `os.replace`
failures and postpublication diagnostics without rollback/deleting output.
Status is freshly derived per destination; no persisted READY/history registry.

Native FIFO/symlink cases remain capability-dependent with narrow setup skips,
not evidence that a service rejected an object that setup failed to create.
Current [overwrite tests](../tests/test_timesheet_overwrite.py) include deterministic
same-size/restored-mtime evidence injecting changed change-time only at the actual
final recheck. Preserve that distinction from native filesystem evidence; do not
assume Windows creation/change-time semantics or claim detection when every
compared observation is unchanged. Unexpected errors remain failures.
Bounded observations are not atomic compare-and-replace, hostile-directory safety
or universal power-loss proof. UI consent cannot make an unreadable/unstable or
unsuitable target safe.

## Windows desktop and release qualification

Native Windows is required for applicable desktop, filesystem, PowerShell and
packaged qualification. Early Stage 1 onedir smoke starts this evidence, not final
qualification. Test actual SQLite profile/runtime, bundled offline timezone rules,
main/mini controls, inline History, Timesheet/POL-R confirmation, reminders,
publication/overwrite, backup/restore and queued shutdown. A package that starts
but omits core POL-R is not a qualified pilot.

Inspect [BUILDING.md](../BUILDING.md), [build.ps1](../scripts/build.ps1),
[run.ps1](../scripts/run.ps1) and metadata before selecting commands. Current
scripts build JSONL source and install dependencies/remove build outputs; do not
run them as a documentation check. Linux Tk results do not establish Windows Tk,
NTFS, packaging or installation. Source and packaged checks are distinct. No
release/merge approval follows from a successful build/test run alone.

## User-data protection

Use disposable temporary datasets only. Do not initialize services against
`~/.task_timer_data`, read actual user settings for source investigation, import
old history, delete user files or change installation paths. Fresh rewrite scope
removes migration/compatibility obligations, not data protection. Exact release
cutover/cleanup remains Open; future new-runtime backup/restore/upgrades require
integrity evidence. No arbitrary startup deletion is authorized.

## Commands and evidence classification

Current [pyproject.toml](../pyproject.toml) requires Python 3.11+, `src` pytest
imports and pinned tzdata; optional test dependencies retain the unshipped JSONL
suites. Inspect the existing environment; do not invent new dependency or command
workflows. These are source-grounded examples to select
proportionally, not universal per-task requirements:

- Retained legacy pure/semantic baseline: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/test_mixed_accounting.py tests/test_work_entry_inputs.py`.
- Connected rewrite: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/rewrite/`.
- Real Tk rewrite: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/rewrite/ -k real_tk`.
- Full applicable regression: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts=''`.
- Syntax only: `.venv/bin/python -B -c "from pathlib import Path; paths=sorted({*Path('src').rglob('*.py'), *Path('tests').rglob('*.py'), *Path('.').glob('*.py')}); [compile(p.read_bytes(), str(p), 'exec') for p in paths]; print(f'{len(paths)} files compiled in memory')"`.

Syntax compilation imports no application and writes no bytecode; it establishes
no runtime guarantee. Rewrite commands above target the implemented suites;
retained JSONL tests are separate predecessor evidence, not a compatibility
requirement. A documentation task may request an unchanged-runtime baseline or
syntax check explicitly; otherwise select them proportionally, not automatically.
Retained legacy checks provide no SQLite/quarter-hour behavior evidence. No full
regression or desktop launch is needed for a verified Markdown-only delta absent
another applicable requirement.

Documentation checks cover the complete affected owner set, relative links and
anchors including incoming links from unedited files, formatting/whitespace,
working/staged scope and absence of executable changes. A fresh ephemeral checker
outside tracked source is sufficient; no permanent validation framework or ledger.

## Reporting and maintenance

Report exact commands/results, skips/reasons, materially applicable omissions,
platform limits and independent review boundaries. Distinguish current execution,
historical evidence, assessed carried-forward evidence and not run/unavailable.
Source inspection is not runtime validation; old passing JSONL results cannot
qualify SQLite transactions or complete a rewrite stage. Receipts are evidence,
not independent product authority. Preserve historical acceptance without claiming
new checks, Windows/NTFS, concurrency, power-loss or release qualification.
