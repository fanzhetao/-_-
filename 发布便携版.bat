@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_portable.ps1"
set "RELEASE_EXIT_CODE=%errorlevel%"
echo.
if not "%RELEASE_EXIT_CODE%"=="0" (
    echo Release failed. See the error details above.
) else (
    echo Release succeeded. Artifacts are in the release directory.
)
pause
exit /b %RELEASE_EXIT_CODE%
