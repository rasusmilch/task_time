# Chronicle repository instructions

## Authority and actor boundary

User-approved behavior is authoritative for desired product requirements.
[docs/TIMESHEET_REQUIREMENTS.md](docs/TIMESHEET_REQUIREMENTS.md) owns the selected
replacement/POL-R contract. Source establishes what currently executes;
[DESIGN_NOTES.md](DESIGN_NOTES.md) describes inspected architecture and limitations.
[README.md](README.md) provides overview/status. Tests and execution receipts are
evidence, not product authority.
[docs/ROADMAP.md](docs/ROADMAP.md) owns development phases, priorities,
dependencies, phase completion criteria and deferred implementation work; it
does not replace requirements or technical design authority.
[docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) owns validation applicability,
test evidence and release-qualification boundaries.
[docs/DECISIONS.md](docs/DECISIONS.md) preserves historical product/architecture
decision evidence, rationale, provenance and supersessions. Current-state
requirements take precedence for present selected behavior; decision history
does not replace current authority or close Open matters.
[docs/EXPORT_EVIDENCE_CONTRACT.md](docs/EXPORT_EVIDENCE_CONTRACT.md) owns the
approved technical export-snapshot, decimal-hour, materialization/recovery and
POL-R confirmation-batch contracts. Approval does not mean implementation.

The user and ChatGPT approve product behavior and architecture. Codex implements
approved tasks and reports constraints; it must not independently decide
requirements, policies, schemas, workflows or previously Open matters. Return an
unresolved material design choice for user/ChatGPT adjudication.

Read the product contract before POL-R-related work. Selected does not mean
implemented. Do not claim target functionality is active or treat superseded
legacy behavior as permanent replacement-product policy.

## Reading map

| Owner | Read for |
| --- | --- |
| [README.md](README.md) | Overview, actual status and navigation. |
| [docs/TIMESHEET_REQUIREMENTS.md](docs/TIMESHEET_REQUIREMENTS.md) | Selected target behavior and Open/Unverified/Deferred boundaries. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Current development phases, priorities, dependencies, completion gates and deferred work. |
| [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) | Proportional validation scope, evidence requirements and release-qualification boundaries. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Historical product/architecture decision evidence, rationale, provenance and supersessions. |
| [docs/EXPORT_EVIDENCE_CONTRACT.md](docs/EXPORT_EVIDENCE_CONTRACT.md) | Approved export evidence, decimal representation, verification/recovery and confirmation technical contracts. |
| [DESIGN_NOTES.md](DESIGN_NOTES.md) | Current service/event/storage contracts and verified limitations. |
| [BUILDING.md](BUILDING.md) | Existing Windows launch, packaging and distribution instructions. |
| [pyproject.toml](pyproject.toml) | Python requirement, package dependencies and pytest configuration. |
| [CHANGELOG.md](CHANGELOG.md) | Sole canonical cumulative project-change history. |

## Validation and command evidence

Apply the [testing strategy](docs/TESTING_STRATEGY.md) to select validation for
the changed guarantees and affected dependencies; known commands are not
automatically mandatory for every change.

Inspect existing scripts and package metadata before documenting or invoking
commands. Actual execution results, checks not run and environment limitations
belong in the current task receipt. Earlier results may be cited as historical
or carried-forward evidence with an applicability judgment; they must not be
represented as tests executed during the present task.

Source-grounded command examples (select according to applicability):

- Linux regression: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts=''`.
- Windows source launch: `python .\run_chronicle.py` or `./scripts/run.ps1`.
- Optional development install: `python -m pip install -e .`.
- Windows packaging: `./scripts/build.ps1`, optionally `-OneFile`; see BUILDING.

`pyproject.toml` requires Python 3.11+ and configures pytest's `src` import path.
Use the appropriate existing interpreter/virtual environment. Assess Windows
validation availability for each execution. Linux results do not establish
Windows GUI, NTFS, PowerShell or packaging correctness; do not invent CI/release
checks. Runtime tests must use isolated temporary datasets and protect existing
user data. Documentation-only changes ordinarily need focused documentation
checks; executable changes need applicable behavioral/regression
and syntax validation. Keep focused execution distinct from integrated validation.

## Documentation and changelog reconciliation

When approved behavior or implemented status changes, reconcile affected
current-state owners coherently in place. Search directly affected references
beyond edited paragraphs; do not append contradictory correction sections.
Stop for adjudication if reconciliation would change an Open product decision.

Root CHANGELOG.md is the only canonical changelog. Keep Unreleased cumulative,
reflecting material effects rather than one entry per task/commit. Intermediate
commits need not update it unless coherence requires it. Final merge-readiness
review must reconcile cumulative behavior and documentation; this rule does not
authorize merging.

## Durability, review and publication

Durably commit completed, validated tracked changes locally before ending an
execution. ChatGPT independently reviews Codex receipts; passing tests alone
never establish product correctness.

The user authorizes normal non-force publication only to
`feature/chronicle-projects-timesheets` in `rasusmilch/task_time`, as a
workstream-specific exception to the ordinary local-only Codex_guide boundary.
Verify the starting state and remote branch; stop on unexpected advancement or
divergence. Review, validate, commit, push normally and verify the remote commit.
Retain a validated local commit and report any publication failure. This does
not authorize hosted operations in other repositories/workstreams. Do not write
main, force-push, merge, rebase, create a PR or modify unrelated hosted metadata.

## Execution receipts

Use compact Codex_guide v4.1 receipts with accurate evidence scope, limitations
and exactly one next action. The raw receipt must have one outer tilde fence:
opening `~~~text`, closing `~~~`. Inside it, use matching separator boards around
`Receipt` at the beginning and `End Receipt` at the end. No local Codex_guide
installation or external static template is required.
