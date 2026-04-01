@echo off
setlocal enabledelayedexpansion

echo Tank Battle Arena - Server Suite
echo =================================

python3 --version >nul 2>&1
if errorlevel 1 (
    echo Python3 is not installed
    pause
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment...
    python3 -m venv venv
)

call venv\Scripts\activate.bat

echo Installing server requirements...
pip3 install -q -r requirements.txt

if not exist "grid.png" (
    echo Generating grid texture...
    python3 generate_grid.py
)

echo.
echo Starting all servers...
echo.

echo Starting Login Server (port 8766)...
start "Login Server" python3 login_server.py

timeout /t 2 /nobreak

echo Starting Game Server (port 8765)...
start "Game Server" python3 server_v2.py

timeout /t 2 /nobreak

echo Starting Website (port 5000)...
start "Website" python3 website.py

timeout /t 2 /nobreak

echo Starting Client...
start "Game Client" python3 client_complete.py

echo.
echo All servers started!
echo Close individual windows to stop each server.
pause