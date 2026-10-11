@echo off
REM ver-mod.bat - Launch Claude Code with the Margarita panel mod loaded for THIS session only,
REM so you can preview Clawd in the side pane without installing anything permanently.
REM
REM The mod renders Clawd with terminal block characters (not the SDL device simulator). Inside
REM the Claude Code session, open the pane and pin an animation with the /margarita command:
REM     /margarita idle      (a fixed pose)
REM     /margarita happy     (the widest animation)
REM     /margarita auto      (back to following the real session state)
REM
REM Clawd is drawn at V2_SCALE (see claude-mod/margarita-band/hooks/playback.ts): lower that
REM constant to shrink him further, raise it toward 1 for the original size.
setlocal

set "MOD=%~dp0claude-mod\margarita-band"

where claude >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] 'claude' CLI not found on PATH. Install Claude Code first.
  echo.
  pause
  exit /b 1
)

if not exist "%MOD%\.claude-plugin\plugin.json" (
  echo.
  echo [!] Mod not found at:
  echo     %MOD%
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   Margarita panel mod - live preview
echo ============================================================
echo   Loading the mod for this session only (nothing installed).
echo   Once Claude Code opens, run:
echo       /margarita idle      pin a fixed pose
echo       /margarita happy     the widest animation
echo       /margarita auto      follow the real session state
echo ============================================================
echo.

claude --plugin-dir "%MOD%"
