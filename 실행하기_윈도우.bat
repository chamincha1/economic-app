@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py -3"
) else (
    set "PYCMD=python"
)
if not exist ".venv\Scripts\python.exe" (
    %PYCMD% -m venv ".venv"
    if errorlevel 1 goto err
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto err
".venv\Scripts\python.exe" -m streamlit run app.py
exit /b 0
:err
echo.
echo Python 3.10+ and internet connection for first setup are required.
echo Try: python -m pip install -r requirements.txt
pause
exit /b 1
