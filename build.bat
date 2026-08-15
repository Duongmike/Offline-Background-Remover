@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Chua co moi truong build. Hay chay setup.bat truoc.
    if not defined CI pause
    exit /b 1
)

echo [1/4] Cai cong cu dong goi va test...
".venv\Scripts\python.exe" -m pip install -r build-requirements.txt
if errorlevel 1 goto :error

echo [2/4] Chay kiem thu...
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :error

echo [3/4] Dong goi Offline Background Remover...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean OfflineBackgroundRemover.spec
if errorlevel 1 goto :error

echo [4/4] Chay packaged self-test...
powershell -NoProfile -Command "$process = Start-Process -FilePath (Resolve-Path 'dist\OfflineBackgroundRemover\OfflineBackgroundRemover.exe') -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru; exit $process.ExitCode"
if errorlevel 1 goto :error
powershell -NoProfile -Command "$process = Start-Process -FilePath (Resolve-Path 'dist\OfflineBackgroundRemover\OfflineBackgroundRemover.exe') -ArgumentList '--ui-smoke-test' -WindowStyle Hidden -Wait -PassThru; exit $process.ExitCode"
if errorlevel 1 goto :error

echo.
echo Build thanh cong: dist\OfflineBackgroundRemover\OfflineBackgroundRemover.exe
if not defined CI pause
exit /b 0

:error
echo.
echo [LOI] Build that bai. Xem thong bao phia tren.
if not defined CI pause
exit /b 1
