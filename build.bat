@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Chua co moi truong build. Hay chay setup.bat truoc.
    pause
    exit /b 1
)

echo [1/4] Cai cong cu dong goi va test...
".venv\Scripts\python.exe" -m pip install -r build-requirements.txt
if errorlevel 1 goto :error

echo [2/4] Chay kiem thu...
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :error

echo [3/4] Dong goi Khong biet gi dung noi...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean KhongBietGiDungNoi.spec
if errorlevel 1 goto :error

echo [4/4] Chay packaged self-test...
powershell -NoProfile -Command "$process = Start-Process -FilePath (Resolve-Path 'dist\KhongBietGiDungNoi\KhongBietGiDungNoi.exe') -ArgumentList '--self-test' -WindowStyle Hidden -Wait -PassThru; exit $process.ExitCode"
if errorlevel 1 goto :error
powershell -NoProfile -Command "$process = Start-Process -FilePath (Resolve-Path 'dist\KhongBietGiDungNoi\KhongBietGiDungNoi.exe') -ArgumentList '--ui-smoke-test' -WindowStyle Hidden -Wait -PassThru; exit $process.ExitCode"
if errorlevel 1 goto :error

echo.
echo Build thanh cong: dist\KhongBietGiDungNoi\KhongBietGiDungNoi.exe
pause
exit /b 0

:error
echo.
echo [LOI] Build that bai. Xem thong bao phia tren.
pause
exit /b 1
