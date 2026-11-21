#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 wurde nicht gefunden. Bitte Python 3 installieren."
    read -r -p "Eingabetaste zum Schliessen ..."
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Die Python-Umgebung konnte nicht erstellt werden."
        read -r -p "Eingabetaste zum Schliessen ..."
        exit 1
    fi
fi

".venv/bin/python" -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Die Abhaengigkeiten konnten nicht installiert werden."
    read -r -p "Eingabetaste zum Schliessen ..."
    exit 1
fi

".venv/bin/python" app.py
if [ $? -ne 0 ]; then
    echo "Die MFT-App wurde mit einem Fehler beendet."
    read -r -p "Eingabetaste zum Schliessen ..."
    exit 1
fi
