param(
    [ValidateNotNullOrEmpty()][string]$DataDir,
    [string]$Timezone,
    [switch]$Create
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

$launchArgs = @("$repoRoot\run_chronicle.py")
if ($DataDir) { $launchArgs += @('--data-dir', $DataDir) }
if ($Timezone) { $launchArgs += @('--timezone', $Timezone) }
if ($Create) { $launchArgs += '--create' }
if (Test-Path $venvPython) { & $venvPython @launchArgs }
else { python @launchArgs }
exit $LASTEXITCODE
