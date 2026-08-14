@echo off
chcp 65001 >nul
echo 开始打包游戏机器人...
echo.

REM 使用PyInstaller打包，--windowed表示不显示控制台窗口，--onefile表示生成单个exe文件
REM 将模板和默认配置一并嵌入单文件EXE
set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
if not exist "%PYINSTALLER%" set "PYINSTALLER=pyinstaller"
"%PYINSTALLER%" --clean --noconfirm --onefile --name="start_game" --add-data "templates;templates" --add-data "config.json;." game_bot.py

echo.
echo 打包完成！
echo 可执行文件位于 dist/start_game.exe
pause