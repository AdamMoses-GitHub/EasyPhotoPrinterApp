param(
    [string]$Version = '0.1.0'
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$appBuildScript = Join-Path $root 'build_exe.ps1'
$installerScript = Join-Path $root 'installer/EasyPhotoPrinter.iss'
$installerOutput = Join-Path $root 'dist/installer'

if (-not (Test-Path $appBuildScript)) {
    throw "Build script not found at $appBuildScript"
}

if (-not (Test-Path $installerScript)) {
    throw "Installer script not found at $installerScript"
}

& $appBuildScript
if ($LASTEXITCODE -ne 0) {
    throw 'Application build failed'
}

$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$isccPath = $null
foreach ($candidate in @($isccCommand.Path, 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe', 'C:\Program Files\Inno Setup 6\ISCC.exe')) {
    if ($candidate -and (Test-Path $candidate)) {
        $isccPath = $candidate
        break
    }
}

if (-not $isccPath) {
    throw @'
Inno Setup compiler (ISCC.exe) was not found.
Install Inno Setup 6, or add ISCC.exe to PATH, then re-run this script.
'@
}

New-Item -ItemType Directory -Force -Path $installerOutput | Out-Null

& $isccPath "/DMyAppVersion=$Version" $installerScript
if ($LASTEXITCODE -ne 0) {
    throw 'Installer build failed'
}

Write-Host "Installer build complete: $installerOutput"