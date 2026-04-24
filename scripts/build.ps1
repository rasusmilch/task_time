Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

param(
    [switch]$OneFile
)

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$VenvPath = Join-Path $RepoRoot '.venv'
$DistPath = Join-Path $RepoRoot 'dist'
$BuildPath = Join-Path $RepoRoot 'build'
$SpecPath = Join-Path $RepoRoot 'task_timer.spec'
$LauncherPath = Join-Path $RepoRoot 'run_task_timer.py'

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment at $VenvPath ..."
    py -3.11 -m venv $VenvPath
}

$PythonExe = Join-Path $VenvPath 'Scripts\python.exe'
if (-not (Test-Path $PythonExe)) {
    throw "Could not find Python in venv at $PythonExe"
}

Write-Host 'Upgrading pip ...'
& $PythonExe -m pip install --upgrade pip

Write-Host 'Installing build dependencies ...'
& $PythonExe -m pip install -e . pyinstaller

if (Test-Path $BuildPath) {
    Remove-Item -Recurse -Force $BuildPath
}
if (Test-Path $DistPath) {
    Remove-Item -Recurse -Force $DistPath
}

Push-Location $RepoRoot
try {
    if ($OneFile) {
        Write-Host 'Building optional onefile executable ...'
        & $PythonExe -m PyInstaller --noconfirm --clean --windowed --name 'Task Timer' --paths src --onefile $LauncherPath
        $OutputPath = Join-Path $DistPath 'Task Timer.exe'
    }
    else {
        Write-Host 'Building default onedir distribution via spec ...'
        & $PythonExe -m PyInstaller --noconfirm --clean $SpecPath
        $OutputPath = Join-Path $DistPath 'Task Timer'
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host "Build complete. Output: $OutputPath"
