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
echo [4/4] Slack Integration Setup
echo.
echo ==========================================
echo   You need Slack App tokens.
echo   Get them at https://api.slack.com/apps
echo ==========================================
echo.

:: Bot Token
set /p BOT_TOKEN="Slack Bot Token (starts with xoxb-): "
if "!BOT_TOKEN!"=="" (
    echo   This field is required.
    set /p BOT_TOKEN="Bot Token: "
)

echo.

:: App Token
set /p APP_TOKEN="Slack App Token (starts with xapp-): "
if "!APP_TOKEN!"=="" (
    echo   This field is required.
    set /p APP_TOKEN="App Token: "
)

echo.

:: Work Directory
set "DEFAULT_DIR=%cd%"
set /p WORK_DIR="Work Directory [%DEFAULT_DIR%]: "
if "!WORK_DIR!"=="" set "WORK_DIR=%DEFAULT_DIR%"

:: Create .env file
(
echo SLACK_BOT_TOKEN=!BOT_TOKEN!
echo SLACK_APP_TOKEN=!APP_TOKEN!
echo WORK_DIR=!WORK_DIR!
) > .env

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
echo Or simply run:
echo.
echo   run.bat
echo.

pause
