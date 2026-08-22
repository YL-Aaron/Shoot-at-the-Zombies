@echo off
chcp 65001 >nul
setlocal

echo 开始打包智能识别版...
echo.

set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
if not exist "%PYINSTALLER%" set "PYINSTALLER=pyinstaller"

"%PYINSTALLER%" --clean --noconfirm --onefile --console --name="start_game_smart" --add-data "templates;templates" --add-data "config.json;." game_bot_smart.py

if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo 打包完成！
echo 可执行文件位于 dist\start_game_smart.exe
pause
endlocal
