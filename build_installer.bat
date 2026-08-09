@echo off
setlocal
cd /d "%~dp0"

if defined ISCC if exist "%ISCC%" goto :iscc_ready
set "ISCC="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
if defined ISCC if exist "%ISCC%" goto :iscc_ready
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :iscc_ready
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :iscc_ready
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

:iscc_ready
if not exist "%ISCC%" (
    echo [LOI] Khong tim thay Inno Setup 6.
    echo Cai bang lenh: winget install JRSoftware.InnoSetup
    if not defined CI pause
    exit /b 1
)

if not exist "dist\KhongBietGiDungNoi\KhongBietGiDungNoi.exe" (
    echo [LOI] Chua co ban build. Hay chay build.bat truoc.
    if not defined CI pause
    exit /b 1
)

set "APP_VERSION="
for /f "usebackq delims=" %%V in (`".venv\Scripts\python.exe" -m image_tool.version`) do set "APP_VERSION=%%V"
if not defined APP_VERSION (
    echo [LOI] Khong the doc phien ban ung dung.
    if not defined CI pause
    exit /b 1
)

"%ISCC%" installer.iss
if errorlevel 1 (
    echo [LOI] Tao bo cai that bai.
    if not defined CI pause
    exit /b 1
)

powershell -NoProfile -Command "$file = Get-Item -LiteralPath ('release\KhongBietGiDungNoi_Setup_' + $env:APP_VERSION + '.exe'); $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash; Set-Content -LiteralPath 'release\SHA256SUMS.txt' -Encoding ascii -Value ($hash + '  ' + $file.Name)"
if errorlevel 1 (
    echo [LOI] Khong the tao SHA256.
    if not defined CI pause
    exit /b 1
)

echo.
echo Bo cai da san sang trong folder release.
if not defined CI pause
exit /b 0
