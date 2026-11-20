@echo off
cd /d "%~dp0"
echo Starting Sandbox Studio. Keep this window open during your presentation.
echo Once ready, open http://127.0.0.1:8080 in your browser.
wsl -u root -- bash ./start-demo.sh --offline
if errorlevel 1 (
  echo.
  echo Startup failed. Run wsl -u root -- bash ./start-demo.sh to prepare dependencies.
  pause
)
