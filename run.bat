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

echo ============================================
echo            Movie News Crawler
echo ============================================
echo.

echo [1/2] Crawling news from 8 sources... (takes 1-2 min)
python -m crawler.main
if errorlevel 1 goto error

echo.
echo [2/2] Building static site...
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
