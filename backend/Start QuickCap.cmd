@echo off
cd /d "%~dp0"
python quickcap.py
if errorlevel 1 pause
