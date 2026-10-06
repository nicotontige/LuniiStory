@echo off
REM Launches luniiStory, setting everything up on first run.
REM
REM   run.bat            graphical interface
REM   run.bat list       any command line argument is passed through
setlocal
cd /d "%~dp0"

if not exist "vendor\Lunii.QT\pkg\api\device_lunii.py" (
    echo Fetching the Lunii.QT submodule...
    git submodule update --init --recursive || goto :error
)

if not exist ".venv" (
    echo Creating the virtual environment...
    python -m venv .venv || goto :error
)

if not exist ".venv\.requirements-stamp" (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto :error
    ".venv\Scripts\pip.exe" install --quiet -r requirements.txt || goto :error
    echo. > ".venv\.requirements-stamp"
)

".venv\Scripts\pythonw.exe" -m luniistory %*
goto :eof

:error
echo.
echo Setup failed. See the message above.
exit /b 1
