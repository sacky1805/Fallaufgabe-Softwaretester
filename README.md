# README – Python-Skript ausführen (Windows, macOS, Linux)

Diese Anleitung erklärt, was benötigt wird und wie man das Python‑Skript ausführt.

---

## 1) Voraussetzungen

* **Internetverbindung** (zum Installieren von Paketen)
* **Python** ≥ 3.10 (empfohlen 3.12)
* **pip** (kommt mit Python)
* **Git** 
* **Editor/IDE** PyCharm oder ähnliches

> **Windows**: Prüfen, ob Python installiert ist

```powershell
py -V
```

> **macOS/Linux**

```bash
python3 --version
```

Wenn nicht vorhanden, Python von [https://python.org](https://python.org) installieren (Windows-Installer: **"Add Python to PATH"** anhaken).

---

## 2) Projekt beziehen

* **Variante A (ZIP)**: Projekt als ZIP von GitHub herunterladen → entpacken.
* **Variante B (Git)**: 
```bash
# Windows PowerShell oder Git Bash
cd C:\Projekte
git clone https://github.com/sacky1805/Fallaufgabe-Softwaretester.git
cd <repo>
```

---

## 3) Virtuelle Umgebung anlegen und aktivieren

Eine virtuelle Umgebung hält Projekt‑Abhängigkeiten getrennt vom System.

**Windows (PowerShell/CMD)**

```powershell
py -m venv .venv
.\.venv\Scripts\activate
```

**macOS/Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> Aktivierte Umgebungen erkennst du am Präfix `(venv)` bzw. `(.venv)` vor deiner Konsole. Deaktivieren mit `deactivate`.

---

## 4) pip aktualisieren und Abhängigkeiten installieren

```bash
python -m pip install --upgrade pip
```

```bash
pip install requests python-dotenv
```

### Optionale Spezialfälle (häufig in Automations-/QA‑Projekten)

* **Selenium (mit webdriver-manager)** – keine manuelle Treiberinstallation nötig:

```bash
pip install selenium webdriver-manager
```

* **.env-Unterstützung** (Konfiguration über Umgebungsvariablen):

```bash
pip install python-dotenv
```

---

## 5) Konfiguration (.env) – optional, aber empfohlen

Wenn das Skript sensible Daten (Tokens, Passwörter, API‑Keys) nutzt, lege im Projektverzeichnis eine Datei **`.env`** an:

```
# .env (Beispiel)
API_BASE_URL=https://api.example.com
API_KEY=abc123
DEBUG=true
```

Das Skript lädt diese Werte mit `python-dotenv` oder über die eigenen OS‑Umgebungsvariablen.

---

## 6) Skript ausführen

**Windows**

```powershell
# Im Projektordner, virtuelle Umgebung aktiv
python .\src\UI-Test-Checkout.py
# oder, wenn die Datei im Root liegt
python .\UI-Test-Checkout.py
```

**macOS/Linux**

```bash
python3 ./src/UI-Test-Checkout.py
# oder
python3 ./UI-Test-Checkout.py
```

Hinweis!
Bitte bei folgenden Zeilen im Code die Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden!

CLIENT_ID: str = os.getenv("SC_CLIENT_ID", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
CLIENT_SECRET: str = os.getenv("SC_CLIENT_SECRET", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
GENERAL_CONTRACT_ID: str = os.getenv("SC_GCR", "bitte die validen Testdaten aus dem PDF Fallaufgabe Softwaretester verwenden")
