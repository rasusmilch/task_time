#requires -Version 5.1
<#
.SYNOPSIS
Fixed sixteen-instance F2b-Focus qualification; no manual GUI actions.
#>
[CmdletBinding()]
param(
    [string]$ExpectedRevision,
    [string]$OutputParent,
    [string]$Python
)
$Repo = Split-Path -Parent $PSScriptRoot
$CollectionSeconds = 90
$PhaseSeconds = 900
$ErrorActionPreference = 'Stop'
$Utf8 = [Text.UTF8Encoding]::new($false)
$Child = $null
$Evidence = $null
$ExitCode = 4
$Finished = $false
$ChildStarted = $false
$FinalStatus = 'BLOCKED'
$ControllerStatus = $null
function Quote-Argument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $Escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $Escaped = [regex]::Replace($Escaped, '(\\+)$', '$1$1')
    return '"' + $Escaped + '"'
}
try {
    if (-not $ExpectedRevision -or $ExpectedRevision -notmatch '^[0-9a-fA-F]{40}$') { throw 'BLOCKED: required -ExpectedRevision full SHA is missing/invalid; no prompting' }
    if ($env:OS -ne 'Windows_NT') { throw 'BLOCKED: native Windows 11 required' }
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or $PSVersionTable.PSEdition -ne 'Desktop') { throw 'BLOCKED: approved Windows PowerShell 5.1 required' }
    $Windows = Get-CimInstance Win32_OperatingSystem -OperationTimeoutSec 10
    if ([int]$Windows.BuildNumber -lt 22000 -or $Windows.ProductType -ne 1) { throw 'BLOCKED: Windows 11 client required' }
    if (-not $OutputParent) {
        if (-not $env:LOCALAPPDATA) { throw 'BLOCKED: LOCALAPPDATA unavailable' }
        $OutputParent = Join-Path $env:LOCALAPPDATA 'Chronicle Qualification\F2b Focus'
    }
    $Repo = (Get-Item -LiteralPath $Repo).FullName
    $OutputParent = [IO.Path]::GetFullPath($OutputParent)
    $Helper = Join-Path $Repo 'scripts\qualify_f2b_focus.py'
    $Entry = Join-Path $Repo 'scripts\qualify_f2b_focus_windows.ps1'
    if ((Get-FileHash -LiteralPath $Entry).Hash -ne (Get-FileHash -LiteralPath $PSCommandPath).Hash) {
        throw 'BLOCKED: executing wrapper differs from selected repository'
    }
    if (-not $Python) {
        $Candidate = Join-Path $Repo '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $Candidate) { $Python = (Get-Item -LiteralPath $Candidate).FullName }
        else { $Python = (Get-Command python -CommandType Application).Source }
    }
    $Python = (Get-Item -LiteralPath $Python).FullName
    if ($Python -match '\\WindowsApps\\') { throw 'BLOCKED: select installed Python, not a Store alias' }
    $Arguments = @('-u','-B',$Helper,'--repo',$Repo,'--expected-revision',$ExpectedRevision,
        '--output-parent',$OutputParent)
    $Start = [Diagnostics.ProcessStartInfo]::new()
    $Start.FileName = $Python
    $Start.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $Start.WorkingDirectory = $Repo
    $Start.UseShellExecute = $false
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.StandardOutputEncoding = $Utf8
    $Start.StandardErrorEncoding = $Utf8
    $Start.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $Start.EnvironmentVariables['CHRONICLE_FOCUS_POWERSHELL'] = '5.1'
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    $HostObservation = @{
        os = ($Windows | Select-Object Caption,Version,BuildNumber,OSArchitecture,ProductType)
        computer = (Get-CimInstance Win32_ComputerSystem -OperationTimeoutSec 10 | Select-Object Manufacturer,Model)
        user = $Identity.Name
        elevated = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        output_parent = $OutputParent
        powershell_executable = (Get-Process -Id $PID).Path
        powershell_version = $PSVersionTable.PSVersion.ToString()
        wrapper = $PSCommandPath
    }
    $Start.EnvironmentVariables['CHRONICLE_FOCUS_HOST'] = ($HostObservation | ConvertTo-Json -Depth 5 -Compress)
    $Child = [Diagnostics.Process]::new()
    $Child.StartInfo = $Start
    if (-not $Child.Start()) { throw 'BLOCKED: Python controller did not start' }
    $ChildStarted = $true
    $Out = $Child.StandardOutput.ReadLineAsync()
    $Err = $Child.StandardError.ReadLineAsync()
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $LastDraw = -1.0
    $LastText = -10.0
    $LastProgressAt = 0.0
    $Progress = $null
    while (-not $Child.HasExited -or $null -ne $Out -or $null -ne $Err) {
        for ($Drain=0; $Drain -lt 100; $Drain++) {
            $Read = $false
            foreach ($Kind in @('Out','Err')) {
                $Task = if ($Kind -eq 'Out') { $Out } else { $Err }
                if ($null -ne $Task -and $Task.IsCompleted) {
                    $Line = $Task.GetAwaiter().GetResult()
                    if ($null -ne $Line) {
                        if ($Line.StartsWith('Evidence directory: ')) { $Evidence = $Line.Substring(20); Write-Host $Line }
                        elseif ($Line.StartsWith('Final status: ')) {
                            $ControllerStatus = ($Line.Substring(14) -split ' ')[0]
                            if ($ControllerStatus -ne 'PASS') { Write-Host ('Controller diagnostic: ' + $Line.Substring(14)) }
                        }
                        elseif ($Line.StartsWith('CHRONICLE_PROGRESS ')) { $Progress = $Line.Substring(19) | ConvertFrom-Json; $LastProgressAt = $Timer.Elapsed.TotalSeconds }
                        else { Write-Host $Line }
                    }
                    if ($Kind -eq 'Out') { $Out = if ($null -eq $Line) { $null } else { $Child.StandardOutput.ReadLineAsync() } }
                    else { $Err = if ($null -eq $Line) { $null } else { $Child.StandardError.ReadLineAsync() } }
                    $Read = $true
                }
            }
            if (-not $Read) { break }
        }
        $Elapsed = $Timer.Elapsed.TotalSeconds
        if ($Elapsed - $LastDraw -ge 1) {
            $LastDraw = $Elapsed
            $Status = 'Prerequisites/collection; elapsed ' + [int]$Elapsed + 's'
            $Percent = -1
            if ($null -ne $Progress) {
                $EventAge = [Math]::Round(([double]$Progress.since_event + $Elapsed - $LastProgressAt),1)
                $Overall = if ($Progress.qualification_phase -eq 'subjects') { 4 + [int]$Progress.completed } elseif ($Progress.qualification_phase -eq 'controls') { [int]$Progress.completed } else { 0 }
                $Status = 'total ' + $Overall + '/16; ' + ('{0}/{1}: {2}/{3}; counts {4}; elapsed {5}s; last event {6}s; {7}' -f $Progress.qualification_phase,$Progress.phase,$Progress.completed,$Progress.selected,($Progress.counts | ConvertTo-Json -Compress),[int]$Elapsed,$EventAge,$Progress.node)
                if ($null -ne $Progress.percent) { $Percent = [int]$Progress.percent }
            }
            Write-Progress -Activity 'Chronicle F2b-Focus (16 instances)' -Status $Status -PercentComplete $Percent
            if ($Elapsed - $LastText -ge 10) { Write-Host "Heartbeat: $Status"; $LastText = $Elapsed }
        }
        if ($Elapsed -gt (3*$PhaseSeconds + 120)) { throw 'EVIDENCE_INCOMPLETE: controller/archiving outer deadline exceeded' }
        if ($null -eq $Progress -and $Elapsed -gt $CollectionSeconds) { throw 'BLOCKED: prerequisite deadline exceeded' }
        if ($null -ne $Progress -and $Elapsed - $LastProgressAt -gt 120) { throw 'EVIDENCE_INCOMPLETE: controller/evidence progress deadline exceeded' }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Child.WaitForExit(5000)) { throw 'EVIDENCE_INCOMPLETE: controller exit unavailable' }
    $ExitCode = $Child.ExitCode
    if ($ControllerStatus -notin @('PASS','FAIL','BLOCKED','EVIDENCE_INCOMPLETE')) { throw 'EVIDENCE_INCOMPLETE: missing exact controller status' }
    $FinalStatus = $ControllerStatus
    if ($ExitCode -eq 0) {
        if (-not $Evidence -or $ControllerStatus -ne 'PASS') { throw 'EVIDENCE_INCOMPLETE: controller exit/status disagreement' }
        $Summary = Get-Content -LiteralPath (Join-Path $Evidence 'summary.json') -Raw | ConvertFrom-Json
        if ($Summary.status -ne 'PASS' -or $Summary.archive_status -ne 'VERIFIED' -or $Summary.completed -ne 16) { throw 'EVIDENCE_INCOMPLETE: final evidence status disagrees' }
    } elseif ($ControllerStatus -eq 'PASS') { throw 'EVIDENCE_INCOMPLETE: nonzero controller claimed PASS' }
    $Finished = $true
} catch {
    $FinalStatus = if ($ChildStarted) { 'EVIDENCE_INCOMPLETE' } else { 'BLOCKED' }
    Write-Host ('Reason: ' + $_.Exception.Message)
    $ExitCode = 4
} finally {
    if ($null -ne $Child) {
        if ($ChildStarted -and -not $Finished -and -not $Child.HasExited) {
            # Signal only our exact evidence phase. Then stop only the owned
            # controller if necessary; its noninherited Job handle kills its tests.
            if ($Evidence) {
                foreach ($Phase in @('collection','controls','subjects')) {
                    $Cancel = Join-Path (Join-Path $Evidence $Phase) 'cancel.request'
                    if (Test-Path -LiteralPath (Split-Path -Parent $Cancel)) {
                        try { $Stream = [IO.File]::Open($Cancel,[IO.FileMode]::CreateNew); $Stream.Dispose() }
                        catch { Write-Warning "Cancellation signal unavailable: $_" }
                    }
                }
            }
            if (-not $Child.WaitForExit(10000)) { $Child.Kill(); $null = $Child.WaitForExit(5000) }
            Write-Warning 'Interrupted controller: no PASS; inspect retained logs and owned cleanup. ZIP may be unavailable.'
        }
        $Child.Dispose()
    }
    Write-Progress -Activity 'Chronicle F2b-Focus (16 instances)' -Completed
    if ($Evidence) { Write-Host "Complete evidence directory: $Evidence"; Write-Host "Evidence ZIP candidate (verify final status): $Evidence.zip" }
    else { Write-Host 'Evidence directory: not created; evidence ZIP: not created' }
}
Write-Host ('Final status: ' + $FinalStatus)
exit $ExitCode
