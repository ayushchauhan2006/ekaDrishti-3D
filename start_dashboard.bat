@echo off
setlocal enabledelayedexpansion

echo =======================================================
echo EkaDrishti Dashboard Windows Setup ^& Runner
echo =======================================================

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Creating one...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Make sure python is installed and in your PATH.
        pause
        exit /b 1
    )
    
    echo [INFO] Virtual environment created successfully.
    echo [INFO] Installing required packages from requirements.txt...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements. Please check any error messages above.
        pause
        exit /b 1
    )
    echo [INFO] Dependencies installed successfully.
) ELSE (
    echo [INFO] Virtual environment found.
)

echo.
echo [INFO] Starting Dashboard server...
.venv\Scripts\python.exe dashboard\server.py

pause
