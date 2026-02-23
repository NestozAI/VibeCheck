@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

:: =============================================================================
:: VibeCheck - Windows Setup Script
:: =============================================================================

echo.
echo ==========================================
echo   VibeCheck Setup (Windows)
echo ==========================================
echo.

set ENV_NAME=vibecheck

:: =============================================================================
:: Check Conda
:: =============================================================================

echo [1/4] Checking Conda...

where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Conda is not installed.
    echo Please install Miniconda or Anaconda first.
    echo https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo   Conda found

:: =============================================================================
:: Create Conda Environment
:: =============================================================================

echo.
echo [2/4] Creating Conda environment (%ENV_NAME%)...

conda env list | findstr /b "%ENV_NAME% " >nul 2>nul
if %errorlevel% equ 0 (
    echo   Existing environment found, reusing...
) else (
    call conda create -n %ENV_NAME% python=3.11 -y
    echo   Environment created
)

:: Activate environment
call conda activate %ENV_NAME%

:: =============================================================================
:: Install Dependencies
:: =============================================================================

echo.
echo [3/4] Installing dependencies...

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo   Packages installed

:: =============================================================================
:: Setup Environment Variables
:: =============================================================================

echo.
echo [4/4] Configuration
echo.

:: Work Directory
set "DEFAULT_DIR=%cd%"
set /p WORK_DIR="Working directory [%DEFAULT_DIR%]: "
if "!WORK_DIR!"=="" set "WORK_DIR=%DEFAULT_DIR%"

echo.

:: Web port
set /p WEB_PORT="Web UI port [8501]: "
if "!WEB_PORT!"=="" set "WEB_PORT=8501"

echo.
echo ==========================================
echo   Slack integration (optional)
echo   Press Enter to skip if not using Slack.
echo   Get tokens at https://api.slack.com/apps
echo ==========================================
echo.

:: Bot Token (optional)
set /p BOT_TOKEN="Slack Bot Token (xoxb-...): "

:: App Token (optional)
set /p APP_TOKEN="Slack App Token (xapp-...): "

:: Create .env file
(
echo WORK_DIR=!WORK_DIR!
echo WEB_PORT=!WEB_PORT!
) > .env

if not "!BOT_TOKEN!"=="" if not "!APP_TOKEN!"=="" (
    (
    echo SLACK_BOT_TOKEN=!BOT_TOKEN!
    echo SLACK_APP_TOKEN=!APP_TOKEN!
    ) >> .env
    echo.
    echo   Slack integration: enabled
) else (
    echo.
    echo   Slack integration: disabled (web-only mode^)
)

echo.
echo .env file created successfully.

:: =============================================================================
:: Complete
:: =============================================================================

echo.
echo ==========================================
echo   Setup Complete!
echo ==========================================
echo.
echo To run:
echo.
echo   conda activate %ENV_NAME%
echo   python main.py
echo.
echo Then open in your browser:
echo.
echo   http://localhost:!WEB_PORT!
echo.
echo Or simply run:
echo.
echo   run.bat
echo.

pause
