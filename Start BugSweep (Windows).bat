@echo off
rem Double-click this file to open BugSweep.
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw -m bugsweep
    exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
    python -m bugsweep
    exit /b
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m bugsweep
    exit /b
)

echo.
echo  BugSweep needs Python, which isn't installed on this computer yet.
echo.
echo  1. Go to https://www.python.org/downloads/ and click the big yellow Download button.
echo  2. When the installer opens, tick "Add python.exe to PATH", then click Install Now.
echo  3. Double-click this file again.
echo.
echo  Stuck? Contact tech support - see support.json in this folder for details.
echo.
start "" https://www.python.org/downloads/
pause
