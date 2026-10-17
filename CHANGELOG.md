# Changelog

This is Chronicle's sole canonical historical project-change record.
Unreleased changes describe cumulative material effects, not individual tasks,
receipts or commits. No release or production activation is implied below.

## Unreleased

### Staged service capability

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
  direction: current-week/custom/All periods, persisted user-wide date sorting,
  full-interval segment editing/deletion, effective history with audit access,
  and removal of replacement Reset actions/counters. Those UI/preference/editing,
  audit and production reset-removal integrations remain pending. Stage closed
  genuine-interval correction preparation/registration using existing replacement
  events: no-op saves write nothing, unchanged endpoints retain precision, comments
  are optional and stale priors reject. Frozen identities, prospective replay and
  synchronized recovery/reuse preserve newer state; results distinguish verified
  registration from projection/snapshot failures. No production editor is activated.
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
  Reuse matching files and retry without new evidence; protect conflicting files.
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
production application workflow. Legacy UI/export paths remain active during
staging; new production date-only duration writers and release cutover are inactive.
POL-R confirmation/reconciliation UI and weekly summaries, general file-status/recovery UI,
automatic missing-file recovery, configurable week starts and weekly allocation
management are not implemented.

### Documentation and governance

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
