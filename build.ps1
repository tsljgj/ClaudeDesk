# Build ClaudeDesk.exe (PyInstaller one-file, no console) and place it in this folder.
#   build.cmd                 # build
#   build.cmd -Install        # build + start with Windows + launch
#   build.cmd -Python C:\path\to\python.exe
# The interpreter is only used to create .venv the first time (Python 3.10 or newer).
# Most people don't need this: download ClaudeDesk.exe from the GitHub Releases page instead;
# it updates itself. A locally built exe reports build 0 and does not self-update.
param([switch]$Install, [string]$Python = '')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venvPy = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPy)) {
    $pyArgs = @()
    if (-not $Python) {
        if (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py'; $pyArgs = @('-3') }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
        else { throw 'Python 3.10+ not found; pass -Python <path to python.exe>' }
    }
    Write-Host 'creating .venv ...'
    & $Python @pyArgs -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $root 'requirements.txt') pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

$b = Join-Path $root 'build'
New-Item -ItemType Directory -Force $b | Out-Null
Push-Location (Join-Path $root 'src')
try { & $venvPy -m claudedesk.icon (Join-Path $b 'claudedesk.ico') } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'icon generation failed' }

& $venvPy -m PyInstaller --noconfirm --clean --onefile --windowed --name ClaudeDesk `
    --icon (Join-Path $b 'claudedesk.ico') --version-file (Join-Path $root 'packaging\version.txt') `
    --paths $root --paths (Join-Path $root 'src') `
    --add-data "$(Join-Path $root 'src\claudedesk\assets');claudedesk/assets" `
    --add-data "$(Join-Path $root 'desk.py');bundled" `
    --hidden-import pystray._win32 --collect-submodules webview `
    --exclude-module tkinter --exclude-module unittest `
    --distpath (Join-Path $b 'dist') --workpath (Join-Path $b 'work') --specpath $b `
    --log-level WARN (Join-Path $root 'scripts\ClaudeDesk.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

# Stop the instance running from this folder so the exe can be replaced.
$target = Join-Path $root 'ClaudeDesk.exe'
$running = Get-Process -Name ClaudeDesk -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $target }
if ($running) { $running | Stop-Process -Force; Start-Sleep -Milliseconds 800 }
# 1.x builds were one-folder: remove the old runtime folder
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root '_internal')
Copy-Item -Force (Join-Path $b 'dist\ClaudeDesk.exe') $target
Write-Host ('built: ' + $target)

if ($Install) {
    Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'ClaudeDesk' -Value ('"' + $target + '" --minimized')
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('Startup')) 'ClaudeDesk.lnk')
    Write-Host 'starts with Windows (HKCU Run)'
    Start-Process -FilePath $target -WorkingDirectory $root
}
