$ErrorActionPreference = 'Stop'

$pythonExe = Join-Path $PSScriptRoot '.conda/python.exe'

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe"
}

& $pythonExe -m pip install --upgrade pip pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install/upgrade PyInstaller'
}

& $pythonExe -m PyInstaller --noconfirm --clean "$PSScriptRoot/EasyPhotoPrinter.spec"
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller build failed'
}

Write-Host "Build complete: $PSScriptRoot/dist/EasyPhotoPrinter.exe"
