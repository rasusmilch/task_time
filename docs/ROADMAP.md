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
Stage 2B is delivered for independent functional review. Native Windows source operation
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
The subsequent explicit Stage 2A and Stage 2B execution approvals authorize the
bounded connected mixed-work and History outcomes below, not Stage 3 execution.

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

**IN PROGRESS — Stage 2A independently accepted; Stage 2B delivered for independent review.**
Stage 2A connects genuine timed and date-only creation, immutable typed revisions,
closed/date-only correction/deletion services, shared exact main/mini/daily Actual,
task-scoped history/revision reads and all seven persisted week-start choices.
Active-reader completeness is established before exposing manual writers.

Stage 2B connects the modal mixed History browser and inline whole-entry
correction/deletion with immutable revision/deleted-entry navigation. It adds one
consistent detached snapshot, owned standard-library calendar panels, session-only
date direction and exact-request retry through the existing application owner.
Stage 2 is submitted for independent functional adjudication, not declared Complete.
Preserve periods/drafts/session sorting, full-entry identity, unchanged precision,
minute changes and explicit DST resolution.

Gate: all active readers include every exposed work type before a writer becomes
available; no omission or fabricated endpoints. Main/mini/task/project/report
conservation, deleted-work inclusion, complete-entry editing, stale rejection and
UTC/DST behavior agree. Reader/writer delivery may need coordinated slices;
History alone never bypasses that gate. This stage still lacks the complete
Stage 3 POL-R workflow and is not pilot-ready.

## Stage 3 — Core frozen Timesheet AND POL-R reconciliation

**Selected / not implemented in the rewrite.** Explicit This week/Last week/Custom
preview, independent All/Selected tasks, frozen export commit, protected text
publication and saved-report recovery; explicit whole/checked/manual absolute
quarter-hour confirmation, defer/later review, daily Actual/Suggested/Confirmed,
Daily Delta, suggested-entry gap, exact weekly adjustment, Unknown/zero,
stale-prior safety, weekly summaries and required reminder scheduling. Use the
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

**Selected / not implemented.** Interruption/restart, storage faults, second-instance
refusal, supported SQLite backup/independent restore validation, protected schema
upgrades, queued response/shutdown behavior, native Tk and Windows source operation.
Exercise timer → frozen export → absolute confirmation → correction → reconciliation.

Gate: complete core integrity, recovery and restore demonstrated, no data-loss
blocker, truthful uncertain outcomes, no obsolete callback installation after
restore. Integrity testing starts in earlier slices, not here for the first time.
Proportional validation still applies to individual tasks; final integration is
broader than isolated unit success.

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
integration only if explicitly approved. Tags and template/convenience scope must
be inventoried rather than silently carried over or deleted; replacement template
semantics need adjudication before implementation.

Gate: independent acceptance of each optional outcome. Core POL-R is already
complete and validated by Stage 5. No optional limit, unavailable external value
or allocation may prevent recording Actual.

## Dependency constraints and adjudication

| Reserved decision | First affected gate |
| --- | --- |
| Dataset timezone changes | Stage 1 configuration / Stage 2 accounting before affected code. |
| Exact fresh release path, installation/cutover, retired-data cleanup | Before affected deployment and Stage 5 setup; no startup deletion or legacy import. |
| External redistribution authorization and worked-day zero/omitted-entry treatment | Before affected Stage 3 connected official reporting and Stage 5 pilot; mathematical policy is selected, not reopened. |
| Replacement template semantics | Before optional Stage 6 work. |
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
