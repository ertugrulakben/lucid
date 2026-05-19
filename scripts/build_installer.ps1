# Build Lucid .exe installer. Requires PyInstaller and NSIS on PATH.
# Usage: .\scripts\build_installer.ps1 [-Version 0.1.0]
param(
    [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot\..

try {
    Write-Host "==> Cleaning dist/" -ForegroundColor Cyan
    Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

    Write-Host "==> Installing build dependencies" -ForegroundColor Cyan
    uv sync --extra build

    Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
    uv run pyinstaller `
        --name lucid `
        --onedir `
        --windowed `
        --icon assets\icon.ico `
        --add-data "assets;assets" `
        --collect-submodules anthropic `
        --collect-submodules PySide6 `
        src\lucid\__main__.py

    if (-not (Get-Command makensis -ErrorAction SilentlyContinue)) {
        Write-Warning "makensis not found on PATH. Skipping installer step; PyInstaller bundle is in dist\lucid\"
        return
    }

    Write-Host "==> Running NSIS" -ForegroundColor Cyan
    makensis /DVERSION=$Version installer\lucid.nsi
    Write-Host "==> Done. Installer in dist\Lucid-Setup-$Version.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
