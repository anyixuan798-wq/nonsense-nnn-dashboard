@echo off
title NNN dashboard - local pusher (GPU state -> GitHub live branch)
cd /d D:\home\nonsense-dashboard
echo ============================================================
echo  pushes GPU / miner state to the dashboard every 180 seconds
echo  data -> https://github.com/anyixuan798-wq/nonsense-nnn-dashboard (branch: live)
echo  close this window to stop pushing
echo ============================================================
:loop
python local_pusher.py
timeout /t 180 /nobreak >nul
goto loop
