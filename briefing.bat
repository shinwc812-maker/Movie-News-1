@echo off
chcp 65001 >nul
setlocal
title Movie News - AI Briefing

REM 임원 보고 직전 한 번 더블클릭으로 실행.
REM 흐름: git pull(최신 데이터) -> claude -p로 AI 브리핑 생성 -> 빌드 -> push.

cd /d "%~dp0"
set PYTHONUTF8=1

echo ============================================
echo            Movie News - AI Briefing
echo ============================================
echo.

echo [1/4] git pull (latest data)...
git pull --ff-only
if errorlevel 1 (
  echo [warn] git pull 실패 — 로컬 데이터로 계속 진행합니다.
)

echo.
echo [2/4] claude -p 로 AI 브리핑 생성... (60-180초)
python -m crawler.ai_briefing
if errorlevel 1 goto error

echo.
echo [3/4] 대시보드 재빌드...
python site\build.py
if errorlevel 1 goto error

echo.
echo [4/4] git commit + push...
git add data\ai_briefing.json dist\index.html
git commit -m "chore: AI 브리핑 갱신 (%date%)"
if errorlevel 1 (
  echo [info] 커밋할 변경 없음 — 건너뜀.
) else (
  git push origin main
)

echo.
echo 완료. 브라우저에서 dist\index.html을 새로고침(Ctrl+F5)하세요.
start "" "%~dp0dist\index.html"
goto end

:error
echo.
echo [ERROR] 단계에서 실패. 위 메시지를 확인하세요.

:end
echo.
pause
