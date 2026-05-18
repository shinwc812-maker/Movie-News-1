@echo off
chcp 65001 >nul
setlocal
title Movie News Viewer

REM Move to this script's folder (project root)
cd /d "%~dp0"

echo ============================================
echo            Movie News Viewer
echo ============================================
echo.

echo Getting the latest news... (downloading update)
git pull
if errorlevel 1 (
  echo.
  echo [WARN] Could not get the latest update.
  echo        Check your internet or Git installation.
  echo        Opening the version you already have...
)

echo.
echo Opening today's movie news in your browser...
if exist "%~dp0dist\index.html" (
  start "" "%~dp0dist\index.html"
) else (
  echo.
  echo [ERROR] dist\index.html not found.
  echo         The first update may have failed - check the messages above.
)

echo.
pause
