@echo off
REM ============================================================
REM  Nova IDE - Windows .exe builder
REM  Pure ASCII on purpose: cmd.exe reads .bat files in the
REM  OEM codepage (CP866 on Russian Windows), so any non-ASCII
REM  byte gets mangled. Keeping this file ASCII-only makes it
REM  work on any Windows regardless of system language.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === Nova IDE: building Windows .exe ===
echo.

REM --- Check Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install Python 3.9+ from https://python.org
    echo and tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install "PySide6>=6.5" "PyInstaller>=6.0"
if errorlevel 1 goto :fail

echo.
echo [2/3] Building single-file NovaIDE.exe ...
python -m PyInstaller nova_ide_win.spec --noconfirm --clean
if errorlevel 1 goto :fail

echo.
echo [3/3] Done.
echo.
echo   Output: dist\NovaIDE.exe
echo.
echo   Note: first launch of the .exe takes a few seconds
echo   because it unpacks itself to a temp folder.
echo.
pause
exit /b 0

:fail
echo.
echo [ERROR] Build failed. See messages above.
echo.
pause
exit /b 1
