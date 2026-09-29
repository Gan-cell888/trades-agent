@echo off
chcp 65001 >nul
title TradeS Agent - Data Clean
cd /d "%~dp0"

echo ============================================
echo   [TradeS Agent] Data Clean Assistant
echo   Local only. URL will be printed below.
echo ============================================

set PYTHON=
if exist "%~dp0runtime\python.exe" set "PYTHON=%~dp0runtime\python.exe"
if "%PYTHON%"=="" if not "%MIMO_PYTHON%"=="" set "PYTHON=%MIMO_PYTHON%"
if "%PYTHON%"=="" set "PYTHON=python"

echo [1/2] Checking Python...
"%PYTHON%" --version
if errorlevel 1 (
  echo [ERROR] Python 3.10+ is required.
  pause
  exit /b 1
)

"%PYTHON%" -c "import pandas, openpyxl"
if errorlevel 1 (
  echo Installing pandas openpyxl ...
  "%PYTHON%" -m pip install pandas openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo [2/2] Starting TradeS Agent...
"%PYTHON%" server.py

echo.
echo Server stopped.
pause
