# Chronicle development roadmap

This owner defines the selected rewrite sequence and completion gates, not
product or architecture alternatives. Read [requirements](TIMESHEET_REQUIREMENTS.md),
[target architecture](ARCHITECTURE.md), [export/POL-R contract](EXPORT_EVIDENCE_CONTRACT.md)
and [testing strategy](TESTING_STRATEGY.md). [Design Notes](../DESIGN_NOTES.md)
describes retained unshipped JSONL source; [decisions](DECISIONS.md) retains chronology.

## Status and gate rules

The active sequence is **Stages 0–6**, superseding the old JSONL Phase 1–6 plan.
Selected does not mean implemented; old component tests do not complete SQLite
stages. Stage 0 is independently accepted Complete for documentation only;
Stage 1 functionality is independently accepted, with native source deployment
qualification separate. Its connected Stage 1A timer slice is accepted at
`897aec2c0d57b6d4aa5c0c5109f55270a4bb1968`. Stage 1B portable reliability is
independently accepted at
`1e84a043c1c055aced9b8c4b000ef766bbf6d178`; its executable-build preparation is
superseded by Stage 1C's standard sqlite3 DELETE/EXTRA and source-only deployment.
Stage 2A is independently accepted at `7bc1bce2894fd5d4ccddbcedfd7ae0f4e7c1323f`.
Stage 2B/complete recording is independently accepted at
`adc09ba0935e8718c4ad2101057af9c6022074cc`, as reported by the later Stage 3A approval.
Stage 3A is independently accepted at `d1e775c33982f109337ec237e3c78e8dc7b56f2e`.
Stage 3B protected file Save/recovery is independently accepted at
`76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`. Stage 3C confirmation is independently accepted for functional development by the
later Stage 3D GO instruction. The later explicit Stage 4A GO instruction records
independent Stage 3 functional acceptance, including Stage 3D. The later Stage 4B
GO independently accepts Stage 4A. The later Stage 4C GO independently accepts
Stage 4B portable reliability. Subsequent independent review accepts Stage 4C
compatibility inspection, protected refusal and bounded owned SQLite-native
rollback recovery for functional development; Stage 4 remains IN PROGRESS.
Native Windows source operation
is required before deployment/pilot, not an unavailable executable-build gate.

Each stage can contain several substantial, independently reviewed tasks. Do not
make every helper a staged feature or authorize the whole rewrite in one task.
Core includes recording **and POL-R**, including confirmation, reconciliation,
summaries and reminders before pilot. Stage 1 is not a complete MVP.

## Stage 0 — Authority reconciliation

**COMPLETE — independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`.** Reconciled behavior,
Tkinter/SQLite architecture, source status, historical supersessions and validation
map. Accepted gate: one coherent current authority set, no JSONL-as-target/Qt
direction, no optional post-pilot POL-R. This completes documentation, not runtime.

The authorized active workstream is `feature/chronicle-rewrite`, created from that
accepted commit. Preserve `feature/chronicle-projects-timesheets` as the Stage 0
source/history branch; normal rewrite publication uses the new branch under
[AGENTS.md](../AGENTS.md). Its origin does not pin the old branch's future HEAD.
The independently reviewed bounded plan led to the explicitly approved Stage 1A
execution. Subsequent substantial slices remain independently reviewed; this
status alone does not authorize later stages or resolve reserved release policy.
The subsequent explicit Stage 2A/2B and Stage 3A approvals authorize the bounded
connected recording and preview/evidence slices below, not later Stage 3 execution.

## Stage 1 — Working timer foundation

**FUNCTIONALLY ACCEPTED — Stage 1A/1B/1C; native source-deployment qualification
remains separate. NOT complete MVP or pilot.**
The functional gate includes fresh SQLite, task/project identities, Start/Stop/Switch,
persisted active timer, main/mini display, worker bridge and direct source startup.
Design immutable frozen-export and absolute-confirmation batches/cells/current-reference
schema and transaction boundaries into the core from the start.

Gate: real recording/reopen path, atomic Switch at one accepted time, active-timer
uniqueness, same-request committed-result reuse and truthful failures. Verify
built-in SQLite DELETE/EXTRA/foreign keys/STRICT constraints (SQLite 3.37.0+) and
UI/worker thread ownership. Integrity
and failure tests start here. The approved clock/sleep/restart and explicit
active-start/uncertain-exit policies are in requirements. Active-start editor
completion now follows matching asynchronous results, retains rejected drafts and
exposes exact reconciliation/exceptional exit within the modal editor. That repair
alone did not complete Stage 1. Stage 1B tests process interruption, committed receipt
reuse, ownership/startup refusal and explicit cleanup retry; it repairs primary
validation diagnostics and ownership retention through failed startup cleanup.
Source launch requires no compiler, project build or executable bundle; pinned
tzdata installs through ordinary permitted pip. Stage 1C removes the obsolete
WAL-specific version floor and executable tooling, retaining transactions and
immutable receipts/evidence. Later independent review accepted Stage 1 functionality.
Actual Windows Python/SQLite/Tk,
NTFS locking, GUI input, exceptions, offline zones, close/reopen and suspend/resume
remain source-deployment qualification before real use/pilot. Linux evidence does
not replace it; lack of the eventual work computer is not a permanent Stage 2 blocker.
Timezone-change policy stays reserved; Stage 1A has no zone-changing operation.
A foundation without POL-R is not core signoff.

## Stage 2 — Complete core work recording

**FUNCTIONALLY ACCEPTED — Stage 2A/2B, complete recording at
`adc09ba0935e8718c4ad2101057af9c6022074cc`.**
Stage 2A connects genuine timed and date-only creation, immutable typed revisions,
closed/date-only correction/deletion services, shared exact main/mini/daily Actual,
task-scoped history/revision reads and all seven persisted week-start choices.
Active-reader completeness is established before exposing manual writers.

Stage 2B connects the modal mixed History browser and inline whole-entry
correction/deletion with immutable revision/deleted-entry navigation. It adds one
consistent detached snapshot, owned standard-library calendar panels, session-only
date direction and exact-request retry through the existing application owner.
The later Stage 3A instruction independently accepts Stage 2 functional recording;
this does not complete core POL-R or qualify a pilot.
Preserve periods/drafts/session sorting, full-entry identity, unchanged precision,
minute changes and explicit DST resolution.

Gate: all active readers include every exposed work type before a writer becomes
available; no omission or fabricated endpoints. Main/mini/task/project/report
conservation, deleted-work inclusion, complete-entry editing, stale rejection and
UTC/DST behavior agree. Reader/writer delivery may need coordinated slices;
History alone never bypasses that gate. This stage still lacks the complete
Stage 3 POL-R workflow and is not pilot-ready.

## Stage 3 — Core frozen Timesheet AND POL-R reconciliation

**FUNCTIONALLY ACCEPTED — independent acceptance recorded by the later explicit
Stage 4A GO instruction, including Stage 3D.** Native/external-policy and pilot
qualification remain separate.
This week/Last week/Custom preview, independent All/Selected UUID scope, exact
full-week suggestions and immutable SQLite registration/list/read are connected.
Preview writes no evidence. Stage 3B adds verified Save/Retry/Copy, owned one-call
overwrite consent, fresh status and Saved Reports recovery without retained widgets.
Registration precedes publication; uncertainty retains the exact request.
Stage 3C implements whole/checked/manual absolute quarter confirmations, Unknown/zero,
complete frozen source and fresh selected-prior validation, individual stale consent,
atomic immutable batches/current references, history and bounded immediate task/day
feedback. Defer writes nothing; uncertainty retains the same Request. Stage 3D
connects comprehensive daily/weekly reconciliation, cross-task summaries, coverage,
current/frozen comparison, full rounding explanations and required reminders in
the same modal Timesheet. Explicit Dismiss for today persists one local date;
startup/relevant commits/rollover/manual recheck coalesce reads, without per-second
reconciliation polling. Functional acceptance does not establish native
qualification or authorize Stage 5 pilot. Stage 4A is separately approved. Use the
single [full-week allocation contract](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation),
including partial Custom and provisional current weeks, not daily Actual rounding
as submission input. This is core submission distribution, not optional budgets.

Gate: exact reviewed bytes and immutable evidence; registration before publication;
retry without recalculation/widget authority; exact weekly ceiling/largest-remainder
examples C–G, earlier-date ties, no zero-work allocation/carryover, full-week frozen
basis and scoped cells. Export-linked confirmation uses frozen suggested quarters:
positive defaults include already-equal values, zeros are explicit, complete
reviewed source includes unchecked cells, and acknowledgements exactly match selected stale conflicts.
Fresh selected-prior changes reject the whole batch; unchecked newer confirmations
need not invalidate checked selection. Partial/zero/defer and compatible A/B
5.00/3.00/+2.00/5.00 and 2.50/3.00/-0.50/2.50 cases retain immutable evidence.
Corrections may reallocate other dates, not historical confirmations. Current
Actual remains exact and independent. Explain rounding without hiding Unknown,
daily allocation mismatch or incomplete coverage behind equal weekly totals.
Previous week checked every application-used local day including
restart/rollover, current week Friday/Monday, explicit Dismiss today. No automatic
confirmation, Reset, timer operation or reminder dismissal on Save/open.

External employer/customer authorization for redistribution and worked-day 0.00
versus omitted/no-entry behavior require validation before the affected connected
official reporting workflow/pilot. Do not mark an unconfirmed zero-suggestion day
reconciled or reopen the approved formula because that boundary is unverified.

These are mandatory core outcomes, not Stage 6 additions. Ordinary default
protection and separately confirmed overwrite both need connected evidence.

## Stage 4 — Stabilization

**IN PROGRESS — Stages 4A–4C independently accepted for functional development.** Online worker-owned
SQLite backup, independent complete image validation and cold restore into new
absent directories are connected. Restore exits before Tk/worker construction;
normal later startup creates a fresh session and preserves the active timer and
all immutable work/export/confirmation/receipt evidence. The original is untouched.
No live/in-place restore, schema change, migration, schedule or registry is added.
Stage 4B extends real transaction/file/backup process-interruption evidence and
complete-fact failure injection, exact uncertainty reconciliation and queued timer
shutdown. Failed independent-probe close retains ownership; authoritative outcome
delivery survives main-status faults and rejects mismatched Request/file context.
Definitive worker stop retains uncertainty without queueing a dead-worker retry.
Representative small/medium/larger measurements preserve complete confirmation
validation; see the [testing inventory](TESTING_STRATEGY.md#portable-operational-measurements).
Stage 4C adds cold read-only compatibility inspection, exact current-schema/literal
signatures, complete startup receipt validation and protected refusal before adoption,
backup verification or restore reservation. Ordinary startup admits genuine hot
DELETE rollback journals into exclusively owned SQLite-native recovery, then
requires complete validation before readiness; cold inspection remains read-only
and non-recovering. Stage 4C acceptance includes this bounded recovery repair.
Unit A's provisional filesystem repair is accepted for portable development;
Unit B's collector and evidence-safety repair are accepted for limited native
MetadataProbe use. Windows qualification is NOT COMPLETE. The accepted integration
coverage audit identified no material missing portable cross-boundary coverage
at its flat-schema baseline. B1 separately exercises changed v2 boundaries. See
[acceptance provenance](DECISIONS.md#stage-4c-and-portable-tooling-acceptance).
B1 originally introduced schema 2. E now implements exact fresh schema 3 for
independent review, with the same application ID; versions 1/2 refuse without
transformation, replacement or compatibility mode. Stage 4C's historical future-transition safety contract is not
a hierarchy migration requirement; no migration engine is active. B2 movement is implemented for review.
C1 Archive/Unarchive/Archived Items and C2 unused-only Delete are accepted for
functional development. D nested active management UI is delivered for independent
review at their original delivery; E templates are independently reviewed on fresh schema 3.
Remaining stabilization and the complete gate include actual native Windows source/
NTFS, operator GUI/modal/focus, backup/restore, hot-journal recovery, actual
suspend/resume and deployment qualification. Any hypothetical future data-preserving
transition would require separate approval; hierarchy instead starts fresh. Exercise timer → frozen export → absolute
confirmation → correction → reconciliation → backup → cold restore/new session.

The bounded source-startup usability slice adds first-run local folder/readable
zone setup and zero-argument remembered reopening, with unchanged explicit CLI and
recovery contracts. Its native Windows first-run/timezone suggestion/chooser/focus
and reopen evidence remains pending independent qualification. Prior automated
qualification retains its recorded limits and does not qualify this new UI.

Gate: complete core integrity, recovery and restore demonstrated, no data-loss
blocker, truthful uncertain outcomes, no obsolete callback installation after
restore. Integrity testing starts in earlier slices, not here for the first time.
Proportional validation still applies to individual tasks; final integration is
broader than isolated unit success.

## Hierarchy target — bounded packages A-F

**A/B1/B2/C1/C2/D/E ACCEPTED FOR FUNCTIONAL DEVELOPMENT; F DEVELOPMENT DELIVERABLE FOR REVIEW; NATIVE GATES PENDING.** The later explicit hierarchy-design
instruction selects tree-oriented main/mini, three task levels, branch management
and nested templates. It supersedes their earlier Open/Stage 6 template placement.
This is a proposed execution sequence for separately reviewed tasks, not permission
to begin them or a declaration of complete Stage 4/5. Requirements own the behavior;
[architecture](ARCHITECTURE.md#fresh-hierarchy-foundation) owns B1's implemented
fresh model and the separately proposed later operations. Current runtime supports
only schema 3; historical schema-1/2 evidence retains its original limits, with
applicable regression rerun on fresh v3 fixtures.

| Package | Bounded implementation and dependencies | Review/acceptance gate |
| --- | --- | --- |
| A — Main/mini restoration on flat data | Delivered for independent review: Project → Task/empty groups/Unassigned, existing project-scoped New Task and selected-project rename. Restore visible state colors/text, Show Main, Keep Mini Open, shared Today/This Week Individual/Cumulative columns, minute-boundary repaint and immediate refresh using existing services. Keep Mini Open defaults Off/session-local; Show Main retains mini only when On; Sort A-Z is initially session-local. With no descendants, Cumulative equals Individual. Do not imply hierarchy, archive or templates work yet. | Same accepted timer/worker accounting, no row churn for unchanged data, modal focus/grab protection, clock/date/unavailable detection, close/reopen, actual Tk input. No persistence/schema changes merely for presentation. |
| B1 — Fresh hierarchy/recording foundation | Implemented for independent review: exact schema 2/application ID 0x4348524E; parent adjacency, three levels under projects/virtual Unassigned, reviewed child creation without parent version increment, leaf-only new work, retained parent History and derived Individual/Cumulative. Explicit archive fields exist without lifecycle actions. Finite administrative/protected receipt classes and survivor creation/version verification; no retirement service. | Fresh/empty creation; unchanged clean-v1 refusal; full DDL/integrity/forest/receipt/work/export/confirmation validation and backup/restore; native rollback recovery retained. No migration, subtree movement, lifecycle, templates or nested end-user workflow. |
| B2 — Structural movement | Implemented for independent review: one frozen complete subtree request, current source/destination checks, guard-respecting detach/project-update/reattach transaction, changed-row-only versions and one exact administrative receipt. Schema 2 unchanged; no movement UI. Retain UUID/direct work/frozen evidence. | Cycles/depth/project/Unassigned consistency, all-or-none subtree effects, stale/uncertain receipt handling and complete independent validation. No implicit Stop. |
| C1 — Reversible lifecycle and Archived Items | Implemented for independent review on unchanged schema 2: four typed Archive/Unarchive services, selected-only timestamps/versions, chronological archive/move/active validation and modeless full-depth Archived Items with four sorts/direct History. No Delete control. | Active-containing Archive refusal; independent/inherited state, nearest timestamp/DST, no-op/exact retry/uncertainty, main/mini/modal ownership, in-place selection/expansion, backup/cold restore and full regression. Native changed UI remains unqualified. |
| C2 — Irreversible unused-only Delete | Implemented for independent review on unchanged schema 2: worker preview, exact frozen review and typed DELETE, finite retirement/survivor proof, deepest-first atomic deletion and full retained-image equality/validation. No Archive prerequisite or persistent Delete receipt. | Scope/counts/cannot-undo warning, typed DELETE and final closure recheck. All-or-none unused-row/exclusively owned administration removal; protected references/unresolved dependencies refuse. No recoverable tier, tombstones or deletion ledger. |
| D — Connected main/archived hierarchy trees | Implemented for independent review on unchanged schema 2. Connect A presentation to B1/B2/C snapshots/services: context New Task, project distinctions, active ancestors, direct History, management, full expansion and targeted structural refresh in both trees. | Selected UUID/expansion survive sorting and ordinary refresh while visible. Archived Items sibling/top-level Name A–Z/Z–A and Date Archived Newest/Oldest, newest default, deterministic ties. No flattening/duplicate identities, double count, flicker or recording eligibility from archived selection. Existing modal main/mini ownership remains. |
| E — Nested templates | Implemented for independent review on fresh schema 3 after accepted B1/B2/D: connect Create/Edit/Duplicate/Archive/Unarchive/actual Delete/Apply. Preserve active trim/casefold name uniqueness and atomic fresh task UUID insertion. | Nested depth/active destination guards, duplicate project/task names allowed, conflicting Unarchive-name refusal, no merging/copied work, applied instances unchanged. No soft-delete template tier, tombstones or silent loss of retained request/evidence references. Protected retained requests still retry exactly. |
| F — Target integration and native qualification | Dedicated connected schema-3 worker/SQLite and callback/XTest suites, independent C–G expectations, lifecycle/erased-provenance and temporal/restart scenarios; unchanged production code. Separate opt-in full-source Windows wrapper and supervised operator/Sleep runbook prepared. | F1 portable evidence remains distinct from native acceptance. The original October 30 F2 attempt at `56b4e4451d8c738f70d23938c2f60be009d61a84` remains EVIDENCE_INCOMPLETE. The later 19:10:50 UTC evidence reports 1,922 supported completed (1,816 pass/15 fail/91 skip), 1,905 legacy NOT RUN after inventory refusal: F2 FAIL. Bounded test/tooling corrections add deterministic legacy parameters, exact mismatch evidence, PowerShell capture and History/focus observation; native root causes remain unverified, all 29 unresolved skips remain open. Independent review precedes a new complete native run. F3 operator and F4 actual Sleep remain NOT RUN. Exact revision/inventory/JUnit/cleanup and verified artifact delivery required; historical results cannot qualify changed source. No Stage 4 completion/pilot/cutover follows without adjudication. |

Package D connects the accepted A/B1/B2/C1/C2 foundations to full active hierarchy,
context-sensitive child creation, reviewed Move / Reparent and existing lifecycle/
direct History. E delivers nested templates; F complete changed-product/native
qualification remains outstanding. No migration, further schema change or installation
approval follows. Stage 4 remains IN PROGRESS; Stage 5 is NOT STARTED.
Keep each package coherent rather than one helper per task.

All packages preserve SQLite/worker/file protection and the exact Actual/frozen/
confirmed boundary. Fresh schema creation never deletes, transforms or reuses old
database files. Entity Delete is not dataset-file cleanup. The final owner decision
supersedes the former soft-delete/Deleted Items/Permanent Delete and tombstone
plans. Only Archive (with Unarchive reversal) and unused-only irreversible Delete
are selected. The finite administrative deletion allowlist,
closure/survivor proof, stale/uncertain handling and complete validation are now
implemented by C2 on unchanged DDL; E resolves referenced-template Delete through retained self-contained snapshots
and the explicitly limited erased-provenance contract. Fully erased
administrative requests deliberately have no exact historical retry promise; retain
normal guarantees for every surviving/protected request. Add no permanent identity
registry or deletion ledger. See [remaining decisions](TIMESHEET_REQUIREMENTS.md#open--reserved-userchatgpt-decisions).
Stage 4 remains IN PROGRESS; Stage 5 NOT STARTED. Native qualification, external
reporting policy, installation/cutover and optional allocation decisions remain
separate. No backup/copy rewrite or secure-byte-erasure guarantee is selected.

## Stage 5 — Complete core pilot

**Selected / not started.** Use a deliberately fresh dataset for daily main/mini
timing, manual work/corrections, frozen exports, whole/partial/zero/manual POL-R
quarter-hour confirmation, Unknown, daily/weekly reconciliation, reminders and
restore. Exercise full/partial-week reporting, provisional suggestions and their
changes after correction, explained upward adjustment, daily allocation agreement
and confirmation coverage, including worked dates with zero suggestion.

Gate: representative reporting-week end-to-end workflow without counting errors
or UI workarounds, on the qualified native deployment. External redistribution
and zero-entry treatment must be validated; correct mathematics alone is not
employer/customer compliance evidence. **No core signoff when
POL-R reconciliation/confirmation/reminders are absent.** Optional allocations
are not a pilot gate. Independent review and actual platform evidence are required;
passing tests or a source-launch smoke alone are not release approval.

## Stage 6 — Optional expansion

**Reserved / separately prioritized.** Allocations only after recurrence/override/
control decisions, separately approved conveniences, and future external POL-R
integration only if explicitly approved. Tags and other conveniences remain
separately inventoried. Nested hierarchy templates now belong to the approved
target packages above, not an unresolved optional Stage 6 carryover. Their lifecycle
defaults follow the final Archive/Delete model; referenced-template deletion
dependencies, precise fresh DDL and the bounded administrative Delete/receipt
design still require independent technical adjudication.

Gate: independent acceptance of each optional outcome. Core POL-R is already
complete and validated by Stage 5. No optional limit, unavailable external value
or allocation may prevent recording Actual.

## Dependency constraints and adjudication

| Reserved decision | First affected gate |
| --- | --- |
| Dataset timezone changes | Stage 1 configuration / Stage 2 accounting before affected code. |
| Exact fresh release path, installation/cutover, retired-data cleanup | Before affected deployment and Stage 5 setup; no startup deletion or legacy import. |
| External redistribution authorization and worked-day zero/omitted-entry treatment | Before affected Stage 3 connected official reporting and Stage 5 pilot; mathematical policy is selected, not reopened. |
| Unused-only Delete engineering and exact fresh schema/DDL | Before B/C: finite administrative allowlist, closure/cross-entity/survivor proof, transaction order, stale/uncertain handling and independent validation, without tombstones/ledger. Selected lifetime limit for erased requests is not reopened. |
| Referenced-template actual Delete dependencies | Before E; no hidden recoverable deletion or silent removal of retained references. |
| Allocation controls, defaults/overrides and week-change effects | Before optional Stage 6 work. |

Return material choices to user/ChatGPT. These do not reopen Tkinter/SQLite or
justify postponing core POL-R. No migration, compatibility layer, dual authority,
new framework or data cleanup is implied. Existing user files stay protected.

## Historical JSONL evidence — not rewrite completion

The former **Phase 2 bounded export/confirmation/daily-reconciliation service gate
was independently accepted Complete**, under serialized JSONL dataset ownership.
That acceptance remains historical evidence; it is not revoked or transferred to
SQLite. Old Phase 3 was In Progress and the old replacement workflow was not
complete. The old phase sequence is superseded as the active plan.

Current source has main/mini mixed Actual, production read-only Work History and
frozen modal Timesheet, plus staged timed-correction and absolute confirmation
services. See [Design Notes](../DESIGN_NOTES.md) for exact current contracts.
Those tests and implementation are useful semantic evidence, not transaction,
worker, inline-editor or complete POL-R UI qualification of the rewrite.
