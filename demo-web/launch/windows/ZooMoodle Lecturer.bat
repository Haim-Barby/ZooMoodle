@echo off
REM Double-click after Python 3.12 is installed. This file does not download scripts.
cd /d "%~dp0\..\.."
echo ZooMoodle lecturer launcher
echo This is not fully automatic hotspot setup.
py -3 -m helper.launch_wizard
if errorlevel 1 (
  echo If Python was not found, install Python 3.12 from python.org and run this again.
  pause
)
