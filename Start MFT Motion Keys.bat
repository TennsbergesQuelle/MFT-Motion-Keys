@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python-Umgebung fehlt. Richte sie jetzt ein...
    python -m venv .venv
    if errorlevel 1 (
        echo Fehler: Python konnte die virtuelle Umgebung nicht erstellen.
        echo Bitte Python installieren und in den PATH aufnehmen.
        pause
        exit /b 1
    )

)

if not exist ".venv\Scripts\python.exe" (
    echo Fehler: Python wurde installiert, aber python.exe fehlt.
    pause
    exit /b 1
)

echo Pruefe HID-Abhaengigkeit...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Fehler: Abhaengigkeiten konnten nicht installiert werden.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app.py
if errorlevel 1 (
    echo Die MFT-App wurde mit einem Fehler beendet.
    pause
    exit /b 1
)
