param()

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
$SpecPath = Join-Path $RepoRoot 'chronicle.spec'
$VenvPythonExe = Join-Path $VenvPath 'Scripts\python.exe'

$PythonCommand = Find-PythonCommand
Write-Host "Using Python: $($PythonCommand.Display)"

$NeedsVenvCreate = $false
if (-not (Test-Path $VenvPath)) {
    $NeedsVenvCreate = $true
}
elseif (-not (Test-Path $VenvPythonExe)) {
    throw "Existing .venv is not a Windows environment; preserve it and choose a prepared Windows checkout."
}

if ($NeedsVenvCreate) {
    New-VirtualEnvironment -VenvPath $VenvPath -PythonCommand $PythonCommand
}

if (-not (Test-Path $VenvPythonExe)) {
    throw "Could not find Python in venv at $VenvPythonExe"
}

Write-Host 'Installing build dependencies ...'
& $VenvPythonExe -m pip install -e $RepoRoot 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $VenvPythonExe -B -c "from chronicle.sqlite_store import runtime_info; print(runtime_info())"
if ($LASTEXITCODE -ne 0) { throw 'Unsupported SQLite runtime; build refused.' }

if ((Test-Path $BuildPath) -or (Test-Path $DistPath)) {
    throw 'Existing build/ or dist/ preserved. Inspect/move them explicitly before building.'
}

Push-Location $RepoRoot
try {
    Write-Host 'Building onedir distribution via spec ...'
    & $VenvPythonExe -m PyInstaller --noconfirm --clean $SpecPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller onedir build failed with exit code $LASTEXITCODE."
    }

    $OutputPath = Join-Path $DistPath 'Chronicle'
}
finally {
    Pop-Location
}

if (-not (Test-Path $OutputPath)) {
    throw "Build succeeded but expected output was not found at $OutputPath"
}

Write-Host ''
Write-Host "Build complete. Output: $OutputPath"
