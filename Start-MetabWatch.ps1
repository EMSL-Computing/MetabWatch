# Launch MetabWatch GUI from the repo virtual environment (unconfigured form).
#
# Desktop shortcut Target example (name the shortcut with the version, e.g. "MetabWatch 0.2.0"):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\repo\Start-MetabWatch.ps1"

$ErrorActionPreference = "Stop"

function Stop-WithError {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
$PythonW = Join-Path $AppDir ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    Stop-WithError @"
Virtual-environment Python was not found at:
$Python

Create a venv in the repo root and install MetabWatch, e.g.:
  py -3 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -e .
  .\.venv\Scripts\python.exe -m pip install pythonnet
"@
}

# Prefer pythonw (no console under the GUI); fall back to python.exe.
$Launcher = $PythonW
if (-not (Test-Path -LiteralPath $PythonW)) {
    $Launcher = $Python
}

# Preflight: package importable
& $Python -c "import metabwatch.gui" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError @"
MetabWatch is not installed in this virtual environment.

From the repo root run:
  .\.venv\Scripts\python.exe -m pip install -e .
"@
}

Write-Host ""
Write-Host "Starting MetabWatch GUI" -ForegroundColor Green
Write-Host ""

Set-Location -LiteralPath $AppDir

try {
    Start-Process -FilePath $Launcher -ArgumentList @("-m", "metabwatch.gui") -WorkingDirectory $AppDir
}
catch {
    Stop-WithError "Failed to start MetabWatch GUI:`n$($_.Exception.Message)"
}

exit 0
