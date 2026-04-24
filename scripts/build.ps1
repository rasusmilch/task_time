param(
    [switch]$OneFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [string[]]$Arguments = @()
    )

    try {
        & $Executable @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Find-PythonCommand {
    if ($env:PYTHON) {
        if (Test-PythonCommand -Executable $env:PYTHON) {
            return @{
                Executable = $env:PYTHON
                BaseArgs   = @()
                Display    = $env:PYTHON
            }
        }

        Write-Warning "Ignoring PYTHON='$($env:PYTHON)' because it is not a working Python 3.11+ executable."
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and (Test-PythonCommand -Executable $pythonCmd.Source)) {
        return @{
            Executable = $pythonCmd.Source
            BaseArgs   = @()
            Display    = $pythonCmd.Source
        }
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        if (Test-PythonCommand -Executable $pyCmd.Source -Arguments @('-3.11')) {
            return @{
                Executable = $pyCmd.Source
                BaseArgs   = @('-3.11')
                Display    = "$($pyCmd.Source) -3.11"
            }
        }

        if (Test-PythonCommand -Executable $pyCmd.Source -Arguments @('-3')) {
            return @{
                Executable = $pyCmd.Source
                BaseArgs   = @('-3')
                Display    = "$($pyCmd.Source) -3"
            }
        }
    }

    throw 'Could not find a usable Python 3.11+ interpreter. Install Python 3.11 or newer and ensure it is available via $env:PYTHON, `python` on PATH, or `py` launcher on PATH.'
}

function New-VirtualEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VenvPath,

        [Parameter(Mandatory = $true)]
        [hashtable]$PythonCommand
    )

    Write-Host "Creating virtual environment at $VenvPath ..."
    & $PythonCommand.Executable @($PythonCommand.BaseArgs + @('-m', 'venv', $VenvPath))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment at $VenvPath using '$($PythonCommand.Display)'."
    }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$VenvPath = Join-Path $RepoRoot '.venv'
$DistPath = Join-Path $RepoRoot 'dist'
$BuildPath = Join-Path $RepoRoot 'build'
$SpecPath = Join-Path $RepoRoot 'task_timer.spec'
$LauncherPath = Join-Path $RepoRoot 'run_task_timer.py'
$VenvPythonExe = Join-Path $VenvPath 'Scripts\python.exe'

$PythonCommand = Find-PythonCommand
Write-Host "Using Python: $($PythonCommand.Display)"

$NeedsVenvCreate = $false
if (-not (Test-Path $VenvPath)) {
    $NeedsVenvCreate = $true
}
elseif (-not (Test-Path $VenvPythonExe)) {
    Write-Warning "Found broken virtual environment at $VenvPath (missing Scripts\\python.exe). Recreating it."
    Remove-Item -Recurse -Force $VenvPath
    $NeedsVenvCreate = $true
}

if ($NeedsVenvCreate) {
    New-VirtualEnvironment -VenvPath $VenvPath -PythonCommand $PythonCommand
}

if (-not (Test-Path $VenvPythonExe)) {
    throw "Could not find Python in venv at $VenvPythonExe"
}

Write-Host 'Upgrading pip ...'
& $VenvPythonExe -m pip install --upgrade pip

Write-Host 'Installing build dependencies ...'
& $VenvPythonExe -m pip install -e . pyinstaller

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
        & $VenvPythonExe -m PyInstaller --noconfirm --clean --windowed --name 'Task Timer' --paths src --onefile $LauncherPath
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller onefile build failed with exit code $LASTEXITCODE."
        }

        $OutputPath = Join-Path $DistPath 'Task Timer.exe'
    }
    else {
        Write-Host 'Building default onedir distribution via spec ...'
        & $VenvPythonExe -m PyInstaller --noconfirm --clean $SpecPath
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller onedir build failed with exit code $LASTEXITCODE."
        }

        $OutputPath = Join-Path $DistPath 'Task Timer'
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $OutputPath)) {
    throw "Build succeeded but expected output was not found at $OutputPath"
}

Write-Host ''
Write-Host "Build complete. Output: $OutputPath"
