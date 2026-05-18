@echo off
chcp 65001 >nul
setlocal
title Movie News Crawler

REM Move to this script's folder (project root)
cd /d "%~dp0"

REM Force UTF-8 so Korean text from Python prints correctly
set PYTHONUTF8=1

REM --- To enable Korean translation, remove REM below and paste your key ---
REM set ANTHROPIC_API_KEY=sk-your-key-here

REM --- Required for KOBIS box office / reservation dashboard data ---
REM set KOBIS_API_KEY=your-kobis-key

echo ============================================
echo            Movie News Crawler
echo ============================================
echo.

echo [1/2] Crawling briefing data... (takes 1-3 min)
python -m crawler.main
if errorlevel 1 goto error

echo.
echo [2/2] Building static dashboard...
python site\build.py
if errorlevel 1 goto error

echo.
echo Done. Opening the result in your browser...
start "" "%~dp0dist\index.html"
goto end

:error
echo.
echo [ERROR] Something went wrong. Check the messages above.

:end
echo.
pause
