@echo off
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found.
    echo Please run setup_env.bat first.
    pause
    exit /b 1
)

echo Starting AO3 Studio at http://127.0.0.1:8093/
start "" "http://127.0.0.1:8093/"
python main.py --port 8093
pause
