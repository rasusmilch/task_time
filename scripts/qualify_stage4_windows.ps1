<#
.SYNOPSIS
Opt-in full-source Stage 4 automated evidence. Does not run operator/Sleep gates.
.EXAMPLE
.\scripts\qualify_stage4_windows.ps1 -Repo C:\src\task_time -ExpectedRevision FULL_SHA -OutputParent 'C:\Chronicle qualification'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedRevision,
    [Parameter(Mandatory=$true)][string]$OutputParent,
    [string]$Python,
    [ValidateRange(1,3600)][int]$CollectionSeconds = 180,
    [ValidateRange(1,3600)][int]$TestSeconds = 240,
    [ValidateRange(1,86400)][int]$PhaseSeconds = 7200
)
$ErrorActionPreference = 'Stop'
$Utf8 = [Text.UTF8Encoding]::new($false)
$Child = $null
$Evidence = $null
$ExitCode = 4
$Finished = $false
$ChildStarted = $false
function Quote-Argument([string]$Value) {
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $Escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $Escaped = [regex]::Replace($Escaped, '(\\+)$', '$1$1')
    return '"' + $Escaped + '"'
}
try {
    if ($env:OS -ne 'Windows_NT') { throw 'BLOCKED: native Windows 11 required' }
    $Repo = (Get-Item -LiteralPath $Repo).FullName
    $OutputParent = (Get-Item -LiteralPath $OutputParent).FullName
    $Helper = Join-Path $Repo 'scripts\stage4_qualification.py'
    $Entry = Join-Path $Repo 'scripts\qualify_stage4_windows.ps1'
    if ((Get-FileHash -LiteralPath $Entry).Hash -ne (Get-FileHash -LiteralPath $PSCommandPath).Hash) {
        throw 'BLOCKED: executing wrapper differs from selected repository'
    }
    if (-not $Python) {
        $Candidate = Join-Path $Repo '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $Candidate) { $Python = (Get-Item -LiteralPath $Candidate).FullName }
        else { $Python = (Get-Command python -CommandType Application).Source }
    }
    $Python = (Get-Item -LiteralPath $Python).FullName
    $Arguments = @('-u','-B',$Helper,'--repo',$Repo,'--expected-revision',$ExpectedRevision,
        '--output-parent',$OutputParent,'--collection-seconds',"$CollectionSeconds",'--test-seconds',"$TestSeconds",'--phase-seconds',"$PhaseSeconds")
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
    $Start.EnvironmentVariables['CHRONICLE_QUALIFICATION_POWERSHELL'] = $PSVersionTable.PSVersion.ToString()
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    $HostObservation = @{
        os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture)
        computer = (Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model)
        user = $Identity.Name
        elevated = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        output_parent = $OutputParent
    }
    $Start.EnvironmentVariables['CHRONICLE_QUALIFICATION_HOST'] = ($HostObservation | ConvertTo-Json -Depth 5 -Compress)
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
                $Status = '{0}: {1}/{2}; counts {3}; elapsed {4}s; last event {5}s; {6}' -f $Progress.phase,$Progress.completed,$Progress.selected,($Progress.counts | ConvertTo-Json -Compress),[int]$Elapsed,$EventAge,$Progress.node
                if ($null -ne $Progress.percent) { $Percent = [int]$Progress.percent }
            }
            Write-Progress -Activity 'Chronicle Stage 4 full regression' -Status $Status -PercentComplete $Percent
            if ($Elapsed - $LastText -ge 10) { Write-Host "Heartbeat: $Status"; $LastText = $Elapsed }
        }
        if ($Elapsed -gt (2*$PhaseSeconds + 120)) { throw 'EVIDENCE_INCOMPLETE: controller/archiving outer deadline exceeded' }
        if ($null -eq $Progress -and $Elapsed -gt $CollectionSeconds) { throw 'BLOCKED: prerequisite deadline exceeded' }
        if ($null -ne $Progress -and $Elapsed - $LastProgressAt -gt 120) { throw 'EVIDENCE_INCOMPLETE: controller/evidence progress deadline exceeded' }
        Start-Sleep -Milliseconds 100
    }
    if (-not $Child.WaitForExit(5000)) { throw 'EVIDENCE_INCOMPLETE: controller exit unavailable' }
    $ExitCode = $Child.ExitCode
    $Finished = $true
} catch {
    Write-Host ('BLOCKED/EVIDENCE_INCOMPLETE: ' + $_.Exception.Message)
    $ExitCode = 4
} finally {
    if ($null -ne $Child) {
        if ($ChildStarted -and -not $Finished -and -not $Child.HasExited) {
            # Signal only our exact evidence phase. Then stop only the owned
            # controller if necessary; its noninherited Job handle kills its tests.
            if ($Evidence) {
                foreach ($Phase in @('collection','regression')) {
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
    Write-Progress -Activity 'Chronicle Stage 4 full regression' -Completed
    if ($Evidence) { Write-Host "Retained evidence: $Evidence" }
}
exit $ExitCode
