@echo off
chcp 65001 > nul
cd /d %~dp0
echo Запуск TillyPad Relay Agent...
python -m uvicorn app.relay_agent:app --host 0.0.0.0 --port 8010
pause
