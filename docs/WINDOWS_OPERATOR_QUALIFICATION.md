# Stage 4 Windows qualification — current ordinary schema 4

This covers unattended F2 automation and separate supervised F3/F4 procedures
for the checked-out ordinary fresh-schema-4 source, not a record that native gates
ran. E/E1 provide the existing production runtime; F1 production integration is
independently accepted for continued development. F2a reconciles metadata and this
runbook only. The separately approved F2b-Focus implementation adds six production
subjects and bounded control identity/evidence checks; native execution remains
unauthorized. Filesystem/skip-ledger preparation, native F2, supervised F3 and actual
Sleep F4 require separate authorization. Native prerequisites remain unverified.
Stage 4 remains **IN PROGRESS**, Stage 5 **NOT STARTED**. Hardware power loss,
external POL-R redistribution/worked-zero policy and installation/cutover remain
separate. Never enter data into an employer/customer POL-R system during this run.

## Gates and evidence rules

| Gate | Required evidence | Development-host status |
| --- | --- | --- |
| F1 | Production schema-4 SQLite/worker integration and separately executed real Tk workflows | Independently accepted for continued development at `5b2367fd59f2ef9c001f0a01815dda52a8379339`; portable/X11 evidence only |
| F2 | Current-revision native Windows automated collection/events/JUnit/logs, inventory, cleanup and verified delivery | NOT RUN on the present source; F2b-Focus implementation/portable evidence is separate; historical attempts below remain EVIDENCE_INCOMPLETE/FAIL |
| F3 | Actual supervised Windows controls, focus, dialogs, files and restored fresh session | NOT RUN |
| F4 | Actual Windows Sleep/resume with preserved timer and validated recovery | NOT RUN |

Use PASS, FAIL, BLOCKED, NOT RUN or EVIDENCE_INCOMPLETE for each scenario. PASS
requires its observations AND supporting evidence. A required FAIL makes its gate
FAIL; missing, skipped, blocked, not-run or invalid required evidence prevents gate
PASS. Tool exit zero alone is insufficient. Prior-revision results (including the
earlier Extended 657 passes/22 skips) are context, not current schema-4 acceptance.
F1 portable success does not establish F2, F3 or F4 success.
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

## Later October 30 supported execution and outstanding evidence

The later 19:10:50 UTC run is supplied independently inspected evidence, not execution
on this development host. Archive:
`Chronicle Stage4 20261030T191050Z 1b5b039d77884f81a687d9f9b9646ba2.zip`.
SHA-256: `b809ec22841d2cf4dbbbd7777005a759f7e2d2353f164ab6b5d678b398127419`.
It reports 3,827 collected, 1,922 supported completed: 1,816 passed, 15 failed,
91 skipped. Retained legacy: 1,905 selected, zero executed after inventory mismatch.
The archive comparison identified two eager UUID parameters changing node identities;
two more eager nested parameter values are also fixed without altering runtime UUIDs.
The 15 supported failures are eight PowerShell fixture cases, six History/Timesheet
foreground preconditions and one History details completion failure. F2 FAIL;
F3/F4 NOT RUN. Verified delivery does not convert failed execution to success.

The original ZIPs, detailed archive-analysis report and separately generated 29-node
ledger were not accessible on this corrective development host. Source changes do
not claim fresh inspection of those artifacts or establish native root causes.
The supplied 62 INAPPLICABLE and **29 UNRESOLVED** skip classifications are preserved.
Do not invent missing node IDs/reasons. Obtain the original ledger for separate
coverage adjudication; keep raw machine paths outside source. Symlink-creation
privileges remain distinct from the unreadable-source permission case. A sharing
violation is not ACL-denial evidence; hard-link evidence does not establish reparse
safety. No security changes, replacement filesystem tests or waivers are authorized.

## F2 — separate automated runs

The commands below are retained for a separately authorized native run, not F2a
execution. Only after independent F2b preparation/adjudication and explicit F2
authorization, run the full source regression against the exact reviewed SHA:

```powershell
& .\scripts\qualify_stage4_windows.ps1 -Repo $Repo -ExpectedRevision $Expected -OutputParent $Parent -Python $Py
$FullExit = $LASTEXITCODE
Write-Host "Full wrapper exit: $FullExit"
```

The wrapper immediately prints its NEW absolute evidence directory. `collection/`
retains the complete original inventory. `partitions.json` assigns every node
exactly once: SUPPORTED_RUNTIME is direct `tests/rewrite/*.py` sources plus the
approved root-launcher bridge `tests/test_root_launcher.py`; RETAINED_LEGACY is the finite reviewed list of
other top-level Task Time modules in `stage4_qualification.py`. Unknown/new/shared
sources remain UNCLASSIFIED and block supported qualification. No test disappears.
The partition contains ordinary schema-4 production, candidate schema-4, explicit
historical schema-3, pure/shared domain, collector/tooling and platform-specific
tests. Source membership alone does not establish production schema-4 execution.
`environment.json` records integer `schema_required: 4`, the ordinary application
requirement, not the version of every test. Future native F2 must verify that actual
record. A successful collector does not qualify every product/platform requirement;
F2b-Focus implements the approved current-runtime native focus set for review;
native execution remains unauthorized. Separate adjudication must address missing
filesystem/recovery evidence and original 29-node ledger. The frozen bounded
allowlists stay unchanged.

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
All original 29 filesystem skips remain unwaived; their individual source-bound
ledger is required, never reconstructed from counts. F1's 505 portable skips are
not that ledger. APPLICABLE must execute; INAPPLICABLE requires an identified
replacement; BLOCKED_REQUIRED lacks a required capability; UNRESOLVED lacks a
reviewed disposition. F2a assigns no new classifications. The POSIX-only runtime4
journal-unlink fixture remains POSIX evidence. No Windows replacement is authorized
here. Actual NTFS identity, sharing, hard links/reparse points, private recovery
and cleanup require F2b/F2 evidence; Linux execution cannot close those gates.

For the focused native reproductions, use a NEW task-owned temporary path and retain
raw output/JUnit before the full wrapper. Use an already active, unlocked Windows 11
interactive test session on its normal input desktop, preferably in a dedicated VM.
F2 requires no operator clicks, Alt+Tab or per-case supervision. Do not use a locked,
disconnected or noninteractive session. An ordinary unlocked workstation is a
compromise: reserve the entire session, including mouse/keyboard and remote access,
for the run. Concurrent use, notifications and policy locks can invalidate evidence.
The driver never logs in, unlocks, switches desktops or answers security dialogs.
```powershell
$FocusedTemp = Join-Path $Q ('focused-' + [guid]::NewGuid().ToString('N'))
$FocusedXml = Join-Path $Q ('focused-' + [guid]::NewGuid().ToString('N') + '.xml')
& $Py -B -m pytest -q -p no:cacheprovider -o 'addopts=' -ra tests/rewrite/test_stage4_qualification.py tests/rewrite/test_qualification_collector.py tests/rewrite/test_app.py tests/rewrite/test_chronicle_history_modal.py tests/rewrite/test_chronicle_timesheet_ui.py tests/rewrite/test_reconciliation_ui.py --basetemp $FocusedTemp --junitxml $FocusedXml
$FocusedExit = $LASTEXITCODE
```
Focus failures emit `CHRONICLE_TK_OBSERVATION` with root mapping, native top-level
and Tk client HWND, foreground HWND/PID, focus/grab, widget identity and bounded
ordering. PRECONDITION versus RESULT remains explicit. History details require
matching entry/task/token delivery and rendered immutable content, not a null token.
No production selection/rendering or focus behavior is changed.

### Unattended native focus characterization

#### One-command focused runner

F2b-Focus's subject/control implementation is independently accepted at
`8bd0ecac8c7ca4b9f63868928cbd9b5aaeaf7647`. The bounded runner is implemented
for independent review; Codex has not executed native qualification. After runner
acceptance, the Windows operator starts **only** this script once, from the reviewed
checkout in Windows PowerShell 5.1, supplying the full independently approved
complete-checkout revision from its execution receipt. `-ExpectedRevision` binds
the entire current source, not necessarily the historical runner-development commit:

```powershell
& .\scripts\qualify_f2b_focus_windows.ps1 -ExpectedRevision FULL_REVIEWED_40_CHARACTER_SHA
```

The generated native-control fixture has a bounded ordering correction: production
`controlled_origin(root, monkeypatch, request, ordinary)` explicitly waits for the
actual StartupWindow/schema-4 worker handoff before control preparation grids the
wrong-return Entry. Previously the autouse fixture could grid that Entry before
StartupWindow packed its frame into the same root, causing a setup conflict. This
was a test-harness defect; no production defect was demonstrated. Historical
controls retain `controlled_origin(root, monkeypatch, request)` and their connected
schema-3 runtime. Both production normal/negative controls use the same dependency.
The wrong-focus operation, native PRECONDITION/RESULT validation, deadlines, input,
Job and cleanup contracts are unchanged. A disposable portable body probe verifies
real Tk/worker lifecycle ordering; it is not native Windows control evidence. The
corrected source and portable evidence require independent acceptance before any
separately authorized one-command Windows execution. F2b/F2/F3/F4 are not thereby
passed; original failed/incomplete attempts and the 29-node ledger remain unchanged.

Optional `-OutputParent` and `-Python` select an existing trusted evidence location
and installed interpreter. The default evidence parent is
`LOCALAPPDATA\Chronicle Qualification\F2b Focus`, separate from ordinary data;
missing dedicated parent directories are created only after their existing ancestor
passes admission. The repository comes from the script location. Interpreter
selection prefers `.venv\Scripts\python.exe`, then the existing installed `python`;
Store aliases refuse. No package/environment installation, execution-policy change,
elevation, security change or manual GUI action is part of this procedure. An absent
required SHA refuses without prompting. A blocked policy or prerequisite remains
BLOCKED; the script never chooses another disk or unlocks the desktop.

Reserve an exclusive, connected, unlocked Windows 11 client desktop and leave it
undisturbed. Output must be fixed local NTFS, canonical and outside repositories,
datasets, cloud/network paths and existing evidence runs. Each invocation reserves
one new GUID directory and preserves earlier output. Source admission requires the
exact reviewed clean branch/SHA, remote agreement, current source hashes and imported
Chronicle identity. Actual Python/SQLite/Tcl/Tk/tzdata/pytest/dependency, interpreter
image/venv, desktop and Job-containment observations remain required.

The corrective runner uses strict UTF-8 without a BOM for authoritative collector
records, native observation text and archive JSON readback. PowerShell 5.1 reads
summary bytes through an explicit throwing UTF8Encoding before ConvertFrom-Json;
invalid encoding prevents PASS. Git text is decoded strictly as UTF-8 and tracked
filenames are split on raw NUL bytes before individual UTF-8 decoding, preserving
Unicode pathname identity. There is no ANSI fallback, replacement decoding or
automatic BOM conversion. Locale-adversarial portable tests exercise the actual
collector writer and corrected reader; native Windows verification remains pending.

The corrected source-launcher regression independently uses a genuine schema-4
backup, cold CLI restore and fresh ordinary GUI/worker session, preserving timer,
work and source/backup bytes while accepting one new Request. A separate historical
schema-3 backup must refuse ordinary CLI restore without creating a target or
changing either input. The earlier failed legacy success expectation is retained
in historical diagnostic evidence; no compatibility fallback or migration is added.

The fixed collection is exactly **six historical subjects, six production subjects
and four independent native controls**. Exact full IDs, source/fixture closure and
schema roles are checked before input and again against the original manifest at
execution collection. Four controls run serially first: each fixed History `[none]`
subject's normal and deliberately wrong-return control. Their existing validator
must distinguish a genuine negative RESULT failure from setup failure. Any failed
or incomplete control stops before the twelve subjects; no scope widening or retry
occurs. All sixteen enclosing tests must pass without skips, xfail/xpass, deselection
or omission. Native driver code, input count and every existing deadline are unchanged.

The script prints source, phase, completed/expected counts, heartbeat, final status
and evidence paths. PASS requires exact inventories/source agreement, complete
events/JUnit/native/control evidence, owned cleanup and verified archive delivery.
FAIL retains a demonstrated assertion failure. BLOCKED denotes a prerequisite
refusal before the affected phase; EVIDENCE_INCOMPLETE retains execution/evidence/
cleanup/delivery uncertainty. A demonstrated failure is retained even alongside
independent incompleteness. Exit zero is reserved for verified PASS. Archive summary
bytes are proposed completion records until successful controller acknowledgement;
an unverified ZIP candidate is never proof of PASS.

Return the printed evidence ZIP for independent review. The directory retains raw
commands, source/environment records, manifests, event health, stdout/stderr, JUnit,
native PRECONDITION/RESULT, four control directories, production readiness, SQLite
fact comparisons, watchdog/Job/cleanup records and source rechecks. Existing archive
machinery records omitted links and verifies exact membership/CRC; the runner also
checks available member hashes and final-summary readback. Preserve the directory
and any unverified candidate after delivery failure; do not rerun to continue a failed
attempt. This focused run does not execute the full Stage 4 collector, filesystem
qualification, supervised F3 or Sleep F4. Case C and the original 29-node ledger remain
unresolved and unwaived.

#### Retained subject/control protocol and historical diagnostic command

The original six cases below remain historical schema-3 native controls. They do
not automatically qualify the ordinary schema-4 GUI. F2b-Focus adds exactly six
production schema-4 node/source authorizations, for twelve total; it authorizes no
native execution. The existing root fixture attaches the same unchanged driver
before StartupWindow hands that root to the ordinary application and sole worker.

The new exact source is `tests/rewrite/test_runtime4_native_focus.py`. Its subjects
are `test_ordinary_schema4_history_parent_grab_focus_return_identity_and_guard`
with exactly `[local]`, `[none]`, `[missing]`, `[reused]`,
`test_ordinary_schema4_timesheet_origin_return_competing_grab_destroy_and_reentry`,
and `test_ordinary_schema4_global_grab_and_deleted_focus_origin_are_not_replaced`.
Their phase pairs remain respectively `PRECONDITION History origin focus` /
`History actual return focus`, `PRECONDITION Timesheet origin focus` /
`Timesheet actual return focus`, and `PRECONDITION Timesheet destroyed origin` /
`Timesheet root fallback focus`. Exact collected nodes and fixture identities must
match the reviewed source before any separately authorized native execution.

The global-grab subject deliberately attempts one refused opening: no Timesheet
owner, unchanged competing global grab/facts and exactly one actual ValueError,
`Timesheet cannot replace an unrelated or global grab`. The diagnostic is retained;
destroying the competitor and completing the valid destroyed-origin/root fallback
must add no diagnostic. The other Timesheet subject preserves its historical
competing-local-grab follow-up and exact intentional refusal. Other callback
exceptions fail. Portable real-Tk evidence does not establish native focus success.

The diagnostic command below is retained for provenance, not an additional operator
step or the new sixteen-instance runner. Only after separate execution review, use the approved interpreter/source and
the existing disposable `$Q`; this does not execute or qualify complete F2/F3. Record `$Expected`, runtime,
console command, UTC action times and the resulting console transcript/JUnit. Run
the six cases serially together with the focused controls, without manual activation.
The test-only `win32_focus.py` driver is registered by the existing root fixture
only for the twelve exact reviewed node/source identities. The historical command
below retains its original six-subject list; it is not the new production list.
Collection performs no activation.

```powershell
$History = 'tests/rewrite/test_chronicle_history_modal.py::test_real_tk_history_parent_grab_focus_return_identity_and_guard'
$Sheet = 'tests/rewrite/test_chronicle_timesheet_ui.py::'
$FocusNodes = @(($History + '[local]'), ($History + '[none]'), ($History + '[missing]'), ($History + '[reused]'),
    ($Sheet + 'test_real_tk_timesheet_origin_return_competing_grab_destroy_and_reentry'),
    ($Sheet + 'test_real_tk_global_grab_and_deleted_focus_origin_are_not_replaced'))
$CaseTemp = Join-Path $Q ('focus-' + [guid]::NewGuid().ToString('N'))
$CaseXml = Join-Path $Q ('focus-' + [guid]::NewGuid().ToString('N') + '.xml')
$CaseLog = Join-Path $Q ('focus-' + [guid]::NewGuid().ToString('N') + '.log')
& $Py -B -m pytest -q -p no:cacheprovider -o 'addopts=' -ra --capture=tee-sys tests/rewrite/test_win32_focus.py @FocusNodes --basetemp $CaseTemp --junitxml $CaseXml 2>&1 | Tee-Object -FilePath $CaseLog
$CaseExit = $LASTEXITCODE
```

Confirm exact nodes against focused `--collect-only` output. The driver verifies live
Tk/native identities, owned window markers against HWND reuse, exact process/thread
and Job membership, active/unlocked session and normal input desktop, visibility/enabled/cloaking,
mouse/modifier/capture/menu state and an unobstructed non-client caption point.
Caption hit testing runs on a separate GUI-free observation thread: same-input-queue
`SendMessageTimeout` does not enforce its timeout. Tk keeps pumping within the
original shared eight-second deadline. Late/unbounded inspection cannot send input.

At most one verified SendInput move/down/up activates the root when necessary.
Then ordinary Tk focus_set selects the exact live origin widget; exact foreground
and native input ownership must agree. A different same-PID top-level is insufficient.
The driver ends terminally DISARMED before returning to the unchanged modal test.
RESULT observations are read-only: no further input, focus repair or retries.
No focus_force, SetForegroundWindow, AttachThreadInput or native focus forcing is used.

Structured observations distinguish BLOCKED environmental/target prerequisites from
FAIL activation/return results. Existing pytest/F2 error aggregation is unchanged;
neither status can qualify. Refused/partial input retains counts and native errors,
without assuming UIPI. Uncertain synthetic button state stops the pytest session;
the driver never releases a button/key it did not press or blindly repairs input.
Outstanding state must be safely resolved outside qualification before another run.
Desktop observations and input insertion are not atomic; this is no concurrent-user
or hostile-desktop guarantee. Existing Job containment/watchdogs/cleanup remain intact.

Portable injected faults are not native acceptance. The native-control launcher
has exactly two fixed complete subject identities: historical schema-3 History
`[none]` and production schema-4 History `[none]`, each with positive/negative
return, for four native-only control executions. It runs the selected authorized
node with a normally presented, disposable foreign control
window and requires real caption activation. A second control deliberately directs
ordinary return focus to the wrong widget after valid setup and requires a RESULT
failure, with zero subsequent driver input. Inability to establish the real control
is a failure, never a mocked PASS. Config, command, native observations, JUnit,
source hashes and status must all identify that exact selected subject. The subject
module's hash accompanies the existing driver/control hashes. Production RESULT
must retain actual dataset UUID, schema 4, semantic/ordinary readiness, schema4
presentation, non-candidate status and the live DatabaseWorker identity; missing or
inconsistent readiness refuses qualification. Preserve all six original historical
grab/identity/purity assertions. No native control has run under F2b-Focus; F3
operator and F4 actual Sleep remain NOT RUN through this automation.

For the eight PowerShell fixture failures, first run the independent known-output
control and then the unchanged fixtures in ordinary PowerShell 5.1:

```powershell
$PsTemp = Join-Path $Q ('powershell-' + [guid]::NewGuid().ToString('N'))
$PsXml = Join-Path $Q ('powershell-' + [guid]::NewGuid().ToString('N') + '.xml')
$PsLog = Join-Path $Q ('powershell-' + [guid]::NewGuid().ToString('N') + '.log')
$PSVersionTable
Get-Command powershell -CommandType Application | Select-Object Source,Version
& $Py -B -m pytest -q -p no:cacheprovider -o 'addopts=' -ra tests/rewrite/test_qualification_collector.py -k 'actual_powershell_capture_identity_control or explicit_repo_parameter_binding or powershell_fallback_reserved_manifest or powershell_final_status_after_archive_outcome or failed_python_then_failed_fallback' --basetemp $PsTemp --junitxml $PsXml 2>&1 | Tee-Object -FilePath $PsLog
$PsExit = $LASTEXITCODE
```

The helper records its actual executable; if PowerShell 7 is also installed, the
current helper prefers `pwsh`. Do not label that comparison PowerShell 5.1. Use an
already approved environment where the selected executable is the intended 5.1 host,
or mark the 5.1 comparison NOT RUN without changing machine policy. Retain failed
`collector functions ü.ps1`, its SHA-256/BOM, `subprocess.json`, stdout.bin and
stderr.bin from each owned test directory. Compare exact invocation/cwd, actual
exit and independently captured streams with the control; empty is not unavailable.
Supplied focused evidence confirms the eight cases failed before their functions:
PowerShell 5.1 evaluated an empty $PSScriptRoot in the copied default -Repo expression.
Only the test helper's invocation now supplies explicit -Repo from the reviewed
checkout; generated scripts/BOM and wrapper defaults are unchanged. The separate
binding control verifies PSBoundParameters and the exact repository path. All eight
original expected exits remain 0/4; new native execution is still required. Do not
instrument the script under test, bypass execution policy, alter archive expectations
or extend timeouts. Preserve diagnostics for independent adjudication.

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
These are future supervised ordinary schema-4 scenarios, not F2a observations.
Keep one Tk root, one production worker/store and DatasetLock exclusion. Creation
is fresh only: no migration/import, schema selector or incompatible-data repair.

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
   source-backed evidence separately. Also use a CLEAN disposable schema-3 image
   supplied only by separately authorized test infrastructure, never a personal or
   production dataset. With isolated remembered selection pointing to it, ordinary
   schema-4 Open must refuse; compare original database bytes/identity/metadata and
   remembered selection before/after. No replacement dataset or migration/import
   offer may appear. If no authorized image is supplied, record this required case
   BLOCKED/NOT RUN; do not create it by editing schema markers. A hot schema-3
   original requires separate approved native fixture/F2 evidence. Never manufacture
   or edit a rollback journal. Refusal is expected protection, not an error to repair.

## F3 — connected main, templates and recording

Use $Data throughout; launch with `& $Py -B .\run_chronicle.py --data-dir "$Data"`.
Use actual mouse/keyboard for all UI claims. Record generated UUIDs from review/
History fields or the cold evidence snapshot below. Names are never identity.

1. Use **New root project** for Alpha, Beta and Empty. Select Alpha and use
   **New child project** for Assembly; beneath it create Board, then Validation.
   Review each full parent ancestry, UUID and version before accepting the name.
   The structure is Alpha → Assembly → Board → Validation (four project levels),
   plus separate roots Beta and Empty. Select Alpha, **New Task**: Design. Record
   0:10 date-only work on the form's actual dataset-local date (record that date),
   comment parent-before-child. Select Validation and create a separate direct leaf
   with 0:20 on that same local date. No host-clock change. Projects own no time.
   Select Design, **New Task**: Circuit; select Circuit, **New Task**: Routing.
   Full UUID paths distinguish organizational ancestry from these three task levels;
   a fourth task level must refuse. Create another Routing root task in Beta and
   General under virtual Unassigned; duplicate names are distinct UUIDs, never a
   lookup key. Empty remains visible. Rename it Empty renamed, and Beta's Routing
   to Routing reference without changing either UUID. Customer grouping is an
   ordinary Project use, not another entity.
2. Expand/collapse both project and task depths, choose **Sort A-Z**, toggle
   **Today / This Week**. Sorting stays among siblings; selected UUID, expansion
   and meaningful scroll survive refresh. Task Individual is its direct work;
   Task Cumulative includes its task descendants once. Project Individual is **—**,
   not project-owned work. Backend Project Direct sums Individual contributions
   immediately assigned to that project; Project Cumulative includes descendant
   projects without duplication. Application Actual sums task Individual once,
   never all project Cumulative rows. Collapsing a branch changes no totals.
   Before other work below, independently verify Design10 + deep leaf20 =30 minutes
   application contribution; Alpha Direct10/Cumulative30; Validation Direct20;
   Beta Cumulative0. Preserve complete task-owned facts/UUIDs/work/revisions.
   Select the Assembly PROJECT and **Move / Reparent** to Beta, reviewing its whole
   subtree and both complete ancestries. This is one project-subtree Request,
   not repeated task reassignment. After completion: Alpha Cumulative10, Beta20;
   task Individual, Project Direct, application30 and work/revisions unchanged.
   Record this isolated comparison before later worksheet work changes totals.
   Active-path expansion includes all project/task ancestors; historical October
   work belongs in its matching History/Custom report, not fabricated Today values.
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
   Select the deep Validation PROJECT (now under Beta/Assembly/Board); Apply Board,
   reviewing full destination ancestry/versions, template/version/definition and
   ordered fresh node-to-task mapping; apply again
   under General (level one plus this depth-two blueprint fits level three).
   Fresh task UUIDs, no copied time, no parent bump.
   Later editing the definition leaves instances unchanged. Active name collision
   trim/casefold refuses; duplicate task names remain valid.
7. Keep Project Move and Task Move separate. The Assembly PROJECT move in step 2
   uses the owned project modal: complete selected project/task scope and source
   ancestry, permitted destination project or Root and complete destination ancestry,
   then one Request. Attached task UUIDs/work remain; only approved organizational
   relationships change. Self/descendant/cycle, stale or archived targets refuse;
   a fully valid same-parent no-op has no receipt. Unassigned is not a project parent.
   For TASK Move, add 0:01 today to the applied Validation TASK, select its
   Documentation task parent and **Move / Reparent**. The existing task modal reviews
   the exact task branch, UUIDs/versions and source/destination project ancestries.
   Choose Beta project root; Confirm Move. Identity/direct work remain, grouping
   changes once and selection follows the UUID. Cancel a second review without writes.
   Task self/descendant/depth-overflow/running-parent/archived destinations refuse;
   a permitted active-leaf move preserves entry UUID/start. Neither operation copies
   work or creates another recording authority. Cite automated stale-review evidence
   where modal exclusion prevents an interactive stale setup; never bypass that guard.
   Retain D1a authoritative result settlement and Close protections after completion,
   including presentation errors; accepted/unverified work remains app-owned.
8. On a nonrunning applied branch, Archive its Validation task first, then its
   root. Also Archive a qualification-owned nested project. Only the selected
   explicit flag/accepted timestamp changes; descendants inherit effective state,
   not rewritten flags. Active descendants block ancestor Archive without implicit
   Stop/Switch. Main hides archived branches; historical accounting remains.
   **Archived Items** retains original project/task ancestry and read-only context
   rows. Identify the nearest explicit archive source UUID/date in dataset timezone
   with actual offset. Exercise Name—A to Z, Name—Z to A, Date Archived—Newest first
   (default), Date Archived—Oldest first, among siblings. Context/inherited-only
   rows cannot clear an ancestor. Unarchive explicit ancestor; an independently
   archived child stays archived until separately unarchived. Direct task History
   stays available; no archived recording control is introduced.
9. **Delete** a qualification-owned unused nested project/task branch: inspect the
   entire descendant project/task closure, counts and dependency/retirement review, Cancel first,
   then typed DELETE on that SAME disposable branch. It disappears irreversibly,
   no Trash/Restore. Protected Design/work/applied partial-batch Delete must refuse.
   Create a new Batch only project and Apply Board there, without work. Delete of
   one root must refuse because another root belongs to the same Apply receipt;
   Delete of the whole otherwise-unused Batch only project may commit after full
   review. Retain the protected instance. Template definition Delete after Apply must preserve instances
   and frozen Apply/Duplicate snapshots. No Delete retry on uncertain outcome: inspect
   current presence only (not historical outcome proof), record historical UNVERIFIED,
   explicitly exit/reopen and obtain a fresh review/typed confirmation. Delete stores
   no receipt. Work, retained/deleted revisions, frozen export/project references,
   confirmations including zero and whole-Apply dependencies block unsafe removal.
   No soft Delete, Trash, tombstone or erased-history recovery promise exists.

## F3 — History, frozen reports and POL-R

1. Use a fresh eligible task Quarter example. Add date-only work 2026-10-19 0:03
   and 2026-10-20 0:03. Add another task Unknown with 0:03 on October 19. Add timed
   work on Routing, 2026-10-21 09:00–10:00, only when this end is in the actual past.
   Work History must show real endpoints vs endpoint-free declared work. Set **All**
   when current week excludes these dates. Edit timed end to 09:30; Details retains
   both revisions. Delete a disposable closed entry, confirm, inspect retained deleted
   revision. Parent History lists direct work only, not child entries. Check full
   date/time direction: newest date/latest UTC segment first or oldest/earliest
   first, deterministic UUID ties, date-only after timed without invented clocks.
   Multi-day portions retain one entry/revision identity; repeated DST clocks use
   UTC endpoints and existing offset text, not HH:MM string sorting.
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
   Frozen task scope, full seven-day basis and saved labels/bytes never expand by
   project ancestry. After closing the modal, an otherwise eligible later project
   Move may change live grouping; reload and verify the original report bytes and
   TaskLabel project UUID/name remain unchanged. Registration and external Save are
   distinct; no automatic replacement or rewritten frozen path is allowed.
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
   Keep independent C–G controls (Monday/Tuesday Actual → quarter counts; adjustment):
   C 1:08/1:07 →5/4,0min; D 1:08/1:08 →5/5,+14min;
   E 1:10/0:20 →5/1,0min; F 0:03/0:03 →1/0,+9min;
   G 0:15/0:30 →1/2,0min. Do not derive these expectations from displayed decimals.
   For a separate 1:15/0:45 task, confirm4/4 quarters: suggested gaps+1/−1 remain
   MISMATCH/MISMATCH despite equal weekly eight-quarter totals. Explicit zero has
   a batch/current reference; Unknown is not a numeric zero. Existing arithmetic,
   precision, formatting and external-policy limits are unchanged.
7. Reminders check previous week on a used day and current week Monday/Friday. With
   outstanding work in one applicable period, observe banner, **Open Timesheet** and
   **Dismiss for today**; opening/saving alone must not dismiss. Dismiss writes only
   approved date/request state and persists same-local-day restart. If the actual
   date provides no due condition, create disposable prior-week declared work dated
   from that actual local calendar (record dates), or mark presentation NOT RUN.
   Never change the host clock or falsely call a programmatic evaluation native UI proof.

## F3 — modal worksheet and backup/fresh session

For New Task name, frozen New child project destination/name, Project Move review,
Task Move review, full nested Delete, deep-project Template Apply, History
correction/calendar, Timesheet preview, source/manual confirmation, backup chooser
and template editor/definition Delete:
open with pointer/keyboard, type, verify blocked main/mini mutation, Escape/Cancel
where supported, ordinary close/reopen, no double acceptance, focus return to LIVE
origin, no stuck local grab. Archived Items/Templates are MODELESS; their operations
may open owned modals. Record per-window actual outcomes, unexpected dialogs and
OS focus/topmost behavior. Keep compact Mini controls/size and the existing
topmost policy; one root, worker, modal owner and accepted Request remain. Pending/
unverified guards prevent unrelated mutation and double submission. Never answer
an unknown security/file dialog automatically.

1. Start a legitimate leaf timer and record its UUID/start. **Backup Chronicle** →
   **Choose destination** $Backup → **Create Backup**. Require verified completion,
   responsive GUI, same active identity, no fabricated Stop. Canceling chooser does
   nothing; existing backup target refuses. This uses the existing worker-owned
   consistent SQLite backup, never a direct copy of a live main file. Close dialog
   and original app/worker normally before the restored session.
2. Cold commands; no Tk/worker should start during verify/restore. $Restored MUST
   not exist; use the current schema-4 image validator; cold inspect only after
   closing all owners. Protected paths and non-overwriting publication remain:

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
owner on this operator-reviewed disposable directory, record it, then close.
All GUI/worker owners of that directory MUST be closed first. ProfileProof opens
and closes one new task-owned production profile session; never run it alongside
the app or on personal data. It supplements, never replaces, native F2/F3 evidence:

```powershell
$ProfileProof = @'
import sys,json
sys.path.insert(0,'src')
from chronicle.sqlite_store import SQLiteStore
s=SQLiteStore(sys.argv[1],schema_version=4)
try:
 if s.schema_version!=4:raise ValueError('Profile proof requires ordinary schema 4')
 profile={pragma:s.connection.execute('pragma '+pragma).fetchone()[0]
          for pragma in ('application_id','user_version','journal_mode','synchronous','foreign_keys')}
 required=dict(application_id=0x4348524E,user_version=4,journal_mode='delete',synchronous=3,foreign_keys=1)
 if profile!=required:raise ValueError('Profile mismatch: '+repr(profile))
 s._verify_selected(s.connection)
 print(json.dumps(dict(dataset_id=s.dataset_id,timezone=s.timezone,schema_version=s.schema_version,
                       profile=profile,runtime=s.info,complete_verified=True)))
finally:s.close()
'@
& $Py -B -c $ProfileProof "$Data"
if ($LASTEXITCODE -ne 0) { throw 'ProfileProof refused or failed; preserve diagnostics' }
```

## F4 — actual Windows Sleep/resume (separate gate)

1. Record policy permission, machine/VM sleep capability and source. Use a NEW
   `$SleepData = Join-Path $Q 'actual sleep dataset'`, explicit create command with
   America/Chicago, fresh schema 4. Create one leaf Sleep test. Start it normally. Record wall clock,
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
| F2 | Exact current source/inventory/partitions, native prerequisites, approved focus, NTFS/locks/files, private hot recovery and incompatible-data preservation | Current source NOT RUN; F2b-Focus portable implementation is separate; historical EVIDENCE_INCOMPLETE/FAIL, Windows Case C and original 29-node ledger remain outstanding; review and explicit execution authorization required |
| F3 | First-run 1–4; main/templates/recording 1–9; History/report/POL-R 1–7; each modal; backup/fresh session 1–3 | NOT RUN |
| F4 | Real Sleep/resume 1–5, exact stopped work and reopen | NOT RUN |

Keep failure inventory with expected/actual, portable/native scope, reproduction,
diagnostic paths and disposition (deferred/returned for adjudication). Do not merge
different revisions into one result. An operator result is evidence for independent
review, not authority to close Stage 4. No automatic Stage 5, installation, merge
or release follows this procedure.
