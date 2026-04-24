param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    & $venvPython "$repoRoot\run_task_timer.py"
} else {
    python "$repoRoot\run_task_timer.py"
}
