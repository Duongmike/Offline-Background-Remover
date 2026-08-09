@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python 3.10 hoac 3.11.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Dang tao moi truong ao...
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo Dang cai thu vien...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo Dang tai model AI va kiem tra SHA256...
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 goto :error

echo.
echo Cai dat thanh cong. Chay app bang file run.bat
pause
exit /b 0

:error
echo.
echo [LOI] Cai dat that bai. Kiem tra ket noi mang va thu lai.
pause
exit /b 1
