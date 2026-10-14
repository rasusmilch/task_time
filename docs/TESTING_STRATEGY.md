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

The following inventory is based on inspected tests and source, **not a new
execution or a claim of exhaustive coverage**. Use it to find affected tests and
inspect their assertions before selecting a run.

| Area | Existing test sources and observed scope |
| --- | --- |
| Project/task identity | [test_projects.py](../tests/test_projects.py): independent identities, membership/reassignment, invalid targets, replay and data isolation. |
| Date-only replay | [test_dated_durations.py](../tests/test_dated_durations.py): endpoint-free records, correction/deletion, ownership/payload rejection, equal-second replay, archives, rebuild and backup/restore. Uses isolated private event fixtures; it does not activate production writers. |
| Accounting and time boundaries | [test_mixed_accounting.py](../tests/test_mixed_accounting.py), [test_time_utils.py](../tests/test_time_utils.py): conservation, selection, cutoffs, midnight/DST, corrections, resets, fractional amounts and fixed Sunday weeks. |
| Rendering | [test_timesheet_renderer.py](../tests/test_timesheet_renderer.py): scope, partial/multiple weeks, calendar boundaries, exact durations, duplicate identity, wrapping/geometry and Unicode escaping. |
| Reporting/file publication | [test_timesheet_service.py](../tests/test_timesheet_service.py): real service orchestration, UTF-8 bytes, no-clobber publication, concurrent targets, injected staging/publication/cleanup failures and state/file purity. |
| Existing storage and backups | [test_storage.py](../tests/test_storage.py), [test_backups.py](../tests/test_backups.py), plus project/dated/accounting fixtures: restart, rotation, snapshots, backup contents, retention and restore behavior. |
| Legacy compatibility | [test_exporter.py](../tests/test_exporter.py), [test_timeline_corrections.py](../tests/test_timeline_corrections.py), and neighboring tags/subtask/template/selected-export tests protect current behavior during staging. Legacy submission/checkpoint tests are not proof of replacement POL-R semantics. |
| UI and launch routing | [test_app_ui.py](../tests/test_app_ui.py), dialog/window tests and [test_root_launcher.py](../tests/test_root_launcher.py): callbacks, formatting and routing; some construct fake roots, SimpleNamespace widgets or instances without real GUI initialization. They do not establish real Windows desktop usability or packaged execution. |

Fixtures inspected use pytest `tmp_path` and `monkeypatch`, including fixed clocks
and America/Chicago timezone examples. File/state snapshots make purity and
invalid-operation assertions meaningful. No new fixtures or tests are created
by this strategy.

Currently, mixed accounting is staged and Sunday-only, production date-only
writers are inactive, and saving publishes a file without immutable export-event
registration. Configurable weeks, new POL-R confirmations/reconciliation and
replacement installation are not implemented or validated by existing foundation
tests. Future acceptance obligations below are explicitly conditional on approved
implementation; test names or prior receipts do not change that status.

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

For renderer/service changes, additionally assert precise output against supplied
accounting totals, authoritative scope/timezone, partial weeks, Unicode escape
reversibility, complete wrapped names, aligned borders and no repeated chargeable
values on continuation rows. Capture input/state/events/files to test purity.

## Future POL-R reconciliation acceptance

These obligations come from the product contract, **not an implemented system**.
After relevant contracts are approved, validate Actual, immutable Exported and
latest Confirmed POL-R independently:

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
External entry format remains Open; do not infer it from Chronicle's text format.

## Persistence, replay and recovery evidence

For event-backed changes, validate before mutation and compare state, event count
and authoritative file bytes on rejection. Test stable UUIDs, append-only history,
deterministic replay including equal-timestamp read order, effective corrections
and deletions, restart, archive rotation, derived snapshots and reconstruction.
Compare rebuilt projections with authoritative archived and active events.

Validate backup creation and restoration with representative records and audit
history, malformed event envelopes/payloads, partial event writes and meaningful
append/interruption failures. Earlier valid work must not be silently lost.
Assertions must follow approved failure semantics, not invent repair or rollback
behavior. Existing happy-path restart/restore tests do not prove every
interrupted-recovery scenario.

Inspected [storage.py](../src/task_timer/storage.py) appends JSONL, flushes/fsyncs,
orders archived/active reads and replaces derived JSON files. The service validates
new project/dated lifecycle events before append and replay. These mechanisms
do not establish universal transactional or power-loss guarantees.

Future export/confirmation events need appropriate replay and fault injection;
confirmation batches require all-or-nothing tests **after** their persistence
contract is approved. This document selects no event names, serialized fields,
transaction format or recovery mechanism.

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

Future immutable export evidence adds a cross-resource validation boundary.
After adjudication, test event-log append failures and relevant interruptions
alongside file-output failures according to the approved consistency contract.
Backup/restore interruptions require corresponding recovery evidence where
applicable. File/event coordination remains Open: this strategy does not choose
commit order, rollback rules or a crash-recovery transaction. Staging fsync is
not directory fsync or guaranteed power-loss durability; do not claim either
without implemented, applicable verification.

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

**Source-grounded, not executed in this documentation task:**

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

This compile example is **not executed here** and proves syntax only. Substitute
the affected files; no new runner or fixture is required.

**Executed for this documentation baseline:** Git branch/status/HEAD and remote
inspection; read-only `rg` and file reads; `git diff --check`, diff/stat review;
in-memory Python link checks and unchanged non-Markdown-content checks. These
are documentation evidence, not test-suite execution. Their results belong in
the execution receipt, not an accumulating validation ledger here.

**Windows-specific, unavailable here:** the source launch and PowerShell build
commands documented in BUILDING were inspected, not executed on this Linux
environment. Neither a source launch nor a successful build alone proves
packaged installation or GUI workflow correctness.

**Historical evidence only:** earlier passing results belong to their original
receipts. They are not re-executions in this task. No CI command, numeric coverage
threshold or Windows result is established by this strategy.

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
coverage and results. Event contracts, cross-resource consistency, external
format, allocation details and replacement cutover remain with user/ChatGPT
adjudication; POL-R backend facts remain Unverified. The roadmap's testing
governance can be established without closing Phase 1 or qualifying the release.
