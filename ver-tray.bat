@echo off
REM ver-tray.bat - Run the Margarita Tank tray app from source (dev checkout) to try
REM the tray menu, e.g. the "Floating desk pet" item that shows the crab on the desktop.
REM
REM WARNING: this is the REAL tray app, not a sandbox. On start it:
REM   - rewrites the Claude Code hooks in %USERPROFILE%\.claude\settings.json (the
REM     PermissionRequest hook gets a 70 s timeout and waits for the desk-window bubble),
REM   - starts the daemon and its Unix/TCP sockets,
REM   - kills any running clawd-tank-sim.exe (stale-sim cleanup) and starts its own.
REM   - reads/writes %USERPROFILE%\.clawd-tank\preferences.json.
REM Quit it from the tray menu ("Quit Margarita Tank") or with Ctrl+C here.
REM Only one tray instance can run at a time: quit the installed one first.
setlocal

set "ROOT=%~dp0"
set "PY=%ROOT%host\.venv\Scripts\python.exe"
set "SIMDIR=%ROOT%simulator\build"
set "SIM=%SIMDIR%\clawd-tank-sim.exe"

if not exist "%PY%" (
  echo.
  echo [!] Host virtualenv not found at:
  echo     %PY%
  echo.
  echo Create it with:
  echo     cd host
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -r requirements-dev.txt
  echo.
  pause
  exit /b 1
)

if not exist "%SIM%" (
  echo.
  echo [!] Simulator binary not found at:
  echo     %SIM%
  echo.
  echo Build it first with:
  echo     cmake -B simulator\build -S simulator -G Ninja -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ -DSTATIC_SDL2=ON
  echo     cmake --build simulator\build
  echo.
  pause
  exit /b 1
)

REM The tray looks for the simulator next to python.exe, then on PATH.
set "PATH=%SIMDIR%;%PATH%"

echo Starting the Margarita Tank tray app (look for the crab icon in the tray).
echo Use the tray menu: "Floating desk pet". Close it with "Quit Margarita Tank".
cd /d "%ROOT%host"
"%PY%" -m clawd_tank_menubar
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [!] The tray app exited with code %RC%. Log: %USERPROFILE%\.clawd-tank\logs\clawd-tank.log
  pause
)
exit /b %RC%
