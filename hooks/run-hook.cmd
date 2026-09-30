: <<'CMDBLOCK'
@echo off
REM Cross-platform wrapper for content-design hooks.
REM Usage: run-hook.cmd session-start <agent|cursor>

if /I not "%~1"=="session-start" exit /b 0

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    py -3 "%~dp0session-start.py" "%~2"
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    python "%~dp0session-start.py" "%~2"
    exit /b %ERRORLEVEL%
)

exit /b 0
CMDBLOCK

if [ "${1:-}" != "session-start" ]; then
  exit 0
fi

SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
HARNESS="${2:-agent}"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/session-start.py" "$HARNESS"
fi
if command -v python >/dev/null 2>&1; then
  exec python "${SCRIPT_DIR}/session-start.py" "$HARNESS"
fi

exit 0
