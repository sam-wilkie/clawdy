@echo off
REM ver-sim.bat - Launch the Clawd Tank SDL2 simulator window to preview
REM animations live before flashing the device. Shows the crab with the clock
REM and usage bars, exactly as the device renders.
REM
REM The sim window opens in the FOREGROUND; close it (q / Esc / click X) to
REM return to this menu. We do NOT use `start` (its quoting breaks on the
REM --events strings that contain quotes and semicolons) and we pass --bordered
REM so the window has a normal title bar and is easy to find.
setlocal

set "SIM=%~dp0simulator\build\clawd-tank-sim.exe"

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

set "SCALE=%~1"
if "%SCALE%"=="" set "SCALE=3"
REM The desk pet (--desk) has its own default scale; the normal window keeps SCALE.
set "DESKSCALE=%~2"
if "%DESKSCALE%"=="" set "DESKSCALE=2"

REM Window mode: a normal bordered window, or --desk (crab only, transparent, always on top).
set "WINFLAG=--bordered"
set "WINLBL=ventana normal"

:menu
cls
echo ============================================================
call :effscale
echo   Clawd Tank - Simulator preview  (scale x%ES%)
echo ============================================================
echo   Pick an animation. The sim window opens with a title bar;
echo   press q or Esc (or close it) to come back to this menu.
echo   The crab sits on the grass with the clock + usage bars.
echo.
echo    1) idle          6) building     11) debugger
echo    2) wake          7) confused     12) conducting
echo    3) happy         8) dizzy        13) alert
echo    4) thinking      9) sweeping     14) low_battery
echo    5) typing       10) sleeping     15) hat_mishap
echo.
echo    a) MUESTRARIO - parade ALL animations automatically
echo    s) change scale (current x%ES%)
echo    d) window: %WINLBL%  (toggle)
echo    q) quit
echo ============================================================
set /p "CH=Choice: "

if /i "%CH%"=="q" goto :eof
if /i "%CH%"=="s" (
  if "%WINFLAG%"=="--desk" (
    set /p "DESKSCALE=New desk scale (1, 2 or 3): "
  ) else (
    set /p "SCALE=New scale (2 or 3): "
  )
  goto menu
)
if /i "%CH%"=="a" goto muestrario
if /i "%CH%"=="d" (
  if "%WINFLAG%"=="--desk" (
    set "WINFLAG=--bordered"
    set "WINLBL=ventana normal"
  ) else (
    set "WINFLAG=--desk"
    set "WINLBL=escritorio flotante"
  )
  goto menu
)

set "ANIM="
if "%CH%"=="1"  set "ANIM=idle"
if "%CH%"=="2"  set "ANIM=wake"
if "%CH%"=="3"  set "ANIM=happy"
if "%CH%"=="4"  set "ANIM=thinking"
if "%CH%"=="5"  set "ANIM=typing"
if "%CH%"=="6"  set "ANIM=building"
if "%CH%"=="7"  set "ANIM=confused"
if "%CH%"=="8"  set "ANIM=dizzy"
if "%CH%"=="9"  set "ANIM=sweeping"
if "%CH%"=="10" set "ANIM=sleeping"
if "%CH%"=="11" set "ANIM=debugger"
if "%CH%"=="12" set "ANIM=conducting"
if "%CH%"=="13" set "ANIM=alert"
if "%CH%"=="14" set "ANIM=low_battery"
if "%CH%"=="15" set "ANIM=hat_mishap"

if "%ANIM%"=="" (
  echo Unknown choice: %CH%
  timeout /t 1 >nul
  goto menu
)

echo.
call :effscale
echo Launching "%ANIM%" at x%ES%. Close the window to return here...
"%SIM%" --scale %ES% %WINFLAG% --events "connect; sessions %ANIM% 1"
goto menu

:muestrario
echo.
call :effscale
echo Launching MUESTRARIO at x%ES% (all 15 anims, 2.5s each). Close the window to return...
"%SIM%" --scale %ES% %WINFLAG% --events "connect; sessions idle 1; wait 2500; sessions wake 1; wait 2500; sessions happy 1; wait 2500; sessions thinking 1; wait 2500; sessions typing 1; wait 2500; sessions building 1; wait 2500; sessions confused 1; wait 2500; sessions dizzy 1; wait 2500; sessions sweeping 1; wait 2500; sessions sleeping 1; wait 2500; sessions debugger 1; wait 2500; sessions conducting 1; wait 2500; sessions alert 1; wait 2500; sessions low_battery 1; wait 2500; sessions hat_mishap 1; wait 2500"
goto menu

:effscale
set "ES=%SCALE%"
if "%WINFLAG%"=="--desk" set "ES=%DESKSCALE%"
goto :eof
