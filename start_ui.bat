@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Activating Python virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo [2/2] Launching Jarvis Modern Transparent Desktop Widget...
python run_ui_widget.py

echo Done.
