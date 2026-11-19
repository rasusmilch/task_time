# Chronicle repository instructions

## Authority and actor boundary

The user and ChatGPT own product behavior, architecture, compatibility policy and
acceptance. Codex implements approved work and returns genuinely unresolved material
decisions for adjudication. Current user instructions take precedence over older
repository decisions and tests.

[Requirements](docs/TIMESHEET_REQUIREMENTS.md) own product behavior;
[Architecture](docs/ARCHITECTURE.md) owns implementation boundaries;
[Export evidence](docs/EXPORT_EVIDENCE_CONTRACT.md) owns frozen report, precision,
quarter allocation and absolute confirmation semantics;
[Testing](docs/TESTING_STRATEGY.md) owns evidence applicability;
[Roadmap](docs/ROADMAP.md) owns completion gates;
[Decisions](docs/DECISIONS.md) records current selections and supersessions.
Read the applicable owners before changing behavior.

Chronicle has one current schema-5 SQLite application, one worker/store/transaction
owner and one Tk root. Every task belongs to a real project. There is no migration,
version selector, compatibility application, default project, backup/restore feature
or historical qualification runner. Earlier executable prototypes and decisions are
available through Git history. Do not restore obsolete paths merely to satisfy old
tests. Current tests must use genuine current components for integrated claims.

## Validation and evidence

Use disposable test-owned datasets. Never access or modify personal databases.
Use the existing supported Python environment and source from this checkout.
Run applicable current behavior tests, compile changed Python in memory, inspect
imports/dependencies, check documentation links and inspect the complete patch.
Record commands, exits, logs, failures, skips and unverified checks accurately.
Real Tk tests require an actual display; managed-window tests require a real window
manager. Portable or X11 results do not establish native Windows qualification.
Do not claim a test passed unless it executed. Do not weaken an assertion to hide a
production defect or introduce an unapproved product/architecture decision.

## Documentation

Reconcile affected current-state owners coherently. Root CHANGELOG.md is the sole
cumulative changelog. Historical Git provenance does not require parallel executable
implementations or obsolete runtime tests. Documentation must describe what is
actually implemented and distinguish independent review from implementation.
Stage 4 remains IN PROGRESS. Stage 5 remains NOT STARTED.

## Durability, review and publication

Preserve a completed validated semantic unit in one local commit. Publish normally
when the environment provides the required origin, network and credentials:

```sh
git push origin HEAD:refs/heads/feature/chronicle-rewrite
```

This authorizes only non-force publication to feature/chronicle-rewrite in
rasusmilch/task_time. Verify origin/branch, check remote advancement, and independently
read back the commit, parent, tree and changed-file hashes. Preserve local work if
publication is unavailable. Never force-push, reset, clean, merge, rebase, update main
or unrelated references, modify PRs or deploy under this workflow. Stop and report
unexpected remote advancement rather than reconcile it automatically.

ChatGPT independently reviews published source and evidence. A receipt, passing test
or successful push does not establish acceptance, merge/release or pilot permission.

## Execution receipts

Use Codex_guide v4.1 with accurate scope, limitations and exactly one next action.
Use one outer tilde fence, opening `~~~text` and closing `~~~`, with matching separator
boards around Receipt and End Receipt. No external template installation is needed.
