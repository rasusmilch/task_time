# Chronicle Architectural and Product Decision History

## Purpose and authority

This document is **HISTORICAL EVIDENCE**: established decisions, their provenance,
design purpose, corrections and unresolved questions. It is not current-state
product authority. The [product contract](TIMESHEET_REQUIREMENTS.md) states what
Chronicle is currently required to do; readers need not reconstruct that from
this history. [Design Notes](../DESIGN_NOTES.md) describes implementation,
[ROADMAP.md](ROADMAP.md) owns sequencing/gates, and
[TESTING_STRATEGY.md](TESTING_STRATEGY.md) owns validation. Historical project
changes belong to [CHANGELOG.md](../CHANGELOG.md).
The approved [export evidence contract](EXPORT_EVIDENCE_CONTRACT.md) owns the
technical event, decimal, verification/recovery and batch rules recorded below.

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

**Status:** current. **Provenance:** explicit user-approved replacement behavior
supplied with the mixed work-history reader instructions; current owners:
[Actual records](TIMESHEET_REQUIREMENTS.md#selected--actual-time-records) and
[mixed history](TIMESHEET_REQUIREMENTS.md#selected--mixed-work-history).

Normal history combines current effective intervals and date-only entries,
independent of resets. Timed work crossing midnight appears as linked daily
segments of its underlying interval; segment editing/deletion acts on that full
interval, with affected-date deletion warnings. Editing preserves entry type;
earlier versions/deletions remain accessible through audit/details. Current week
is the UI default, with custom dates and All history. Date direction is a single
user-wide persisted preference, initially newest first, switched through the
date-column header. Exact link-marker styling remains undecided.

The explicit direction removes replacement Reset actions and resettable counters.
It narrows the earlier reset-independence wording so it cannot imply a requirement
for replacement counters; the earlier guarantee that historical Actual survives
legacy resets remains true. No earlier approved replacement-counter decision is
established by that wording or by legacy source. POL-R stays per task/day.
The staged projection is implementation evidence, not approval or delivery of
the future UI, preference, editing, audit or production reset-removal work.

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

### Local dates and configurable reporting weeks

**Status:** current. **Provenance:** explicit user confirmation; current owner:
[week convention](TIMESHEET_REQUIREMENTS.md#selected--configurable-week-convention).

Actual work is assigned to local dates; genuine elapsed intervals split across
midnight/week/DST boundaries. Any weekday may start reporting weeks, initially
Sunday. Changing it reorganizes weekly presentation without changing work dates,
amounts or daily confirmations. Saved exports retain their original convention.
Fixed Sunday calculations are current implementation, not permanent target policy.

### Separate Actual, Exported and Confirmed POL-R evidence

**Status:** current. **Provenance:** explicit user confirmation; current owners:
[three-record distinction](TIMESHEET_REQUIREMENTS.md#selected--actual-exported-and-confirmed-pol-r-are-distinct),
[saved exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports) and
[evidence integrity](TIMESHEET_REQUIREMENTS.md#selected--confirmation-evidence-and-batch-integrity).

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

### Absolute daily external confirmations

**Status:** current. **Provenance:** explicit user confirmation of daily
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

**Status:** current. **Provenance:** explicit user approval of one authoritative
immutable snapshot registered before external publication, reproducible verified
copies, recoverable pending exports and no overwrite. ChatGPT selected the
concrete event identities, contents, registration/retry, verification and batch
contracts under that user-approved direction. Technical owner:
[EXPORT_EVIDENCE_CONTRACT.md](EXPORT_EVIDENCE_CONTRACT.md); product owner:
[saved exports](TIMESHEET_REQUIREMENTS.md#selected--preview-and-saved-exports).

The journal holds export truth before file materialization. A failed file write
leaves reusable evidence rather than an apparent successful export without a
matching authoritative record. Retry uses the same frozen work and identity;
success requires verified bytes. This resolves the earlier Open consistency and
event-contract direction without claiming an implementation or general crash
transaction. The separately rejected file-first proposal is recorded below.

### Decimal-hour replacement reporting

**Status:** current. **Provenance:** explicit user requirement for decimal-hour
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
details and first-release inclusion remain open. POL-R backend administration
and enforcement remain Unverified, not an external authorization guarantee.

### Manual external integration boundary

**Status:** current. **Provenance:** explicit user confirmation; current owner:
[Actual/Exported/Confirmed boundary](TIMESHEET_REQUIREMENTS.md#selected--actual-exported-and-confirmed-pol-r-are-distinct).

Chronicle assists the user in entering and correcting POL-R values; it does not
connect or synchronize automatically. User confirmation records what the user
believes is present, not independent external verification. Zero Delta therefore
means agreement with the latest confirmation, not a verified POL-R query.

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

### Still-active legacy mechanisms and staged limits

**Status:** implementation-only. **Provenance:** current-source observation in
[app.py](../src/task_timer/app.py), [models.py](../src/task_timer/models.py) and
[accounting.py](../src/task_timer/accounting.py); current technical owner:
[Design Notes](../DESIGN_NOTES.md).

The production application still has parent/subtask handling, local-noon synthetic
manual intervals, timestamp export checkpoints and legacy submission markers.
Mixed service accounting currently uses Sunday weeks; the new save service
publishes a file without immutable export registration. Source presence does not
select these as permanent product behavior or approve reuse of legacy submission
semantics for POL-R. New endpoint-free replay/accounting services are staged;
they do not make replacement production entry or reconciliation operational.

## Open decisions

**Status:** open. **Provenance:** questions explicitly reserved for user/ChatGPT
adjudication in the [product contract](TIMESHEET_REQUIREMENTS.md#open--reserved-userchatgpt-decisions)
and [roadmap dependency boundaries](ROADMAP.md#dependency-constraints-and-adjudication).
This summary preserves unresolved decision context, not a competing requirements
owner or candidate implementation design.

- Allocation defaults/overrides and their interaction with week-start changes.
- Exact installation replacement and old-data cutover.
- Whether allocations belong in the first replacement release (reserved release
  scope in the roadmap, not a choice delegated to Codex).

Formerly Open export event, confirmation, consistency/recovery and decimal-format
questions are now resolved by the approved technical owner, with provenance
recorded above. This history defines no alternate schema or recovery authority.
POL-R allotment administration/enforcement remains an
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
