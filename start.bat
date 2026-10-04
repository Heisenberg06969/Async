@echo off
title Async 2.0 Launcher
cd /d "%~dp0"
chcp 65001 >nul

:: Check if user specifically requested console Cava mode
if "%1"=="--cli" goto launch_cli
if "%1"=="-c" goto launch_cli

:: By default, launch the silent, zero-friction Windows System Tray app
where pythonw >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "" pythonw app_tray.py
    exit /b 0
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" app_tray.py
    exit /b 0
)

:launch_cli
echo ========================================================
echo   Async 2.0: Terminal Cava Visualizer Mode
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
