@echo off
cd /d "%~dp0"
"D:\Python311\python.exe" -X utf8 main.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Application exited with code %ERRORLEVEL%
    pause
)
