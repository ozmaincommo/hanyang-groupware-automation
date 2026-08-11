@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

python -c "import playwright, tkcalendar, win32gui, psutil" >nul 2>nul
if errorlevel 1 goto install

goto run

:install
echo Required packages not found. Installing now (needs internet, 1-2 min).
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto installfail
echo.
echo Install complete.
echo.
goto run

:run
del /f /q error.log >nul 2>nul
start "" /min cmd /c "pythonw control_panel.py > error.log 2>&1"
timeout /t 3 /nobreak >nul

for %%A in (error.log) do set errsize=%%~zA
if not "%errsize%"=="0" goto crashed
del /f /q error.log >nul 2>nul
exit

:crashed
echo Something went wrong starting the program. Details below
echo (also saved to error.log in this folder):
echo.
type error.log
pause
exit /b 1

:nopython
echo Python not found.
echo Please install Python 3.10 or newer from https://www.python.org/downloads/
echo During install, check the box that adds Python to PATH.
echo Then run this file again.
pause
exit /b 1

:installfail
echo.
echo Package install failed. See the messages above.
pause
exit /b 1
