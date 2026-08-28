@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_portable.ps1"
set "RELEASE_EXIT_CODE=%errorlevel%"
echo.
if not "%RELEASE_EXIT_CODE%"=="0" (
    echo 发布失败，请查看上方错误信息。
) else (
    echo 发布成功，产物已保存到 release 目录。
)
pause
exit /b %RELEASE_EXIT_CODE%
