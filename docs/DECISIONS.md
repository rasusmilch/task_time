# Chronicle Architectural and Product Decision History

## Purpose and authority

This document is **HISTORICAL EVIDENCE**: established decisions, their provenance,
design purpose, corrections and unresolved questions. It is not current-state
product authority. The [product contract](TIMESHEET_REQUIREMENTS.md) states what
Chronicle is currently required to do; readers need not reconstruct that from
this history. [ARCHITECTURE.md](ARCHITECTURE.md) owns the current selected rewrite;
[Design Notes](../DESIGN_NOTES.md) describes legacy implementation,
[ROADMAP.md](ROADMAP.md) owns sequencing/gates, and
[TESTING_STRATEGY.md](TESTING_STRATEGY.md) owns validation. Historical project
changes belong to [CHANGELOG.md](../CHANGELOG.md).
The approved [export evidence contract](EXPORT_EVIDENCE_CONTRACT.md) owns the
frozen-export, decimal, verification/recovery and absolute batch semantics.
The later Tkinter/SQLite entry below supersedes JSONL technical mechanisms,
constructor/modal sequencing, nested correction and retained-widget recovery
where earlier approvals selected them; it does not rewrite their provenance.
The later quarter-hour entry below supersedes daily-Actual-as-Enter and arbitrary
hundredth POL-R units while restoring existing confirmation-integrity guarantees.
It does not supersede exact Actual, frozen evidence or explicit confirmation.

The user and ChatGPT approve product/architecture choices. Codex records and
implements approved work; recording a choice does not make Codex its approver.
Product choices below are explicit user confirmations preserved in the approved
contract. The later snapshot-first and decimal-hour direction is directly
user-approved; its concrete technical contracts were selected by ChatGPT under
that direction. Entries distinguish those provenances. Corrections and
supersession identify their separate evidence.
Source observations establish execution, not approval of target policy.

Precise decision dates are not established here and are omitted. Commit dates
are not decision dates. Unsupported quotations, rejected alternatives and
proposal origins are omitted. A user-approved ChatGPT
recommendation is distinct from direct user selection; that provenance requires
evidence of both the recommendation and acceptance, not an assistant proposal
alone. This record does not infer it where the available evidence establishes
only the approved result.

Entry statuses are `current`, `open`, `superseded`, `rejected`, `retired`,
`implementation-only` or `proposal`. `current` means an approved active choice,
not necessarily an implemented feature. Deferred implementation and Unverified
external facts retain their classifications in the product contract.

## Material product and architecture decisions

### Replacement installation and fresh data

**Status:** current. **Provenance:** explicit user confirmation and replacement
clarification; current owner:
[replacement/data boundary](TIMESHEET_REQUIREMENTS.md#selected--replacement-installation-and-data-boundary).

The redesigned local Windows-friendly application replaces the legacy workflow
and installation rather than maintaining a permanent parallel interface. It
starts with fresh timekeeping data, without task, interval, submission or template
migration. Existing files remain protected during development; replacement does
not authorize deletion. Exact release cutover is still open. The clarification
and its limited historical meaning are recorded below.

### Independent task ownership and organizational projects

**Status:** current. **Provenance:** explicit user confirmation of the reviewed
project/task architecture; current owner:
[independent projects/tasks](TIMESHEET_REQUIREMENTS.md#selected--independent-projects-and-tasks).

Projects organize but own no direct time or timer. Independent UUID-based tasks
own work, may be Unassigned or belong to one project, and may share display names.
POL-R identification is by task name, not invented external numbers. Moving a
task preserves its work and identity; current membership groups all historical
work. Informational project sums are never additional hours. The established
purpose is to preserve task-level accounting and prevent double counting or loss
of independent task time.

### Genuine intervals and date-only amounts

**Status:** current. **Provenance:** explicit user rejection of synthetic duration
endpoints and confirmation of the date-only model; current owner:
[actual-time records](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records).

Timed work has genuine endpoints. A manual duration declares a task, date and
amount, not a start/stop time; the full amount belongs to that date. Corrections
and deletions change effective work while retaining historical evidence.
Historical date-based Actual survives logical counter resets. Manual amounts
are not evidence of clock positions: a 14-hour Saturday entry stays Saturday.
The rejected representation remains a legacy source artifact, described below.

### Mixed history and removal of replacement reset counters

**Status:** current except the persistence clause superseded by the later
application-session direction decision below. **Provenance:** explicit
user-approved replacement behavior supplied with the mixed work-history reader
instructions; current owners:
[Actual records](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records) and
[mixed history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

Normal history combines current effective intervals and date-only entries,
independent of resets. Timed work crossing midnight appears as linked daily
segments of its underlying interval; segment editing/deletion acts on that full
interval, with affected-date deletion warnings. Editing preserves entry type;
earlier versions/deletions remain accessible through audit/details. Current week
is the UI default, with custom dates and All history. At that approval, date
direction was a single user-wide persisted preference, initially newest first,
switched through the date-column header; the persistence clause is superseded
below. Exact link-marker styling was left undecided at that approval; the later
standalone-table approval below resolves it.

The explicit direction removes replacement Reset actions and resettable counters.
It narrows the earlier reset-independence wording so it cannot imply a requirement
for replacement counters; the earlier guarantee that historical Actual survives
legacy resets remains true. No earlier approved replacement-counter decision is
established by that wording or by legacy source. POL-R stays per task/day.
The staged projection is implementation evidence, not approval or delivery of
the future UI, preference, editing, audit or production reset-removal work.

### Calendar Actual production displays

**Status:** current. **Provenance:** later explicit user approval in the production
Actual-display implementation instructions, following the read-only reader
inventory; current owner: [calendar Actual displays](TIMESHEET_REQUIREMENTS.md#selected--calendar-actual-displays).

Main task rows show own Today and This week, including parents without descendant
roll-up. Mini-mode shows Today. Application totals include retained deleted-task
work. All use one application-refresh observation and the complete containing
calendar week (currently Sunday-start). Timed work is cutoff-capped; whole-date
amounts retain their dates, including later dates within the week. Failed
calculation shows — with one inline error per window, preserves Start/Stop and
recovers on a later normal refresh. This later approval specifies display choices
not established by earlier labels or reset-sensitive source. It activates readers
only; remaining exports/readers still block dated-writer activation. It selects no
migration, cutover, configurable-week setting or production POL-R integration.

### Minute-only replacement clock input and daylight-saving choices

**Status:** current. **Provenance:** explicit user approval supplied with the
staged timed-input validation instructions; current owner:
[Actual-time records](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records).

Replacement timed-work entry, editing and display use minutes, with separate
start/end dates and times. Repeated local times require explicit first/second
occurrence selection in chronological UTC order; nonexistent local times are
rejected. Genuine elapsed ordering uses resolved UTC endpoints, without guessed
overnight rollover or gap adjustment. This approval selects input/display
behavior, not a billing-rounding rule or conversion of earlier recorded work.
Existing raw-precision accounting remains binding. The staged pure validators
do not establish delivery of the replacement editor, writer or display.

### Closed timed corrections and unchanged recorded precision

**Status:** current for behavior; replacement-interval/journal mechanism superseded by
the later Tkinter/SQLite decision. **Provenance:** explicit user-approved behavior and
ChatGPT architecture adjudication supplied with the staged timed-correction
instructions; current owner: [Actual-time
records](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records).

Unchanged saves write no event. Changing one endpoint preserves the other;
comments are optional and attach to actual time corrections, not standalone
comment edits. Ordinary editing is for closed genuine intervals. Reviewed-entry
changes reject the save; original/replacement values and correction time stay
auditable. Minute-only controls do not authorize rounding existing precision.
These Selected rules differ from legacy required-reason and endpoint handling;
they neither change the active legacy mutators nor establish an earlier approved
replacement-editing policy.

At that approval, the selected mechanism reused `interval_edited` and its replacement identity.
A detached prepared event retains both identities through uncertain appends;
authoritative replay and journal synchronization establish registration before
projection installation. No revision token, operation store or new event/schema
is selected. This foundation does not activate record-editor UI or dated writers.

### Mixed-history table presentation and related-portion feedback

**Status:** current. **Provenance:** explicit user approval supplied with the
standalone mixed-history table instructions, after the history-reader planning
review; current owner: [mixed history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

The later approval resolves the earlier presentation questions: minute clocks
include a differing endpoint date and actual UTC offsets for repeated minutes;
durations show completed whole minutes, with 0:00 for zero and <1 min for positive
sub-minute work. Raw amounts and endpoints remain unchanged. Linked portions show
↔; selecting a portion highlights its other visible task/kind/entry portions
without selecting them or performing edits. Running portions remain task-scoped;
dated entries do not link. No routine explanatory text is added.

This selects standalone rendering and visual feedback, not browser controls,
preferences, editing/deletion, production activation or removal of legacy Reset.
It establishes no earlier approval of the previously undecided styling, no billing
rounding and no new persistent identity or state.

### Standalone history browsing and global direction scope

**Status:** current for browser interactions; the global/persistence clause is
superseded by the application-session decision below. **Provenance:** explicit
user approval supplied with the single-task history browser instructions after
the browser planning review;
current owner: [mixed history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

The later approval specifies loading on opening, Apply, Current week/All switches
and explicit Refresh. Current week uses seven local dates from a caller-supplied
weekday, initially Sunday, and rolls over on refresh. Sorting reorders existing
rows without new work/cutoff capture; within-day order stays fixed. Custom typed
and calendar-picked drafts require Apply; Refresh uses committed period/dates.
Failures retain drafts and truthful last-successful information, preserving the
table's preparation-versus-widget failure boundary. Successful replacement or
sorting clears selection. No polling or automatic data refresh is selected here.

At this approval, the earlier user-wide direction requirement was clarified as
global across tasks and datasets for the same computer account, initially newest first and persistent
across restarts. The browser then staged only an initial argument and local
direction; storage ownership/cross-window coordination were not selected by that
approval. The later application-session decision below discards this persistence
requirement and the account-global persistence proposal. No production callers
were activated and no legacy timeline was retired. This clarification established
no earlier approval of account-global storage or change to the configurable-week
gate.

### Application-session history direction and single-window ownership

**Status:** current. **Provenance:** latest explicit user decisions supplied with
the session-only replanning and application-owned handoff instructions; current
owner: [mixed history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

Each new application owner starts newest-first. Successfully rendered direction
changes are remembered across subsequent history openings for different tasks
and datasets in that running session. Browser closure does not reset the choice;
application restart does. This supersedes the earlier history-direction
cross-restart/account-global persistence clauses above. The discarded persistence
proposal supplies no storage, failure, recovery or lifecycle requirements. No
preference file, account-location resolver, settings field or cross-process
coordination is needed.

At that approval, at most one history window could be open per application, but
behavior for an attempted second opening was not selected. The later modal
approval below resolves it. The unrouted browser factory and post-success
callback did not activate history routing or enforce that window rule.
Notification failure preserves the completed sort and reports inability
to remember direction without rollback or automatic retry. Other approved
browser interactions, Phase 3 dependencies and Open matters are unchanged.

### Modal owned history browsing

**Status:** current for modality/task binding; blocking window-wait mechanism superseded
for the rewrite. **Provenance:** explicit user approval supplied with the staged
application-owned modal history-window instructions, after session direction and window
planning review; current owner: [mixed
history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

History blocks main-application interaction until closed, stays attached to its
original task, and supplies browsing controls and Close without main-window
Start/Stop functions. Timers continue unchanged. Close history before using the
main application or selecting another task. Duplicate/reentrant opening requests
have no effect: no new window, retargeting, replacement or refresh. This resolves
the earlier unselected repeated-opening behavior without attributing modality
or that behavior to the earlier session-direction approval.

The staged wrapper is constructed before modal presentation, allowing application
ownership to be published before a local grab/normal Tk window wait. Identity-
checked destruction cleanup and a construction guard protect that opening path.
The approval activates neither production timeline route and does not establish
production-wide enforcement; editor/audit and other Phase 3 work remain separate.

### Originating-parent history return prerequisite

**Status:** historical/current legacy implementation; target return principles retained
with callback-driven presentation. **Provenance:** later explicit architecture
adjudication supplied with the originating-parent/modal-return implementation
instructions, after production-access planning. Technical owner: [owned history
window](../DESIGN_NOTES.md#owned-modal-history-window).

The application owner selects and validates the live originating top-level and
captures its local grab and focus. The history shell owns its own widgets/grab
and rechecks acquisition after visibility processing. The owner restores eligible
captured context only after disposal, outside destruction callbacks, while the
opening guard remains active. Destroyed origins are not recreated or redirected;
competing live grabs and their focus are left alone. Return restores only a
previous local parent grab and uses ordinary focus, without forced activation.
Unexpected restoration failures propagate; an earlier construction/presentation
failure remains primary with additional diagnostics retained.

This approval extends the staged shell without production routing. It does not
authorize changes to task-editor drafts or its unrelated recursive lifecycle,
choose production access locations/transitional editing access, or select
legacy-dataset applicability. No modal-stack framework or new durable mechanism
is approved or needed. Earlier modal/session approvals retain their chronology.

### Replacement Work History access

**Status:** historical/current legacy routing; recursive metadata-editor route
superseded as target navigation. **Provenance:** explicit user approval supplied with
the replacement Work History integration instructions, after acceptance of the
originating-parent prerequisite. Current owner: [mixed
history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

Both former Edit Timeline commands become Work History, using the application
owner and each originating top-level, including recursive task editors. The
fresh replacement has no migration/backward-compatibility requirement and no
temporary parallel legacy history UI. Old timeline presentation and its editing
controls are retired; replacement creation, correction/deletion, missed-stop UI
and audit remain separate outcomes. This later approval resolves the previously
unselected production access/transitional-retention boundary; it does not
retroactively attribute activation to the earlier staged approvals.

Read-only access preserves the accepted browser, session direction and modal
return contracts. Launch failures are inline at their origin with original Tk
diagnostics; unsupported synthetic work is a visible reader error, never a
fallback or silent omission. No user files are removed, no dataset is converted,
and installation/data-directory cutover and unrelated Open matters remain Open.
History access alone does not satisfy the Phase 3 active-reader gate.

### Local dates and configurable reporting weeks

**Status:** current. **Provenance:** explicit user confirmation; current owner:
[week convention](TIMESHEET_REQUIREMENTS.md#selected--configurable-week-convention).

Actual work is assigned to local dates; genuine elapsed intervals split across
midnight/week/DST boundaries. Any weekday may start reporting weeks, initially
Sunday. Changing it reorganizes weekly presentation without changing work dates,
amounts or daily confirmations. Saved exports retain their original convention.
Fixed Sunday calculations are current implementation, not permanent target policy.

### Separate Actual, Exported and Confirmed POL-R evidence

**Status:** current for semantic separation; mandatory event-backed storage superseded
by SQLite. **Provenance:** explicit user confirmation; current owners: [three-record
distinction](TIMESHEET_REQUIREMENTS.md#selected--actual-exported-and-confirmed-pol-r-are-distinct),
[saved exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports) and
[evidence
integrity](TIMESHEET_REQUIREMENTS.md#selected--confirmation-evidence-and-batch-integrity).

Actual is derived work; Exported freezes the task/day amounts and reporting
context of a saved timesheet; Confirmed POL-R records absolute external totals
explicitly confirmed by the user. Neither evidence type creates additional work;
saving does not confirm external entry. The selected model requires immutable
event-backed saved-export and confirmation evidence, auditable earlier records,
whole-batch validation without partial commitment, and derived Delta/outstanding
values rather than independent balance counters. Event and recovery questions
previously reserved for adjudication are now selected in the
[technical contract](EXPORT_EVIDENCE_CONTRACT.md). The staged file-only service
does not fulfill immutable export registration merely by publishing text.

### Frozen preview and eventual Timesheet export replacement

**Status:** current. **Provenance:** later explicit user approval supplied with
the standalone timesheet-preview implementation instructions; current owner:
[preview and saved exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports).

One eventual Timesheet window replaces shipped exports, with This week/Last week/
Custom periods, typed/calendar dates, and All or independently selected task UUIDs.
Retained deleted work remains reportable. Save publishes the exact frozen preview;
changing dates or selection requires another preview even after backtracking.
No automatic submission, confirmation, Reset or post-export deletion is selected.
That approved first component prepared and displayed only an unregistered candidate,
without Save/retry or production routing. It retained the then-existing export
routes until replacement was ready; the later modal approval below replaces them.
This earlier approval did not activate dated writers or choose
remembered paths, restart policy, configurable weeks or installation cutover.

### Standalone frozen-export Save/retry

**Status:** current for frozen saving; event-registration and instance-retention
mechanics superseded for the rewrite. **Provenance:** later explicit user approval
supplied with the standalone saving/retry implementation instructions. This extends the
earlier preview-only component approval without changing its historical boundary.

Compose the accepted preview with existing registration and verified
materialization services. Save publishes the reviewed event unchanged, with an
explicit destination, after verified registration. Uncertainty retains exact
retry inputs; every retry re-registers the same event before publication. Lock
preview editing after the first registration attempt; no recalculation or
confirmation/submission/checkpoint/timer effects are authorized. Matching copies
may be reused; that approval required another path for conflicts (superseded by
the later explicit-overwrite approval below). Completion follows
only a successful materializer return and survives later presentation failure.

The approved standalone component's single-operation instance and deep-copied
in-memory attempt handoff do not select permanent Timesheet-window lifecycle,
Close behavior, path memory or restart recovery UI. Production routing and Close
behavior were selected later below, not by this standalone approval. General
recovery UI, dated writers and installation cutover remain outside this approval.

### Explicit confirmed frozen-export replacement

**Status:** current. **Provenance:** later explicit user approval and ChatGPT
architecture adjudication supplied with the explicit-overwrite implementation
instructions. This narrowly supersedes the earlier blanket no-overwrite clause,
without changing ordinary Save/Retry or the separate file-only save API.

After a fully inspected stable regular-file content conflict, the standalone
Save component offers a separate default-cancel confirmation naming the exact
destination. Authorization applies to one materialization call only, after exact
event re-registration. Matching copies are reused; absent destinations still use
exclusive creation. Unsuitable/inconclusive observations do not authorize
replacement. The active dataset tree and aliases resolving into it are protected.
Owned staging and `os.replace()` require a last target identity/metadata recheck
and complete final verification; no unlink-first/direct-write fallback is allowed.
These bounded checks assume trusted directories/serialized ownership and are not
atomic compare-and-replace or hostile/concurrent-directory protection. Failures
after replacement retain original diagnostics and do not imply the old file
survives or the new file is absent. Immutable evidence never changes. No overwrite
permission is persisted in events or attempt handoffs. That unit left production
routing and window/reminder integration separate; the later approval below selects
modal session behavior without activating dated writers, migration or cutover.

### Production modal Timesheet and unfinished session attempts

**Status:** current for modal/frozen behavior; widget-retained attempt recovery
superseded for the rewrite. **Provenance:** later explicit user approval and
implementation contract for replacing shipped export workflows with the accepted
Timesheet components. Current owners: [saved
exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports) and [owned
Timesheet](../DESIGN_NOTES.md#application-owned-modal-timesheet).

All shipped export entry points use one application-owned modal Timesheet.
Main/mini input is blocked while timers and ordinary Tk events continue. Fresh
openings start This week/All tasks and require explicit Preview. Close before an
attempt discards the preview; Close after known completion permits a fresh opening.
An unsuccessful Save may close only after default-cancel confirmation, retaining
the same withdrawn window/component for this session. Reopening does not prepare,
retry or reconstruct it. Save/confirmation/path busy guards prevent interruption.
Exit warns before losing unfinished automatic session resumption and takes
precedence over the old monthly close prompt. No evidence/files are undone.
Forced destruction, crashes and restart resumption are not promised. No New export,
Abandon, persistent attempt or general recovery UI is selected by this unit.

This later approval replaces the full/selected export UI, overlap/post-export
choices and checkpoint-reopening command without compatibility aliases or parallel
legacy access. Independently used backend export/replay/evidence contracts remain.
Save never confirms POL-R, marks a reminder handled, submits, creates a checkpoint,
deletes a task or operates timers. Opening from the monthly close reminder returns
to the application, without automatic exit or a claim of Save success.

The same approval selects future reconciliation reminders: check the previous
week every local day used, including opening after absence and rollover while
running; check the current week Friday and Monday. Compare per task/day so weekly
totals cannot cancel differences. Offer Open Timesheet and Dismiss for today;
saving is not reconciliation. These weekly rules remain pending. Existing monthly
visibility/settings may remain temporarily, without becoming replacement policy.
This implementation approval does not activate configurable weeks, dated writers,
migration or installation cutover. Their existing Selected/Open boundaries remain.

### Absolute daily external confirmations

**Status:** current for absolute confirmation/Unknown/Daily Delta; Enter-as-daily-
Actual is superseded by the later quarter-hour policy. Compatible examples remain.
**Provenance:** explicit user confirmation of daily
replacement-cell semantics and the mandatory example; current owners:
[daily reconciliation](TIMESHEET_REQUIREMENTS.md#selected--daily-reconciliation)
and [contractual example](TIMESHEET_REQUIREMENTS.md#selected--mandatory-300--500-contractual-behavior-test).

Confirmed POL-R is the complete known external task/day cell value, not an
increment. Unknown differs from confirmed zero. When known, Delta is signed
Actual minus Confirmed; Enter in POL-R is the complete current Actual. When
unknown, Delta is Unverified and Enter still shows Actual. Further work changes
Actual without resetting the confirmation.

The approved sequence saves 3:00, records another 2:00, then confirms that the
earlier 3:00 was entered: **Actual = 5:00; Confirmed = 3:00; Delta = +2:00;
Enter in POL-R = 5:00**. Updating the external cell to 5:00 and confirming it
produces **Delta = 0:00**. The cell is replaced with 5:00, not a second independent
2:00 entry. If Actual 3:00 is corrected to 2:30 after confirmation at 3:00,
**Delta = -0:30; Enter in POL-R = 2:30**; the earlier evidence remains intact.
These preserve the original work-time acceptance semantics. The later selected
decimal representation displays the corresponding values as 5.00, 3.00, +2.00
and, for the correction, 2.50 and -0.50.

### Authoritative snapshot-first publication and recoverable exports

**Status:** current for snapshot-first semantics; journal authority superseded by
SQLite. **Provenance:** explicit user approval of one authoritative immutable snapshot
registered before external publication, reproducible verified copies, recoverable
pending exports and then no overwrite. The blanket no-overwrite clause is superseded by
the later explicit-overwrite approval; default protection and immutable evidence remain.
ChatGPT selected the concrete event identities, contents, registration/retry,
verification and batch contracts under that user-approved direction. Technical owner:
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md); product owner: [saved
exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports).

At that approval, the journal held export truth before file materialization.
SQLite now owns replacement evidence; snapshot-first semantics remain binding.
A failed file write
leaves reusable evidence rather than an apparent successful export without a
matching authoritative record. Retry uses the same frozen work and identity;
success requires verified bytes. This resolves the earlier Open consistency and
event-contract direction without claiming an implementation or general crash
transaction. The separately rejected file-first proposal is recorded below.

### Decimal-hour replacement reporting

**Status:** current for displayed Actual; arbitrary hundredth POL-R submission/
confirmation units are superseded by the later quarter-hour decision.
**Provenance:** explicit user requirement for decimal-hour
replacement output; ChatGPT selected two places, ROUND_HALF_UP, integer hundredths
and displayed-cell rollups under that approval. Technical owner:
[decimal representation](EXPORT_EVIDENCE_CONTRACT.md#decimal-hour-representation);
product owner:
[replacement output](TIMESHEET_REQUIREMENTS.md#selected--decimal-hour-replacement-output).

Exact accounting seconds remain authoritative. Rounded external cells and their
summed displayed rollups reconcile with values entered into POL-R without creating
work. Decimal format was previously Open and is now selected; the existing exact
HH:MM:SS renderer remains a staged implementation, not the replacement format.

### Low-friction explicit confirmation

**Status:** current. **Provenance:** explicit user confirmation; current owners:
[confirmation workflow](TIMESHEET_REQUIREMENTS.md#selected--explicit-pol-r-confirmation-workflow),
[stale exports](TIMESHEET_REQUIREMENTS.md#selected--corrections-and-stale-exports),
[incomplete days](TIMESHEET_REQUIREMENTS.md#selected--incomplete-current-workdays)
and [primary workflow](TIMESHEET_REQUIREMENTS.md#selected--low-friction-primary-workflow).

Confirm an entire applicable export, checked task/day cells, or a manual absolute
external amount; deferral allows returning later. Propose frozen exported values
without repeated typing. Unchecked cells retain previous values; zero cells are
not automatically confirmed, while explicit zero is allowed. A stale export
replacing a newer differing confirmation requires acknowledgement of that
specific conflict. Prior confirmations remain evidence. Export/confirmation is
allowed during incomplete days without stopping timers or resetting Actual.
The stated purpose is easy external entry without duplicating manual timekeeping
work; ordinary bulk confirmation does not demand a reason for each cell.

### Optional weekly allocations

**Status:** current. **Provenance:** explicit user confirmation of the optional
model; current owner:
[allocations](TIMESHEET_REQUIREMENTS.md#selected--optional-weekly-allocations-implementation-deferred).

Allocations are user-supplied informational weekly amounts: Unknown differs from
zero; recurring defaults, specific overrides and manual adjustments are approved
future behavior. Remaining allocation and projected remaining after Actual are
estimates, separate from outstanding unconfirmed time. Insufficiency may warn but
never blocks timers or discards work. Implementation is Deferred; configuration
details remain open. First-release inclusion was reserved then; the later rewrite
decision explicitly places allocations outside the complete core pilot.
POL-R backend administration
and enforcement remain Unverified, not an external authorization guarantee.

### Manual external integration boundary

**Status:** current. **Provenance:** explicit user confirmation; current owner:
[Actual/Exported/Confirmed boundary](TIMESHEET_REQUIREMENTS.md#selected--actual-exported-and-confirmed-pol-r-are-distinct).

Chronicle assists the user in entering and correcting POL-R values; it does not
connect or synchronize automatically. User confirmation records what the user
believes is present, not independent external verification. Zero Delta therefore
means agreement with the latest confirmation, not a verified POL-R query.

### Tkinter transactional rewrite and core POL-R before pilot

**Status:** current for Tkinter/SQLite/core scope; its daily-Actual-as-Enter clause
is superseded below. Its WAL/FULL profile is superseded by Stage 1C below.
At Task 1b this documentation was pending final independent
acceptance. Stage 0 was subsequently independently accepted at
`a24aca706740b7e02cc1f856baa194042785bbcb`, as explicitly supplied with the branch
bootstrap instructions; that accepts the documentation gate, not SQLite runtime.
**Provenance:** explicit user instructions titled “Reconcile
Chronicle's Tkinter rewrite requirements, architecture and roadmap,” including
the user's correction that POL-R reconciliation is an absolute core requirement.
No unsupported decision date is inferred from a commit or source snapshot.
Current owners: [requirements](TIMESHEET_REQUIREMENTS.md),
[target architecture](ARCHITECTURE.md), [export contract](EXPORT_EVIDENCE_CONTRACT.md)
and [Stages 0–6](ROADMAP.md).

Python + Tkinter/ttk remains final. The user explicitly supersedes the preceding
Qt/PySide6 clean-rewrite planning assumptions, not because of an alleged Qt
capability defect. No Qt runtime exists in the inspected baseline. The earlier
nested Work History correction/global pending-retry implementation task remains
superseded and must not be executed as fallback.

Select one local SQLite authority, relational current facts plus immutable typed
work revisions/export/absolute-confirmation evidence, stable work-entry UUIDs,
expected revisions and atomic committed request receipts. Exact request reuse
returns committed results before stale checks; changed content under the same ID
fails. Unchanged edits write no revision/artificial receipt. This approval selected
WAL/FULL/foreign keys, constraints, supported backups, exact integer microseconds,
explicit IANA/offline tzdata and future rewritten-data upgrade protection; Stage 1C
below supersedes WAL/FULL only.

This supersedes JSONL-as-target envelopes/manifests/replay/synchronization,
replacement-interval UUIDs, Python authoritative projections/JSON snapshots and
same-widget retry dependence. Retain frozen report, exact retry, protected default
publication/explicit one-call overwrite and absolute confirmation semantics.
SQLite commit and file publication remain distinct resources, without universal
power-loss or hostile/concurrent-directory guarantees.

Use shallow modules, all Tk calls on the UI thread and one worker-owned SQLite
connection/database/file I/O via queues and a bounded UI result drain. Constructors
construct only; explicit presentation/completion callbacks replace application
blocking modal sequencing. Short toolkit dialogs are allowed with legitimate
parent/grab/focus return. Main selection → task-bound modal History → inline editor
supersedes subordinate correction dialogs and recursive metadata-editor History
routing in the rewrite. Current code remains untouched by this documentation.

Core is task recording AND explicit POL-R: frozen export, whole/checked/manual
absolute confirmation, Unknown versus zero, stale-prior rejection, daily/weekly
Actual/Confirmed/Delta/Enter and previous-week/every-used-day plus current-Friday/
Monday reminders. All must be complete before core pilot. The earlier proposed
Stage 6 POL-R deferral is expressly rejected; Stage 1 timer foundation is an
engineering slice, not complete MVP/pilot. Allocations/conveniences are optional
Stage 6 after reserved decisions, superseding the earlier Open first-release
allocation-inclusion question. At that approval, Enter was whole current Actual,
never Delta (now superseded by weekly allocation); mandatory
5.00/3.00/+2.00/5.00, then zero Delta at 5.00, and corrected 2.50/-0.50 examples remain.

Fresh rewrite requires no legacy migration/import, old schema/API support,
dual-write or parallel runtime. This does not authorize startup deletion. Exact
release paths/cutover/cleanup, abnormal clock/sleep/restart, dataset-timezone changes,
replacement templates and allocation policy remain reserved at their first affected
gates. Existing JSONL Phase 2 acceptance stays historical, not SQLite completion.

Preserve the feature branch and full history. After independent architecture
acceptance, a separately authorized runtime branch originates at that accepted
commit. Next runtime work is a bounded Stage 1 read-only implementation plan,
not another whole-app planning cycle. No branch or runtime is created by this
Markdown-only reconciliation.

### Quarter-hour submission and restored confirmation integrity

**Status:** current. **Provenance:** later explicit user clarification that POL-R
accepts daily inputs only in 0.25-hour multiples, followed by user approval of
Chronicle's per-task weekly upward rounding, largest-remainder distribution,
earlier-date ties, no zero-work allocation and no cross-week carryover, as supplied
in the Task 1b instructions. No unsupported decision date or independent external
compliance approval is inferred. Owners: [requirements](TIMESHEET_REQUIREMENTS.md#selected--weekly-pol-r-suggestions),
[single algorithm/precision contract](EXPORT_EVIDENCE_CONTRACT.md#full-week-quarter-hour-allocation),
[architecture](ARCHITECTURE.md) and [core gates](ROADMAP.md#stage-3--core-frozen-timesheet-and-pol-r-reconciliation).

Separate exact integer-microsecond Actual, its existing HALF_UP task/day display
hundredths, and proposed/confirmed integer quarter-hour POL-R units. The chosen
weekly calculation uses full seven-date task/week Actual at one explicit cutoff,
not daily/weekly displayed decimals. Partial Custom reports retain the full basis
but expose/confirm only selected cells; current-week suggestions are provisional.
A fresh calculation can reallocate other dates after correction, never historical
Actual dates, frozen suggestions or confirmed values. No rounding/carryover ledger,
additional work, worker or datastore is selected.

This supersedes the earlier rule that Enter always equals independently rounded
daily Actual: Enter is the current quarter-hour suggestion. Retain Daily Delta as
Actual-display minus known Confirmed, and distinguish suggested-entry gap, exact
weekly upward adjustment, daily allocation mismatch, incomplete coverage, Unknown
and stale review. Zero suggestion on a worked day is not known zero or complete
reconciliation. Existing 3.00/5.00 and 2.50 examples remain compatible; mandatory
C–G in the technical owner exercise the broader policy rather than silently
reinterpreting old Actual decimals as quarter-hour inputs.

Task 1a consolidation weakened **previously approved** confirmation guarantees.
This task restores them from the predecessor at
`b65c16084ba60ff82178166bcbbd8cca4d51f9c6`, specifically its whole-batch/stale-export
and staged proposal/selection sections; it does not invent a new historical
approval or reinstate JSONL mechanisms. Restore positive-default selection even
when already equal, exact cell-specific acknowledgement keys with fresh selected
priors, and complete reviewed frozen source coverage including unchecked cells.
Adapt their amount source to frozen suggested quarters and their authority/order
to SQLite transactions/current references. Unrelated unchecked confirmation changes
need not invalidate valid checked review; changed selected prior rejects the whole
batch. Exact committed request reuse cannot roll back newer confirmations.

The external daily restriction is accepted user context. Employer/customer
redistribution authorization and worked-day 0.00 versus omitted/no-entry treatment
remain independently unverified, to validate before affected Stage 3 official
reporting/pilot. They do not reopen the approved math or permit auto-confirmed zero.
Core POL-R still precedes Stage 5; optional budgets, unrelated Open decisions,
Tkinter/SQLite, immutable evidence and fresh-data/no-compatibility scope remain.
This is documentation reconciliation, not allocation/SQLite implementation or a
runtime validation result.

## Material corrections, supersession and legacy evidence

### File-first, event-second proposal

**Status:** rejected. **Provenance:** explicit user rejection supplied in the
approved export/evidence architecture direction. Current technical owner:
[snapshot-first sequence](EXPORT_EVIDENCE_CONTRACT.md#snapshot-first-creation-and-publication).

The earlier proposal to publish an external file before registering its evidence
was rejected in favor of the approved authoritative-snapshot-first direction.
This records rejection of a proposal, not supersession of a previously approved
user architecture. Current staged file-only code remains an implementation
observation; it does not implement the rejected two-resource proposal.

### Replacement clarification

**Status:** current. **Provenance:** explicit user correction identified in the
approved decision-history instructions; current owner: the
[replacement requirement](TIMESHEET_REQUIREMENTS.md#selected--replacement-installation-and-data-boundary).

The user clarified that the redesigned application replaces the old installation
and workflow. Earlier descriptions suggesting permanent retention of the old
installation do not establish a previously approved user choice. This records
the correction's effect without inventing a superseded user decision or an exact
date. Temporary coexistence during staged development is not the target product.

### Earlier hierarchy-oriented export plan

**Status:** superseded. **Provenance:** explicit user direction in the project/task
foundation instructions that the earlier hierarchical-export plan was superseded
and the reviewed project/task architecture remained approved. Current owner:
[independent tasks/projects](TIMESHEET_REQUIREMENTS.md#selected--independent-projects-and-tasks).

The replacement is independent task accounting with organizational projects,
not inclusive parent/subtask export roll-ups. This is a documented plan
supersession; it does not establish that existing legacy hierarchy was ever
approved as permanent replacement architecture. Original plan dates and detailed
alternative reasoning are not established here.

### Synthetic manual endpoints as target behavior

**Status:** rejected. **Provenance:** explicit user correction rejecting the
local-noon synthetic interval representation in the dated-duration replanning
instructions. Current owner:
[actual-time representation](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records).

The approved replacement uses a work date and amount without artificial endpoints.
This rejects a representation for the target, not real timestamps for timed work.
It is not evidence that the user had previously approved fabricated intervals.

### Legacy mechanisms observed at Stage 0

**Status:** historical implementation observation; its shipped route is superseded
by Stage 1A below. **Provenance:** Stage 0 source inspection in
[app.py](../src/task_timer/app.py), [models.py](../src/task_timer/models.py) and
[accounting.py](../src/task_timer/accounting.py); current technical owner:
[Design Notes](../DESIGN_NOTES.md).

At that inspection, the JSONL application had parent/subtask handling. Its backend
services supported synthetic intervals, checkpoints and submission markers;
their old UI routes were removed. Accounting used Sunday weeks; the separate
file-only save lacked immutable registration, while Timesheet used registration
and verified materialization. These facts describe the retained unshipped source,
not current launcher capabilities or permanent replacement policy. Staged date-only
and reconciliation services did not complete the replacement. Stage 1A connects
a different timer-only runtime without importing these services.

### Connected Stage 1A timer and approved recovery policies

**Status:** current. **Provenance:** explicit user task “Chronicle — Stage 1A:
Connected SQLite Timer Application,” approving execution after the Stage 1 plan.
This later approval resolves the earlier clock/sleep/restart reservation; it does
not retroactively attribute these choices to Stage 0.

Capture accepted wall UTC once before queueing and preserve exact microseconds.
Sleep and ordinary exit leave the timer running; restart/crash restores the same
committed UUID/effective start, without a new Start or inferred Stop. Do not
rewrite forward jumps. Reject impossible/nonpositive stops/switches; an observation
before the start displays a warning/unavailable value. Explicit minute/DST-aware
active-start correction preserves immutable original/prior/new starts, audit,
comment and exact request receipt under stale-version protection. No-op writes
nothing; no automatic timer deletion or historical editor is introduced.

Mini shows active, otherwise selected task, otherwise no task. Main/mini share
one observation/report. Shutdown drains accepted work without Tk-thread joining.
Idle-but-unverified storage offers exact Retry/Reconcile or explicit default-cancel
exit despite possible commitment and volatile retry loss. Executing I/O is never
silently interrupted. This approval then required the documented SQLite WAL-reset
fix beyond the STRICT feature floor, with explicit disposable engineering paths.
Stage 1C below supersedes only that runtime/profile requirement. Production cutover
and timezone changes remain Open. Stage 1A does not
complete Stage 1 qualification or later core/POL-R/pilot gates.

### Asynchronous active-start completion and draft preservation

**Status:** current. **Provenance:** explicit user execution task “Chronicle —
Stage 1A Repair: Asynchronous Active-Start Correction and Draft Preservation,”
following the connected timer approval above. Queue acceptance cannot close an
editor or prove Save. Matching committed/unchanged completion may close; validation,
known rollback and unavailable outcomes retain drafts; stale authority requires
fresh review rather than retargeting. Unverified work freezes the same Request and
offers owner-mediated Retry/Reconcile and the approved default-cancel exceptional
exit inside the modal editor. Executing I/O blocks ordinary Close. View destruction
cannot discard owner-held evidence; later presentation failure cannot undo verified
completion. This is a bounded timer repair, not Stage 1 operational acceptance,
Stage 2 History editing or Stage 3 POL-R delivery.

### Stage 1A acceptance and bounded operational qualification

**Status:** current. **Provenance:** explicit user task “Chronicle — Stage 1B:
Operational Reliability and Native Windows Qualification.” The user independently
accepts Stage 1A at `897aec2c0d57b6d4aa5c0c5109f55270a4bb1968` for its bounded
implementation, and authorizes operational tests/repairs and controlled Windows
build engineering even when native Windows is unavailable. At this approval,
missing native source/NTFS/Tk/PowerShell and packaged evidence remained a Stage 1
gate; Linux experiments did not replace it. Stage 1C below supersedes the packaged
requirement and separates functional acceptance from native source-deployment
qualification, while preserving this chronology. Stage 4
still owns full backup/restore/upgrades; no Stage 2/3 delivery, new recovery authority,
release approval or production cutover is implied.

### Stage 1C — Standard sqlite3 and Python-source deployment

**Status:** current. **Provenance:** explicit user-approved execution task
“Chronicle — Stage 1C: Standard SQLite and Python-Source Deployment Simplification.”
The project is under development; no production Chronicle SQLite databases exist.
The user judges the former WAL-reset runtime restriction and packaged Windows
executable assumptions unnecessarily restrictive for this single-user timer.

Use built-in sqlite3 exclusively, DELETE rollback journaling, synchronous EXTRA
and foreign keys, checked before transactions. SQLite 3.37.0+ is the STRICT floor;
remove the extra 3.51.3 floor and 3.52.0 exclusion. Preserve explicit transactions,
immutable evidence/receipts, uncertainty handling and one serialized worker.
Development databases are disposable; no migration/conversion/compatibility
machinery is required, and unknown files/databases must never be deleted or
recreated automatically. This supersedes earlier profile/version clauses only.

Run ordinary Python source through the existing Chronicle launcher, with pinned
tzdata installed through pip within available IT permissions. No custom SQLite
provider, DLL replacement, administrator/compiler requirement, executable builder
or editable project build is needed. Prior executable-build preparation is
superseded, not retroactively unapproved. Earlier audit and POL-R decisions stand.

Stage 0 is accepted; Stage 1A connected timer and Stage 1B portable reliability
are accepted (the latter at `1e84a043c1c055aced9b8c4b000ef766bbf6d178`). Stage 1
may receive independent functional acceptance after this simplification and its
relevant checks. Actual native Windows source operation remains required before
real deployment/complete core pilot, without permanently blocking Stage 2 work
because the eventual work computer is unavailable. At that approval Stage 2/3 were unimplemented;
POL-R stays mandatory before complete core pilot. Release paths/cutover remain Open.

### Stage 2A — Connected mixed work, revisions and week configuration

**Status:** current. **Provenance:** explicit user “GO — APPROVED FOR EXECUTION”
task titled “Chronicle — Stage 2A: Complete Mixed-Work Persistence, Manual Entry,
Revision Services, Shared Accounting, and Week Configuration,” on the independently
verified starting source `2f4328232c3e86426e354c87fa60dcdc40061bfc`. This later approval
adds the bounded work below; it does not retroactively attribute it to Stage 1.

Extend the same fresh work_entries/work_revisions schema for timed and date_only
kinds, stable UUIDs, positive typed values, immutable corrections/deletions and
atomic exact receipts. No production SQLite migration is needed; revise the fresh
schema directly and refuse incompatible files without recreation. Existing timer,
audit, one-worker, DELETE/EXTRA/FK and uncertain-outcome guarantees remain binding.

Manual date-only input is positive H:MM, minute resolution, no 24-hour cap within
integer bounds, wholly at a real declared civil date including future dates. New
and changed timed input resolves separate local dates/minutes with explicit DST
occurrences; historical timed work cannot end after its accepted observation.
Unchanged endpoints retain exact precision; unchanged/comment-only edits write
nothing. Deletion is a retained terminal revision, not physical removal.

Connect task-bound Add forms with local-date/blank-time initialization, explicit
Save and the existing asynchronous owner/reconciliation session. New manual work
is additional work, without inferred overlap correction or changes to a running
timer. All active mixed readers must agree before exposing those writers. Week
start is a persisted expected-prior checked mutation, all seven weekdays with
Sunday initially, changing periods rather than work facts. History/revision reads
were delivered as backend foundations; at that approval the modal browser/inline
historical editor, audit UI and deletion controls remained Stage 2B. Stage 2 remains In Progress.
Stage 3 Timesheet/quarter-hour POL-R/reminders remain mandatory, unimplemented core.

### Stage 2B — Connected History and inline whole-entry revision workflow

**Status:** current. **Provenance:** later explicit user “GO — APPROVED EXECUTION
TASK” titled “CHRONICLE — STAGE 2B: Complete Work History, Inline Correction/Deletion,
Revision Details, and Modal Integration,” against independently accepted
`7bc1bce2894fd5d4ccddbcedfd7ae0f4e7c1323f`. That instruction also reports independent
Stage 1 functional acceptance and Stage 2A acceptance at that SHA; neither is a
Codex inference from passing tests. Native Windows source qualification remains
separate and unverified here.

Connect one application-owned, fixed-task local-modal History from main selection,
using callback presentation and legitimate origin return, no subordinate correction
Toplevel or nested application wait. Current week/Custom/All preserve Apply-only
drafts, explicit Refresh and one application-session chronological direction.
Use an inline standard-library calendar, not a new runtime dependency.

Add one transaction-consistent detached snapshot with context, effective rows and
deleted-entry index, sharing existing History/accounting logic. Keep immutable
details discoverable in revision order, including deleted entries. Inline editing
and confirmed whole-entry deletion use the accepted Stage 2A services and existing
application pending request/worker. Stale review never retargets; uncertainty keeps
the identical Request and owned exceptional exit. Successful mutation refreshes
the applied History context without applying drafts or changing sort direction.
Read/render failure cannot reclassify committed work or make stale/partial rows
current. Stage 2B delivery requires independent functional adjudication before
Stage 2 completion. Stage 3 and all reserved Open policies remain unchanged.

### Stage 2 acceptance and Stage 3A preview/evidence approval

**Status:** current. **Provenance:** explicit user “GO — APPROVED EXECUTION TASK”
“CHRONICLE — STAGE 3A: Exact Weekly POL-R Allocation, Connected Timesheet Preview,
and Immutable SQLite Export Evidence,” against independently verified
`adc09ba0935e8718c4ad2101057af9c6022074cc`. That instruction independently accepts
Stage 2A/2B and complete Stage 2 functional recording. It does not retroactively
attribute acceptance to the earlier implementation receipt or qualify Windows.

Implement the already selected full-week allocation and precision policy in pure
modules, a detached frozen candidate, connected read-only modal preview and four
immutable relational export tables with exact atomic receipts and detached recovery.
Use the existing accounting/worker; no current Actual recalculation on registration,
second database or persistent aggregate cache. Preview writes no evidence/files.
The approved staged boundary omits Save/Confirm controls: Stage 3B connects full
verified file Save/status/one-call overwrite/recovery UI, Stage 3C absolute
confirmation and Stage 3D reconciliation/reminders. There is no SQLite-only UI Save
or prematurely selected unfinished-Save lifecycle. Stage 3A delivery is for
independent review, not Stage 3/pilot completion or external-policy qualification.
Earlier integrity guarantees, fresh-data protection and Open matters remain binding.

### Stage 3A acceptance and Stage 3B protected publication approval

**Status:** current. **Provenance:** explicit user GO execution instruction
“CHRONICLE — STAGE 3B Protected Timesheet File Publication, Verified Save, and
Saved-Report Recovery,” against independently accepted Stage 3A
`d1e775c33982f109337ec237e3c78e8dc7b56f2e`. This later approval accepts Stage 3A;
it does not attribute acceptance to the prior implementation receipt.

Connect Save to the exact reviewed Candidate through existing atomic registration
and exact-request reconciliation, then worker-owned protected materialization.
An absent original preferred destination may be filled with the first chosen path
as metadata only before registration; alternate paths do not change immutable
content/identity. Unknown registration cannot publish. Matching files are reused,
absent paths use exclusive publication and stable regular-file conflicts require
owned default-No one-call overwrite consent tied to the inspected target. Protect
all dataset paths/aliases even when absent. Stage/final full verification and
truthful postpublication diagnostics remain binding; no final-file rollback.

Saved Reports recovers frozen text/context after restart without current Actual,
renderer or retained widget. File status is fresh, not persisted. Executing work
blocks Close/exit. Unverified registration retains the existing pending Request;
registered incomplete file Save can close after confirmation into a minimal session
UUID/path handoff, disposing the widget. Fresh opening still requires Preview;
explicit recovery replaces former legacy retained-window assumptions. Application
exit warns before losing volatile context without undoing evidence/files.
No schema/status ledger, automatic retry, reusable consent, Stage 3C confirmation
or Stage 3D reconciliation/reminder implementation is authorized. Stage 3B delivery
requires independent review; Stage 3 remains In Progress and unqualified for pilot.

### Stage 3B acceptance and Stage 3C absolute confirmation approval

**Status:** current. **Provenance:** explicit user GO execution instruction
“CHRONICLE — STAGE 3C Explicit POL-R Confirmation, Immutable Absolute Batches,
Frozen-Source Integrity, and Stale-Cell Protection,” against independently verified
and accepted `76df4d5bc3b5d0796a269b8c9d23d1d3ac66ba57`. This later instruction
accepts Stage 3B, not the earlier implementation receipt itself.

Implement exactly three relational confirmation tables and one atomic absolute
quarter-hour use case through the existing worker/pending Request/transaction helper.
Preserve Unknown versus explicit zero and immutable history. Validate the entire
frozen reviewed source including unchecked/zero rows, positive-only defaults
including equal values, exact selected priors and individual newer-differing-source
acknowledgements by committed sequence, not audit clocks. Newer unchecked priors do
not unnecessarily reject valid checked batches. Manual confirmation is independent
of an export/current Actual and accepts exact nonnegative decimal quarter values.
A new explicit equal amount is still new evidence. Old exact retries never reinstall
superseded values. Reopen proves original receipts, prior chains and latest pointers.

Connect inline source/manual/history controls to the same modal Timesheet. Defer
writes nothing; uncertain submission retains identical batch/Request and existing
exceptional-exit protection. Known commitment survives presentation/refresh failure.
Bounded immediate task/day feedback does not deliver the Stage 3D comprehensive
dashboard, weekly summaries or reminders. No external POL-R connection, automatic
confirmation, allocation change, migration or persisted Delta ledger is authorized.
Stage 3C delivery requires independent review; Stage 3 remains In Progress. External
redistribution and worked-day zero-entry policy remain unverified before pilot.

### Stage 3C functional acceptance and Stage 3D reconciliation/reminder approval

**Status:** current. **Provenance:** the later explicit user GO execution instruction
“CHRONICLE — STAGE 3D Complete Daily/Weekly POL-R Reconciliation, Coverage,
Current-Source Comparison, and Reminder Workflow” independently accepts Stage 3C
for functional development. This is later approval, not an earlier receipt's claim.

Use one read-only current reconciliation projection, shared accounting/allocation,
latest immutable confirmation references and explicit cutoff. Preserve Unknown,
known zero, daily allocation mismatches despite net equality, explained Delta,
complete-week rounding and partial visible scope. Compare immutable frozen source
with current suggestions/convention separately from newer-differing confirmation
flags. Keep all confirmation/file rules and Open external-policy questions intact.

Connect one Reconciliation section within the existing modal Timesheet, with
explicit draft Apply/Refresh, copyable absolute suggestions and existing source/
manual/history navigation. Previous week is checked every used dataset-local day;
current week on civil Monday/Friday. Startup, rollover, relevant commits and recheck
coalesce reads on the existing worker, never per-second reconciliation polling.
One explicit Dismiss for today persists a nullable canonical local date in metadata
through the existing exact-request receipt transaction; it survives same-day restart
and suppresses both categories even after later work. A new date expires it by
comparison. Opening/Save never dismisses or confirms. Unavailable is not all-clear.
No new datastore, scheduler, summary ledger, migration or external API is authorized.

Stage 3D delivery and Stage 3 functional completeness require independent review.
Native qualification, external redistribution/worked-day zero policy, Stage 4
stabilization and Stage 5 pilot remain separate. This approval does not authorize
later stages, merge or release.

### Stage 3 functional acceptance and Stage 4A recovery approval

**Status:** selected. **Provenance:** the later explicit user GO instruction,
“Stage 4A — Consistent SQLite Backup, Independent Restore Validation, and Safe
Recovery Startup,” records ChatGPT's independent Stage 3 functional acceptance and
authorizes this bounded stabilization slice. Earlier delivery/review statements
above preserve their original chronology; they are not claims of pending current
Stage 3 acceptance.

The user selects online `Connection.backup()` on the existing worker-owned source,
private same-directory staging, independent full SQLite/Chronicle validation and
exclusive hard-link publication to an absent external file. A running timer stays
active. No raw live-file copy, overwrite/reuse, schedule, registry, extra datastore,
schema change or persisted backup status is authorized. Publication/verification
uncertainty preserves primary diagnostics and never rolls back final files.

Cold restore validates the source before reserving a new absent local directory,
uses DatasetLock plus SQLite backup/staging/independent verification, then exits
without constructing Tk/app/worker. A later ordinary launch creates a fresh session;
no old requests, view tokens or callbacks survive. The original remains untouched.
The restored dataset retains its UUID and all exact evidence, so original/clone must
not operate as competing authorities. External report copies are not bundled or
automatically materialized. Only proven-owned temporary artifacts may be cleaned;
unknown objects and partial directories are protected.

Stage 4A is delivered for independent review, not complete Stage 4 or pilot approval.
No live/in-place restore, migration or automatic repair is selected. Native source/
NTFS, suspend, hostile filesystem and power-loss qualification remain separate.

### Stage 4A acceptance and Stage 4B portable reliability approval

**Status:** selected. **Provenance:** the later explicit user GO instruction,
“Stage 4B — Portable Operational Reliability, Interruption Recovery,
Storage-Failure Integrity, and Queued Shutdown Qualification,” records independent
Stage 4A acceptance and authorizes bounded qualification and demonstrated repairs.
Earlier delivery/review statements preserve their original chronology.

The existing SQLite profile, worker/Request/Outcome path, local modality, exact
retry, immutable evidence and cold-restore boundary remain selected. Reuse existing
fault and process barriers; add complete-fact comparisons, queued shutdown and a
connected recovery scenario. Retain failed probe cleanup ownership and definitive
uncertainty, and prevent optional rendering or unrelated replies from consuming
known outcomes. No watchdog, persistent request ledger, automatic worker restart,
new schema or recovery framework is selected.

Measure representative small/medium/larger workloads through actual supported APIs,
including whole confirmation-history validation. Preserve integrity semantics;
measurements do not establish an arbitrary SLA or native Windows performance.
Stage 4B is delivered for independent review. Native Windows/NTFS, actual suspend,
power-loss limitations, protected future upgrades and complete pilot remain separate.

## Open decisions

**Status:** open. **Provenance:** questions explicitly reserved for user/ChatGPT
adjudication in the [product contract](TIMESHEET_REQUIREMENTS.md#open--reserved-userchatgpt-decisions)
and [roadmap dependency boundaries](ROADMAP.md#dependency-constraints-and-adjudication).
This summary preserves unresolved decision context, not a competing requirements
owner or candidate implementation design.

- Allocation defaults/overrides and their interaction with week-start changes.
- Exact installation replacement and old-data cutover.
- Dataset-timezone changes before affected configuration/accounting.
- Replacement template semantics before optional implementation.

The later rewrite approval places allocations in optional Stage 6; earlier
first-release inclusion is superseded, not a remaining core pilot decision.

Formerly Open export/confirmation/decimal semantic questions were resolved by
the approved technical owner; their JSONL storage/recovery mechanisms are now
superseded by the later SQLite transaction approval, with provenance
recorded above. This history defines no alternate schema or recovery authority.
Redistribution authorization and worked-day zero-entry treatment also need
external validation before affected Stage 3 reporting/pilot, without reopening
the approved formula. POL-R allotment administration/enforcement remains an
[Unverified external fact](TIMESHEET_REQUIREMENTS.md#unverified-external-behavior--pol-r-backend),
not a resolved decision.

## Maintenance and provenance

Record only supported choices, established rationale and genuine supersessions.
Link each entry to its current owner; when an approved decision changes, reconcile
that owner and record the evidenced relationship here. A proposal becomes current
only after approval, never because it appears in source, tests, comments or an
assistant response. Do not infer dates from commits or add one entry per task.

Keep explicit user confirmation, accepted ChatGPT recommendation, user correction,
source observation and open question provenance distinct. Where evidence is
insufficient, omit the historical assertion rather than fill it by assumption.
Design-purpose statements do not imply undocumented user quotations or reasoning.
This history records approved resolutions but grants no implementation
authorization and makes no independent product or architecture decisions.
