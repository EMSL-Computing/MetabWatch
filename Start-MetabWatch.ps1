# Launch MetabWatch GUI from the repo virtual environment.
# Optional: -Config path\to\pipeline.json (pre-selects Custom JSON in the GUI).
# Paths for raw/output live in the JSON — not in this script.
#
# Desktop shortcut Target example:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\repo\Start-MetabWatch.ps1" -Config "C:\path\to\repo\data\lab_hilic_pos.json"

param(
    [string]$Config = ""
)

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

$GuiArgs = @("-m", "metabwatch.gui")

if ($Config) {
    if (-not [System.IO.Path]::IsPathRooted($Config)) {
        $Config = Join-Path $AppDir $Config
    }
    if (-not (Test-Path -LiteralPath $Config)) {
        Stop-WithError "Configuration file was not found at:`n$Config"
    }
    $Config = (Resolve-Path -LiteralPath $Config).Path
    if ([System.IO.Path]::GetExtension($Config).ToLowerInvariant() -ne ".json") {
        Stop-WithError "Configuration file must be a .json file:`n$Config"
    }

    try {
        $cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Stop-WithError "Could not parse configuration JSON:`n$Config`n`n$($_.Exception.Message)"
    }

    # Simplified flat schema (preferred)
    $inputFolder = $cfg.input_folder
    $outputFolder = $cfg.output_folder
    # Legacy nested schema fallback
    if (-not $inputFolder -and $cfg.watcher) {
        $inputFolder = $cfg.watcher.raw_dir
    }
    if (-not $outputFolder -and $cfg.processor) {
        $outputFolder = $cfg.processor.output_dir
    }

    if (-not $inputFolder -or -not $outputFolder) {
        Stop-WithError @"
Config is missing input/output paths.
Expected top-level input_folder and output_folder
(or legacy watcher.raw_dir / processor.output_dir):
$Config
"@
    }

    function Resolve-ConfigPath {
        param([string]$PathValue)
        if ([System.IO.Path]::IsPathRooted($PathValue)) {
            return $PathValue
        }
        return (Join-Path $AppDir $PathValue)
    }

    $RawDir = Resolve-ConfigPath -PathValue ([string]$inputFolder)
    $OutputDir = Resolve-ConfigPath -PathValue ([string]$outputFolder)

    if (-not (Test-Path -LiteralPath $RawDir)) {
        Stop-WithError "RAW data directory from config was not found at:`n$RawDir`n`n(Config: $Config)"
    }

    if (-not (Test-Path -LiteralPath $OutputDir)) {
        Write-Host "Creating output directory from config:" -ForegroundColor Yellow
        Write-Host "  $OutputDir"
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }

    Write-Host ""
    Write-Host "Starting MetabWatch GUI" -ForegroundColor Green
    Write-Host "Config:  $Config"
    Write-Host "RAW:     $RawDir"
    Write-Host "Results: $OutputDir"
    Write-Host ""

    $GuiArgs += @("--config", $Config)
}
else {
    Write-Host ""
    Write-Host "Starting MetabWatch GUI (no config pre-selected)" -ForegroundColor Green
    Write-Host ""
}

Set-Location -LiteralPath $AppDir

try {
    Start-Process -FilePath $Launcher -ArgumentList $GuiArgs -WorkingDirectory $AppDir
}
catch {
    Stop-WithError "Failed to start MetabWatch GUI:`n$($_.Exception.Message)"
}

exit 0
