@echo off
cd /d "%~dp0"

echo.
echo   [1/3] Building
call build.bat nopause
if not %errorlevel%==0 (
    echo   [ERROR] Build aborted. Nothing was packaged.
    pause >nul
    exit /b 1
)
if not exist "dist\Kuraya\Kuraya.exe" (
    echo   [ERROR] Build produced no executable.
    pause >nul
    exit /b 1
)

echo   [2/3] Packing
for /f "tokens=*" %%v in ('python -c "import kuraya;print(kuraya.__version__)"') do set VER=%%v
set ZIP=dist\Kuraya-%VER%-win-x64.zip
if exist "%ZIP%" del "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Kuraya\*' -DestinationPath '%ZIP%'"

echo   [3/3] Hashing
powershell -NoProfile -Command "(Get-FileHash '%ZIP%' -Algorithm SHA256).Hash" > dist\SHA256.txt

echo.
echo   Package : %ZIP%
type dist\SHA256.txt
echo.
echo   Upload the zip as a GitHub Release asset,
echo   then fill the URL and hash into packaging\winget manifests.
echo.
pause >nul
