@echo off
title iPOS Accounting Report Server
echo Dang kiem tra va tat cac ban server dang chay ngam...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM LedgerReport_ChuLong.exe /T >nul 2>&1
taskkill /F /IM iPOS_Ledger_Studio.exe /T >nul 2>&1
taskkill /F /IM iPOS_Accounting_Report.exe /T >nul 2>&1

echo Dang khoi dong Server...
cd /d "%~dp0"
python server.py
pause
