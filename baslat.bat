@echo off
REM =====================================================================
REM  Lucid v0.5 - Tray Launcher (guvenli)
REM  - Eski Lucid process'lerini (pythonw) kapatir
REM  - Tek bir tray instance baslatir (WMI detach)
REM  - Parent bash/cmd kapansa bile tray yasamaya devam eder
REM =====================================================================
setlocal enableextensions
cd /d "%~dp0"
title Lucid v0.5 Launcher

echo.
echo   ================================================================
echo     Lucid v0.5 - Masaustu AI Ajani
echo     Ctrl+Alt+J ile overlay, Ctrl+Alt+K ile kill switch
echo     Loglar: data\logs\lucid.log
echo   ================================================================
echo.

REM -- 1) Onceki Lucid pythonw / python process'lerini durdur -----------
echo   [1/4] Eski Lucid process'leri durduruluyor...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | Where-Object { $_.CommandLine -like '*-m lucid*' -or $_.ExecutablePath -like '*\Lucid\.venv*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('      killed pid=' + $_.ProcessId) } catch {} }" 2>nul
timeout /t 1 /nobreak >nul

REM -- 2) Sanal ortam (.venv) var mi? yoksa uv sync ---------------------
if not exist ".venv\Scripts\pythonw.exe" (
    echo   [2/4] Kurulum: .venv bulunamadi, 'uv sync' calistiriliyor...
    where uv >nul 2>nul
    if errorlevel 1 (
        echo   [X] HATA: 'uv' kurulu degil. Kur:
        echo       winget install --id=astral-sh.uv
        echo.
        pause
        exit /b 1
    )
    uv sync
    if errorlevel 1 (
        echo   [X] HATA: uv sync basarisiz.
        pause
        exit /b 1
    )
    echo       kurulum tamam.
) else (
    echo   [2/4] .venv hazir.
)

REM -- 3) .env uyarisi --------------------------------------------------
if not exist "..\..\.env" if not exist ".env" (
    echo   [!] .env yok. ANTHROPIC_API_KEY olmadan Execute calismaz.
    echo       Elle kur: uv run lucid setup
)

REM -- 4) Tray'i WMI ile tam detach baslat ------------------------------
echo   [3/4] Lucid tray baslatiliyor (WMI detach)...
powershell -NoProfile -Command "$r = ([wmiclass]'Win32_Process').Create('cmd /c \"\"' + (Get-Location).Path + '\.venv\Scripts\pythonw.exe\" -m lucid\"', (Get-Location).Path); if ($r.ReturnValue -eq 0) { Write-Host ('      baslatildi, pid=' + $r.ProcessId) } else { Write-Host ('      HATA, ReturnValue=' + $r.ReturnValue); exit 1 }"
if errorlevel 1 (
    echo   [X] Baslatma hatasi. Tanilama icin:
    echo       .venv\Scripts\python.exe -m lucid
    pause
    exit /b 1
)

REM -- 5) Ayaga kalktigini dogrula (log'a ilk satir yazilmali) ----------
echo   [4/4] Dogrulama (2 sn)...
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "$pw = Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*\Lucid\.venv\Scripts\pythonw.exe' }; if ($pw) { Write-Host ('      OK, pid=' + $pw[0].Id) } else { Write-Host '      [!] pythonw gorulmuyor; tanilama icin python.exe -m lucid calistirin' }"

echo.
echo   Hazir! Ctrl+Alt+J ile overlay'i acin.
echo   Kapatmak: saat yaninda tray ikon ^> sag tik ^> Quit
echo.
timeout /t 3 /nobreak >nul
endlocal
exit /b 0
