# Stage 4 Windows qualification — schema 3

This is a supervised procedure for the checked-out source, not a record that it
ran. Package F delivers portable connected tests and this native preparation.
Stage 4 remains **IN PROGRESS**, Stage 5 **NOT STARTED**. Hardware power loss,
external POL-R redistribution/worked-zero policy and installation/cutover remain
separate. Never enter data into an employer/customer POL-R system during this run.

## Gates and evidence rules

| Gate | Required evidence | Development-host status |
| --- | --- | --- |
| F1 | Connected schema-3 worker/SQLite and real Tk workflows, focused and full regression | Portable execution recorded in the Package F receipt; independent review required |
| F2 | Current-revision native Windows automated collection/events/JUnit/logs, inventory, cleanup and verified delivery | October 30 attempt EVIDENCE_INCOMPLETE; corrective source requires review before native repeat |
| F3 | Actual supervised Windows controls, focus, dialogs, files and restored fresh session | NOT RUN |
| F4 | Actual Windows Sleep/resume with preserved timer and validated recovery | NOT RUN |

Use PASS, FAIL, BLOCKED, NOT RUN or EVIDENCE_INCOMPLETE for each scenario. PASS
requires its observations AND supporting evidence. A required FAIL makes its gate
FAIL; missing, skipped, blocked, not-run or invalid required evidence prevents gate
PASS. Tool exit zero alone is insufficient. Prior-revision results (including the
earlier Extended 657 passes/22 skips) are context, not current schema-3 acceptance.
Retain each original skip reason; do not convert those limitations to passes.

Stop the affected path on a defect. Record source, steps, expected/actual result,
minimal disposable fixture and diagnostics; return it for independent adjudication.
Do not repair source on the Windows machine, increase deadlines to hide a hang,
delete journals, accept security dialogs, elevate, change ACL/Defender/execution
policy, install packages or alter the system clock. Uncertain Delete never retries.

## Source, environment and disposable workspace

Use an ordinary approved PowerShell 5.1+ session on Windows 11, an interactive
desktop, approved installed Python 3.11+, linked SQLite 3.37.0+, actual Tcl/Tk and
offline tzdata 2026.5. VM evidence must be identified; physical sleep capability is
a separate prerequisite. Replace the first three literals with reviewed values.
The output parent must ALREADY exist on local NTFS outside source, production data,
network/cloud-sync directories and any existing dataset. Supplying it attests to
that operator review. No tool can infer all corporate sync/storage policies.

```powershell
$Repo = 'C:\src\task_time'
$Expected = 'REPLACE_WITH_REVIEWED_FULL_40_CHARACTER_COMMIT'
$Parent = 'C:\Chronicle qualification'
Set-Location -LiteralPath $Repo
git status --short
git branch --show-current
git rev-parse HEAD
git diff --check
if ((git rev-parse HEAD).Trim() -ne $Expected) { throw 'Source mismatch' }
if (git status --porcelain --untracked-files=all) { throw 'Dirty checkout; retain it and stop' }
if (Test-Path -LiteralPath '.\.venv\Scripts\python.exe') {
    $Py = (Resolve-Path -LiteralPath '.\.venv\Scripts\python.exe').Path
} else { $Py = (Get-Command python -CommandType Application).Source }
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model
Get-TimeZone
Get-Date -Format o
whoami
$PSVersionTable
[IO.DriveInfo]::new([IO.Path]::GetPathRoot($Parent)) | Select-Object Name,DriveType,DriveFormat,AvailableFreeSpace
& $Py -B -c "import sys,sqlite3,tkinter,importlib.metadata; print(sys.executable); print(sys.version); print(sqlite3.sqlite_version); c=sqlite3.connect(':memory:'); print(c.execute('select sqlite_source_id()').fetchone()); c.execute('create table strict_probe(x integer) strict'); c.close(); r=tkinter.Tk(); print(r.tk.call('info','patchlevel'),r.tk.call('package','require','Tk'));r.destroy();print(importlib.metadata.version('tzdata'))"
& $Py -B -c "from importlib.resources import files; from zoneinfo import ZoneInfo; [(print(z,ZoneInfo.from_file(files('tzdata.zoneinfo').joinpath(*z.split('/')).open('rb'),key=z))) for z in ('America/Chicago','Australia/Lord_Howe')]"
$Q = Join-Path $Parent ('Chronicle operator ' + [Guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $Q) { throw 'Unexpected existing test path' }
New-Item -ItemType Directory -Path $Q -ErrorAction Stop | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Q 'evidence') -ErrorAction Stop | Out-Null
$Data = Join-Path $Q 'Operator Ω dataset'
$Backup = Join-Path $Q 'operator backup.sqlite3'
$Restored = Join-Path $Q 'restored dataset'
$Report = Join-Path $Q 'frozen report.txt'
```

Record effective user, elevation (ordinary/non-elevated), physical/virtual status,
display, permission to launch source/child processes, available space, dependency
versions and missing capabilities. No provision/upgrade is authorized here. An
unavailable prerequisite is BLOCKED, not failed production behavior. Retain console
output with a task-owned transcript if local policy permits; no secrets/user data.

## Original October 30 attempt — retained incomplete evidence

At `56b4e4451d8c738f70d23938c2f60be009d61a84`, supplied independently inspected
Windows 11 Enterprise build 26200 / Python 3.15.2 / SQLite 3.53.4 / Tcl/Tk 9.0.4 /
PowerShell 5.1 / NTFS / tzdata 2026.5 evidence reports 3,783 collected and 2,208
completed: 2,073 passed, 30 failed, 12 errored, 93 skipped; 1,575 not completed.
Final session and regression JUnit are missing; ZIP delivery and cleanup were
recorded verified. Outcome is EVIDENCE_INCOMPLETE, never PASS. The external original
ZIP is immutable and was unavailable on this repair's Linux host.

Reported failure/error inventory: collector 24; History modal 4; Timesheet UI 3;
Stage4 helper 3; reconciliation UI 2; app 1; legacy app UI 2; legacy file status 3.
The logger reopened events under a legacy filesystem monkeypatch, causing
INTERNALERROR. Repairs isolate F2 logging, exact JUnit/source identities, parser
binding, diagnostics and active-lock fixtures. Native focus/visibility hypotheses
remain unresolved; no production Tk correction is claimed. Legacy file-status
failures remain historical regression failures, not schema-3 production defects.

## F2 — separate automated runs

Only after independent approval of the wrapper, run the full source regression:

```powershell
& .\scripts\qualify_stage4_windows.ps1 -Repo $Repo -ExpectedRevision $Expected -OutputParent $Parent -Python $Py
$FullExit = $LASTEXITCODE
Write-Host "Full wrapper exit: $FullExit"
```

The wrapper immediately prints its NEW absolute evidence directory. `collection/`
retains the complete original inventory. `partitions.json` assigns every node
exactly once: SUPPORTED_RUNTIME is `tests/rewrite/` plus the supported root-launcher
bridge `tests/test_root_launcher.py`; RETAINED_LEGACY is the finite reviewed list of
other top-level Task Time modules in `stage4_qualification.py`. Unknown/new/shared
sources remain UNCLASSIFIED and block supported qualification. No test disappears.

`supported-runtime/` and `retained-legacy/` are separate owned sessions, each with
its own selected inventory, command/pytest arguments, fresh basetemp, manifest,
stdout/stderr, events, event-health finalization, actual JUnit, process/pytest codes,
completion counts and cleanup. The same clean SHA is checked before and after.
Full source FAIL remains visible when legacy fails, even if supported execution
passes. Only verified delivery publishes `supported_runtime_automated`; raw
`supported_runtime_execution` is not evidence delivery or F3/F4 acceptance.

Unknown native dialogs obstruct and receive no automatic answer. Default limits:
collection 180s, node 240s including setup/teardown, each phase 7200s, cleanup 5s;
the PowerShell outer bound is three phase limits plus 120s for collection and the
two separate executions. Changes need a reviewed reason. Ctrl+C targets only the
owned phases/controller/Job. Inspect cleanup evidence after interruption.
Progress identifies the active partition; percentages count actual completed nodes.

The F2 writer exclusively reserves its event and health descriptors before pytest.
Hooks do not reopen paths. Short/interrupted writes are handled; write/sync/close
failure latches and prevents successful evidence finalization. The parent verifies
sequences, digest, complete events, exact pytest/JUnit identities and process/session
agreement. No session or XML is manufactured. Collection-only has JUnit NOT APPLICABLE.
Execution that began but cannot finish reconciliation remains EVIDENCE_INCOMPLETE,
not NOT RUN. A successful ZIP does not repair an incomplete test run.

Every raw skip/xfail/xpass remains recorded. Applicability is independently
APPLICABLE/INAPPLICABLE/BLOCKED_REQUIRED/UNRESOLVED, using finite reviewed exact
source/fixture metadata rules, never reason-text substring waivers. Recognized POSIX/XTest
mechanisms on Windows are inapplicable with native replacement gates still required.
Unknown skips, module collection skips, xfail/xpass or unavailable required desktop/
filesystem capability prevent supported PASS. No blanket symlink/privilege waiver.

For the focused native reproductions, use a NEW task-owned temporary path and retain
raw output/JUnit before the full wrapper. Do not run focus cases on a locked or
noninteractive desktop; supervise initial ordinary activation without force-focus.
```powershell
$FocusedTemp = Join-Path $Q ('focused-' + [guid]::NewGuid().ToString('N'))
$FocusedXml = Join-Path $Q ('focused-' + [guid]::NewGuid().ToString('N') + '.xml')
& $Py -B -m pytest -q -p no:cacheprovider -o 'addopts=' -ra tests/rewrite/test_stage4_qualification.py tests/rewrite/test_qualification_collector.py tests/rewrite/test_app.py tests/rewrite/test_chronicle_history_modal.py tests/rewrite/test_chronicle_timesheet_ui.py tests/rewrite/test_reconciliation_ui.py --basetemp $FocusedTemp --junitxml $FocusedXml
$FocusedExit = $LASTEXITCODE
```
Focus failures emit `CHRONICLE_TK_OBSERVATION` with root mapping, foreground PID/HWND,
focus, local/global grab, widget identity and bounded event order. Distinguish a
failed PRECONDITION from a return-focus defect. Geometry waits require visible
restored content, not merely a cleared read token. Preserve diagnostics and return
reproducible production failures for independent adjudication; do not patch Tk on
site, force foreground activation, accept hidden output or waive failed assertions.

Read execution-result.json (raw automated evidence), summary.json (delivery-aware
result), collection/manifest.json, partitions.json, and each partition's manifest.json,
events.jsonl, event-health.json, junit.xml and stdout/stderr logs. Tool/source digests, environment,
arguments, UTC start/end, deferred F3/F4 and cleanup are retained. Only an archive
that passes reopen, CRC and member checks is exclusively published BESIDE the
directory as .zip. A .partial.zip is not successful delivery. Archive errors retain
the directory and raw execution result; overall exit 4 cannot mean PASS. Explicit
link/reparse exclusions are listed; unreadable traversal is an error, never a silent
omission. No archive follows link targets or includes itself. Review artifacts for
task-only contents before manually sharing the verified ZIP; no automatic upload.

Run old bounded scopes SEPARATELY, only where authorized. They are frozen sets,
not full Package F, and previous Storage success does not qualify this revision:

```powershell
& .\scripts\qualify_windows.ps1 -Repo $Repo -ExpectedRevision $Expected -OutputParent $Parent -Scope MetadataProbe
& .\scripts\qualify_windows.ps1 -Repo $Repo -ExpectedRevision $Expected -OutputParent $Parent -Scope Storage
& .\scripts\qualify_windows.ps1 -Repo $Repo -ExpectedRevision $Expected -OutputParent $Parent -Scope Extended
```

Record each distinct printed directory/ZIP, command, exit and source. Inspect hot
journal tests in Storage by full node identity: genuine dirty-page spill/readonly
recovery refusal, cold status 4 with unchanged DB/journal, owned native recovery,
full evidence/profile validation, repeated reopen and exact retries. These fixtures
kill ONLY their owned disposable child. A filename alone is not hot-journal proof;
inability to reproduce is EVIDENCE_INCOMPLETE, not PASS. NTFS identity/alias/lock and
file-publication tests must report actual outcomes and capability skips. Never kill
the operator's ordinary app or infer power-loss safety from process termination.

## F3 — first-run and source setup

Each numbered row below needs its own worksheet entry and timestamp. Use only $Q.

1. Reserve `$LauncherProfile = Join-Path $Q 'isolated launcher profile'` as a new directory.
   Confirm it contains no Chronicle selection/data. Temporarily set LOCALAPPDATA
   only for these source launches; restore it in finally. Do not touch the user's
   real selection file. First launch must show **Welcome to Chronicle**; verify
   the readable suggested timezone, or choose **Advanced / Other** and explicitly
   enter America/Chicago. Click **Cancel**. No Data folder, selection file or worker
   may have been created under this new profile.

```powershell
$LauncherProfile = Join-Path $Q 'isolated launcher profile'
New-Item -ItemType Directory -Path $LauncherProfile -ErrorAction Stop | Out-Null
$PriorLocalAppData = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $LauncherProfile
    & $Py -B .\run_chronicle.py
    Get-ChildItem -LiteralPath $LauncherProfile -Force -Recurse
    # Second launch: choose $Data and America/Chicago, then Create and Open.
    & $Py -B .\run_chronicle.py
    # After normal Close, zero-argument reopen must use the SAME dataset.
    & $Py -B .\run_chronicle.py
} finally { $env:LOCALAPPDATA = $PriorLocalAppData }
```

2. Confirm app-ready state, same dataset UUID/timezone after normal Close/reopen,
   no setup replacement, no legacy-data discovery. Record the new selection record
   under $LauncherProfile/Chronicle only. For a separate explicit creation smoke use a NEW
   `$Engineering = Join-Path $Q 'engineering source dataset'`:

```powershell
$Engineering = Join-Path $Q 'engineering source dataset'
& $Py -B .\run_chronicle.py --data-dir "$Engineering" --timezone America/Chicago --create
& $Py -B .\run_chronicle.py --data-dir "$Engineering"
```

3. On $Data while first owner is ready, start a second explicit process with
   `& $Py -B .\run_chronicle.py --data-dir "$Data"`. It must refuse ownership and
   never become ready. Close its diagnostic window; never delete .chronicle.lock.
   First owner's ordinary operation must continue. Lock-file existence is not ownership.
4. Existing nonempty task-owned folder: create one sentinel file in a new test
   folder, attempt explicit Create, require refusal and unchanged sentinel. For
   v1/v2 refusal use the existing `test_hierarchy_foundation.py` historical fixtures
   through F2; inspect original bytes/identity/modification comparisons and cold
   refusal before restore reservation. No operator may select an old PERSONAL
   dataset for this test. If separate manual v1/v2 images are not supplied as
   qualification-owned fixtures, record the manual case NOT RUN, citing automated
   source-backed evidence separately. No conversion or replacement is allowed.

## F3 — connected main, templates and recording

Use $Data throughout; launch with `& $Py -B .\run_chronicle.py --data-dir "$Data"`.
Use actual mouse/keyboard for all UI claims. Record generated UUIDs from review/
History fields or the cold evidence snapshot below. Names are never identity.

1. **Create project**: create Alpha, Beta and Empty. Select Alpha, **New Task**: Design.
   Select Design, **Add date-only work**: keep the form's actual dataset-local
   date (record it), 0:10, comment parent-before-child. This permits today's main
   Individual/Cumulative observation without changing the machine clock.
   Save. Select Design, **New Task**: Circuit; select Circuit, **New Task**: Routing.
   The destination review must show each immediate parent path. A fourth level is
   disabled/explained. Create another root named Routing in Beta and an Unassigned
   root General (select Unassigned before New Task). Select Empty, **Rename project**
   to Empty renamed; select Beta's Routing, **Rename task** to Routing reference.
   Both retain UUIDs; the renamed empty project stays visible.
2. Expand/collapse all three levels, choose **Sort A-Z**, toggle **Today / This Week**.
   Retain selected UUID and open state; no flicker/row reconstruction on unchanged
   minute refresh. Parent Individual includes its own prior 00:10 for Today; Cumulative adds
   descendants once. Historical October dates appear in the corresponding History/
   Custom report, not falsely in today's total. Groups are organizational placeholders.
3. Select Routing leaf under Circuit: **Start**, select General: **Switch**, then
   **Stop** after a short observed interval. There is exactly one active entry.
   Parent cannot Start/Switch into new work; Stop with a project selected still
   stops the actual active entry. Active leaf says Running, ancestors Running
   descendant, project Group—Running task; none claims the descendant's timer.
4. Start a leaf, **Correct active start** using a reviewed past minute today in
   America/Chicago; record original/effective start and immutable correction. Cancel
   a second review without writes. Ordinary Close does not Stop. Reopen $Data;
   entry UUID/effective start/version persist, then Stop explicitly.
5. **Mini mode**: green/red text state, active task or eligible selected leaf,
   Individual Today. **Show Main** closes mini when **Keep Mini Open** is Off
   (default), retains it when On. Toggle is session-local. Check actual topmost
   behavior. Opening History/Timesheet/Move/Backup/editor must suppress competing
   mini input and topmost/focus theft. No implicit Stop on navigation.
6. **Templates... → Create**: name Board; **Add root** Assembly, **Add child** Test,
   **Add root** Documentation. Review tree; Save. Edit Test to Validation, reparent
   that child beneath Documentation, and reorder the two roots with Up/Down. Keep
   maximum template depth two. Cancel once and verify no definition version change;
   repeat and Save the real edit. **Duplicate** as Board copy; node UUIDs independent.
   Select Alpha; apply Board, reviewing full destination and mapping; apply again
   under General (level one plus this depth-two blueprint fits level three).
   Fresh task UUIDs, no copied time, no parent bump.
   Later editing the definition leaves instances unchanged. Active name collision
   trim/casefold refuses; duplicate task names remain valid.
7. In the Alpha instance add 0:01 date-only work today to Validation. Select its
   Documentation parent: **Move / Reparent**, review source UUID/path/descendant
   count, choose Beta root, **Confirm Move**. UUID/direct work unchanged, grouping
   and Cumulative change once; selection follows moved identity. Cancel another
   review without movement. Self/descendant/depth-overflow/running-parent destinations
   refuse. Move a running leaf only while it stays a leaf; identity/start cannot change.
8. On a nonrunning applied branch, **Archive** its Validation child first (record
   its own timestamp), then Archive its root. Main hides descendants; accounting retains them.
   **Archived Items** expands original tree; exercise four sort choices, select
   direct **Work History**, **Unarchive** explicit parent. Independently archived
   child remains archived. Unarchive that child separately. Archiving a
   running-containing branch refuses without Stop.
9. **Delete** a new unused branch: inspect complete counts/dependencies, Cancel first,
   then typed DELETE on that SAME disposable branch. It disappears irreversibly,
   no Trash/Restore. Protected Design/work/applied partial-batch Delete must refuse.
   Create a new Batch only project and Apply Board there, without work. Delete of
   one root must refuse because another root belongs to the same Apply receipt;
   Delete of the whole otherwise-unused Batch only project may commit after full
   review. Retain the protected instance. Template definition Delete after Apply must preserve instances
   and frozen Apply/Duplicate snapshots. No Delete retry on uncertain outcome: inspect
   current presence, record historical UNVERIFIED, explicitly exit/reopen.

## F3 — History, frozen reports and POL-R

1. Use a fresh eligible task Quarter example. Add date-only work 2026-10-19 0:03
   and 2026-10-20 0:03. Add another task Unknown with 0:03 on October 19. Add timed
   work on Routing, 2026-10-21 09:00–10:00, only when this end is in the actual past.
   Work History must show real endpoints vs endpoint-free declared work. Set **All**
   when current week excludes these dates. Edit timed end to 09:30; Details retains
   both revisions. Delete a disposable closed entry, confirm, inspect retained deleted
   revision. Parent History lists direct work only, not child entries.
2. **Week starts** Monday. **Timesheet / POL-R** → Custom October 19–25, All tasks,
   **Preview**. Exact task/day Actual vs decimal hundredths vs suggested quarters
   remain distinct. Quarter example Monday/Tuesday suggestions 0.25/0.00, Actual
   0.05/0.05. Choose Selected tasks/Tuesday only: seven-day basis still gives Tuesday
   0.00, not independently rounded 0.25. Selecting parent UUID never selects descendants.
   Preview alone writes no report/receipt/confirmation. Return to full-week scope.
3. **Save Timesheet** to $Report. Require verified saved status and exact UTF-8
   content/digest, export UUID and original destination. Close/reopen Timesheet,
   **Saved Reports → Load registered report → Check File Status** reproduces bytes.
   **Save Copy As** Cancel does nothing. Pick a task-owned existing different file;
   ordinary Save/Retry must not overwrite. **Overwrite** defaults No. Only explicitly
   approve replacement of that disposable sentinel; original registered evidence stays
   fixed. Record native chooser and confirmation observations, not just file existence.
4. **Review POL-R Confirmation**: positives selected by default; choose only Quarter
   example Monday and explicitly check its Tuesday zero. Leave Unknown unchecked.
   **Confirm checked** records absolute 0.25 and 0.00; unchecked work remains Unknown.
   Confirmation History shows immutable batch and current references. **Manual POL-R
   Confirmation** on another fresh task/day with 3.00; invalid 2.30 refuses unchanged.
   Manual may operate without a source report; this is local declaration, never
   external submission verification. Repeating amount replaces absolute state, not adds.
5. On a fresh task add October 19 Monday 3:00, save to a NEW $Q/a-original.txt report
   and confirm 3.00. Add the same Monday 2:00:
   Actual 5.00, Confirmed 3.00, Delta +2.00, Suggested 5.00. On a separate 3:00 task
   save to NEW $Q/b-original.txt, confirm 3.00, then History correct to 2:30:
   Delta -0.50, Suggested 2.50. Earlier
   report text/basis/digest and confirmation history remain exact. Explicit fresh
   Preview recalculates; Compare loaded report flags changes without rewriting source.
6. **Reconciliation** daily/weekly/partial Custom: inspect Unknown vs confirmed zero,
   signed Delta vs Suggested gap and full-week rounding adjustment. Opposing daily
   mismatches never become complete coverage just because weekly sums agree. Stale
   confirmation review requires fresh prior review and individual stale acknowledgement.
   **Defer / Review later** does not confirm. Read-only views create no work.
7. Reminders check previous week on a used day and current week Monday/Friday. With
   outstanding work in one applicable period, observe banner, **Open Timesheet** and
   **Dismiss for today**; opening/saving alone must not dismiss. Dismiss writes only
   approved date/request state and persists same-local-day restart. If the actual
   date provides no due condition, create disposable prior-week declared work dated
   from that actual local calendar (record dates), or mark presentation NOT RUN.
   Never change the host clock or falsely call a programmatic evaluation native UI proof.

## F3 — modal worksheet and backup/fresh session

For New Task name, Move/Reparent, History correction/calendar, Timesheet preview,
source/manual confirmation, backup chooser, Delete, template editor/Apply/Delete:
open with pointer/keyboard, type, verify blocked main/mini mutation, Escape/Cancel
where supported, ordinary close/reopen, no double acceptance, focus return to LIVE
origin, no stuck local grab. Archived Items/Templates are MODELESS; their operations
may open owned modals. Record per-window actual outcomes, unexpected dialogs and
OS focus/topmost behavior. Never answer an unknown security/file dialog automatically.

1. Start a legitimate leaf timer and record its UUID/start. **Backup Chronicle** →
   **Choose destination** $Backup → **Create Backup**. Require verified completion,
   responsive GUI, same active identity, no fabricated Stop. Canceling chooser does
   nothing; existing backup target refuses. Close dialog and app normally.
2. Cold commands; no Tk/worker should start during verify/restore. $Restored MUST
   not exist; cold inspect only after closing all owners:

```powershell
& $Py -B .\run_chronicle.py --inspect-dataset "$Data"
$InspectExit = $LASTEXITCODE
& $Py -B .\run_chronicle.py --verify-backup "$Backup"
$VerifyExit = $LASTEXITCODE
& $Py -B .\run_chronicle.py --restore-from "$Backup" --data-dir "$Restored"
$RestoreExit = $LASTEXITCODE
& $Py -B .\run_chronicle.py --inspect-dataset "$Restored"
Get-FileHash -LiteralPath (Join-Path $Data 'chronicle.sqlite3'),$Backup,$Report -Algorithm SHA256
& $Py -B .\run_chronicle.py --data-dir "$Restored"
```

3. Fresh app/worker/session, same dataset UUID/zone/week, work/revisions/active start,
   template graphs/mappings, archive state, registered report, confirmations and
   dismissal. No retained preview/editor/pending callback from original session.
   Explicitly Stop after a recorded interval; add 0:01 legitimate date-only work.
   Close, inspect restored again, rehash ORIGINAL/image/report: unchanged. Restored
   database legitimately differs. Do not require identical source/backup SQLite page
   layout; compare complete logical facts and immutable bytes instead.

With all owners CLOSED, these task-only read-only observations can support claims.
Pass only $Data or $Restored from this procedure; retain their output under $Q/evidence.

```powershell
$Facts = @'
import sys,sqlite3,json,hashlib
from pathlib import Path
p=Path(sys.argv[1])/'chronicle.sqlite3'
c=sqlite3.connect(p.absolute().as_uri()+'?mode=ro',uri=True)
try:
 print('identity',c.execute('pragma application_id').fetchone(),c.execute('pragma user_version').fetchone())
 print('integrity',c.execute('pragma integrity_check').fetchall(),'foreign_keys',c.execute('pragma foreign_key_check').fetchall())
 for (name,) in c.execute("select name from sqlite_schema where type='table' order by name"):
  rows=sorted(c.execute('select * from "'+name.replace('"','""')+'"').fetchall(),key=repr)
  raw=json.dumps(rows,default=lambda v:{'blob_hex':v.hex()},sort_keys=True,separators=(',',':')).encode()
  print(name,len(rows),hashlib.sha256(raw).hexdigest())
 print('metadata',c.execute('select * from dataset_meta').fetchall())
 print('active',c.execute('select * from active_timer').fetchall())
finally:c.close()
'@
& $Py -B -c $Facts "$Data" | Tee-Object -FilePath (Join-Path $Q 'evidence\original-facts.txt')
& $Py -B -c $Facts "$Restored" | Tee-Object -FilePath (Join-Path $Q 'evidence\restored-facts.txt')
```

Take matching original/restored snapshots BEFORE new restored work and separate
after snapshots with NEW output filenames. Compare full facts/digests, not counts
alone. The inspector supplies complete Chronicle validation. Synchronous/FK are
connection-local: read-only PRAGMA defaults do not prove Chronicle's runtime profile.
F2 schema/worker tests verify DELETE/3/1 on the actual owning production connection.
For an additional operator profile proof after closing the UI, run the production
owner on this disposable directory, record it, then close; never open alongside UI:

```powershell
$ProfileProof = @'
import sys
sys.path.insert(0,'src')
from chronicle.sqlite_store import SQLiteStore
s=SQLiteStore(sys.argv[1])
try:
 print(s.dataset_id,s.timezone,s.info)
 for pragma in ('journal_mode','synchronous','foreign_keys','user_version','application_id'):
  print(pragma,s.connection.execute('pragma '+pragma).fetchone()[0])
 s._verify_complete(s.connection)
finally:s.close()
'@
& $Py -B -c $ProfileProof "$Data"
```

## F4 — actual Windows Sleep/resume (separate gate)

1. Record policy permission, machine/VM sleep capability and source. Use a NEW
   `$SleepData = Join-Path $Q 'actual sleep dataset'`, explicit create command with
   America/Chicago. Create one leaf Sleep test. Start it normally. Record wall clock,
   displayed task and accepted entry UUID/start from read-only active facts while
   idle (never read the actively locked lock byte). No second writable owner.
2. Initiate normal **Windows Start → Power → Sleep manually**. Do not run a sleep,
   hibernation, shutdown or clock-setting script. Resume the SAME machine/session
   after a recorded interval. Lock/display blank alone is insufficient.
3. Record observed suspend/resume evidence where available: timestamped Windows
   System Power-Troubleshooter/Kernel-Power entries, permitted `powercfg /lastwake`
   output or machine/VM event record. Read-only event access may be unavailable;
   record the limitation, do not elevate. If no reliable evidence establishes real
   sleep, mark EVIDENCE_INCOMPLETE. If policy prevents sleep, BLOCKED/NOT EXECUTED.
4. Same active entry/start/task after resume, continuous elapsed Actual INCLUDING
   the suspended interval, responsive tree/mini, no automatic Stop/Switch or duplicate
   work. Record any backward-clock/unavailable warning truthfully; do not dismiss it
   by guessing time. Stop explicitly at a recorded time; History retains exact UTC
   endpoints and local attribution. Close/reopen and cold inspect; immutable evidence
   validates and no active duplicate appears. Compare exact endpoint difference to
   recorded elapsed period, acknowledging observation precision.
5. F1 deterministic DST/midnight/forward/backward/simulated-gap cases supplement
   this evidence but NEVER replace real Sleep. Process termination is not hardware
   power-loss safety. Neither a VM lock nor Linux time injection qualifies F4.

## Evidence worksheet and adjudication

Create separate records for F2, each numbered F3 scenario/window, and F4. Use NEW
task-owned evidence files; never overwrite prior observations. Suggested CSV fields:

```text
gate,scenario_id,source_sha,windows_build,physical_or_vm,python_executable,python_version,sqlite_source_id,tcl_version,tk_version,tzdata,ntfs_volume,dataset_uuid,dataset_path,utc_timestamp,operator_action,expected,actual,status,exit_status,evidence_path,logical_comparison,cleanup_or_lock_state,skip_or_block_reason,defect_id
```

For each high-value preservation claim attach original output, exact request/export/
timer identity and table/content digest comparison or validated test evidence.
Record screenshots where useful for focus, labels and unexpected dialogs, using
only synthetic names. A checked box or a ZIP filename alone proves no integrity.

| Section | Scenario inventory | Result before execution |
| --- | --- | --- |
| F2 | Runtime/source, full inventory/partitioned regression, MetadataProbe and authorized bounded scopes, hot journal, NTFS/locks/files, v1/v2 refusal | Original attempt EVIDENCE_INCOMPLETE; native repeat pending review |
| F3 | First-run 1–4; main/templates/recording 1–9; History/report/POL-R 1–7; each modal; backup/fresh session 1–3 | NOT RUN |
| F4 | Real Sleep/resume 1–5, exact stopped work and reopen | NOT RUN |

Keep failure inventory with expected/actual, portable/native scope, reproduction,
diagnostic paths and disposition (deferred/returned for adjudication). Do not merge
different revisions into one result. An operator result is evidence for independent
review, not authority to close Stage 4. No automatic Stage 5, installation, merge
or release follows this procedure.
