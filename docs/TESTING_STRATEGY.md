# Chronicle testing strategy

This document owns validation expectations, applicability, evidence requirements
and release-validation boundaries. It does not select product behavior,
architecture, persistence/recovery mechanisms or a new release policy.

The [product contract](TIMESHEET_REQUIREMENTS.md) owns acceptance semantics;
the [roadmap](ROADMAP.md) owns sequencing and completion gates;
[ARCHITECTURE.md](ARCHITECTURE.md) owns the selected Tkinter/SQLite target;
[Design Notes](../DESIGN_NOTES.md) owns retained unshipped JSONL source/limitations. [AGENTS.md](../AGENTS.md) routes repository work;
[README.md](../README.md) describes status; [RUNNING.md](../RUNNING.md) owns
Python-source setup and native deployment checks; [CHANGELOG.md](../CHANGELOG.md) is the sole
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
| E — Windows/platform | Exercise actual Windows Python-source/Tk, filesystem and installation guarantees where applicable. Linux results cannot establish them independently. |
| F — Release qualification | Apply the roadmap's final gates: integrated workflow evidence, actual Windows source execution, approved installation/data protection and independent integrated review. Unit tests alone do not qualify a release. |

For Levels A–C, state which suite ran and its actual result; a focused run is not
a full regression. Levels D–F require evidence of interactions/platforms actually
exercised, with material omissions explicit. Implementation tests and integrated
qualification remain distinct.

## Connected SQLite timer evidence

The Stage 1A/1B/1C, Stage 2A/2B, Stage 3A/3B/3C/3D and Stage 4A/4B/4C suites below exercise the shipped `chronicle` source with disposable
SQLite datasets. This inventory describes assertions, not an automatic passing
result or native qualification; current command outcomes belong in receipts.

| Suite | Exercised boundary |
| --- | --- |
| [test_schema.py](../tests/rewrite/test_schema.py) | Real DELETE/EXTRA(3)/FK(1), STRICT/CHECK/UUID constraints, readback rejection and transaction-order guards, fresh/reopen/refusal, immutable evidence, active/closed guards and pre-COMMIT orphan postcondition. Version-floor mocks test only gate eligibility, not a substituted SQLite library; real feature tests use the actual linked runtime. Unsupported development journal profiles refuse before writable configuration, without conversion. Ordinary startup uses bounded header/metadata admission without whole-file hashes (WAL refusal creates no sidecars), preserves clean invalid-data non-mutating preflight, and rechecks admission under ownership before native recovery and complete validation. Tests enforce bounded reads, no cold fingerprint calls and rejection of WAL/foreign changes at lock acquisition. The shared DDL signature preserves quoted literals. No hostile database guarantee. |
| [test_services.py](../tests/rewrite/test_services.py) | Independent UUID task/project operations, atomic same-instant Switch/rollback, exact receipt reuse before stale checks, changed-content rejection, bounded busy including a real shared-reader-blocked rollback-journal COMMIT, failed COMMIT with open transaction, failed rollback/close, independent committed lookup, lost acknowledgement, unverified retry and immutable active-start audit/precision/DST behavior. Injected failures are not universal power-loss evidence. A failed independent reconciliation-probe close retains the actual handle and dataset ownership until explicit successful cleanup; a second owner remains refused. |
| [test_timekeeping.py](../tests/rewrite/test_timekeeping.py) / [test_accounting.py](../tests/rewrite/test_accounting.py) | Integer microseconds, range/type/canonical-date rejection, bundled IANA rules, gaps/repeats/non-hour transitions, local midnight/week, running cutoff, own/deleted work conservation, sleep/forward elapsed and impossible-observation warnings without refresh writes. These suites alone do not exercise date-only creation or quarter-hour allocation; the Stage 2A suites below cover mixed work. |
| [test_worker.py](../tests/rewrite/test_worker.py) / [test_bootstrap.py](../tests/rewrite/test_bootstrap.py) | Worker-thread connection lifecycle, exact reconciliation, startup failure, actual separate-process exclusion/ordinary directory aliases, committed active restart and abrupt process exit. Native alias cases skip narrowly where unsupported. Process tests are bounded examples, not hostile/multiwriter qualification. |
| [test_app.py](../tests/rewrite/test_app.py) | Actual main/mini construction and callbacks with real services/worker; server-delivered X11 task selection/buttons, Start/Switch/Stop, active-start correction, shared totals, slow-worker event delivery, duplicate guards and queued shutdown. Correction cases retain exact drafts/occurrences across real service validation, stale conflict, injected COMMIT rollback and pre-execution unavailability; queued work locks Close/fields, unchanged writes nothing, and unverified editor-local retries retain the same Request through absence/committed lookup. Dispatch tokens reject duplicate completions; unexpected view destruction retains owner evidence. Server-delivered keyboard/mouse cases cover rejection-to-success, repeated selection, blocked main/mini, Escape, editor Retry and the actual toolkit default-No exceptional-exit warning. WM Close is separately exercised through its registered handler. Known completion survives numeric/cleanup failure; cancellation/confirmed exit, read purity and late-result handling remain covered. Additional connected cleanup cases use server input for retry, retain lock ownership after failure, prohibit cancel-back-to-editing once cleanup started, and deliver failed-constructor cleanup to the owning worker. Worker exceptions/queued reads/shutdown are separately covered in test_worker.py. Repeated-interpreter test cleanup is UI-thread-owned; doubles alone do not establish desktop interaction. |
| [test_interruptions.py](../tests/rewrite/test_interruptions.py) | Separate disposable children killed at before-BEGIN, acquired transaction, partial work facts, receipt-before-COMMIT, after-COMMIT/before-ack and inside a subsequent read transaction for Start/Stop/Switch/correction. Independent reopen checks all facts, exact request reuse after newer work, no partial Switch/orphans, active-owner/reopen crashes, written rollback journal immediately before COMMIT and removed journal after COMMIT, interrupted initialization with existing rollback-journal preservation, and accepted-work shutdown. Pipe barriers/bounded waits replace sleep-only timing. The barriers surround SQLite COMMIT; they do not interrupt its internal journal unlink/page flush or establish universal hardware power-loss safety. Stage 4B adds barrier-controlled reminder dismissal at BEGIN/facts/receipt/post-COMMIT, and actual-worker report link/explicit replace and backup page-progress/validation/link deaths; independent reopen compares complete facts and preserves active identity. Interrupted private stages are not successful backups or automatically cleaned. Genuine hot-journal fixtures force main-file dirty-page spill with a small SQLite cache before killing a disposable child: independent read-only integrity reads require writable recovery. Cold inspection/CLI preserve database and journal bytes/identities/modification metadata; Store and real-worker startup recover under exclusive ownership and compare every committed logical fact/association, frozen output and receipt, then repeat reopen/exact retries/new work. Pending uncommitted identity/version changes roll back; a separate injected bounded-header observation checks that raw markers cannot preempt recovered identity (the exercised SQLite may hold page 1 until COMMIT). Faults cover admission/lock/open/native-read/full-validation/profile and retained connection/lock cleanup retry; readiness waits for full validation/profile. Invalid recovered evidence refuses without runtime configuration. Real-Tk/XTest exercises recovered ready/active state, Stop, orderly Close and reopen. This is Linux process-death evidence, not native Windows/NTFS or hardware power-loss qualification. |
| [test_operational_lifecycle.py](../tests/rewrite/test_operational_lifecycle.py) | Persisted midnight/week/DST and simulated sleep continuity, repeated corrections/reopen/Stop, no startup/tick writes, separate-process create/owner races and crash release, late unknown-file preservation, partial/profile/schema/header/version refusal and primary validation plus cleanup diagnostics. Native POSIX permission cases skip only where unavailable; they do not establish Windows ACL/NTFS behavior. |
| [test_launcher_selection.py](../tests/rewrite/test_launcher_selection.py) / [test_startup.py](../tests/rewrite/test_startup.py) | Isolated per-user suggestions and bounded versioned preferences, strict shape/identity/link/corruption refusal, exclusive publication and stale-record/fault preservation, exact Windows-key mapping/offline zone validation and no guesses. Real Tk/XTest plus the existing worker exercise Cancel/owned chooser, first creation and one-root handoff, ready-only remembering, default/remembered existing opens and active timers, draft/data preservation, cleanup retry/ownership, explicit CLI preference independence, hot-journal normal recovery without cold inspection, and separate no-argument source-launch create/reopen subprocesses. Headless recovery never enters setup. Tests inject only disposable preference/data paths; Linux and synthetic mappings are not native Windows first-run/focus evidence. |
| [test_source_runtime.py](../tests/rewrite/test_source_runtime.py), [test_root_launcher.py](../tests/test_root_launcher.py) | Replacement-only root import and src resolution without project installation; forbidden legacy/alternative-provider/builder imports, minimal pinned runtime dependency, builtin sqlite3 identity, offline IANA loading and actionable missing Tk/tzdata errors. These are source-runtime tests, not native Windows qualification. |
| [test_manual_work.py](../tests/rewrite/test_manual_work.py) | Real typed initial timed/date-only facts, UUID/task guards, exact H:MM bounds, invalid/future/DST/non-hour/UTC input, initial identity/revision/reference/receipt fault rollback and exact retry, direct-SQL nullable-kind/FK/active/deletion-successor checks and unknown schema-object refusal. Uses fresh SQLite files, not an old-schema migration. |
| [test_work_revisions.py](../tests/rewrite/test_work_revisions.py) | Real immutable corrections/deletions, unchanged/comment-only purity, exact endpoint precision/reverted minute, stale/owner/kind/active guards, deleted evidence/reopen, failed COMMIT versus verified receipt, uncertain identity reuse after newer work, malformed-chain refusal and barrier-driven process deaths for new work, revisions, deletion and week changes. Independent reopen checks atomicity; not hardware power-loss proof. |
| [test_mixed_work_accounting.py](../tests/rewrite/test_mixed_work_accounting.py) | Actual SQLite services through shared accounting: mixed/fractional/running amounts, future Saturday date-only attribution, independent/project conservation, retained deleted-task totals, DST/midnight, redating/correction/deletion and read/file-byte purity. Distinct from the retained JSONL test_mixed_accounting.py. |
| [test_history_reader.py](../tests/rewrite/test_history_reader.py) | Current week/Custom/All, complete endpoints and daily linked identity, exact precision/offsets, active UUID/version/audit and zero observation without a saved Stop, future dated work, retained deleted tasks, deleted-entry details, invalid requests and detached read/accounting agreement. Backend reader evidence, not a rendered History or inline editor. |
| [test_week_settings.py](../tests/rewrite/test_week_settings.py) | All seven persisted metadata conventions, containing-week/history agreement, unchanged/stale/type rejection, exact historical receipt reuse, restart and unchanged work evidence. No timezone change or allocation policy. |
| [test_manual_entry_ui.py](../tests/rewrite/test_manual_entry_ui.py) | Actual ChronicleApp/worker/service forms, fixed task/defaults, positive duration/timed validation and retained drafts, matching completion, uncertainty/exact retry, destroyed forms, construction/presentation faults, owned default-cancel exceptional exit, unchanged running timers, midnight/manual mixed totals, persisted week changes/restart, one-cutoff main/mini and scheduled refresh recovery. Server-delivered XTest mouse/keyboard exercises actual Add/Save/Cancel controls, blocked main/mini and weekday combobox selection; separate direct-callback tests isolate faults. Tk calls are checked on the creator thread. Display/window manager required; Linux evidence is not native Windows qualification. |
| [test_chronicle_history_snapshot.py](../tests/rewrite/test_chronicle_history_snapshot.py) | Actual one-transaction snapshot context/deleted index, seven week conventions, retained deleted tasks, detached row-list agreement, exact duration/midnight/link/repeated-offset formatting and immutable revision ordering. Pure presentation is separate from accounting. |
| [test_chronicle_history_ui.py](../tests/rewrite/test_chronicle_history_ui.py) | Actual History/application/worker/services: periods/draft-only calendars, applied refresh/rollover, empty/unavailable/preparation/widget distinctions, session direction and notification failure, linked metadata, complete timed/date-only editing, precise/no-op behavior, stale/rollback/unavailable drafts, exact uncertain retry, duplicate/late delivery, committed-result preservation and owned exceptional exit. Direct callbacks isolate faults; they alone are not operator-input evidence. |
| [test_chronicle_history_modal.py](../tests/rewrite/test_chronicle_history_modal.py) | Actual Tk local/global grab eligibility, Map-time conflicts, identity-checked origin return/focus fallback including reused paths, construction/presentation/return diagnostics, loading closure, obsolete-session rejection, root/calendar destruction and worker cleanup. Focus return requires a working window manager; local-grab evidence is distinct from Windows qualification. |
| [test_chronicle_history_operator.py](../tests/rewrite/test_chronicle_history_operator.py) | Production main → modal History → inline Edit/Delete/Details → return/restart on one disposable dataset. Server-delivered XTest input exercises controls, heading, periods/Custom Apply, calendar select/cancel/Escape, blocked main/mini, native default-No and affirmative Delete, full-entry precision, deleted navigation and origin return. Scheduled events/timer observations continue; a second actual application verifies persistence and newest-first reset. Native toolkit buttons use actual pointer geometry with bounded cleanup, not nested test pumping within the toolkit wait. No Windows/power-loss or Stage 3 evidence. |
| [test_polr_allocation.py](../tests/rewrite/test_polr_allocation.py) | Independent C–G, exact/sub-minute/zero weeks, rank/tie/conservation, permutation independence, seven calendar starts, strict integer/date/overflow bounds, HALF_UP ties, cell-summed display versus rerounded aggregate and exact quarter text. Pure arithmetic, no external-policy qualification. |
| [test_timesheet_candidate.py](../tests/rewrite/test_timesheet_candidate.py) | Actual SQLite mixed work through one consistent read context/cutoff, full-week basis with Tuesday-only C and multiple weeks, seven settings, Selected UUID rejection, retained deleted tasks, duplicate names/projects, safe Unicode/control text, future dates, running precision, corrections/deletions, DST/non-hour/year/leap boundaries and no preview writes. |
| [test_timesheet_registration.py](../tests/rewrite/test_timesheet_registration.py) | Four real immutable relational tables, sealed children, complete coverage/text/digest validation, atomic exact receipt, later-work/label/week independence, detached reopen recovery without a future renderer, malformed/corrupt evidence rejection, pre/post-COMMIT faults and uncertain lookup/exact retry. Disposable child processes die at task/basis/cell/master/receipt/pre-COMMIT/post-COMMIT barriers; independent reopen checks atomicity. These are bounded process-death experiments, not hardware power-loss proof. |
| [test_chronicle_timesheet_ui.py](../tests/rewrite/test_chronicle_timesheet_ui.py) | Actual application/worker/SQLite preview, no opening preparation, defaults/read-only exact text, independent scope, calendars/drafts/readiness, empty/error/partial-render recovery, original diagnostics and obsolete-session/attempt rejection. Callback faults cover launch/return/liveness/competing grabs and root cleanup; separate server-delivered XTest input exercises the production Timesheet control, main/mini blocking, period/scope selection, typed Custom dates, picker selection/Escape, explicit Preview and ordinary Close while events/timers continue. This suite retains Preview coverage; connected Save/file evidence is owned by the new suites below. Linux focus depends on the window manager; no Windows/NTFS, confirmation or release qualification. |
| [test_file_observations.py](../tests/rewrite/test_file_observations.py) | Raw six-field contract, native unchanged observations, strict identity/type and complete same-domain stability. Isolated synthetic Windows creation/change-time and executable-bit differences exercise explicit cross-domain binding without global platform patches; unknown/zero/differing IDs, unexplained mode/size/mtime/birthtime differences reject. Real bounded reads reject changed pathname/descriptor observations, incomplete and growing content. Synthetic descriptor ctime drives actual startup, cold inspection, backup/restore and report publication/reuse paths. This is provisional candidate evidence, not native Windows/NTFS field or runtime qualification. |
| [test_timesheet_files.py](../tests/rewrite/test_timesheet_files.py) | Actual SQLite registration gate and frozen-byte publication: five fresh states, full matching reuse without rewrite, exclusive absent publication, strict consent/typed conflicts, dataset paths/resolved aliases, unsuitable objects, incomplete/unstable/unreadable inspections, owned staging write/flush/fsync/close/content/cleanup and link/replace/final-verification faults. Target real changes plus injected final ctime (other compared metadata preserved) exercise the actual replacement decision; no native ctime advancement assumption. Fresh complete pre-replacement reinspection also rejects same-size/restored-mtime changed bytes with all six observations injected unchanged, preserves original read errors, and retains the immediate metadata guard afterward. Narrow native FIFO/symlink capability skips affect only setup, unexpected failures remain failures. Separate barrier-controlled child deaths immediately before/after link/replace independently reopen registered evidence and retry exact bytes; no automatic orphan cleanup or power-loss/hostile-directory claim. |
| [test_timesheet_save_ui.py](../tests/rewrite/test_timesheet_save_ui.py) | Actual Tk/app/worker/SQLite callback fault coverage: readiness/path cancellation/draft recheck, original preferred-path metadata, exact registration-before-publication, uncertainty both injected and actual committed-but-unprobed receipt, unchanged Request reconciliation, overwrite default-No/reentry/one-call gates, alternate paths, restart recovery without renderer/current labels, current status after removal, known completion before presentation, close/exit confirmations, busy/obsolete deliveries, destroyed views and primary/secondary diagnostics. Read-only recovery render failure cannot offer unreviewed publication. These direct callbacks isolate effects, not server-input evidence. |
| [test_timesheet_file_operator.py](../tests/rewrite/test_timesheet_file_operator.py) | Server-delivered XTest input through production Timesheet → explicit Preview → Save/cancel → Saved Reports/load → Check READY/MISSING → Retry → native default-No/affirmative Overwrite → Copy/cancel → New Preview/Close. Actual modal ownership blocks enabled main/mini probes; scheduled processing and the running timer continue. Frozen text/UUID and work evidence survive retry; fresh Preview has a new identity and current labels. File chooser decisions are doubled; overwrite confirmation uses actual toolkit buttons with bounded server input. Linux local-grab evidence is distinct from window-manager focus, native Windows/NTFS and release qualification. |
| [test_polr_confirmation.py](../tests/rewrite/test_polr_confirmation.py) | Real three-table SQLite confirmation: exact quarter parsing/bounds, Unknown/explicit zero, new equal-value evidence, whole/checked/manual batches, complete source including unchecked/zero, canonical metadata/names/selection, individual stale acknowledgements, selected identity changes versus unchecked newer priors, commit_seq precedence independent of audit time, duplicate/archived tasks (frozen status false), partial-source basis exclusion, mandatory A/B/F, immutable exports/files/work, and optional unavailable manual calculation context. UPDATE/DELETE guards, current/prior/source/receipt corruption, exact old retries, partial SQL/COMMIT/independent-probe faults and barrier-controlled child death at batch/cell/current/receipt/pre/post-COMMIT establish atomicity/reopen refusal. Disposable process kills are not hardware power-loss proof. |
| [test_polr_confirmation_ui.py](../tests/rewrite/test_polr_confirmation_ui.py) | Actual app/Timesheet/worker/SQLite source subset and manual replacement, checked zero, defer/read purity, invalid retained decimal drafts, stale prior requiring explicit refresh, individual consent reset, known rollback/unavailability, actual committed-but-unprobed uncertainty/exact Request retry, exceptional-exit cancellation, busy/destroyed origins/late responses, restart source/manual reads, optional unavailable context, worker/UI thread instrumentation and known commitment despite read/widget failure. Direct callbacks isolate these faults; server-input evidence is separate. |
| [test_polr_confirmation_operator.py](../tests/rewrite/test_polr_confirmation_operator.py) | Server-delivered XTest task/work/timer → Timesheet Preview/Save → source review/defer → checked subset and explicit zero → manual invalid/valid decimal → individual stale acknowledgement → immutable history/Close. Actual source/manual/history controls, positive defaults, native keyboard decimal input, enabled main/mini probes blocked by local modality and scheduled timer processing are exercised. File chooser decisions are doubled; no external POL-R connection, native Windows/NTFS or complete pilot qualification is claimed. |
| [test_reconciliation.py](../tests/rewrite/test_reconciliation.py) | Pure classifier and actual SQLite current projection: A/B/F, Unknown/known zero, opposing gaps, explained Delta, full-week/partial scope, cell-rounded rollups, independent task ceilings/deleted work, all weekdays, exact microseconds, DST/non-hour transitions, running/future work, one read/no writes, current/frozen reallocation and committed-sequence flags. Shared basis is calculated once, not a second allocator. |
| [test_polr_reminders.py](../tests/rewrite/test_polr_reminders.py) | All seven local weekdays × seven week conventions, previous-daily/current-Monday-and-Friday eligibility, worked-zero/explained differences, canonical dismissal/date validation, same-day restart/new date/absence, read/reopen refusal, no-op/exact receipt retry, actual failed-COMMIT and committed-but-unprobed reconciliation. These use disposable real SQLite data; not native suspend or power-loss proof. |
| [test_reconciliation_ui.py](../tests/rewrite/test_reconciliation_ui.py) | Actual app/worker/Timesheet/SQLite callbacks: defaults, explicit Custom/calendar drafts, copy, current/frozen/known-zero navigation and current-batch review without an export, manual confirmation, failure-preserved as-of state, hidden partial rendering/recovery, stale/closed-view reads, coalesced startup/commit/rollover/recheck, no per-tick reminder query, banner navigation, queue failure without automatic retry, same-day suppression despite calculation failure before/after Dismiss or startup, date rollover during an unresolved dismissal, known rollback/committed presentation failure, exact uncertain dismissal and same-day restart, UI/worker thread separation and orderly queued-read shutdown. Callback faults are distinct from desktop event evidence. |
| [test_reconciliation_operator.py](../tests/rewrite/test_reconciliation_operator.py) | XTest mouse/keyboard through real banner → Reconciliation → frozen Preview/Save → checked confirmation → manual mismatch → History correction → fresh reconciliation → explicit Dismiss. Exercises actual Selected UUID controls, typed Custom/calendar Apply/cancel, worked zero-suggestion Unknown/copy, current-batch and loaded frozen comparison navigation, weekly explanation/coverage, immutable file/evidence, blocked enabled main/mini probes, running timer and scheduled processing. File chooser decisions are doubled; no external POL-R/Windows/NTFS/pilot claim. |

| [test_backup_restore.py](../tests/rewrite/test_backup_restore.py) | Actual worker-owned SQLite backup, independent read-only full integrity/production semantic validation and cold new-directory restore. Compares every fact table and exact immutable receipt/report bytes across source/image/restore; retains active corrections, revisions, deleted work, full-week basis, source/manual/zero confirmations, latest references and dismissal. Covers empty/rich images, logical rather than page-layout equality, exclusive conflict/alias/type protection, source/stage changes, unknown object retention, actual page-progress interruption, connect/close/fsync/validation/link/acknowledgement/final-comparison/cleanup faults, exact uncertain-request gate and later worker operation/shutdown. FIFO/symlink setup skips only unavailable native capabilities; unexpected setup failures remain failures. CLI subprocesses verify/restore without a display; invalid combinations/source refuse before target/session construction. Corruption bypasses guards only in isolated fixtures. Not hardware power-loss or hostile-directory qualification. |
| [test_backup_ui.py](../tests/rewrite/test_backup_ui.py) | Actual App/worker/SQLite callbacks plus separate XTest controls: empty construction, owned chooser/cancellation, modal/busy/reentry/close guards, live local/global competitor refusal, retained primary diagnostics and outcome despite destroyed view or presentation failure, stale/duplicate completions, verified-file versus cleanup-only failure, timer observation while backup is blocked, enabled main/mini probes excluded by local grab, explicit failure recovery and ordinary/forced-root shutdown. Connected saved/confirmed/dismissed recovery scenario preserves work, active identity, frozen bytes, current references and reminder metadata. Callback faults do not substitute for server input; file decisions may be doubled. |
| [test_portable_reliability.py](../tests/rewrite/test_portable_reliability.py) | Connected App/worker/real SQLite: complete fact/receipt comparisons across edit, confirmation and Switch BEGIN/fact/evidence/reference/receipt/final/COMMIT/independent-probe faults; committed exact retries after newer state and changed-content rejection. Baseline-failing regressions cover committed editor completion after main-status failure, definitive worker stop retaining uncertainty and mismatched file context not consuming publication. Mutation deliveries require matching immutable Request context, not just tokens. XTest accepted Start/Stop/Switch followed by actual root-close protocol drains queued mutation and independently reopens exact receipts/active state. A rich connected scenario spans projects, Switch, checked/manual/zero confirmations and changed-Actual mismatch, then backup, actual committed-but-unprobed manual Save, exact reconciliation, queued shutdown/reopen, independently validated cold restore and fresh App/worker work while original/image/report stay unchanged. Direct callback faults remain distinct from server input. |
| [test_dataset_compatibility.py](../tests/rewrite/test_dataset_compatibility.py) | Real rich and empty current images, seven public diagnostics and deterministic headless source-launch statuses; lower/newer test-only markers, foreign identity, wrong same-version DDL/guards/objects/quoted literals, corrupt/truncated lower-marker files, metadata/work/export/confirmation/receipt-content and valid-FK/wrong-receipt associations. Normal startup/worker, backup validation and cold restore refuse before adoption/reservation without changing bytes, identity/modification metadata, entries or external evidence. Cold directory/ancestor/database aliases, native FIFO/unreadable paths, explicit network paths and all journal sidecars refuse; WAL headers never reach SQLite. Faults cover path/fingerprint/open/identity/version/full-integrity/schema/work/export/confirmation/receipt/close/stability/reporting; original diagnostics survive secondary close, with no reconnect to conceal failed cleanup. Actual changes to contents/directory/profile/sidecars reject, including loss of previously completed validation. Five barrier-controlled child deaths leave source evidence and next ownership intact; an actual killed transaction's outstanding journal is not recovered/deleted. A full mixed/revised/active/exported/confirmed/zero/dismissed image survives inspection, backup, independent restore and further legitimate work without changing original/image/report. Separate real-Tk/XTest smoke exercises normal ready/Stop/Start/Close/new-session reopen and rejected startups with no upgrade UI. Native capability skips remain narrow; Linux is not Windows/NTFS or power-loss qualification. |
| [test_backup_startup.py](../tests/rewrite/test_backup_startup.py) | Separate cold CLI restore followed by an actual root-source-launch subprocess, fresh Tk/App/worker ready state, preserved active timer and immutable evidence, explicit new restored work and orderly close. Original/image bytes remain unchanged. No live-session swap or old callback handoff; native Windows is separate. |

A usable display is required for `real_tk` cases. Linux Xorg/XTest evidence does
not establish native Windows/NTFS or actual suspend/resume. The actual Python,
SQLite source/compile options and DELETE/EXTRA/FK settings are recorded; the GUI
profile is exercised separately. SQLite 3.37.0+ is the only runtime version floor.
Stage 1A and Stage 1B portable reliability are independently accepted. Stage 1C
simplifies the profile/source deployment and retires executable-build assertions.
Stage 1 functionality and Stage 2A are independently accepted under the later
Stage 2B approval. Native Windows source/NTFS/Tk and actual suspend/resume
remain deployment/pilot evidence, not an executable-build requirement or permanent
Stage 2 blocker. The later Stage 3A approval independently accepts Stage 2B/complete
recording at `adc09ba0935e8718c4ad2101057af9c6022074cc`. Stage 3A is independently accepted at `d1e775c33982f109337ec237e3c78e8dc7b56f2e`.
Stage 3B is independently accepted at `76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`.
The later explicit Stage 3D GO instruction independently accepts Stage 3C for
functional development. The later Stage 4A GO instruction records independent
Stage 3 functional acceptance. The later Stage 4B GO independently accepts
Stage 4A. The later explicit Stage 4C GO independently accepts Stage 4B.
Subsequent independent review accepts Stage 4C inspection, protected refusal and
bounded owned SQLite-native rollback recovery for functional development. The
Stage 4 integration coverage audit is independently accepted: existing connected
and compatible composite evidence establishes the portable cross-boundary workflow;
no material gap or new portable integration test was warranted at that flat baseline. This is
coverage sufficiency, not a new execution result or complete Stage 4 acceptance.
Stage 4 remains IN PROGRESS; Stage 5 is NOT STARTED. See
[acceptance provenance](DECISIONS.md#stage-4c-and-portable-tooling-acceptance).
Native qualification and external-policy/installation gates remain outstanding.

## Portable operational measurements

Stage 4B uses three disposable Linux datasets, Python 3.12.14 and linked SQLite
3.53.1, through the production SQLiteStore/TimerService/backup APIs. Three samples
per operation; cells below are median / maximum **seconds**. Seed sizes are
3 / 50 / 100 tasks, 12 / 700 / 2,000 date-only entries, 3 / 50 / 200 immutable
confirmation batches and 1 / 3 / 5 registered full-week exports. Source-linked
confirmations (every 25th batch where selected) include exact stale acknowledgements;
other batches include manual absolute values/zero. Each sample adds actual
Start/Switch/Stop, a date-only revision and a confirmation; thus final files also
contain six closed timed entries and three additional revisions/batches. Measured
file sizes were 225,280 / 2,658,304 / 10,248,192 bytes. Setup is not timed as an
operator action. No measurements/status/cache are persisted in application data.

| Operation | Small | Medium | Larger |
| --- | --- | --- | --- |
| Open/validation | 0.0100 / 0.0103 | 0.2860 / 0.2868 | 1.8099 / 2.2883 |
| Start | 0.0011 / 0.0012 | 0.0553 / 0.0558 | 0.4554 / 0.4606 |
| Stop | 0.0007 / 0.0009 | 0.0542 / 0.0543 | 0.4401 / 0.4514 |
| Switch | 0.0008 / 0.0009 | 0.0566 / 0.0578 | 0.4508 / 0.4526 |
| Manual correction | 0.0008 / 0.0009 | 0.0539 / 0.0549 | 0.4387 / 0.4531 |
| Confirmation commit | 0.0011 / 0.0012 | 0.1022 / 0.1088 | 0.8711 / 0.9360 |
| Current state | 0.0008 / 0.0010 | 0.0616 / 0.0624 | 0.4573 / 0.4643 |
| Timesheet preparation | 0.0016 / 0.0016 | 0.0680 / 0.0687 | 0.4917 / 0.5396 |
| Reconciliation | 0.0014 / 0.0039 | 0.0602 / 0.0661 | 0.4828 / 0.4837 |
| Reminder evaluation | 0.0016 / 0.0018 | 0.0664 / 0.0667 | 0.4621 / 0.5157 |
| Consistent backup | 0.0158 / 0.0172 | 0.4451 / 0.4515 | 2.3780 / 2.7754 |
| Backup validation | 0.0057 / 0.0070 | 0.1684 / 0.1710 | 0.8973 / 0.9037 |
| Cold restore | 0.0202 / 0.0217 | 0.5234 / 0.5416 | 2.9250 / 2.9716 |

Complete immutable confirmation-history validation remains enabled on reads,
commits and reopen. Its growing cost is visible in these results; no integrity
check was removed and no persistent validation cache added. Backup/restore include
multiple independent validations and final verification. These bounded measurements
are not an SLA, cold-cache benchmark, universal scalability claim or native Windows
performance evidence. The slow-I/O Tk tests independently establish event delivery
while the serialized worker is occupied; API timing alone does not prove desktop
responsiveness. Simulated SQLITE_FULL/ENOSPC, read-only and connection faults are
injected evidence, separate from actual local SQLite/process/permission checks.
Native Windows/NTFS, real suspend/resume, hardware power loss, hostile concurrent
filesystem changes, protected future upgrades and complete pilot remain unqualified.

## Cold compatibility inspection measurements

Stage 4C measures the actual cold inspector with full integrity, receipt and complete
confirmation-history verification enabled. Three samples per workload, Linux,
Python 3.12.14, linked SQLite 3.53.1. Seed sizes: 3 / 50 / 100 tasks and
12 / 700 / 2,000 closed work entries (3 / 140 / 400 genuine timed, the remainder
date-only), plus one active timer, one work correction and one active-start audit,
non-default week, dismissal, 1 / 3 / 5 frozen exports and 3 / 50 / 200 source/manual
confirmation batches including zero. Exact stale consent is limited to selected
cells. Source connections are closed before inspection. File sizes:
225,280, 2,592,768, 9,732,096 bytes.

The harness times initial cold path/header/fingerprint checks up to read-only open,
the first profile/application/version reads, the complete current-image gate and
the whole API call. Later validator identity reads do not overwrite the first-phase
measurement. Total also includes connection setup/close and final fingerprint and
metadata/sidecar verification. Values are median / maximum **seconds**:

| Phase | Small | Medium | Larger |
| --- | --- | --- | --- |
| Initial path/header | 0.000207 / 0.000315 | 0.001912 / 0.002109 | 0.007867 / 0.008937 |
| Identity/version | 0.000339 / 0.000343 | 0.000356 / 0.000401 | 0.000410 / 0.000441 |
| Full supported-image validation | 0.007342 / 0.008484 | 0.177103 / 0.180011 | 0.908140 / 0.942422 |
| Total inspection | 0.008393 / 0.009592 | 0.182021 / 0.185360 | 0.924622 / 0.960631 |

These are bounded engineering observations, not an SLA, cold-cache benchmark,
native Windows measurements or universal scale qualification. No validation cache,
persisted inspection/performance state or integrity bypass was added. Prior Stage
4B timings above remain historical measurements of those exercised operations.
No current-schema change or real upgrade is demonstrated by these measurements.

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
Stage 1A and Stage 1B portable reliability are independently accepted on
`feature/chronicle-rewrite`. Stage 1C uses standard sqlite3 DELETE/EXTRA and direct
source execution. Independent Stage 1 functional acceptance is established under
the later approval; native Windows source-deployment/pilot qualification remains pending.
Tests follow the user-selected [architecture](ARCHITECTURE.md) and
[semantic contract](EXPORT_EVIDENCE_CONTRACT.md); they do not choose stronger
recovery/platform policy. Integrity tests begin in each slice, not only Stage 4.

| Stage | Applicable evidence |
| --- | --- |
| 0 authority | Review complete affected Markdown/current source, all material decisions, current/target separation, incoming relative links/anchors and executable scope. No runtime delivery from documentation. |
| 1 foundation | Real SQLite recording/reopen, stable task/project IDs, one active timer, atomic Switch at one accepted time, rollback on rejected use cases, exact request reuse before stale checks and changed-content rejection. Verify actual DELETE/EXTRA/foreign-key/STRICT behavior, bounded lock failure and truthful commit uncertainty. Source startup includes the actual built-in SQLite runtime and offline zone availability. Native Windows source evidence is required before deployment/pilot, not as an executable gate. Approved continuous sleep/restart, explicit active-start recovery and uncertain-exit rules now have Stage 1A assertions; native operational qualification remains pending. |
| 2 recording | Stage 2A delivers connected creation, revision/read services, mixed totals and week settings; Stage 2B/complete recording is independently accepted; its tests remain regression evidence. Complete-stage obligations: integer-unit mixed accounting, genuine/date-only shape integrity, stable work UUID/revision/current references, correction/deletion history, no-op purity, stale drafts, whole-entry segment editing, precise unchanged endpoints, minute changes, DST/UTC, all week starts, applied periods/unapplied drafts/session sorting and all-reader gate before exposed writers. |
| 3 Timesheet AND POL-R | Connected frozen preview/full-week quarter-hour suggestions and saved-report recovery; explicit whole/checked/manual absolute quarter confirmations, complete reviewed source, exact acknowledgements, Unknown/zero, stale priors, daily gaps/adjustments/coverage and reminders. External reporting/zero-entry validation before affected official use. No pilot without these. |
| 4 stabilization | Integrated interruption/commit ambiguity, second-instance refusal, queued shutdown/fresh restore sessions, real backup/restore, strict compatibility inspection/refusal, storage faults and native Tk/Windows source operation. Future approved transitions require separate exact-version transformation tests; no version-2 migration is active. Earlier slices already test their integrity boundaries. |
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
backup captures committed facts consistently, independently validates, cold-restores
and reopens all work/export/confirmation/receipt history, including current references
and reminder metadata. Compare complete logical values/associations, not counts or
physical page layout. Exercise absent/existing/alias paths, staging and publication
failures, no overwrite and owned-only cleanup. CLI validation/restore constructs no
Tk root/worker; normal later launch creates a fresh session. Do not test a live
main-file copy or in-place/live replacement as a valid backup/restore. Cold inspection
uses no writable lock or application session, preserves source metadata/bytes and
refuses unverified cleanup or detected changes. Verify every compatibility category
and exit status, same-version DDL/literal refusal and unsupported-version rejection
by startup, backup and restore before target creation. Distinguish non-recovering
cold inspection from ordinary locked native hot-journal rollback followed by full
validation. Clean invalid candidates must preserve bytes/entries; physical SQLite
rollback effects on journaled candidates are not Chronicle evidence mutations.
Never infer genuine hot-journal recovery solely from a journal filename.
A hypothetical separately approved data-preserving transition would need the
[version-specific safety contract](ARCHITECTURE.md#cold-compatibility-inspection-and-future-transition-boundary).
The hierarchy target instead requires fresh data, a distinct approved schema and
strict old-dataset refusal, not v1 conversion tests. No migration engine, legacy
import or backward-compatibility fixture obligation is selected.
Linux fault injection does not prove arbitrary concurrent-writer, power-loss or
native Windows/NTFS safety.

## Package B2 movement evidence

[test_branch_movement.py](../tests/rewrite/test_branch_movement.py) exercises real
schema-2 triggers and service/worker transactions for roots/nested branches,
project/Unassigned membership, same-project reparenting, complete sorted review,
changed versions/timestamps, exact/no-op retry, archived ancestry, active destination
refusal, running leaf preservation and independently archived descendants.
Independent direct/cumulative/group/application expectations guard double counting.
Faults at detachment/project/attachment/version/receipt/COMMIT prove rollback or
committed reconciliation; separate killed-child barriers prove pre/post-COMMIT
structure/receipt atomicity. Corrupted multi-entity receipts refuse full validation.
Rich frozen/confirmed evidence remains exact across movement, backup, cold restore
and independent reopen. Existing GUI and recording suites remain regression scope;
no movement UI, native Windows or hardware power-loss qualification is claimed.

## Package B1 fresh hierarchy evidence

[test_hierarchy_foundation.py](../tests/rewrite/test_hierarchy_foundation.py)
uses real fresh-v2 SQLite services for project/Unassigned three-level forests,
duplicate names, exact reviewed creation and retry, no parent version bump, depth/
cycle/project refusal, running-parent prevention and effective archive eligibility.
Mixed parent/child/grandchild direct work independently establishes derived amounts,
zero-direct parents, deleted work revisions, complete-period conservation and DST/
cutoff behavior. Parent corrections/History remain direct; frozen parent selection
never includes descendants and later edits leave frozen bytes/values unchanged.

Creation/rename/assignment closure and strict receipt classes protect survivors.
Negative fixtures temporarily bypass guards only on disposable data, restore exact
DDL, then test full startup/inspection/backup/restore and worker-readiness refusal
for invalid forests, active-parent/archive states, missing/orphaned administration,
wrong ownership/current versions/names/results/classification. Refusal preserves
all damaged-source bytes/metadata and creates no restore target. Pre/post-COMMIT
child deaths and lost acknowledgement test atomic structure/receipt/evidence,
rollback, committed survival and exact retry without duplicated children.
Rich v2 backup/restore preserves parentage, archive fields, every fact/receipt and
frozen export/confirmation evidence; a fresh restored worker resumes the active
identity and commits new work without changing source/image.

Real Tk checks parent Individual/Cumulative, disabled new-work/assignment controls,
direct History, eligible mini context and unchanged GUI root-creation behavior.
Full nested operator workflow is not qualified by B1. Existing schema, history,
Timesheet/POL-R, interruption/hot-journal and GUI suites run on fresh v3 fixtures; the earlier v2 delivery remains historical evidence.
Former live soft-delete fixtures now exercise retained archived identities; work
Delete still means immutable revisions. Frozen report is_deleted remains false in
new v2 evidence. Native Windows/NTFS qualification of these changes remains pending.

## Package C1 reversible lifecycle evidence

[test_archive_lifecycle.py](../tests/rewrite/test_archive_lifecycle.py) exercises
real selected-only project/task archive timestamps/versions, inheritance and
independent descendants, no-op purity, stale/strict request refusal, active branch
refusal without timer mutation, exact retries after later changes and B2 movement
in reconstructed archive context. Faults and separate barrier-controlled child
termination around updates/receipt/COMMIT verify atomicity, committed survival and
exact reconciliation. Damaged archival requests/results/class/state/timestamps
refuse complete validation, cold inspection and restore before target reservation.
A rich work/revision/export/confirmation/active/dismissal image survives worker
Archive/Unarchive, backup, independent cold restore and further legitimate work.
Existing B1/B2 archive fixtures now create valid archive receipts through production
services; deliberate damage fixtures continue bypassing guards only on disposable
images before restoring the exact DDL.

[test_archived_items.py](../tests/rewrite/test_archived_items.py) exercises actual
Tk/worker snapshots for full three-level archived structure, empty projects,
independent branch context, no duplicate UUIDs, inherited-only explanations,
selected-only Unarchive, period/shared totals, direct History and modal exclusion.
Four sorts retain hierarchy, expansion/selection and deterministic ties without
unchanged-row writes. DST repeated-hour dates include UTC offset and sort by UTC.
Cancellation, pending/destroyed origins, lost acknowledgement/exact reconciliation
and stale deliveries remain distinct from server-delivered Archive confirmation,
cancel, Archived Items selection and Unarchive input. These are portable Linux
Xorg/XTest tests, not native Windows focus/topmost/NTFS qualification. C1 alone establishes no C2 Delete; C2 evidence is inventoried below.
D now connects full nested active management. Run Level C after this shared
lifecycle/application boundary change, plus focused runtime/UI evidence.
The existing explorer viewport fixture settles pending child layout after its
requested root resize before freezing the baseline; full scroll-fraction, selected
UUID and expansion assertions remain unchanged.

## Package C2 unused-only Delete evidence

[test_unused_delete.py](../tests/rewrite/test_unused_delete.py) uses real schema-3
transactions for active/archived/Unassigned/three-level scopes, unused children of
working parents, duplicate names/fresh UUID reuse, finite administrative closure
and shared-survivor history refusal. Typed work/revision/active/correction, frozen
zero/basis/project and current/prior/zero-confirmation references block; arbitrary
UUID-looking names/comments do not create dependencies. Complete canonical review
changes reject after child/work/export/rename/archive/move/closure changes. Unknown,
incorrect-class or damaged receipts refuse without repair. Failure injection at
task/project/receipt removal, final validation/survivor comparison and COMMIT/close,
plus controlled child-process death, proves all-or-none state and truthful no-retry
uncertainty. Every survivor is compared logically, including immutable bytes; rich
backup/cold restore/reopen/further work preserves original and image evidence.

[test_delete_ui.py](../tests/rewrite/test_delete_ui.py) uses actual Tk/worker/SQLite
for both main/Archived Items entry points, complete hierarchy/counts, exact typed
confirmation, refusal/cancel/stale review, no optimistic hiding, pending/destroyed
origins, lost acknowledgement, current-presence inspection and explicit exit/reopen.
Existing modals and mini ownership cannot be bypassed. Known commitment survives
presentation errors; unknown delivery never becomes a destructive retry. Separate
XTest pointer/keyboard input exercises Cancel and typed DELETE through production
controls. These are portable tests, not Windows/NTFS/operator qualification.
Run Level C for this persistence/application boundary; preserve cold inspection,
native rollback recovery, immutable reporting formulas and the existing schema.

## Package E template and erased-provenance evidence

[test_templates.py](../tests/rewrite/test_templates.py) exercises real fresh schema 3,
canonical graphs/mappings, current Unicode name uniqueness, version/no-op/retry,
archived Edit/Duplicate, complete multi-task ownership, atomic insertion, retained
node IDs and removed-ID refusal. Relinquished-name A/B history remains valid after
A Delete; retained historical name collisions, missing surviving creation history,
corrupt graphs/keys/mappings/results and orphan effects refuse. Source Delete keeps
Apply/Duplicate bytes and original exact results; it makes no erased-interval claim.
C2 full unused Apply batches can retire, partial batches/protected work/zero exports/
zero confirmations refuse. Real pre/post-COMMIT child death, fault/close/ack handling,
worker no-retry Delete/presence, backup/cold restore/reopen/new work are distinct
from hardware power loss. Historical schema-1/2 DDL is test-only refusal evidence;
it is never a runtime parser/migration path. Source bytes/metadata/entries remain.

[test_template_ui.py](../tests/rewrite/test_template_ui.py) uses actual Tk/worker/
SQLite for modeless management, draft node operations/cancel, fresh Duplicate,
frozen Apply review/reveal, restrictions, exact uncertain retry, destroyed views,
owned modal/main/mini exclusions and typed Delete/no-retry presence/exit. Unchanged
manager reads must not churn rows. Separate XTest input exercises manager selection
and Apply confirmation. Linux input and portable tests do not establish Windows/
NTFS/operator correctness. Run Level C after the shared schema/receipt/UI changes;
remaining F qualification and Stage 4 gates stay open.

## Package D connected hierarchy evidence

[test_hierarchy_ui.py](../tests/rewrite/test_hierarchy_ui.py) uses real Tk widgets,
DatabaseWorker and disposable schema-3 data for three-level/Unassigned/duplicate
identity parentage, empty groups, hidden archived work, direct/cumulative totals,
recursive unavailable/recovery, sorting/expansion/selection and unchanged refresh.
It exercises reviewed child creation, depth/running/stale destination refusal,
retained parent History, version purity and successful UUID reveal. Real B2 moves
cover root/subtree/project/Unassigned/parent destinations, no-op receipt purity,
advisory invalid choices, transactional races, active identity and full-path reveal,
manual collapse, fresh nested-active startup and immutable saved/confirmed evidence.
Blocked, destroyed, rejected, unverified and presentation-failure cases retain the
accepted Request, exact Move retry and explicit shutdown; C2 remains no-retry.
Existing modal/mini/Archived Items guards and lifecycle tests remain applicable.
Separate XTest input selects/commits Move and inspects/cancels the real toolkit name
dialog. These are Linux portable/input observations, not native Windows qualification.
Carry forward compatible B1/B2/C mathematical, SQL, refusal, interruption and recovery
evidence; run Level C for this shared owner/rendering boundary. Package E evidence
is inventoried above; remaining F/native/operator gates stay separate,
Stage 4 IN PROGRESS and Stage 5 NOT STARTED.

## Package A explorer evidence

[test_main_explorer.py](../tests/rewrite/test_main_explorer.py) uses actual Tk,
DatabaseWorker and SQLite for typed group/task identity collisions, empty/duplicate
projects/tasks, all creation selection contexts, empty-project rename, assignment
preserving work, shared period/group/application conservation, retained hidden
facts and unavailable recovery. Actual widget-write spies establish unchanged
refresh purity; nonzero scroll/selection/open state survives reads and period
changes. Explicit ticks cover fresh UTC observations without repaint, minute/date
transitions and backward-clock recovery without writes. XTest exercises timer and
mini Show Main/Keep Mini Open/live modal protection. Existing app/History/Timesheet/
backup/startup cases now address typed rows without weakening service assertions;
manual-work tests explicitly exercise the shared period. Linux evidence does not
qualify native Windows theme/topmost/focus behavior.

## Hierarchy evidence and remaining target gates

This section maps the later user-approved
[target requirements](TIMESHEET_REQUIREMENTS.md#approved-hierarchy-target-and-fresh-data-boundary)
to [packages A–F](ROADMAP.md#hierarchy-target--bounded-packages-a-f). It does not
claim all remaining tests exist or ran. Implemented B1/B2/C1 subsets are established
in the inventory above and carried forward; this table retains required assertions
and the remaining F gate; C2 and D are inventoried above.
Retained JSONL tests do not become SQLite qualification. The final owner decision selects Archive/Unarchive plus actual
unused-only Delete without a recoverable tier or deletion ledger. Independently
retain C2's now-selected finite dependency/transaction design on unchanged DDL; E now resolves referenced-template Delete through self-contained retained receipts and explicit erased-provenance limits.

| Guarantee | Required focused evidence |
| --- | --- |
| Fresh schema boundary | E now supports only exact fresh v3; maintain refusal and validation for every subsequent approved change. new/empty creation is exclusive. Old/foreign/partial/damaged/WAL candidates refuse without conversion, replacement, file deletion or repair. Cold inspection stays read-only/non-recovering; supported new images retain locked native rollback recovery and complete validation before readiness. |
| Forest and depth | Real SQLite task/project UUIDs and duplicate task names; virtual Unassigned has the same three task levels as real projects. No-selection New Task creates an Unassigned root; otherwise use the selected project/group or eligible task. Cycles/self-parent/cross-dataset/depth overflow reject. Moving a height-two subtree must check its deepest leaf, not just destination depth. Test SQL-enforced constraints separately from transactional cross-row postconditions. |
| New-time eligibility | Start, Switch destination and both manual writers accept only eligible leaves. Existing parent direct work remains readable/correctable/deletable as work. Adding child/move/template cannot make a running task ineligible; archive/delete active containing branches refuse. No implicit timer event or synthetic Stop. |
| Name reuse | Existing, archived and actually deleted project/task names may be reused through normal Create, always with fresh UUIDs. No automatic restore, merge, overwrite or reuse of an existing identity. Do not transfer the active-template trim/casefold uniqueness rule to tasks/projects. Erased old raw requests have the separate explicitly limited historical-retry promise. |
| Accounting conservation | Independent expected examples with parent direct work plus children/grandchildren: Individual stays direct, Cumulative includes each descendant once, project/application totals never sum rollups twice. Collapse, sort and archived navigation filters do not remove applicable history. One cutoff/main/mini, all weekdays, midnight/DST, exact microseconds, future dated work and unavailable calculations retain existing semantics. Carry forward compatible edge-case suites rather than rebuilding them inside a giant integration test. |
| Branch moves | Complete before/after UUID/work/evidence comparison for same-project reparent and cross-project move; all descendants get coherent current grouping. Effectively archived selected branches refuse until unarchived; allowed moves preserve independently archived descendant states. Stale source/destination/affected state rejects atomically. Frozen labels/text/basis and absolute confirmations remain unchanged while fresh grouping updates. |
| Archive/Unarchive | Only selected explicit flag/current archive time changes; exact accepted UTC instant, IANA/DST display, no creation/mtime inference. Active containing branches refuse without implicit timer action. Descendant flags/relationships/work/grouping/frozen evidence remain unchanged. Unarchive clears only selected flag/time; archived ancestors still hide children; rearchive later gets a new current timestamp. No historical archive-date journal is required. |
| Archived Items tree/sort | Archived projects, independently archived branches with active-ancestor context and inherited-only descendants; one UUID once, original parentage and full expand/collapse. Exactly Name A–Z/Z–A and Date Archived Newest/Oldest with newest default; sibling/top-level sorting, stable UUID ties, nearest-archived-ancestor timestamp versus own explicit time, real UTC chronology across DST repeats. Selection/expansion retained during sorting/refresh while visible; targeted updates avoid unnecessary row rebuild. Read-only for time: no Start/Switch/new manual work, including direct callbacks and stale selected nodes. C1 Direct History/Unarchive and explanatory refusal use worker/Tk and separate server input. C2 adds eligible Delete through its separate owned preview/confirmation. |
| Unused-only Delete | No Archive prerequisite; project/task management and Archived Items routes. Exact selected subtree/counts/cannot-undo warning, typed DELETE for branch removal, final scope/closure recheck and all-or-none row/relationship/exclusively owned administrative removal. Timed/date-only/deleted work/revisions, active/correction evidence, frozen zero scope/basis/labels/project references, all confirmations including zero, reporting/survivor dependencies and unresolved administration each block. One protected descendant blocks whole-project Delete; an independently removable unused child under a working parent may succeed. Zero Actual never proves eligibility. No pruning, scope expansion, history rewrite, automatic cleanup, dataset-file deletion or backup/copy modification. |
| C2 administrative Delete/receipt boundary | Implemented evidence above covers the finite allowlist and typed complete closure, shared/cross-entity/survivor refusal, races/new dependencies, constraint-safe atomic order and full before/after survivor equality. Surviving/protected requests retain exact retry/conflict semantics and commit order. Fully erased administrative requests deliberately have no historical result/replay guarantee; do not require erased UUID reservation or tombstones. Lost Delete acknowledgement plus erased receipt reports uncertainty: present absence is not historical proof. No automatic resubmission or stale callback adoption; queued/concurrent actions pass final current checks. Faults/interruption prove all or none and complete independent startup/backup/restore validation without a deletion registry/ledger. |
| Templates | Real SQLite graph/depth/UUID validation, duplicate task/project names, active template trim/casefold uniqueness including non-ASCII collisions and conflicting Unarchive-name refusal. Archive/Unarchive availability and intended actual definition Delete; E permits definition Delete after Apply with intact self-contained historical receipts. No soft-delete tier, tombstones or silent reference removal. Applied tasks/history stay independent; whole Apply commits or rolls back and retained exact request retries return the original instance. |
| Main/mini and ownership | Actual Tk controls and separate server-input evidence: context New Task, initially session-local sibling A-Z, expansion/selection preserved by UUID, active ancestors expanded/indicated, parent direct History, visible management. Green/red plus text, shared Individual/Cumulative period and mini Individual Today. Keep Mini Open defaults Off on each session; Show Main retains mini only when On. Mini never steals focus/grabs from owned modals. Existing Escape/cancel/pending-result ownership persists; minute repaint does not delay action timestamps or hide time/date changes. |
| Evidence/recovery integration | Representative hierarchical/revised/archived/active data with frozen full-week basis, confirmations/zero/current references and exact retained receipts survives backup validation, cold restore and fresh operation. Current explicit archive timestamps survive unchanged and inherited display remains derived. Separate unused Delete changes no protected/original/image/report facts. Compare complete logical evidence, not page layout. No migration or live replacement. |

Use disposable data through actual services/worker; preserve complete logical and
relevant filesystem snapshots for refusal/read-purity checks without reading an
actively Windows-locked lock byte. Inject partial subtree/template writes and unused-branch Delete,
failed COMMIT/independent probe/result delivery and cleanup failures. Preserve
original diagnostics and exact pending Request, not an invented recovery ledger.
Shared schema/accounting changes require Level C plus applicable integration;
D shared application/rendering changes require Level C and applicable real-Tk/input
integration; isolated presentation changes use proportional focused/affected tests.
Native Windows tree, modal/focus, topmost and actual operator input remain Level E
evidence; Linux tests, source inspection and synthetic observations cannot replace
them. Actual suspend/resume, external reporting policy, installation and Stage 5
remain separate gates. This evidence inventory authorizes no later package execution.

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

Stage 3A allocation/candidate/registration/preview and Stage 3B protected
publication/recovery and Stage 3C confirmation evidence are inventoried above.
Stage 3D reconciliation/reminder evidence is inventoried above; continuing qualification
obligations remain. File checks describe
the implemented boundary and continuing qualification obligations. An inventory
is not a current passing result.
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

The Stage 3C suites above use actual SQLite services/transactions, not independent
mock selection logic. Continue that boundary for affected changes. Inspect useful predecessor cases in
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

Stage 3C real-Tk evidence covers bounded immediate feedback and explicit confirmation;
Stage 3D adds connected summaries/coverage/reminders and separate server-input evidence.
Representative bounded reconciliation/reminder timing is engineering evidence only;
no persistent cache or new integrity validator is justified by hypothetical scale.
Affected real-Tk workflow evidence must distinguish Actual/Suggested/Confirmed,
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

Shared filesystem helpers preserve raw observations and all six same-domain
fields. Unit A is accepted for portable development; this does not establish
Windows compatibility. POSIX pathname/descriptor checks remain complete; provisional
Windows
binding separates legacy pathname ctime from descriptor change time, requires
usable equal identity/type/size/mtime and compatible documented mode synthesis,
and compares birthtime when both expose it. Native Windows observations and focused
tests remain UNVERIFIED pending October 26. A minimal empty SQLite backup/validate/
restore test runs independently of the rich fixture's report publication, so a
publication setup failure cannot masquerade as recovery failure.

Native FIFO/symlink cases remain capability-dependent with narrow setup skips,
not evidence that a service rejected an object that setup failed to create.
Rewrite [file tests](../tests/rewrite/test_timesheet_files.py) and retained historical
[overwrite tests](../tests/test_timesheet_overwrite.py) include deterministic
same-size/restored-mtime evidence injecting changed change-time only at the actual
final recheck. Preserve that distinction from native filesystem evidence; do not
assume native Windows creation/change-time semantics. The rewrite additionally
tests complete content reinspection with unchanged injected metadata; changed bytes
still invalidate consent. It does not claim detection when every complete content
and metadata observation agrees. Unexpected errors remain failures.
Bounded observations are not atomic compare-and-replace, hostile-directory safety
or universal power-loss proof. UI consent cannot make an unreadable/unstable or
unsuitable target safe.

## Windows desktop and release qualification

### Package F connected and native gate evidence

[test_package_f_integration.py](../tests/rewrite/test_package_f_integration.py)
uses the real serialized worker/Store/services on one connected disposable schema-3
dataset: nested/multi-root template Duplicate/Edit/Apply, retained parent work,
Start/Switch/Stop/manual work/revisions, archive/move, full/partial frozen scope,
protected publication, checked/manual/zero confirmation, A/B corrections and
opposing daily mismatches, explicit dismissal, active backup and cold restore to
a fresh owner. Complete logical equality is distinct from SQLite page bytes;
original/image/report bytes stay fixed after restored work. Separate C–G cases
carry independent expected quarters through registration/backup/restore. Another
dataset covers whole-Apply deletion closure, protected/partial/stale/cancel refusal,
source retirement and retained Apply/Duplicate evidence, name reuse and erased
provenance. Lost Apply acknowledgement reconciles exactly; lost Delete never retries.
Temporal cases cover midnight/week rollover, Chicago DST gap/repeat, impossible
backward observation and a simulated long gap with no tick writes or duplicate timer.

[test_package_f_operator.py](../tests/rewrite/test_package_f_operator.py) connects
actual app/worker/Tk child creation, direct parent History correction, template draft/
cancel/Apply, reviewed Move, main/mini modality, archive management and blocked/eligible
Delete, frozen Save/recovery/confirmation/reconciliation, active backup and fresh
restored Tk operation. Callback and XTest variants are distinct. Names/file chooser
responses are local test doubles; XTest drives actual buttons, not Windows dialogs.
Existing adversarial suites remain required for queued shutdown, stale tokens,
destroyed accepted views, storage/presentation faults, process death, genuine hot
journals, protected v1/v2 refusal and corrupted evidence. F does not duplicate all
their algorithms or reinterpret process death as power loss.

[test_stage4_qualification.py](../tests/rewrite/test_stage4_qualification.py)
exercises the new full-wrapper plugin in real tiny pytest subprocesses, original
inventory/parametrization, actual outcome/JUnit mapping, incomplete evidence,
dialog obstruction, bounded POSIX monitor deaths, exclusive manifest/sentinel
protection, traversal/archive/publication failure and verified ZIP membership.
Synthetic cleanup inputs test aggregation only; POSIX children are not Win32 proof.
The PowerShell parser/runtime test skips explicitly when unavailable. Existing
collector behavioral tests continue validating the reused monitor/Job design;
source/static checks are never native execution evidence.

F1 portable tests and full regression support the development deliverable, not
Stage 4 closure. F2 current-source native automation, F3 actual Windows operator
input and F4 actual Sleep/resume remain distinct pending gates. The separate
[full wrapper](../scripts/qualify_stage4_windows.ps1) uses full original collection,
fresh basetemps, guarded callbacks, raw logs/events and structurally verified
pytest JUnit. Every selected node must complete once; ambiguous/missing mapping,
unclean source, cleanup/capture uncertainty or incomplete delivery prevents PASS.
F2 preserves the full original inventory, then executes disjoint source-grounded
SUPPORTED_RUNTIME (`tests/rewrite/` and `tests/test_root_launcher.py`) and finite
RETAINED_LEGACY top-level Task Time partitions in separate owned sessions. Other
sources remain UNCLASSIFIED and block supported qualification. Original node IDs,
actual source paths, fixture closures and exact pytest JUnit serialization remain
separate identities; an empty classname is valid only when the exact serializer
produces it. No basename/fuzzy matching is accepted. Tests audit the reviewed legacy
module list and runtime import separation; new/shared tests require classification.

Raw skipped/xfail/xpass evidence is never changed to passed. F2 records applicability
separately: APPLICABLE, INAPPLICABLE, BLOCKED_REQUIRED or UNRESOLVED. The finite rules
in `stage4_qualification.py` review exact POSIX test identities and the explicit
`test_app.click` Linux XTest platform metadata and fixture source. A missing root/desktop before
that fixture is not waived. Unknown skips, expected failures, missing required
capabilities and collection skips prevent qualification. Symlink privilege failures
have no blanket exemption. Replacement NTFS/Job/ACL/operator evidence gates remain
explicit; F3/F4 do not follow from automation. The old bounded collector skip policy
is unchanged.

The F2-only event writer is preowned before pytest: no event-path reopening, one
serialized UTF-8 record per line, captured low-level write/sync/close, sticky failure,
short/interrupted-write handling, sequence/digest health and nonzero exit on
finalization failure. Parent reconciliation requires actual session/JUnit completion
and exact process agreement; a verified ZIP cannot rescue incomplete execution.
Regression tests include real filesystem-monkeypatch pytest sessions, empty external
path JUnit identities, faulted writes/sync/close, corruption and separate partition
sessions. Controlled POSIX deaths remain portable containment evidence only.

History/Timesheet focus diagnostics distinguish initial desktop/foreground focus
from legitimate modal return. They record mapping, focus/grab owner/status, live
Python/Tcl widget identities, Win32 foreground PID/HWND where available and bounded
event ordering. They never force focus. Recovery tests wait for actual widget mapping
and viewability after authoritative callback delivery, retaining partial-output
hiding and correct restored-content assertions. Native focus/render defects remain
unresolved until reproduced; no production Tk correction is inferred from Linux.

Raw execution and archive delivery are separate. Supported execution may be PASS
while retained legacy is FAIL; full-source status stays FAIL. Supported automated
qualification is published only with verified delivery. Missing source classification,
manifest/JUnit/capture/cleanup/finalization or delivery prevents PASS. Exclusive
archive-manifest reservation, explicit link exclusions, fatal traversal errors,
reopen/CRC/member checks and absent-target publication preserve evidence. Failed ZIP
retains the directory. Frozen MetadataProbe/Critical/Storage/Extended sets remain
separate and unchanged.

The October 30 Windows attempt at `56b4e4451d8c738f70d23938c2f60be009d61a84`
is EVIDENCE_INCOMPLETE: supplied independently inspected evidence reports 3,783
collected, 2,208 completed (2,073 passed/30 failed/12 errored/93 skipped), 1,575 not
completed, missing final session and JUnit, with verified ZIP/cleanup. Its logger
collided with a legacy read-purity filesystem patch. The original external ZIP is
not rewritten and was not available on this repair's development host. The 42
failure/error nodes and native focus/layout hypotheses require fresh native evidence;
legacy file-status expectations remain visible without production backporting.

Use [WINDOWS_OPERATOR_QUALIFICATION.md](WINDOWS_OPERATOR_QUALIFICATION.md) for the
original-attempt inventory, focused rerun, per-scenario actions, isolated settings,
native files/hot recovery and actual Sleep. A prior revision, callback double,
Linux XTest or simulated interval cannot fill a native gate. F2 corrective source
requires independent review before repeat native execution. F3/F4 remain NOT RUN;
Stage 4 IN PROGRESS and Stage 5 NOT STARTED.

The opt-in [Windows collector](../scripts/qualify_windows.ps1) and its private
[pytest helper](../scripts/qualification_pytest.py) implement bounded automated
scopes documented in [RUNNING](../RUNNING.md#bounded-windows-qualification-collector).
Unit B and its bounded evidence-safety repair are independently accepted for
initially limited native MetadataProbe use. That historical authority does not
qualify changed source. The current F2 corrective repeat requires independent
review; no broader/operator/Sleep gate follows automatically. MetadataProbe is the default; Critical/Storage/Extended are frozen
function
manifests with collected fixture-closure checks, not an unattended full regression.
Unknown static fixtures are NOT RUN; unknown dynamic fixtures obstruct before
setup. Every collected rewrite exclusion retains a reason, and retained legacy
cases are listed separately as not collected. Supervised GUI/operator cases are
never promoted to passing evidence by exclusion. Exactly two Extended Backup
callbacks are audited: one locally cancels its owned chooser, the other requests
no native dialog. These differ from actual native operator decisions/input.

The collector retains flushed collection/node/phase/report/completion events,
unique completed-node and outcome counts, independently drained stdout/stderr,
actual process/pytest exit statuses, real JUnit with explicit incomplete/missing
status, commands, source/collector identities, metadata observations and cleanup
results in one isolated evidence tree/ZIP. A setup/teardown failure makes that
node an error even if its call passed; raw report/JUnit counts remain available.
Test execution, evidence completeness and archive delivery are separate results.
PASS requires a valid final selection manifest, exactly one start/completion per
selected node, consistent phase/session counts and mapped pytest JUnit case
evidence, in addition to zero exits and verified cleanup/output capture.
Missing/invalid/unmappable evidence cannot promote a zero pytest exit to PASS.
The validator accepts pytest's suite root/wrapper and multiple error details or
cases belonging to one node; it does not equate XML error counts with node counts.
MetadataProbe's JUnit is explicitly not applicable.
Watchdog termination is not a pytest failure exit code invented by the collector.
Elapsed/event-age heartbeats do not imply completed work or elapsed percentages.
Suspended-start Windows Job Object assignment precedes testing; failure to contain
blocks rather than falling back to kill-by-name. Toolkit guards never answer an
unexpected dialog. Owned native windows are inspected, but external security/OS
windows are not claimed to be universally detectable; unknown obstruction still
has a bounded timeout with no automatic consent.

[test_qualification_collector.py](../tests/rewrite/test_qualification_collector.py)
uses tiny actual pytest subprocess fixtures for parametrization/deselection,
pass/fail/skip/xfail/xpass, setup/teardown errors and hung collection/setup/call/
teardown. It also covers unique completion counts, live concurrent streams,
heartbeat/no-progress warning/deadlines, interruption/cleanup, unexpected Tk/Tcl
dialog obstruction, local dialog doubles, static/dynamic fixture exclusion,
source mismatch/dirty refusal, missing prerequisites, partial XML, isolated ZIP
membership including hidden artifacts, and metadata-only owned files. Portable
repair regressions exercise reserved manifest files/directories/links against
outside disposable sentinels; exclusive post-test receipt writes; root/child
enumeration failures; missing, malformed and inconsistent JUnit/manifest/events;
actual parametrized/xfail/xpass/setup/teardown JUnit; and raw versus final status
after archive timeout, partial output and secondary failures. The archive manifest
is reserved exclusively; traversal failures cannot produce a complete archive.
Final receipts remain pessimistic until archive acknowledgement, while the raw
collector result is retained unchanged. Successful ZIPs contain the completed
receipt bytes; failed/unacknowledged ZIPs are diagnostic artifacts, not delivered
qualification. Conditional PowerShell fallback/finalization tests run only when
PowerShell is installed; source checks alone are not its runtime evidence. Portable
process groups are test fixtures only, not a Windows containment fallback.
Python compilation/static PowerShell checks cannot qualify PowerShell 5.1/7,
CRT quoting, native progress display, Job Objects, NTFS or actual Windows dialogs.
Those remain UNVERIFIED until native execution. Collector completion itself is
not independent Windows/Stage 4 acceptance. No application behavior changes.

Native Windows source operation is required before actual deployment/complete core
pilot: actual Python/built-in SQLite/Tk, offline IANA rules, writable NTFS ownership,
persisted timers, main/mini, active-start correction, modal input/focus, exceptions
and ordinary close/reopen, manual timed/date-only entry and week-start persistence.
Actual suspend/resume needs native evidence. Delivered History/Timesheet Preview
and file Save/recovery/explicit confirmation/reconciliation/reminders require native
validation; delivered backup/cold restore also requires native source/NTFS validation. A source launch without core POL-R is not a
qualified complete pilot. There is no executable-package qualification requirement.

Inspect [RUNNING.md](../RUNNING.md), [run.ps1](../scripts/run.ps1) and metadata before
selecting commands. The source launcher needs only a permitted Python environment
with Tk/sqlite and pip-installed tzdata, not an editable build. No automatic
installation, builder or output cleanup is part of launch. Linux tests cannot
establish Windows Tk/NTFS or deployment permission. Missing work-computer access
does not permanently block Stage 2 development. No release/merge approval follows
from successful tests or source startup alone.

## User-data protection

Use disposable temporary datasets only. Do not initialize services against
`~/.task_timer_data`, read actual user settings for source investigation, import
old history, delete user files or change installation paths. Fresh rewrite scope
removes migration/compatibility obligations, not data protection. Exact release
cutover/cleanup remains Open; new-runtime backup/cold restore and fresh hierarchy
schema admission require integrity evidence. No hierarchy migration/compatibility
work is required, and no arbitrary startup deletion is authorized.

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
