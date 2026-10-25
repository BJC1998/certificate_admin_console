@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python Launcher ^(py^) was not found. Install Python 3.15 with the Windows launcher and reopen your terminal.
  exit /b 1
)
py -3.15 -c "import sys; assert sys.version_info[:2] == (3, 15)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.15 is required. Check: py -3.15 --version
  exit /b 1
)
py -3.15 "%~dp0scripts\dev.py" %*
exit /b %errorlevel%
