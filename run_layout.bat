@echo off
REM ==========================================================================
REM  Menjalankan run_layout.py dengan Python 2.7 bawaan ArcMap.
REM
REM  Contoh:
REM    run_layout.bat --dry-run
REM    run_layout.bat --estate SMSE --jpg
REM    run_layout.bat --config D:\Data\config.xlsx
REM
REM  Bila Python ArcMap tidak terdeteksi otomatis, isi PYTHON_ARCMAP di bawah.
REM ==========================================================================
setlocal

REM --- Isi manual bila perlu (kosongkan untuk deteksi otomatis) ---
set "PYTHON_ARCMAP="

if not defined PYTHON_ARCMAP (
    for %%V in (10.8 10.7 10.6 10.5 10.4 10.3 10.2 10.1) do (
        if not defined PYTHON_ARCMAP if exist "C:\Python27\ArcGIS%%V\python.exe" set "PYTHON_ARCMAP=C:\Python27\ArcGIS%%V\python.exe"
    )
)

if not defined PYTHON_ARCMAP (
    echo [ERROR] Python ArcMap tidak ditemukan di C:\Python27\ArcGIS10.x\
    echo         Edit run_layout.bat dan isi PYTHON_ARCMAP secara manual.
    if "%~1"=="" pause
    exit /b 3
)

if not exist "%PYTHON_ARCMAP%" (
    echo [ERROR] File tidak ada: %PYTHON_ARCMAP%
    if "%~1"=="" pause
    exit /b 3
)

echo Python: %PYTHON_ARCMAP%
cd /d "%~dp0"
"%PYTHON_ARCMAP%" "%~dp0run_layout.py" %*
set "KODE_KELUAR=%ERRORLEVEL%"

REM Bila dijalankan dengan klik ganda (tanpa argumen), tahan jendela
if "%~1"=="" pause
exit /b %KODE_KELUAR%
