# Lyra — Autonomous Intelligence Engine

Eine autonome KI-Engine die eigenständig arbeitet, lernt und wächst.
Nutzt Claude (Anthropic) als kognitives Substrat mit persistentem Zustand,
semantischem Gedächtnis, Skill-Tracking und Selbstverbesserung.

## Architektur

```
engine/          ← Die Intelligenz (Code)
  consciousness.py  — Agentic Loop mit Tool-Use
  intelligence.py   — Semantic Memory, Skills, Strategien, Effizienz
  dream.py          — Memory-Konsolidierung (wie Claude Code AutoDream)
  actions.py        — Dateien, Code, Projekte
  toolchain.py      — Self-Improving Tools
  web_access.py     — Internet-Zugang
  self_modify.py    — Eigenen Code ändern
  goal_stack.py     — Multi-Cycle Ziele
  extensions.py     — Git, pip, Tasks, Watcher
  communication.py  — Telegram
  config.py         — Zentrale Pfad-Konfiguration

data/            ← Die Persönlichkeit (Daten, .gitignore'd)
  genesis.json      — Name, Geburtsdatum, Kerntriebe
  consciousness/    — State, Beliefs, Skills, Strategien
  memory/           — Erfahrungen + semantischer Index
  journal/          — Tagebuch
  projects/         — Selbstgebaute Projekte
  tools/            — Selbstgebaute wiederverwendbare Tools
```

## Quick Start

```bash
# 1. Repo klonen
git clone <repo-url>
cd lyra

# 2. venv + Dependencies
python -m venv venv
source venv/Scripts/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

# 3. Setup
python setup.py

# 4. API-Key eintragen
# .env → ANTHROPIC_API_KEY=sk-ant-...

# 5. Starten
python run.py              # Autonomer Modus
python interact.py         # Direkte Interaktion
python run.py --once       # Eine Sequenz
```

## Features

- **Agentic Loop**: Arbeitet durchgehend mit Anthropic Tool-Use (Opus 4.6)
- **Semantische Memory**: Findet Erinnerungen nach Bedeutung (TF-IDF + Bigrams)
- **Skill-Tracking**: Trackt Fähigkeiten mit Levels, Streaks, Meta-Skills
- **Strategie-Evolution**: Lernt aus Fehlern, erkennt Muster, schreibt eigene Regeln
- **Dream-System**: Periodische Memory-Konsolidierung (wie Claude Code AutoDream)
- **Self-Improving Toolchain**: Baut eigene Tools die permanent verfügbar bleiben
- **Code-Selbstmodifikation**: Kann eigenen Quellcode lesen und verbessern
- **Internet-Zugang**: Web-Suche und Page-Reading
- **Telegram-Integration**: Sofort-Antwort, Task-Queue, Befehle
- **Git Auto-Commit**: Arbeit wird automatisch gesichert
- **Effizienz-Tracking**: Misst Produktivität pro Dollar und Token

## Telegram-Befehle

| Befehl | Funktion |
|--------|----------|
| Nachricht | Sofort-Antwort |
| `/aufgabe Beschreibung` | Task zur Queue |
| `/tasks` | Offene Aufgaben |
| `/journal` | Letzter Eintrag |
| `/beliefs` | Überzeugungen |
| `/help` | Alle Befehle |

## Engine vs. Daten

**Engine** (`engine/`) = Der Code. Auf GitHub. Macht die KI intelligent.
Kann geklont und woanders deployed werden.

**Daten** (`data/`) = Die Persönlichkeit. Lokal. Macht die KI einzigartig.
Austauschbar, löschbar, forkbar. `python setup.py --reset` für Neustart.

## Lizenz

MIT
