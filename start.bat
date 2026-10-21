@echo off
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" game_bot_smart.py --mode=0 --battle_time=150 --battle_count=0
