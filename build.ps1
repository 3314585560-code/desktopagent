param(
    [ValidateSet('1.1.0', '1.2.0', '1.3.0')]
    [string]$Version = '1.3.0'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { $projectPython = 'python' }
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'build\pyinstaller-cache'
$skillPayload = Join-Path $PSScriptRoot 'skills'
& $projectPython -m PyInstaller --noconfirm --onefile --windowed --exclude-module tokenizers --add-data "$skillPayload;skills" --name MiniCursor --workpath build\app --distpath build\bundle --specpath build app.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$appPayload = Join-Path $PSScriptRoot 'build\bundle\MiniCursor.exe'
& $projectPython -m PyInstaller --noconfirm --onefile --windowed --name "MiniCursor-Setup-$Version-x64" --workpath build\installer --distpath release --specpath build --add-data "$appPayload;." installer.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
