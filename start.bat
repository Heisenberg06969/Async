@echo off
title Async 2.0 Launcher
cd /d "%~dp0"
chcp 65001 >nul

:: Check if user specifically requested console Cava mode
if "%1"=="--cli" goto launch_cli
if "%1"=="-c" goto launch_cli

:: Locate Python with priority to real installations (bypassing broken WindowsApps stub)
set "PYW_EXE="
set "PY_EXE="

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    set "PYW_EXE=%~dp0.venv\Scripts\pythonw.exe"
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\pythonw.exe" (
    set "PYW_EXE=%~dp0venv\Scripts\pythonw.exe"
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    set "PYW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe" (
    set "PYW_EXE=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" (
    set "PYW_EXE=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe" (
    set "PYW_EXE=%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) else (
    for /f "tokens=*" %%i in ('where pythonw 2^>nul ^| findstr /v /i "WindowsApps"') do (
        if not defined PYW_EXE set "PYW_EXE=%%i"
    )
    for /f "tokens=*" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do (
        if not defined PY_EXE set "PY_EXE=%%i"
    )
)

if not defined PYW_EXE set "PYW_EXE=pythonw.exe"
if not defined PY_EXE set "PY_EXE=python.exe"

:: By default, launch the silent, zero-friction Windows System Tray app
start "" "%PYW_EXE%" app_tray.py
exit /b 0

:launch_cli
echo ========================================================
echo   Async 2.0: Terminal Cava Visualizer Mode
echo ========================================================
echo.

if defined PY_EXE (
    "%PY_EXE%" main.py
) else (
    echo [ERROR] Python not found in PATH or standard installation directory.
    echo Please install Python 3.10+ or add it to your system PATH.
    pause
    exit /b 1
)
