# Dev runner for Lucid. Assumes `uv` is installed.
# Usage: .\scripts\dev_run.ps1
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot\..
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv is not installed. Install it from https://docs.astral.sh/uv/"
    }
    uv sync --all-extras
    uv run python -m lucid
} finally {
    Pop-Location
}
