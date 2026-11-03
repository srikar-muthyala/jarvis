@echo off
cd /d "%~dp0"
set PY=python
where py >nul 2>nul && set PY=py -3

echo Creating virtual environment...
%PY% -m venv .venv || goto :fail
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
echo Installing packages (this takes a few minutes)...
pip install -r requirements.txt || goto :fail
if not exist .env copy .env.example .env >nul

echo.
echo Setup done. Optional: open .env to add an API key for answering questions.
echo Then double-click run.bat
pause
exit /b 0

:fail
echo.
echo Setup failed. Install Python 3.11 to 3.13 from python.org and tick "Add python.exe to PATH".
pause
exit /b 1
