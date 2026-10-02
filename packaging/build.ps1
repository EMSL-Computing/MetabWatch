# Build the standalone MetabWatch Windows exe (PyInstaller, single file).
#
# Usage (from anywhere; paths resolve relative to the repo):
#   .\packaging\build.ps1                 # reuse .venv-build if present
#   .\packaging\build.ps1 -Clean          # recreate .venv-build and build dirs
#   .\packaging\build.ps1 -Wheelhouse D:\wheels   # offline: install from local wheels
#
# Output: dist\MetabWatch-<version>.exe (+ .sha256). See docs\BUILDING.md.

[CmdletBinding()]
param(
    [switch]$Clean,
    [string]$Python = "py -3.13",
    [string]$Wheelhouse = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv-build"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
$Spec = Join-Path $PSScriptRoot "metabwatch.spec"
$Reqs = Join-Path $PSScriptRoot "requirements-build.txt"
$WorkPath = Join-Path $Root "build\pyinstaller"
$DistPath = Join-Path $Root "dist"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$sw = [Diagnostics.Stopwatch]::StartNew()
Set-Location -LiteralPath $Root

# Version comes from pyproject.toml (same source the spec uses).
$Version = (Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' |
    Select-Object -First 1).Matches[0].Groups[1].Value
$ExeName = "MetabWatch-$Version.exe"
$ExePath = Join-Path $DistPath $ExeName
Write-Host "MetabWatch $Version -> $ExePath"

if ($Clean) {
    Write-Step "Cleaning .venv-build and build output"
    foreach ($p in @($Venv, $WorkPath)) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force }
    }
}

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Step "Creating build venv ($Python)"
    if (Test-Path -LiteralPath $Python) {
        $launcher, $launcherArgs = $Python, @()
    } else {
        $launcher, $launcherArgs = $Python -split "\s+"
    }
    Invoke-Checked $launcher (@($launcherArgs | Where-Object { $_ }) + @("-m", "venv", $Venv))
}

Write-Step "Installing pinned build requirements"
$pipSource = @()
if ($Wheelhouse) { $pipSource = @("--no-index", "--find-links", $Wheelhouse) }
Invoke-Checked $VenvPy (@("-m", "pip", "install", "--disable-pip-version-check", "-q") + $pipSource + @("-r", $Reqs))

Write-Step "Installing metabwatch (non-editable, no deps)"
Invoke-Checked $VenvPy (@("-m", "pip", "install", "--disable-pip-version-check", "-q", "--no-deps", "--force-reinstall") + $pipSource + @($Root))

Write-Step "Running PyInstaller"
Invoke-Checked $VenvPy @("-m", "PyInstaller", $Spec, "--noconfirm", "--clean", "--workpath", $WorkPath, "--distpath", $DistPath)

if (-not (Test-Path -LiteralPath $ExePath)) { throw "Expected output not found: $ExePath" }

Write-Step "Self-test of the built exe"
$Report = Join-Path $WorkPath "self-test.txt"
if (Test-Path -LiteralPath $Report) { Remove-Item -LiteralPath $Report -Force }
$proc = Start-Process -FilePath $ExePath -ArgumentList @("--self-test", "`"$Report`"") -Wait -PassThru
if (Test-Path -LiteralPath $Report) { Get-Content -LiteralPath $Report | Write-Host }
if ($proc.ExitCode -ne 0) { throw "Self-test FAILED (exit $($proc.ExitCode)). See report above / build\pyinstaller\self-test.txt" }

$hash = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLower()
"$hash  $ExeName" | Set-Content -LiteralPath "$ExePath.sha256" -Encoding ascii
$sizeMB = [math]::Round((Get-Item -LiteralPath $ExePath).Length / 1MB, 1)

Write-Host ""
Write-Host "Build OK in $([math]::Round($sw.Elapsed.TotalMinutes, 1)) min" -ForegroundColor Green
Write-Host "  exe:    $ExePath"
Write-Host "  size:   $sizeMB MB"
Write-Host "  sha256: $hash"
