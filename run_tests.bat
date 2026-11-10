@echo off
REM Menjalankan tes unit layout_core dengan Python ArcMap.
setlocal
set "PYTHON_ARCMAP="
for %%V in (10.8 10.7 10.6 10.5 10.4 10.3 10.2 10.1) do (
    if not defined PYTHON_ARCMAP if exist "C:\Python27\ArcGIS%%V\python.exe" set "PYTHON_ARCMAP=C:\Python27\ArcGIS%%V\python.exe"
)
if not defined PYTHON_ARCMAP set "PYTHON_ARCMAP=python"
cd /d "%~dp0"
"%PYTHON_ARCMAP%" -m unittest discover -s tests -v
pause
