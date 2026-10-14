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
Future export/confirmation tests follow the selected
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
| Rendering | [test_timesheet_renderer.py](../tests/test_timesheet_renderer.py): scope, partial/multiple weeks, calendar boundaries, exact durations, duplicate identity, wrapping/geometry and Unicode escaping. |
| Decimal rendering | [test_decimal_timesheet_renderer.py](../tests/test_decimal_timesheet_renderer.py): ROUND_HALF_UP conversion/boundaries, invalid numbers, task/day rounding and displayed-rollup conservation, selection/identity, partial/multiple weeks, calendar edges, Unicode wrapping, purity and exact/legacy byte compatibility. This is a pure staged renderer, not export-evidence persistence. |
| Export registration | [test_export_snapshot_registration.py](../tests/test_export_snapshot_registration.py): frozen request/cells/text/digest, strict validation, stable identity/retry, journal health, ambiguous append and projection failures, immutable replay order, restart/rotation/rebuild/backup restore and no file/confirmation effects. This does not validate materialization or POL-R confirmations. |
| Reporting/file publication | [test_timesheet_service.py](../tests/test_timesheet_service.py): real service orchestration, UTF-8 bytes, no-clobber publication, concurrent targets, injected staging/publication/cleanup failures and state/file purity. |
| Existing storage and backups | [test_storage.py](../tests/test_storage.py), [test_backups.py](../tests/test_backups.py), plus project/dated/accounting fixtures: restart, rotation, snapshots, backup contents, retention and restore behavior. |
| Legacy compatibility | [test_exporter.py](../tests/test_exporter.py), [test_timeline_corrections.py](../tests/test_timeline_corrections.py), and neighboring tags/subtask/template/selected-export tests protect current behavior during staging. Legacy submission/checkpoint tests are not proof of replacement POL-R semantics. |
| UI and launch routing | [test_app_ui.py](../tests/test_app_ui.py), dialog/window tests and [test_root_launcher.py](../tests/test_root_launcher.py): callbacks, formatting and routing; some construct fake roots, SimpleNamespace widgets or instances without real GUI initialization. They do not establish real Windows desktop usability or packaged execution. |

Existing fixtures use pytest `tmp_path` and `monkeypatch`, including fixed clocks
and America/Chicago timezone examples. File/state snapshots make purity and
invalid-operation assertions meaningful.

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

For current exact renderer/service changes, assert output against supplied seconds.
For replacement decimal rendering, assert the selected displayed-cell sums while
preserving full-precision accounting. Both need authoritative scope/timezone,
partial weeks, Unicode escape reversibility, complete wrapped names, aligned
borders and no repeated chargeable values on continuation rows. Pure generation
and rendering must not mutate inputs/state/files. Evidence registration changes
its intended evidence only, never Actual records, timers or export checkpoints.

## Decimal rendering, export registration and future integration validation

The pure decimal renderer/converter and immutable export-snapshot registration
are implemented/staged, with coverage in the test sources above. Verified file
materialization, confirmations and file/evidence recovery remain unimplemented.
Apply the selected technical contract to current rendering/registration changes
and future integration:

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
- PENDING/READY/MISSING/CONFLICT/UNVERIFIABLE derive from the snapshot and path;
  changed/missing copies are rechecked. Matching existing files may be recognized,
  conflicting files are never overwritten, and retry at a different path retains
  the original snapshot/identity without another export event.
- Ambiguous registration reuses a valid journal event, retries a demonstrably
  absent event only with a healthy journal and the same identity, and fails closed
  on malformed/partial/unknown registration. Derived-snapshot failure does not
  undo valid evidence; restart, archive replay, rebuild and backup/restore retain
  pending exports. Duplicate identities cannot duplicate effective evidence.

Decimal conversion/displayed rollups and bounded journal registration/replay have
existing focused coverage. File/evidence materialization/recovery assertions are
future expectations, not existing passing coverage or a mechanism selected by
tests. Preserve current exact renderer and legacy regression assertions during
staging. Registration requires independent GO review before materialization or
confirmation implementation. Linux fault injection is not power-loss or Windows
qualification.

## Future POL-R reconciliation acceptance

These obligations come from the product contract, **not an implemented system**.
Use the approved technical contract to validate Actual, immutable Exported and
latest Confirmed POL-R independently when implemented:

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

Validate backup creation and restoration with representative records and audit
history, malformed event envelopes/payloads, partial event writes and meaningful
append/interruption failures. Earlier valid work must not be silently lost.
Assertions must follow approved failure semantics, not invent repair or rollback
behavior. Existing happy-path restart/restore tests do not prove every
interrupted-recovery scenario.

[storage.py](../src/task_timer/storage.py) appends JSONL, flushes/fsyncs,
orders archived/active reads and replaces derived JSON files. The service validates
new project/dated lifecycle and export-snapshot events before append and replay.
These mechanisms do not establish universal transactional or power-loss guarantees.

Export-snapshot events have bounded replay and fault-injection coverage above;
future confirmation events also need those checks against the
[selected technical contract](EXPORT_EVIDENCE_CONTRACT.md). Validate one-event
confirmation batch integrity and authoritative journal precedence over derived
snapshots. This strategy defines tests, not another event/schema/recovery owner.

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

Materializing committed immutable export evidence adds a future cross-resource
boundary governed by the approved snapshot-first contract. Inject failures
before/during registration, after durable registration but before publication, during derived-snapshot writes,
through staging/publication and during final verification. Validate no external
publication without established registration, retained pending evidence, stable
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
