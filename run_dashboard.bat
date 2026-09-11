@echo off
title NNN dashboard - collector loop (network + local GPU -> GitHub live branch)
cd /d D:\home\nonsense-dashboard
echo ============================================================
echo  every 5 minutes:
echo    1. scrape explorer.nonsense.rodeo (network hashrate / difficulty / miners)
echo    2. read local GPU state (nvidia-smi + miner)
echo    3. push data to branch "live" of anyixuan798-wq/nonsense-nnn-dashboard
echo  close this window to stop collecting
echo ============================================================
:loop
python publish.py
echo.
echo ---- cycle done %DATE% %TIME% / next in 300s ----
timeout /t 300 /nobreak >nul
goto loop
