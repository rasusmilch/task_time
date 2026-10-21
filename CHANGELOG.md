# Changelog

This is Chronicle's sole canonical historical project-change record.
Unreleased changes describe cumulative material effects, not individual tasks,
receipts or commits. No release or production qualification is implied below.

## Unreleased

### Clean rewrite — connected timer foundation and selected core

- Select Python + Tkinter/ttk with transactional SQLite as the sole replacement
  authority, superseding earlier Qt/PySide6 planning and JSONL-as-target mechanics.
  Preserve exact work semantics, immutable revisions/evidence, stable work-entry
  UUIDs, atomic request receipts, serialized worker-owned I/O and callback-driven
  Tk lifecycle and inline History editing. Connect the first SQLite timer
  slice through the sole source route: independent task/project controls,
  atomic Start/Stop/Switch, persisted active identity, audited explicit active-start
  recovery with asynchronous draft retention and editor-local exact-request
  reconciliation/exceptional exit; queue acceptance is never Save completion.
  Connect task-bound manual genuine timed/date-only entry, immutable typed
  revision/deletion services, complete detached History/revision reads and all
  seven persisted week-start choices. Main/mini share exact mixed calendar Actual;
  date-only work retains its whole declared date and unchanged timed endpoints
  retain precision. No-op edits write nothing; expected revisions/settings reject
  stale writes. Manual forms retain drafts and exact uncertain requests through
  the existing worker/session. Connect one modal Work History with Current week/
  Custom/All, draft-only standard-library calendars, session date direction, linked
  precise rows, inline whole-entry correction/confirmed deletion and immutable
  revision/deleted-entry details. Snapshot context is transaction-consistent;
  stale/uncertain outcomes retain review/request identity. One worker keeps Tk
  responsive and shutdown preserves uncertainty.
  Sleep/exit never stops timers; restart uses committed state. Use explicit fresh
  paths and offline tzdata. Use built-in sqlite3 with verified DELETE journaling,
  synchronous EXTRA, foreign keys and the SQLite 3.37.0 STRICT floor. Exercise
  process-death recovery at transaction/receipt/commit boundaries, active restart and exclusive
  dataset ownership; preserve primary startup diagnostics and worker-held cleanup
  through failures, with accessible retry and no return to abandoned mutations.
  Run directly from Python source with a minimal pip-installed runtime dependency;
  retire executable-build tooling and the obsolete WAL-specific version pin.
  Preserve unsupported datasets without conversion/deletion. Stage 1 functionality
  and complete Stage 2 recording are independently accepted. Connect a read-only
  modal Timesheet / POL-R Preview with explicit periods/UUID scope, full-week exact
  allocation basis and in-scope Actual/suggestion cells. Preserve frozen labels,
  exact UTF-8 text/digest and immutable SQLite export/task/basis/cell evidence with
  atomic request registration, exact uncertainty reconciliation and detached
  recovery independent of later work or renderer changes. Preview writes no
  evidence/files; draft changes invalidate readiness and stale/failed reads cannot
  establish current output. Connect Save/Retry/Copy through verified immutable
  registration and protected worker-owned publication: reuse exact matching copies,
  exclusively create absent files, and permit stable regular-file replacement only
  after separate default-No one-call consent bound to reviewed metadata. Protect all
  active dataset paths/aliases; verify owned staging and complete final bytes/digest,
  preserve truthful postpublication uncertainty and never roll back final output.
  Saved Reports loads frozen context/text after restart without current accounting;
  file status is freshly derived, never persisted. Dispose incomplete registered
  views only after confirmation, retaining a minimal session UUID/path handoff;
  fresh opening requires Preview and uncertain registration retains its exact Request.
  Stage 3A/3B are independently accepted. Connect explicit whole/checked/manual
  absolute quarter-hour confirmation through immutable SQLite batches/cells and
  latest current references: preserve Unknown versus zero, complete frozen source
  coverage, positive defaults including equal values, fresh selected-prior rejection
  and exact individual stale consent by committed receipt order. Retain exact
  uncertain requests, immutable history and bounded task/day feedback without
  changing work, exports or files. Stage 3C is independently accepted for functional
  development. Connect current daily/weekly reconciliation, cell-based coverage,
  complete-week/partial-scope summaries, immutable frozen/current comparison and
  copyable absolute suggestions in the same modal Timesheet. Add coalesced local-date
  previous-week/daily and current-week/Monday-and-Friday reminder reads, Open Timesheet
  navigation and explicit same-day durable dismissal through one metadata date and
  the existing atomic receipt. No read/tick/Save confirms or dismisses. Stage 3D and
  Stage 3 functional completeness await independent review; native Windows source/
  actual suspend qualification, Stage 4 stabilization and complete-core pilot remain
  separate.
- Reconcile the core charter and Stages 0–6: timer foundation is not a complete
  MVP; frozen Timesheet, absolute whole/checked/manual POL-R confirmation,
  daily/weekly reconciliation and reminders are mandatory before the complete
  core pilot. Separate exact Actual/display hundredths from selected POL-R integer
  quarter-hour units: round each task's full week upward, distribute by largest
  remainder/earlier-date ties, retain full basis for partial reports and carry no
  residual across weeks. Enter is the suggested allocation, with separate Daily
  Delta, suggested-entry gap and explained weekly adjustment. Freeze original
  suggestions/context; never redistribute historical confirmations. Restore full
  reviewed source coverage including unchecked cells, positive-default selection
  including already-equal values, and exact selected stale acknowledgements.
  Stage 3A implements allocation/preview/evidence and Stage 3B connects protected
  file Save/recovery; Stage 3C connects confirmation and Stage 3D connects derived
  reconciliation, summaries and calendar reminders for independent review.
  Retained JSONL source is unshipped; it is not a parallel runtime.
  External redistribution/zero-entry policy needs validation before official
  reporting/pilot. Allocation budgets/conveniences remain optional and separately
  decided.
  Preserve fresh-data scope without migration/compatibility or startup deletion;
  installation/cutover, timezone changes and template/allocation decisions remain
  reserved. Explicit Stage 1A approval resolves clock/restart and uncertain-exit rules.
- Establish one target architecture owner and distinguish the retained unshipped
  JSONL source, historical bounded Phase 2 acceptance and future SQLite evidence.
  Stage 0 is independently accepted; the connected Stage 1A timer runs on the
  authorized rewrite branch. Stage 1 functionality is accepted, not complete core/pilot.

### Current JSONL workstream capability — retained implementation history

The cumulative entries below describe retained JSONL source and earlier approvals.
Their JSONL envelopes/replay/synchronization, replacement-interval identity,
retained-widget retry and recursive editor routing are superseded **target
mechanisms**, not instructions for the clean rewrite. That old source is unshipped;
its capabilities/pending features are not SQLite stage completion.

- Separate non-time-bearing project containers from independent UUID-based tasks,
  with optional membership and reassignment that preserves recorded work.
- Represent date-only manual durations separately from real intervals, with
  append-only effective-state correction/deletion replay and rebuildable snapshots.
- Derive mixed historical task/day/week actuals from intervals and dated durations,
  including local-day/DST splitting and informational project/Unassigned totals.
  Current weekly calculations use Sunday starts; project subtotals are not
  additional work. Project detached mixed task history as linked local-day
  interval segments and whole dated entries, retaining underlying identity,
  precise seconds, explicit cutoff/date filtering and deterministic ordering
  without journal or state writes. Record the approved replacement history
  direction: current-week/custom/All periods, session-only date sorting remembered
  across task/dataset history openings with newest-first application startup,
  full-interval segment editing/deletion, effective history with audit access,
  and removal of replacement Reset actions/counters. Stage an application-owned
  in-memory direction handoff without persistence. Connect both Work History
  commands, including recursive task editors, through one owned modal browser
  with duplicate protection, safe originating-parent return and inline launch
  diagnostics. Remove the superseded timeline UI/reader/formatter without a
  compatibility interface, migration or user-file/data-directory cutover.
  Remove shipped task Reset controls and Reset branches from both export
  completion paths, preserving Start/Stop. Supersede the old full/selected export
  UI with the frozen Timesheet workflow below.
  Replace main elapsed counters with own-task Today/This week calendar Actual,
  and mini-mode with Today from one coordinated observation. Application totals
  retain deleted-task work; full-week dated amounts preserve exact attribution.
  Failures show unavailable values and inline errors while Start/Stop and normal
  refresh recovery remain usable. Retire superseded display helpers. Backend reset
  contracts, historical evidence and independently callable interval-only backend
  export/submission readers are unchanged. Replacement creation/editing/deletion, missed-stop UI, audit, remaining
  active-reader integration and production POL-R presentation remain pending. Stage closed
  genuine-interval correction preparation/registration using existing replacement
  events: no-op saves write nothing, unchanged endpoints retain precision, comments
  are optional and stale priors reject. Frozen identities, prospective replay and
  synchronized recovery/reuse preserve newer state; results distinguish verified
  registration from projection/snapshot failures. Compose a standalone correction
  dialog with authoritative detached loading, minute controls preserving precise
  unchanged endpoints, stale conflict presentation and locked same-event retries.
  Explicit close handoffs retain uncertain or verified registration evidence;
  no production editor is activated.
- Provide read-only independent-task timesheet rendering and date-range generation
  with precise durations, explicit selection scope, Unicode-safe escaping and
  wrapping, and bounded calendar-week layout. A separate pure decimal-hour renderer
  rounds task/day cells with ROUND_HALF_UP and conserves their integer-hundredth
  displayed rollups; existing exact rendering and service output remain unchanged.
- Publish complete UTF-8 timesheet files through same-directory staging and atomic
  no-overwrite hard links on supporting filesystems. Cleanup is restricted to
  staging; saved files do not create submission or checkpoint records.
- Prepare and register immutable decimal timesheet evidence in the existing
  journal, retaining task/day seconds and hundredths, original identity/labels,
  reporting request, exact text and SHA-256. Validate journal integrity and stable
  retry identities; rebuild detached evidence through replay, rotation and restore.
  Initialize journals only in nonexistent or genuinely empty directories; refuse
  missing authoritative root files in nonempty datasets without replacing them
  or modifying surviving data.
  Registration publishes no report file and records no POL-R confirmation.
  Separately materialize exact frozen UTF-8 copies after journal verification,
  using exclusive staging/publication and complete destination-byte/SHA-256 checks.
  Reuse matching files and retry without new evidence; protect conflicting files
  by default. Permit explicit confirmed replacement only for completely inspected
  stable regular-file conflicts outside the active dataset tree/resolved aliases,
  using staged `os.replace`, bounded target rechecks and complete final verification.
  Retain truthful attempted/known replacement diagnostics without rollback.
  Connect explicit frozen preview and Save/retry through one application-owned modal
  Timesheet for toolbar, File, reminder-banner and close-reminder access. Preserve
  independent task selection, locked reviewed candidates, exact-event retries and
  protected destinations with separate one-call Overwrite confirmation. Retain the
  same unfinished Save instance across confirmed closure/reopening only within the
  session; exit warns before losing resumption, and fresh openings require Preview.
  Retire legacy full/selected export dialogs, overlap/post-export dispatch and
  checkpoint-reopening UI. Timesheet creates no legacy submission/checkpoint,
  task deletion, Reset, confirmation or reminder-dismissal effects. General recovery
  and weekly reconciliation reminders remain pending.
  Evaluate destination-relative PENDING/READY/MISSING/CONFLICT/UNVERIFIABLE outcomes
  from freshly validated evidence and current file inspection, without writes,
  retained status or publication-history state.
  Prepare, validate, register and replay immutable absolute POL-R confirmation
  batches into an in-memory task/day projection, preserving Unknown/zero, physical
  order, reviewed prior identities, stale acknowledgements and duplicate protection.
  Both export and confirmation registration APIs revalidate the journal under
  serialized ownership and synchronize existing journal files through writable,
  non-truncating access suitable for
  portable flushing before same-identity recovery/reuse, without content writes;
  successful recovery/reuse requires complete evidence revalidation and installation,
  not merely visible bytes after failed flushing. Neither changes Actual, snapshots
  or file copies. Simulated access checks do not establish Windows qualification.
  Propose frozen export cells with current reviewed priors and shared stale-conflict
  rules; prepare canonical positive-default or explicitly checked/zero batches with
  exact cell-specific acknowledgements and fresh selected-prior validation.
  Proposal/selection preparation persists nothing; registration remains explicit.
  Derive read-only daily POL-R reconciliation from current full-precision Actual
  and strictly replayed confirmations: cell-rounded Actual, known/Unknown Confirmed,
  signed Delta and absolute replacement Enter, with detached results and no writes
  or cache installation. Preserve explicit zero and selected zero-work dates.
  Validate the connected service sequence from frozen registration and verified
  materialization through default/checked selection, explicit confirmation,
  reconciliation and replay/restore. Cover absolute replacement, negative
  correction, explicit zero/Unknown, stale rejection and exact retries while
  preserving original evidence, file bytes and unrelated timekeeping state.
  Exercise journal-only rotation exclusions with POSIX/Windows path representations
  while retaining unrelated-file mutation detection; native Windows qualification
  remains pending.
  Record independent acceptance of Phase 2's existing bounded POL-R evidence and
  daily-reconciliation service gate under serialized dataset ownership. Services
  remain staged; production, platform and release qualification remain pending.

These services are independently callable but not fully connected to the
production application workflow. Work History, main/mini Actual and frozen
Timesheet access are connected; legacy backend export/evidence APIs remain
independently callable. New production date-only duration writers and release
cutover are inactive.
POL-R confirmation/reconciliation UI and weekly summaries, general file-status/recovery UI,
automatic missing-file recovery, configurable week starts and weekly allocation
management are not implemented.

### JSONL workstream documentation and governance history

- Establish [repository operating instructions](AGENTS.md) and the
  [approved replacement/POL-R product contract](docs/TIMESHEET_REQUIREMENTS.md),
  distinguishing selected targets, inspected implementation, Open decisions,
  deferred work and unverified external behavior.
- Reconcile overview and technical status with those owners. Documenting approved
  future behavior does not represent shipped application functionality.
- Record the approved technical contract for journal-first immutable export
  evidence, verified recoverable file copies, two-decimal-hour presentation and
  atomic absolute POL-R confirmation batches. Reconcile decision history and
  validation/development guidance. Export evidence and decimal rendering are staged
  above, including verified materialization and dedicated confirmation
  preparation/registration/replay; general recovery UI and confirmation UI remain
  unimplemented.
