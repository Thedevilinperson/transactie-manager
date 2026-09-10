@echo off
REM Transactie Manager - starten op Windows.
REM De eerste keer wordt een virtuele omgeving gemaakt en worden de
REM benodigde pakketten geinstalleerd. Daarna start de toepassing meteen.

setlocal
cd /d "%~dp0transactie_manager"

if not exist "..\.venv" (
    echo Virtuele omgeving aanmaken...
    py -3 -m venv ..\.venv || python -m venv ..\.venv
    if errorlevel 1 (
        echo Python 3 is niet gevonden. Installeer Python 3.11 of nieuwer.
        pause
        exit /b 1
    )
    call ..\.venv\Scripts\activate.bat
    echo Pakketten installeren...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    call ..\.venv\Scripts\activate.bat
)

set TM_DATA_DIR=%~dp0data
python start.py
pause
endlocal
