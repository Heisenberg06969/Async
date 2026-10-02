@echo off
title Async - Smart Lighting, Visualizer & Ambilight
cd /d "%~dp0"
chcp 65001 >nul

echo ========================================================
echo   Async: Smart Lighting, Cava Visualizer & Ambilight
echo ========================================================
echo.

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python main.py
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
) else (
    echo [ERROR] Python not found in PATH or standard installation directory.
    echo Please install Python 3.10+ or add it to your system PATH.
    pause
    exit /b 1
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Async stopped unexpectedly with error code %ERRORLEVEL%.
    pause
) else (
    echo.
    echo Async closed cleanly.
    pause
)
