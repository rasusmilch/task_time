# Chronicle repository instructions

## Authority and actor boundary

User-approved behavior is authoritative for desired product requirements.
[docs/TIMESHEET_REQUIREMENTS.md](docs/TIMESHEET_REQUIREMENTS.md) owns the selected
replacement/POL-R contract. Source establishes what currently executes;
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) owns the selected Tkinter/SQLite
rewrite architecture; [DESIGN_NOTES.md](DESIGN_NOTES.md) describes inspected
legacy Tkinter/JSONL implementation and limitations.
[README.md](README.md) provides overview/status. Tests and execution receipts are
evidence, not product authority.
[docs/ROADMAP.md](docs/ROADMAP.md) owns rewrite Stages 0–6, priorities,
dependencies, completion criteria and deferred implementation work; it
does not replace requirements or technical design authority.
[docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) owns validation applicability,
test evidence and release-qualification boundaries.
[docs/DECISIONS.md](docs/DECISIONS.md) preserves historical product/architecture
decision evidence, rationale, provenance and supersessions. Current-state
requirements take precedence for present selected behavior; decision history
does not replace current authority or close Open matters.
[docs/EXPORT_EVIDENCE_CONTRACT.md](docs/EXPORT_EVIDENCE_CONTRACT.md) owns the
selected frozen-export, decimal-hour, materialization/recovery and absolute
POL-R batch semantics and the single full-week quarter-hour allocation algorithm.
Exact Actual/display hundredths are distinct from POL-R quarter units.
ARCHITECTURE owns SQLite transactions; former JSONL
envelope/replay/synchronization mechanics are legacy, not replacement requirements.
Approval does not mean implementation. POL-R confirmation, reconciliation,
summaries and reminders are core before pilot, not optional expansion.

The user and ChatGPT approve product behavior and architecture. Codex implements
approved tasks and reports constraints; it must not independently decide
requirements, policies, schemas, workflows or previously Open matters. Return an
unresolved material design choice for user/ChatGPT adjudication.

Read the product contract and target architecture before replacement work.
Stage 0's documentation gate is independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`. The active rewrite workstream is
`feature/chronicle-rewrite`, originating at that commit. Stage 1 supplies the timer
engineering foundation. Its approved Stage 1A connected SQLite timer slice is
implemented and accepted. Stage 1B portable reliability is accepted at
`1e84a043c1c055aced9b8c4b000ef766bbf6d178`. Stage 1C selects built-in sqlite3,
DELETE/EXTRA/foreign keys and direct Python source execution. Stage 1 functional
completion awaits independent adjudication; native Windows source evidence is
required before deployment/pilot, not an executable-build or Stage 2 blocker.
The explicit Stage 2A approval now authorizes connected mixed work, immutable
revision/read services, shared accounting and week configuration. Stage 2 remains
In Progress; Stage 2B History/inline editing and Stage 3 POL-R remain pending.
Subsequent execution stays bounded and independently reviewed, using substantial
coherent slices without microtasks.
The fresh rewrite
requires no legacy JSONL compatibility/import, old internal APIs or duplicate UI
paths. Existing user files remain protected; no reset, clean or user-data mutation
is authorized as workflow cleanup.
Read the product contract before POL-R-related work. Selected does not mean
implemented. Do not claim target functionality is active or treat superseded
legacy behavior as permanent replacement-product policy.

## Reading map

| Owner | Read for |
| --- | --- |
| [README.md](README.md) | Overview, actual status and navigation. |
| [docs/TIMESHEET_REQUIREMENTS.md](docs/TIMESHEET_REQUIREMENTS.md) | Selected target behavior and Open/Unverified/Deferred boundaries. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Selected Tkinter/SQLite rewrite, responsibilities, atomic requests, worker/Tk lifecycle, time, files and backups. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Active rewrite Stages 0–6, priorities, gates and reserved decisions; old JSONL Phase 2 acceptance is historical. |
| [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) | Proportional validation scope, evidence requirements and release-qualification boundaries. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Historical product/architecture decision evidence, rationale, provenance and supersessions. |
| [docs/EXPORT_EVIDENCE_CONTRACT.md](docs/EXPORT_EVIDENCE_CONTRACT.md) | Selected precision domains, single weekly quarter-hour algorithm, frozen export/file rules and complete confirmation-integrity semantics; not legacy JSONL machinery. |
| [DESIGN_NOTES.md](DESIGN_NOTES.md) | Actual legacy service/event/storage contracts and limitations; not target rewrite instructions. |
| [RUNNING.md](RUNNING.md) | Python-source setup, minimal pip dependency and native source qualification boundaries. |
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
- Windows source launch: `python .\run_chronicle.py --data-dir PATH --timezone America/Chicago --create`; reopen with `--data-dir PATH` only.
- Runtime dependency: `python -m pip install --only-binary=:all: tzdata==2026.5`.
- Source setup and optional virtual environment: see [RUNNING.md](RUNNING.md); no project build is required.

`pyproject.toml` requires Python 3.11+ and configures pytest's `src` import path.
Use the appropriate existing interpreter/virtual environment. Assess Windows
validation availability for each execution. Linux results do not establish
Windows GUI, NTFS or source-deployment correctness; do not invent CI/release
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

**Local durability:** after completing and validating tracked changes, preserve
the completed semantic unit in a local commit before ending execution. GitHub
availability must never be a prerequisite for creating that commit.

**Expected publication:** GitHub publication is the standing Chronicle workflow.
After a successful local commit, publish whenever the execution environment
provides the necessary Git remote, network access and credentials. The user
authorizes only normal non-force publication to
`refs/heads/feature/chronicle-rewrite` in `rasusmilch/task_time`, as a
workstream-specific exception to the ordinary local-only Codex_guide boundary:

```sh
git push origin HEAD:refs/heads/feature/chronicle-rewrite
```

The first successful publication creates that remote branch; later publication
must advance it normally by fast-forward. `feature/chronicle-projects-timesheets`
is the accepted Stage 0 source/history branch, with handoff commit
`a24aca706740b7e02cc1f856baa194042785bbcb`. Preserve its history and references;
future rewrite tasks must not publish there under this standing workflow.
The handoff identifies the rewrite origin, not a permanently fixed future source
HEAD. Do not automatically merge or rebase either branch.

When hosted Git operations are available, verify the intended repository and
feature branch, inspect the remote for unexpected advancement or divergence,
push the validated local commit normally, and verify the remote result when
supported. Report the local commit and publication outcome accurately. Stop and
report unexpected advancement or divergence; do not resolve it automatically.

When hosted operations are unavailable, preserve the validated local commit and
identify it for later publication. Report that publication was not completed and
why; unavailable GitHub access is not a failure of the completed implementation.
Do not repeatedly attempt unavailable operations. Never reset, clean or discard
validated work because access is unavailable or a push fails.

**Task consistency:** future tasks should inherit this publication rule rather
than restate generic local-only instructions. A generated task must not
accidentally suppress the standing workflow. Identify contradictory publication
instructions rather than silently changing the project workflow. An explicit
user-directed exception may authorize local-only delivery for a particular task.
Generic Codex_guide local-only examples do not withdraw Chronicle's authorization.

**Safety limits:** do not force-push, merge, rebase, push to main, create or modify
PRs, modify unrelated GitHub metadata, or publish to another repository or branch.
This authorization does not extend to other workstreams. Retain completed local
work following any publication failure.

**Independent review:** ChatGPT independently inspects published source and
adjudicates GO/NO-GO. Codex reports the local commit and publication outcome;
receipts, passing tests and a successful push do not establish correctness,
integrated validation, merge readiness or permission to merge.

## Execution receipts

Use compact Codex_guide v4.1 receipts with accurate evidence scope, limitations
and exactly one next action. The raw receipt must have one outer tilde fence:
opening `~~~text`, closing `~~~`. Inside it, use matching separator boards around
`Receipt` at the beginning and `End Receipt` at the end. No local Codex_guide
installation or external static template is required.
