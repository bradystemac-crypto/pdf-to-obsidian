@echo off
echo ========================================
echo   PDF-to-Obsidian Launcher
echo ========================================
echo.

:: Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Please run "python setup.py" first to set up the project.
    echo.
    pause
    exit /b 1
)

:: Check if .env exists
if not exist ".env" (
    echo [ERROR] .env file not found.
    echo         Please run "python setup.py" first to configure your API keys.
    echo.
    pause
    exit /b 1
)

:: Activate venv and run
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Starting application...
echo.
python app.py

:: If we get here with an error, keep the window open
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%.
    pause
)
