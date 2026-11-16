@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [MARKET PULSE] 시작 중...
python -c "import pandas,numpy,sklearn,requests,bs4,FinanceDataReader" 2>nul
if errorlevel 1 (
  echo 처음 실행 시 필요한 Python 패키지를 설치합니다.
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 설치에 실패했습니다. 위의 오류를 확인하세요.
    pause
    exit /b 1
  )
)
python app_server.py
if errorlevel 1 pause
