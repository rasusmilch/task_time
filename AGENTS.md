# Chronicle repository instructions

## Authority and actor boundary

User-approved behavior is authoritative for desired product requirements.
[docs/TIMESHEET_REQUIREMENTS.md](docs/TIMESHEET_REQUIREMENTS.md) owns the selected
replacement/POL-R contract. Source establishes what currently executes;
[DESIGN_NOTES.md](DESIGN_NOTES.md) describes inspected architecture and limitations.
[README.md](README.md) provides overview/status. Tests and execution receipts are
evidence, not product authority.

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
| [DESIGN_NOTES.md](DESIGN_NOTES.md) | Current service/event/storage contracts and verified limitations. |
| [BUILDING.md](BUILDING.md) | Existing Windows launch, packaging and distribution instructions. |
| [pyproject.toml](pyproject.toml) | Python requirement, package dependencies and pytest configuration. |
| [CHANGELOG.md](CHANGELOG.md) | Sole canonical cumulative project-change history. |

## Validation and command evidence

Inspect existing scripts and package metadata before documenting or invoking
commands. Distinguish execution from documentation and historical receipts.
The governance baseline verified Git preflight, `git diff --check`,
`git diff --stat`, `git status --short`, read-only `rg` searches, and in-memory
Python checks of Markdown links and unchanged non-documentation files.
It did not execute the application, installation, packaging or Python regression
suite. A historical passing pytest receipt is not a new test execution.

Source-grounded commands documented but not run for this documentation baseline:

- Linux regression: `.venv/bin/python -B -m pytest -q -p no:cacheprovider -o addopts=''`.
- Windows source launch: `python .\run_chronicle.py` or `./scripts/run.ps1`.
- Optional development install: `python -m pip install -e .`.
- Windows packaging: `./scripts/build.ps1`, optionally `-OneFile`; see BUILDING.

`pyproject.toml` requires Python 3.11+ and configures pytest's `src` import path.
Use the appropriate existing interpreter/virtual environment. Windows-specific
launch, NTFS and packaging validation are unavailable on Linux; do not claim
otherwise or invent CI/release checks. Runtime tests must use isolated temporary
datasets and protect existing user data. Documentation-only changes need focused
documentation checks; executable changes need applicable behavioral/regression
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
