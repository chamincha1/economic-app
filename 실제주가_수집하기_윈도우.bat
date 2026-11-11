@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo -----------------------------------------
echo MARKET PULSE - Actual Daily Stock Data
 echo -----------------------------------------
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYCMD=py -3"
) else (
  set "PYCMD=python"
)
if not exist ".venv\Scripts\python.exe" (
  %PYCMD% -m venv ".venv"
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
".venv\Scripts\python.exe" collect_real_data.py
if errorlevel 1 (
  echo.
  echo Some sources failed. Check the messages above.
) else (
  echo.
  echo Daily price CSVs saved in data_cache.
)
pause
exit /b 0
:error
echo.
echo Setup failed. Check your Python installation and network.
pause
exit /b 1
