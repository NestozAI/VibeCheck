@echo off
chcp 65001 > nul

:: VibeCheck Run Script (Windows)

cd /d "%~dp0"

set ENV_NAME=vibecheck

:: Check .env
if not exist ".env" (
    echo Error: .env file not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

:: Activate Conda environment
call conda activate %ENV_NAME%

echo Starting VibeCheck...
python main.py

pause
