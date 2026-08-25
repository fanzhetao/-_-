@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_portable.ps1"
set "RELEASE_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%RELEASE_EXIT_CODE%"=="0" (
    echo 发布失败，请检查上方错误信息。
) else (
    echo 发布成功，文件已生成到 release 目录。
)
pause
exit /b %RELEASE_EXIT_CODE%
