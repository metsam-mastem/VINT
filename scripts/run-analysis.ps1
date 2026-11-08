$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Project = Join-Path $Root "projects/reel-intelligence"
$Venv = if ($env:RI_VENV) { $env:RI_VENV } else { Join-Path $Project ".venv" }
$Command = Join-Path $Venv "Scripts/ri-analyze.exe"

if (Test-Path $Command) {
    & $Command @args
    exit $LASTEXITCODE
}

$Installed = Get-Command "ri-analyze" -ErrorAction SilentlyContinue
if ($Installed) {
    & $Installed.Source @args
    exit $LASTEXITCODE
}

throw "ri-analyze is not installed. Run .\scripts\bootstrap-local.ps1 first."
