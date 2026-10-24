#requires -Version 5.1
<#
.SYNOPSIS
Bounded, noninteractive Chronicle qualification. No installs or application changes.
.EXAMPLE
.\scripts\qualify_windows.ps1 -Scope Critical -OutputParent C:\Qualification
#>
[CmdletBinding()]
param(
    [ValidateSet('MetadataProbe','Critical','Storage','Extended')][string]$Scope = 'MetadataProbe',
    [string]$Repo = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputParent = ([IO.Path]::GetTempPath()),
    [string]$ExpectedRevision,
    [string]$Python,
    [ValidateRange(1,3600)][int]$CollectionSeconds = 90,
    [ValidateRange(1,3600)][int]$TestSeconds = 120,
    [ValidateRange(1,14400)][int]$PhaseSeconds = 900
)
$ErrorActionPreference = 'Stop'
$Evidence = $null
$Collector = $null
$CollectorStarted = $false
$Stdout = $null
$Stderr = $null
$ExitCode = 4
$Helper = $null
$RawCollectorExit = $null
$LauncherFailure = $null
$CleanupUnverified = $false
$Utf8 = [Text.UTF8Encoding]::new($false)

# Windows CRT quoting; ProcessStartInfo.ArgumentList is unavailable in PS 5.1.
function Quote-NativeArgument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $Escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $Escaped = [regex]::Replace($Escaped, '(\\+)$', '$1$1')
    return '"' + $Escaped + '"'
}
function Write-JsonRecord([IO.Stream]$Stream, $Value) {
    $Bytes = $Utf8.GetBytes(($Value | ConvertTo-Json -Depth 30))
    $Stream.Position = 0
    $Stream.SetLength(0)
    $Stream.Write($Bytes,0,$Bytes.Length)
    $Stream.Flush()
}
function Save-Json([string]$Path, $Value) {
    # CreateNew is the ownership operation, including dangling/reparse links.
    $Stream = [IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
    $Primary = $null
    try { Write-JsonRecord $Stream $Value }
    catch { $Primary = $_; throw }
    finally {
        try { $Stream.Dispose() }
        catch { if ($null -eq $Primary) { throw }; Write-Warning "Evidence close also failed: $_" }
    }
}
function New-EvidenceZip([string]$Root, $Completion = $null) {
    # Fallback also includes hidden files. Skip every reparse object, never follow
    # an artifact link out of this unique owned tree; never include the ZIP itself.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $ZipPath = $Root + '.zip'
    if ([IO.File]::Exists($ZipPath)) { throw 'Unexpected existing evidence ZIP; retained without overwrite' }
    $Members = [Collections.Generic.List[string]]::new()
    $Omitted = [Collections.Generic.List[string]]::new()
    $Pending = [Collections.Generic.Stack[string]]::new()
    $Pending.Push($Root)
    while ($Pending.Count -gt 0) {
        foreach ($Path in [IO.Directory]::EnumerateFileSystemEntries($Pending.Pop())) {
            $Attributes = [IO.File]::GetAttributes($Path)
            if (($Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { $Omitted.Add($Path.Substring($Root.Length + 1)); continue }
            if (($Attributes -band [IO.FileAttributes]::Directory) -ne 0) { $Pending.Push($Path); continue }
            $Members.Add($Path)
        }
    }
    $MembershipPath = Join-Path $Root 'archive-members.json'
    $Members.Add($MembershipPath)
    Save-Json $MembershipPath @{files=@($Members | ForEach-Object { $_.Substring($Root.Length + 1) }); omitted=@($Omitted)}
    $FileStream = [IO.File]::Open($ZipPath, [IO.FileMode]::CreateNew)
    $Zip = $null
    $Primary = $null
    try {
        $Zip = [IO.Compression.ZipArchive]::new($FileStream, [IO.Compression.ZipArchiveMode]::Create)
        foreach ($Path in $Members) {
            $Name = $Path.Substring($Root.Length + 1).Replace('\','/')
            if ($null -ne $Completion -and $Completion.Contains($Name)) {
                $Entry = $Zip.CreateEntry($Name)
                $EntryStream = $Entry.Open()
                $EntryPrimary = $null
                try {
                    $Bytes = $Utf8.GetBytes(($Completion[$Name] | ConvertTo-Json -Depth 30))
                    $EntryStream.Write($Bytes,0,$Bytes.Length)
                } catch { $EntryPrimary = $_; throw }
                finally {
                    try { $EntryStream.Dispose() }
                    catch { if ($null -eq $EntryPrimary) { throw }; Write-Warning "Archive entry close also failed: $_" }
                }
            } else { [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($Zip, $Path, $Name, [IO.Compression.CompressionLevel]::Optimal) | Out-Null }
        }
    } catch { $Primary = $_; throw }
    finally {
        foreach ($Resource in @($Zip,$FileStream)) {
            if ($null -ne $Resource) {
                try { $Resource.Dispose() }
                catch { if ($null -eq $Primary) { $Primary = $_ } else { Write-Warning "Archive close also failed: $_" } }
            }
        }
        if ($null -ne $Primary) { throw $Primary }
    }
}
function New-PythonEvidenceZip([string]$Root) {
    $ArchiveArgs = @('-B',$Helper,'--repo',$Repo,'--archive-evidence',$Root,'--archive-completion',(Join-Path $Root 'archive-completion.json'))
    Save-Json (Join-Path $Root 'archive-command.json') @{executable=$Python;arguments=$ArchiveArgs;timeout_seconds=60}
    $ArchiveStart = [Diagnostics.ProcessStartInfo]::new()
    $ArchiveStart.FileName = $Python
    $ArchiveStart.Arguments = (($ArchiveArgs | ForEach-Object { Quote-NativeArgument $_ }) -join ' ')
    $ArchiveStart.UseShellExecute = $false
    $ArchiveStart.RedirectStandardOutput = $true
    $ArchiveStart.RedirectStandardError = $true
    $ArchiveStart.StandardOutputEncoding = $Utf8
    $ArchiveStart.StandardErrorEncoding = $Utf8
    $ArchiveProcess = [Diagnostics.Process]::new()
    $ArchiveProcess.StartInfo = $ArchiveStart
    $Primary = $null
    try {
        if (-not $ArchiveProcess.Start()) { throw 'Archive helper could not start' }
        $ArchiveOut = $ArchiveProcess.StandardOutput.ReadToEndAsync()
        $ArchiveErr = $ArchiveProcess.StandardError.ReadToEndAsync()
        if (-not $ArchiveProcess.WaitForExit(60000)) {
            $ArchiveProcess.Kill(); $null = $ArchiveProcess.WaitForExit(5000)
            throw 'Archive helper exceeded 60-second limit'
        }
        if ($ArchiveProcess.ExitCode -ne 0) { throw ('Archive failed: ' + $ArchiveErr.GetAwaiter().GetResult()) }
        $null = $ArchiveOut.GetAwaiter().GetResult()
    } catch { $Primary = $_; throw }
    finally {
        try { $ArchiveProcess.Dispose() }
        catch { if ($null -eq $Primary) { throw }; Write-Warning "Archive process close also failed: $_" }
    }
}
function Complete-QualificationEvidence([string]$Root, $Raw, $CollectorExit, [string]$Failure, [bool]$UncertainCleanup) {
    # The raw collector receipt is immutable. Final records are exclusively
    # reserved and remain pessimistic until archive closure and acknowledgement.
    $SummaryStream = $null
    $ResultStream = $null
    $FinalExit = 4
    $ArchiveCompleted = $false
    $Summary = @{status='ERROR';collector_status=$Raw.status;collector_exit_code=$CollectorExit;collector_result=$Raw;archive_status='NOT COMPLETED';launcher_failure=$Failure;cleanup_unverified=$UncertainCleanup}
    $Result = @{status='ERROR';success=$false;exit_code=4;collector_status=$Raw.status;collector_exit_code=$CollectorExit;archive_status='NOT COMPLETED';scope=$Scope;qualification='Independent native review required'}
    try {
        $SummaryStream = [IO.File]::Open((Join-Path $Root 'summary.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
        $ResultStream = [IO.File]::Open((Join-Path $Root 'launcher-result.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
        Write-JsonRecord $SummaryStream $Summary
        Write-JsonRecord $ResultStream $Result
        $Good = ($CollectorExit -eq 0 -and $Raw.status -in @('PASS','OBSERVED') -and -not $Failure -and -not $UncertainCleanup)
        $FinalExit = 4
        $Status = $Raw.status
        if ($Good) { $FinalExit = 0 }
        elseif ($Status -in @('PASS','OBSERVED')) { $Status = 'ERROR' }
        $Summary.status = $Status
        $Summary.archive_status = 'VERIFIED'
        $Result.status = $Status
        $Result.success = $Good
        $Result.exit_code = $FinalExit
        $Result.archive_status = 'VERIFIED'
        $Completion = @{'summary.json'=$Summary; 'launcher-result.json'=$Result}
        # Proposed bytes for the final ZIP, not an actual delivery receipt.
        Save-Json (Join-Path $Root 'archive-completion.json') @{purpose='Proposed records; delivery requires launcher acknowledgement';records=$Completion}
        if ($Python -and $Helper -and (Test-Path -LiteralPath $Python) -and (Test-Path -LiteralPath $Helper)) { New-PythonEvidenceZip $Root }
        else { New-EvidenceZip $Root $Completion }
        $ArchiveCompleted = $true
        Write-JsonRecord $SummaryStream $Summary
        Write-JsonRecord $ResultStream $Result
    } catch {
        $Primary = $_
        $FinalExit = 4
        $Summary.status = 'ERROR'; $Summary.archive_status = 'FAILED_OR_UNVERIFIED'
        $Result.status = 'ERROR'; $Result.success = $false; $Result.exit_code = 4; $Result.archive_status = 'FAILED_OR_UNVERIFIED'
        foreach ($Pair in @(@($SummaryStream,$Summary),@($ResultStream,$Result))) {
            if ($null -ne $Pair[0]) {
                try { Write-JsonRecord $Pair[0] $Pair[1] }
                catch { Write-Warning "Final status write also failed: $_" }
            }
        }
        try { Save-Json (Join-Path $Root 'archive-error.json') @{error=$Primary.Exception.ToString();status='ERROR';evidence_retained=$Root;archive='FAILED_OR_UNVERIFIED'} }
        catch { Write-Warning "Archive diagnostic also failed: $_" }
        Write-Host "Evidence finalization failed; directory retained at $Root : $Primary"
    } finally {
        foreach ($Stream in @($SummaryStream,$ResultStream)) {
            if ($null -ne $Stream) {
                try { $Stream.Dispose() }
                catch {
                    $FinalExit = 4
                    $Summary.status = 'ERROR'; $Summary.archive_status = 'FAILED_OR_UNVERIFIED'
                    $Result.status = 'ERROR'; $Result.success = $false; $Result.exit_code = 4; $Result.archive_status = 'FAILED_OR_UNVERIFIED'
                    foreach ($Pair in @(@($SummaryStream,$Summary),@($ResultStream,$Result))) {
                        try { Write-JsonRecord $Pair[0] $Pair[1] }
                        catch { Write-Warning "Final status after close failure could not be written: $_" }
                    }
                    Write-Warning "Final status close failed; delivery unverified: $_"
                }
            }
        }
    }
    if ($ArchiveCompleted -and $Result.archive_status -eq 'VERIFIED') { Write-Host ('Evidence ZIP: ' + $Root + '.zip') }
    return $FinalExit
}
try {
    $Repo = [IO.Path]::GetFullPath($Repo).TrimEnd('\')
    $RepoDirectory = Get-Item -LiteralPath $Repo
    if (-not $RepoDirectory.PSIsContainer) { throw 'BLOCKED: existing source directory required' }
    $SourceAncestor = $RepoDirectory
    while ($null -ne $SourceAncestor) {
        if (($SourceAncestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'BLOCKED: select the canonical source directory, not an alias' }
        $SourceAncestor = $SourceAncestor.Parent
    }
    $Parent = Get-Item -LiteralPath $OutputParent
    if (-not $Parent.PSIsContainer -or $Parent.FullName.StartsWith('\\')) { throw 'BLOCKED: existing local output parent required' }
    $ParentPath = $Parent.FullName.TrimEnd('\')
    if ($ParentPath.Equals($Repo, [StringComparison]::OrdinalIgnoreCase) -or $ParentPath.StartsWith($Repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'BLOCKED: output parent must be outside repository'
    }
    $Ancestor = $Parent
    while ($null -ne $Ancestor) {
        if (($Ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'BLOCKED: output parent aliases are not accepted' }
        if (Test-Path -LiteralPath (Join-Path $Ancestor.FullName 'chronicle.sqlite3')) { throw 'BLOCKED: output must not be inside a Chronicle dataset' }
        $Ancestor = $Ancestor.Parent
    }
    $Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($Parent.FullName))
    if ($Drive.DriveType -ne [IO.DriveType]::Fixed -or $Drive.DriveFormat -ne 'NTFS') { throw 'BLOCKED: approved output parent must be on fixed local NTFS' }
    $Evidence = Join-Path $Parent.FullName ('Chronicle qualification ' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
    Save-Json (Join-Path $Evidence 'collector-owner.json') @{kind='Chronicle qualification';root=$Evidence;id=[Guid]::NewGuid().ToString()}
    Save-Json (Join-Path $Evidence 'launcher.json') @{
        scope=$Scope; repo=$Repo; output=$Evidence; expected_revision=$ExpectedRevision;
        powershell=$PSVersionTable.PSVersion.ToString(); utc=[DateTime]::UtcNow.ToString('o');
        entrypoint=$PSCommandPath; entrypoint_sha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash;
        arguments=@{collection_seconds=$CollectionSeconds; test_seconds=$TestSeconds; phase_seconds=$PhaseSeconds}
    }
    if ($env:OS -ne 'Windows_NT') { throw 'BLOCKED: genuine Windows required; no substitute qualification' }
    try {
        Save-Json (Join-Path $Evidence 'windows.json') @{
            os=(Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec 10 | Select-Object Caption,Version,BuildNumber,OSArchitecture);
            machine=(Get-CimInstance Win32_ComputerSystem -OperationTimeoutSec 10 | Select-Object Manufacturer,Model);
            user=[Security.Principal.WindowsIdentity]::GetCurrent().Name;
            elevated=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        }
    } catch { Save-Json (Join-Path $Evidence 'windows-details-error.json') @{error=$_.Exception.ToString()} }
    if (-not $Python) {
        $Venv = Join-Path $Repo '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $Venv -PathType Leaf) { $Python = $Venv }
        else { $Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source }
    }
    $Python = (Get-Item -LiteralPath $Python -ErrorAction Stop).FullName
    if ($Python -match '\\WindowsApps\\') { throw 'BLOCKED: select an installed Python executable, not a Store execution alias' }
    $Helper = Join-Path $Repo 'scripts\qualification_pytest.py'
    if (-not (Test-Path -LiteralPath $Helper -PathType Leaf)) { throw 'BLOCKED: collector helper missing' }
    $RepoEntrypoint = Join-Path $Repo 'scripts\qualify_windows.ps1'
    if ((Get-FileHash -LiteralPath $RepoEntrypoint -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash) { throw 'BLOCKED: source and executing collector entrypoints differ' }
    $Arguments = @('-u','-B',$Helper,'--defer-archive','--repo',$Repo,'--output',$Evidence,'--scope',$Scope,
                   '--collection-seconds',"$CollectionSeconds",'--test-seconds',"$TestSeconds",'--phase-seconds',"$PhaseSeconds")
    if ($ExpectedRevision) { $Arguments += @('--expected-revision',$ExpectedRevision) }
    Save-Json (Join-Path $Evidence 'launcher-command.json') @{executable=$Python; arguments=$Arguments}
    $Start = [Diagnostics.ProcessStartInfo]::new()
    $Start.FileName = $Python
    $Start.Arguments = (($Arguments | ForEach-Object { Quote-NativeArgument $_ }) -join ' ')
    $Start.WorkingDirectory = $Repo
    $Start.UseShellExecute = $false
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.StandardOutputEncoding = $Utf8
    $Start.StandardErrorEncoding = $Utf8
    $Start.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $Collector = [Diagnostics.Process]::new()
    $Collector.StartInfo = $Start
    if (-not $Collector.Start()) { throw 'BLOCKED: source Python launch failed' }
    $CollectorStarted = $true
    $Stdout = [IO.StreamWriter]::new((Join-Path $Evidence 'launcher-stdout.log'),$false,$Utf8)
    $Stderr = [IO.StreamWriter]::new((Join-Path $Evidence 'launcher-stderr.log'),$false,$Utf8)
    $OutTask = $Collector.StandardOutput.ReadLineAsync()
    $ErrTask = $Collector.StandardError.ReadLineAsync()
    $ProgressState = $null
    $StateReceivedAt = 0.0
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $LastDraw = -1.0
    $LastHeartbeat = -10.0
    while (-not $Collector.HasExited -or $null -ne $OutTask -or $null -ne $ErrTask) {
        $DrainStarted = $Timer.Elapsed.TotalSeconds
        for ($Drain=0; $Drain -lt 100; $Drain++) {
            $Read = $false
            if ($null -ne $OutTask -and $OutTask.IsCompleted) {
                $Line = $OutTask.GetAwaiter().GetResult()
                if ($null -eq $Line) { $OutTask = $null }
                else {
                    $Stdout.WriteLine($Line); $Stdout.Flush()
                    $Position = $Line.IndexOf('CHRONICLE_PROGRESS ')
                    if ($Position -ge 0) {
                        try { $ProgressState = $Line.Substring($Position + 19) | ConvertFrom-Json; $StateReceivedAt = $Timer.Elapsed.TotalSeconds }
                        catch { Write-Host $Line }
                    } else { Write-Host ($Line.Substring(0,[Math]::Min(1000,$Line.Length))) }
                    $OutTask = $Collector.StandardOutput.ReadLineAsync()
                }
                $Read = $true
            }
            if ($null -ne $ErrTask -and $ErrTask.IsCompleted) {
                $Line = $ErrTask.GetAwaiter().GetResult()
                if ($null -eq $Line) { $ErrTask = $null }
                else { $Stderr.WriteLine($Line); $Stderr.Flush(); Write-Host ($Line.Substring(0,[Math]::Min(1000,$Line.Length))); $ErrTask = $Collector.StandardError.ReadLineAsync() }
                $Read = $true
            }
            if (-not $Read -or $Timer.Elapsed.TotalSeconds - $DrainStarted -gt 0.2) { break }
        }
        if ($Timer.Elapsed.TotalSeconds - $LastDraw -ge 0.5) {
            $LastDraw = $Timer.Elapsed.TotalSeconds
            $Status = 'Prerequisites / collection; elapsed ' + [int]$LastDraw + 's'
            $Percent = -1
            if ($null -ne $ProgressState) {
                $EventAge = [Math]::Round(([double]$ProgressState.since_event + $LastDraw - $StateReceivedAt),1)
                $Status = '{0} {1}: {2}/{3}; counts {4}; elapsed {5}s; last event {6}s; {7}' -f $ProgressState.qualification_phase,$ProgressState.phase,$ProgressState.completed,$ProgressState.selected,($ProgressState.counts | ConvertTo-Json -Compress),[int]$LastDraw,$EventAge,$ProgressState.node
                if ($null -ne $ProgressState.percent) { $Percent = [int]$ProgressState.percent }
            }
            Write-Progress -Activity "Chronicle $Scope" -Status $Status -PercentComplete $Percent
            if ($LastDraw - $LastHeartbeat -ge 10) { Write-Host "Heartbeat: $Status"; $LastHeartbeat = $LastDraw }
        }
        # Outer bound protects even a failed collector/ZIP operation. The Python
        # monitor has the tighter collection/node/phase deadlines.
        if ($Timer.Elapsed.TotalSeconds -gt ($PhaseSeconds + 120)) { throw 'Collector outer deadline exceeded' }
        if (($null -eq $ProgressState -or $ProgressState.qualification_phase -ne 'pytest') -and $Timer.Elapsed.TotalSeconds -gt $CollectionSeconds) { throw 'Prerequisite/probe deadline exceeded' }
        Start-Sleep -Milliseconds 100
    }
    $Collector.WaitForExit()
    $ExitCode = $Collector.ExitCode
    $RawCollectorExit = $ExitCode
} catch {
    $LauncherFailure = $_.Exception.ToString()
    $ExitCode = 4
    Write-Host $_.Exception.Message
    if ($Evidence) {
        try { Save-Json (Join-Path $Evidence 'launcher-failure.json') @{status='BLOCKED';error=$LauncherFailure;collector_exit_code=$null} }
        catch { Write-Warning "Launcher failure diagnostic also failed: $_" }
    }
} finally {
    try { if ($CollectorStarted -and -not $Collector.HasExited) {
        if (-not $LauncherFailure) { $LauncherFailure = 'Operator/launcher cancellation before collector completion' }
        if ($Evidence) {
            try { Save-Json (Join-Path $Evidence 'cancel.request') @{reason='operator/launcher cancellation'} }
            catch {
                # An existing/failed cancellation receipt must never skip the
                # bounded wait/owned-process termination below.
                $CleanupUnverified = $true
                Write-Warning "Cancellation receipt unavailable; continuing owned cleanup: $_"
            }
        }
        if (-not $Collector.WaitForExit(8000)) {
            # Only our exact collector process. Its Job handle closes on death,
            # terminating its contained pytest descendants; never kill by name.
            $Collector.Kill()
            $Stopped = $Collector.WaitForExit(5000)
            $CleanupUnverified = $true
            $ExitCode = 4
            if ($Evidence) { Save-Json (Join-Path $Evidence 'forced-collector-stop.json') @{stopped=$Stopped;pytest_exit_code=$null;descendant_cleanup='UNVERIFIED: kill-on-job-close expected; no independent observation';reason='Collector cancellation exceeded bounded cleanup'} }
        }
    } } catch {
        $CleanupUnverified = $true
        $ExitCode = 4
        $CleanupFailure = $_.Exception.ToString()
        if ($Evidence) {
            try { Save-Json (Join-Path $Evidence 'launcher-cleanup-error.json') @{error=$CleanupFailure;cleanup='UNVERIFIED'} }
            catch { Write-Warning "Cleanup diagnostic also failed: $_" }
        }
    }
    if ($CollectorStarted -and $Collector.HasExited) { $RawCollectorExit = $Collector.ExitCode }
    foreach ($Stream in @($Stdout,$Stderr)) {
        if ($null -ne $Stream) {
            try { $Stream.Dispose() }
            catch { $CleanupUnverified = $true; $ExitCode = 4; Write-Warning "Launcher log close failed: $_" }
        }
    }
    Write-Progress -Activity "Chronicle $Scope" -Completed
    if ($Evidence) {
        $Raw = @{status='BLOCKED';pytest_exit_code=$null;junit='missing or unverified: collector incomplete'}
        try {
            $RawPath = Join-Path $Evidence 'collector-result.json'
            if (Test-Path -LiteralPath $RawPath) { $Raw = [IO.File]::ReadAllText($RawPath) | ConvertFrom-Json }
        } catch { $LauncherFailure = 'Raw collector result unavailable: ' + $_.Exception.ToString(); $ExitCode = 4 }
        try { $ExitCode = Complete-QualificationEvidence $Evidence $Raw $RawCollectorExit $LauncherFailure $CleanupUnverified }
        catch {
            $ExitCode = 4
            Write-Host "Final status unavailable; directory retained at $Evidence : $_"
        }
        Write-Host "Evidence directory: $Evidence"
    }
}
exit $ExitCode
