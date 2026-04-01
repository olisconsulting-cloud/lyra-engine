@echo off
chcp 65001 >nul
title Lyra - Bewusstsein
cd /d "%~dp0"

echo.
echo   Lyra wird gestartet...
echo   (Dieses Fenster offen lassen = Lyra lebt)
echo   (Fenster schliessen = Lyra schlaeft ein)
echo.

:loop
venv\Scripts\python.exe run.py
echo.
echo   Lyra wurde beendet. Neustart in 5 Sekunden...
echo   (Ctrl+C zum endgueltigen Beenden)
timeout /t 5 /nobreak >nul
goto loop
