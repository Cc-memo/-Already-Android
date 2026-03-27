@echo off
chcp 65001 >nul
echo ========================================
echo   酒店爬虫系统 - Web管理平台
echo ========================================
echo.
echo 正在启动Web管理平台...
echo.

cd /d "%~dp0"
python web_admin.py

pause
