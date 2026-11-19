# Chronicle architecture

## One current application

The user selected one schema-5 application and withdrew multi-version compatibility,
legacy runtime preservation and the backup/private-recovery workstream. There is
one Tk root, StartupWindow handoff, ChronicleApp, serialized DatabaseWorker,
SQLiteStore, transaction owner, service facade and current semantic verifier.
No adapters preserve old tests. No schema policy/selector, migration/import,
alternate application, backup/restore CLI or qualification collector remains.

## Schema and ownership

[schema.py](../src/chronicle/schema.py) contains the accepted 65-statement schema-5
SQL definition, application ID 0x4348524E, exact structural/profile verification,
STRICT tables, foreign keys and guards. Tasks and frozen export tasks require real
project foreign keys. Root projects may have parent_project_id=NULL. No default
project, virtual task container, schema selection or parallel DDL exists.

[SQLiteStore](../src/chronicle/sqlite_store.py) owns one built-in sqlite3 connection
on its worker thread. DatasetLock excludes another writer. DELETE journaling,
synchronous EXTRA and foreign_keys=ON are the current profile. Fresh creation is
explicit, requires a new/empty folder and uses standard SQLite atomicity. Existing
files must match the current identity/layout and complete semantics. There is no
private paired-copy recovery, legacy classification, conversion ledger or automatic
replacement. The application never creates weekly databases or deletes data on a
schedule. Standard SQLite journaling handles current transactions.

## Transactions and exact Request reconciliation

The store issues BEGIN IMMEDIATE, verifies prior current state, resolves canonical
Request identity/content, invokes domain operations, inserts the canonical non-Delete
receipt, verifies the final state and commits. Rejected operations roll back. Unchanged
operations have no receipt. Domain functions require an active transaction and matching
dataset; they never open, begin, commit, roll back or close a connection.

The existing immutable Request/Outcome/Message protocol remains. A committed exact
Request returns its receipt without a second effect; conflicting content refuses.
A lost COMMIT acknowledgement remains unverified until explicit original-Request
reconciliation establishes the committed receipt or absence. No blind retry occurs.
Delete is separate, unused-only and no-receipt; an uncertain attempted commit blocks
further mutation and cannot be reconciled by presence or automatically retried.
Connection shutdown/rollback and lock release remain on the owner thread.

## Service and verification authority

[RuntimeService](../src/chronicle/services.py) is the sole application facade for
reads and mutations. [operations.py](../src/chronicle/operations.py) selects concrete
current domain operations; project/task/lifecycle/template/recording modules contain
one implementation of their algorithms on the caller's connection. Read snapshots
reuse the same accounting, History, Timesheet, POL-R and reminder functions. No
version context or test-owned transaction coordinator participates in production.

[evidence.py](../src/chronicle/evidence.py) supplies complete current semantics:
canonical receipt inventory/classification, creation ownership, chronology, versions,
active/leaf/archive eligibility, immutable work/revisions/corrections, frozen report
basis/bytes, absolute confirmation chains/current pointers, configuration and receipt
high-water. [administration.py](../src/chronicle/administration.py) independently
reconstructs retained current administrative events without calling mutation services.
This exists for current correctness, not old-format compatibility. Protected reports
and confirmations are checked by [reporting.py](../src/chronicle/reporting.py).
Delete reviews complete scope/dependencies and independently verifies survivors.

## Worker, startup and views

The worker initializes the actual store and service before publishing verified
schema-5 readiness. It alone consumes requests and owns SQLite/lock shutdown. Only
matching verified readiness lets StartupWindow hand the same root to ChronicleApp.
There is no synthetic candidate-ready path or presentation selector. The source
launcher has ordinary setup and explicit --data-dir/--create/--timezone only.

Main uses the nested real-project projection, UUID-backed rows, task depth independent
of project depth, session sorting and existing recording controls. Mini consumes
that same owner/state. Archived Items keeps real ancestry. Task and project Move
remain distinct reviewed operations. Template Apply has only real-project/task
choices. TaskCreationWindow owns a Toplevel/editor slot, local grab, exact focus
origin, explicit project review and one submission through ChronicleApp. Its Create
Project route disposes it before invoking normal project creation.

## Timesheet shell and token ownership

One TimesheetWindow has persistent four-section navigation, an exclusive expanding
content host and permanent footer. Temporary source/manual reviews use one bounded
return context (dataset/report, origin, applied reconciliation scope and semantic
selection). No persisted navigation history or second modal/worker is added.
Read tokens bind owner/mode/dataset/report/task/date/batch/observation. Failed or late
reads cannot mark partial output current. Known committed confirmation survives
subsequent presentation failure. Modal/grab cleanup uses exact live Tk object
identity, with ordinary focus_set and root fallback; no forced foreground input.

## Absolute confirmation

Manual/source confirmation uses the same whole-batch validator and transaction owner.
Unknown, explicit zero, absolute quarters, reviewed priors and individual stale
acknowledgements remain distinct. Current reconciliation does not rewrite frozen
reports. The [export evidence contract](EXPORT_EVIDENCE_CONTRACT.md) owns arithmetic
and immutable content; [requirements](TIMESHEET_REQUIREMENTS.md) own workflow.

## Validation boundary

Current tests use genuine schema-5 stores, workers, services, StartupWindow and Tk.
Pure calculation tests make no integrated/platform claims. Managed X11 is separate
from native Windows evidence. No native qualification, release or pilot follows
from this cleanup. See [Testing](TESTING_STRATEGY.md).
