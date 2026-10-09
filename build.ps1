# Build ClaudeDesk.exe (PyInstaller onedir) and place it in this folder.
#   powershell -ExecutionPolicy Bypass -File build.ps1            # build
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Install   # build + startup shortcut + launch
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Python C:\path\to\python.exe   # pick the interpreter
# The interpreter is only used to create .venv the first time (Python 3.10 or newer).
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
    & $venvPy -m pip install --disable-pip-version-check -q PySide6-Essentials pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
}

$b = Join-Path $root 'build'
New-Item -ItemType Directory -Force $b | Out-Null
& $venvPy (Join-Path $root 'src\icons.py') (Join-Path $b 'claudedesk.ico')
if ($LASTEXITCODE -ne 0) { throw 'icon generation failed' }

& $venvPy -m PyInstaller --noconfirm --clean --windowed --onedir --name ClaudeDesk `
    --icon (Join-Path $b 'claudedesk.ico') --version-file (Join-Path $root 'packaging\version.txt') `
    --paths $root --paths (Join-Path $root 'src') `
    --distpath (Join-Path $b 'dist') --workpath (Join-Path $b 'work') --specpath $b `
    --exclude-module tkinter --exclude-module unittest --exclude-module pydoc `
    --log-level WARN (Join-Path $root 'src\claudedesk.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }

$dist = Join-Path $b 'dist\ClaudeDesk'
# Software OpenGL fallback is not needed by a widgets-only app (saves ~20 MB on disk).
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $dist '_internal\PySide6\opengl32sw.dll')

# Stop the instance running from this folder so the files can be replaced.
$target = Join-Path $root 'ClaudeDesk.exe'
$running = Get-Process -Name ClaudeDesk -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $target }
if ($running) {
    $running | Stop-Process -Force
    Start-Sleep -Milliseconds 800
}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $root '_internal')
Copy-Item -Recurse -Force (Join-Path $dist '_internal') (Join-Path $root '_internal')
Copy-Item -Force (Join-Path $dist 'ClaudeDesk.exe') (Join-Path $root 'ClaudeDesk.exe')
Write-Host ('built: ' + (Join-Path $root 'ClaudeDesk.exe'))

if ($Install) {
    $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'ClaudeDesk.lnk'
    $exe = Join-Path $root 'ClaudeDesk.exe'
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = $exe
    $s.Arguments = '--minimized'
    $s.WorkingDirectory = $root
    $s.IconLocation = "$exe,0"
    $s.Description = 'ClaudeDesk'
    $s.Save()
    Write-Host ('startup shortcut: ' + $lnk)
    Start-Process -FilePath $exe -ArgumentList '--minimized' -WorkingDirectory $root
}
