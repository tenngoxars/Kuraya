@echo off
cd /d "%~dp0"

echo.
echo   [1/4] Checking environment
where python >nul 2>nul
if not %errorlevel%==0 (
    echo   [ERROR] Python not found. Install Python 3 with "Add python.exe to PATH".
    if not "%1"=="nopause" pause >nul
    exit /b 1
)

echo   [2/4] Verifying spec hiddenimports
python packaging\check_spec.py
if not %errorlevel%==0 (
    echo.
    echo   Aborted before building. Fix kuraya.spec and run again.
    if not "%1"=="nopause" pause >nul
    exit /b 1
)

echo   [3/4] Installing build dependencies
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller -r requirements.txt
if not %errorlevel%==0 (
    echo   [ERROR] Dependency install failed.
    if not "%1"=="nopause" pause >nul
    exit /b 1
)

echo   [4/4] Building
rmdir /s /q build dist 2>nul
python -m PyInstaller --clean --noconfirm kuraya.spec
if not %errorlevel%==0 (
    echo   [ERROR] Build failed.
    if not "%1"=="nopause" pause >nul
    exit /b 1
)

echo.
echo   Done. Output: dist\Kuraya\Kuraya.exe
echo   Distribute the whole "dist\Kuraya" folder.
echo.
if not "%1"=="nopause" pause >nul
