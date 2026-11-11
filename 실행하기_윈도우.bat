@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PY_CMD% -m venv ".venv"
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m streamlit run app.py
exit /b 0
:error
echo.
echo Python 3.10+ required. Check installation, internet, and requirements.txt
pause
exit /b 1
