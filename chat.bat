@echo off
cd /d "%~dp0"
set HF_HUB_DISABLE_XET=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
call .venv\Scripts\activate.bat
python jarvis.py --chat %*
pause
