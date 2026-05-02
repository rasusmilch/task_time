param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    & $venvPython "$repoRoot\run_chronicle.py"
} else {
    python "$repoRoot\run_chronicle.py"
}
