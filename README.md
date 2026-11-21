# MFT Motion Keys

MFT Motion Keys ist eine plattformübergreifende Python-App, die das MFT-USB-Board
als konfigurierbare Tastatursteuerung verwendet. Sie unterstützt Windows, Linux
und macOS und installiert keinen eigenen Gerätetreiber.

> **Hinweis:** Dieses Projekt wurde mit Vibe Coding erstellt.

Verbesserungsvorschläge und Bugs können jederzeit gemeldet werden. Öffne dafür
bitte ein Issue im GitHub-Repositorium.

## Portables Paket und Start

Das Paket benötigt eine installierte Python-3-Version und eine Internetverbindung
für die Python-Abhängigkeiten. Beim ersten Start legt das jeweilige Startskript
eine lokale `.venv` an und installiert die passenden Pakete. Es gibt keinen
systemweiten Installer; Programm und virtuelle Umgebung bleiben im entpackten
Ordner.

- **Windows:** `Start MFT Motion Keys.bat` doppelklicken.
- **Linux:** `./Start MFT Motion Keys.sh` im Terminal ausführen.
- **Linux-Desktop-Verknüpfung:** `./install` ausführen. Das Skript legt eine
  Verknüpfung auf dem Desktop an.
- **macOS:** `Start MFT Motion Keys.command` doppelklicken. Falls macOS das
  Öffnen blockiert, im Terminal `bash "Start MFT Motion Keys.command"` ausführen.

## Einrichtung je Plattform

### Windows

Python 3 und Tkinter müssen verfügbar sein. Das Startskript erstellt die
virtuelle Umgebung, installiert PyWinUSB und startet die App.

### Linux

Python 3, Tkinter, X11/XTest und die HIDAPI-Entwicklungsbibliothek müssen
installiert sein. Auf Debian/Ubuntu:

```bash
sudo apt install python3 python3-venv python3-tk python3-dev build-essential libhidapi-dev libx11-dev libxtst-dev
```

In einer Wayland-Sitzung benötigt die Tastaturausgabe eine X11/XWayland-Sitzung;
native Wayland-Eingabe wird von `pynput` nicht allgemein unterstützt.

Falls die Anwendung meldet, dass der Zugriff auf das Board verweigert wurde,
lege für den Sensor eine udev-Regel an und melde dich danach ab und wieder an:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="17b5", ATTRS{idProduct}=="0010", MODE="0660", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-mft-sensor.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### macOS

Installiere Python 3 und die Xcode Command Line Tools. Erlaube Python nach der
ersten Anfrage in **Systemeinstellungen → Datenschutz & Sicherheit →
Bedienungshilfen**, damit die App Tastendrücke an andere Apps senden kann.
`hidapi` benötigt je nach Python/macOS-Version eine verfügbare Binärdatei oder
die HIDAPI-Entwicklungsbibliothek aus Homebrew (`brew install hidapi`).

## Bedienung

1. Verbinde das MFT-Board und klicke **Board verbinden**.
2. Halte das Board still, während die App die Ruhelage einmisst.
3. Aktiviere **Tastenausgabe starten** und wechsle zum gewünschten Spiel oder
   Programm. Die Tasten werden im aktiven Vordergrundfenster gedrückt gehalten.
4. Standardmäßig steuern Vor/Zurück `W`/`S` und Links/Rechts `A`/`D`. Mit
   **Taste ändern** kannst du Buchstaben, Pfeiltasten, Leertaste, Enter und
   Funktionstasten einstellen. Die Empfindlichkeit kann ebenfalls angepasst
   werden.
5. Bei abweichender Montage kannst du im Kalibrierbereich die fünf Haltungen
   neu aufnehmen. Halte jede Haltung ruhig, bis 60 Werte erfasst wurden.
   Beim Aufnehmen der Mitte springt der Live-Kreis ins Zentrum zurück.

Tastenzuweisungen, Kalibrierung und Empfindlichkeit werden in `settings.json`
im Programmordner gespeichert. Aktiviere die Ausgabe nur, wenn du sie brauchst;
beim Trennen des Boards und beim Schließen der App werden gehaltene Tasten
freigegeben.

## Hardware und Grenzen

- MFT Sensor: Vendor ID `0x17B5`, Product ID `0x0010`.
- HID-Report: Report-ID `0`, 64 Datenbytes; X ist signed 16-bit Big-Endian ab
  Byte 2, Y ist signed 16-bit Big-Endian ab Byte 0.
- Windows verwendet PyWinUSB; Linux und macOS verwenden HIDAPI. Für die
  Tastaturausgabe wird `pynput` eingesetzt.
- Diese Plattformversion ist für Windows auf dem vorhandenen Board getestet.
  macOS- und Linux-Installationen sowie Berechtigungen müssen auf dem jeweiligen
  Zielgerät geprüft werden. Der HID-Sensor wurde nicht auf diesen Plattformen
  getestet.

---

# English

MFT Motion Keys is a cross-platform Python app that turns the MFT USB board into
a configurable keyboard controller. It supports Windows, Linux and macOS and
does not install a separate device driver.

> **Note:** This project was vibe coded.

Suggestions for improvements and bug reports can be submitted at any time.
Please open an issue in the GitHub repository.

## Portable package and startup

The package requires Python 3 and an internet connection to install its Python
dependencies. On first launch, the platform's startup script creates a local
`.venv` and installs the required packages. This is a portable application, not
a system-wide installer; the app and its virtual environment stay in the
extracted folder.

- **Windows:** Double-click `Start MFT Motion Keys.bat`.
- **Linux:** Run `./Start MFT Motion Keys.sh` in a terminal.
- **Linux desktop shortcut:** Run `./install`. The script creates a shortcut on the desktop.
- **macOS:** Double-click `Start MFT Motion Keys.command`. If macOS blocks it,
  run `bash "Start MFT Motion Keys.command"` in Terminal.

## Platform setup

### Windows

Python 3 and Tkinter must be available. The startup script creates the virtual
environment, installs PyWinUSB and launches the app.

### Linux

Python 3, Tkinter, X11/XTest and the HIDAPI development library are required.
On Debian/Ubuntu, install them with:

```bash
sudo apt install python3 python3-venv python3-tk python3-dev build-essential libhidapi-dev libx11-dev libxtst-dev
```

In a Wayland session, keyboard output needs an X11/XWayland session; native
Wayland input is not generally supported by `pynput`.

If the app reports that access to the board is denied, add a udev rule for the
sensor and then sign out and back in:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="17b5", ATTRS{idProduct}=="0010", MODE="0660", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-mft-sensor.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### macOS

Install Python 3 and the Xcode Command Line Tools. After the first request,
allow Python under **System Settings → Privacy & Security → Accessibility** so
the app can send keystrokes to other apps. Depending on your Python/macOS
version, `hidapi` may need a compatible binary package or the Homebrew HIDAPI
development library (`brew install hidapi`).

## Using the app

1. Connect the MFT board and click **Connect board**.
2. Keep the board still while the app measures the neutral position.
3. Enable **Start keyboard output**, then switch to the game or app you want to
   control. Keys are held in the active foreground window.
4. By default, forward/back map to `W`/`S` and left/right to `A`/`D`. Use
   **Change key** to choose letters, arrow keys, Space, Enter or function keys.
   You can also adjust the sensitivity.
5. If the board is mounted differently, capture the five poses again in the
   calibration section. Hold each pose steady until 60 samples have been read.
   Capturing the neutral pose recenters the live motion indicator.

Key mappings, calibration and sensitivity are saved to `settings.json` in the
app folder. Enable keyboard output only when needed; held keys are released
when the board disconnects or the app closes.

## Hardware and limitations

- MFT Sensor: Vendor ID `0x17B5`, Product ID `0x0010`.
- HID report: Report ID `0`, 64 data bytes; X is signed 16-bit big-endian at
  byte 2, and Y is signed 16-bit big-endian at byte 0.
- Windows uses PyWinUSB; Linux and macOS use HIDAPI. Keyboard output uses
  `pynput`.
- This version has been tested on Windows with the available board. Linux and
  macOS installation and permissions should be verified on the target device;
  the sensor itself has not been tested on those platforms.
