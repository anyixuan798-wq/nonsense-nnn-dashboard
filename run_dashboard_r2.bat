@echo off
title NNN dashboard - R2 collector loop (local rig -> Cloudflare R2)
cd /d D:\home\nonsense-dashboard
echo ============================================================
echo  every 5 minutes:
echo    1. scrape explorer.nonsense.rodeo  network hashrate / difficulty / miners
echo    2. read local GPU state via nvidia-smi + miner log
echo    3. upload data JSONs to Cloudflare R2 through the cf-hub Worker
echo  live page: https://cf-hub.anyixuan798.workers.dev/sites/nonsense-nnn-dashboard/
echo  close this window to stop collecting
echo ============================================================
:loop
python publish_r2.py
echo.
echo ---- cycle done %DATE% %TIME% / next in 300s ----
timeout /t 300 /nobreak >nul
goto loop
