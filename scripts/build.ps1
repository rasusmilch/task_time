param(
    [string]$Python = $env:PYTHON
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { throw 'Build on native Windows; no cross-build qualification.' }
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPath = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvPath 'Scripts\python.exe'
$BuildPath = Join-Path $RepoRoot 'build'
$DistPath = Join-Path $RepoRoot 'dist'
$SpecPath = Join-Path $RepoRoot 'chronicle.spec'
$LockPath = Join-Path $RepoRoot 'requirements\windows-build.lock'
$Preflight = Join-Path $PSScriptRoot 'build_environment.py'

# Refuse before installing anything. Preserve every existing output and environment.
if ((Test-Path -LiteralPath $BuildPath) -or (Test-Path -LiteralPath $DistPath)) {
    throw 'Existing build/ or dist/ preserved. Use a fresh isolated checkout or inspect/move outputs explicitly.'
}
if (Test-Path -LiteralPath $VenvPath) {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw 'Existing .venv is incompatible. Preserve it and use a fresh Windows checkout.'
    }
}
else {
    if (-not $Python) {
        $command = Get-Command python -ErrorAction Stop
        $Python = $command.Source
    }
    # Explicit interpreter choices never silently fall back to an older Python.
    & $Python -I -B -c "import sys,sqlite3,struct,platform; assert sys.platform=='win32' and platform.python_implementation()=='CPython' and (3,11)<=sys.version_info<(3,16) and struct.calcsize('P')==8 and platform.machine().lower() in ('amd64','x86_64'); v=sqlite3.sqlite_version_info; assert v>=(3,51,3) and v!=(3,52,0), 'Unsupported SQLite WAL-reset runtime'"
    if ($LASTEXITCODE -ne 0) { throw 'Selected interpreter/runtime preflight failed; no environment created.' }
    & $Python -I -B -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed; inspect the partial environment.' }
}

# Verify prefix before pip: a misplaced/system interpreter must never receive installs.
& $VenvPython -I -B $Preflight --venv $VenvPath
if ($LASTEXITCODE -ne 0) { throw 'Environment preflight failed; nothing installed.' }
& $VenvPython -I -B -m pip --isolated install --no-user --require-hashes --only-binary=:all: -r $LockPath
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
# The spec analyzes this checkout's src/ directly. Do not run a project build
# here: setuptools could populate build/ before our isolated work directory exists.
& $VenvPython -I -B -m pip --isolated check
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }

New-Item -ItemType Directory -Path $BuildPath -ErrorAction Stop | Out-Null
$Record = Join-Path $BuildPath 'environment.json'
& $VenvPython -I -B $Preflight --venv $VenvPath --record $Record
if ($LASTEXITCODE -ne 0) { throw 'Build input verification failed; build refused.' }
Push-Location $RepoRoot
try {
    # No --clean, --noconfirm or UPX-dependent variation. Never erase prior artifacts.
    & $VenvPython -I -B -m PyInstaller --workpath $BuildPath --distpath $DistPath $SpecPath
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }
}
finally { Pop-Location }
$Artifact = Join-Path $DistPath 'Chronicle\Chronicle.exe'
if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) { throw "Expected executable missing: $Artifact" }
Write-Host "Build complete: $Artifact"
Write-Host "Build inputs/runtime: $Record"
Write-Host 'Native operator/package qualification is still required; see BUILDING.md.'
