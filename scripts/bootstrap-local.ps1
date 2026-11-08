$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Project = Join-Path $Root "projects/reel-intelligence"
$Venv = if ($env:RI_VENV) { $env:RI_VENV } else { Join-Path $Project ".venv" }
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

& $Python -c "import sys; raise SystemExit(0 if sys.version_info -ge (3,10) else 2)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required." }

& $Python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }

$VenvPython = Join-Path $Venv "Scripts/python.exe"
$ProjectSpec = $Project + "[dev]"
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }

& $VenvPython -m pip install -e $ProjectSpec
if ($LASTEXITCODE -ne 0) { throw "Could not install REEL INTELLIGENCE." }

Write-Host ""
Write-Host "REEL INTELLIGENCE Python environment is ready."
Write-Host "Run tests: $VenvPython -m pytest $Project/tests"
Write-Host "Run analysis: $(Join-Path $Venv 'Scripts/ri-analyze.exe') INPUT --output OUTPUT"
Write-Host "Check optional executables: .\scripts\check-local-tools.ps1"
