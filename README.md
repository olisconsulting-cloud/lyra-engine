# Lyra — Autonomous Intelligence Engine

Eine autonome KI-Engine die eigenständig arbeitet, lernt und wächst.
Multi-LLM-Architektur: Gemma 4 31B als Reasoning-Kraftwerk (80%),
Claude Opus für Tiefenanalyse, GPT-4.1-mini für JSON-Tasks.

## LLM-Strategie

| Modell | Aufgabe | Warum |
|--------|---------|-------|
| **Gemma 4 31B** | Hauptarbeit, Reasoning, Coding, Goal-Planning | GPQA 84%, LiveCodeBench 80%, Vision, $0 (NIM) |
| **Kimi K2.5** | Fallback Stufe 1 | Bewährt, $0, SWE-bench 65.8% |
| **GPT-4.1-mini** | Dream (Memory-Konsolidierung) | JSON-Garantie, Structured Outputs |
| **Claude Opus 4.6** | Audit, Result-Validation | Höchste Analysetiefe, keine Abstriche |
| **DeepSeek V3** | Fallback Stufe 2 | Günstig, solide |
| **Sonnet 4.6** | Letzter Fallback | Stabil, erprobt |

Routing in `engine/llm_router.py` — automatische Modellwahl nach Aufgabentyp.

## Architektur

```
engine/              ← Die Intelligenz (Code)
  consciousness.py     — Agentic Loop mit Tool-Use
  llm_router.py        — Multi-LLM Router (Gemma/Claude/Kimi)
  intelligence.py      — Semantische Memory, Skill-Tracking, Strategien
  dream.py             — Memory-Konsolidierung (Autodream)
  competence.py        — Kompetenz-Matrix + Selbst-Audit
  evolution.py         — Multi-Ebenen-Evolution, Tool Foundry
  quantum.py           — Failure-Memory, Critic-Agent, Prompt-Mutation
  code_review.py       — Dual Code-Review (Opus + Primary parallel)
  security.py          — Security-Gateway mit Pfad-, AST- und Review-Schichten
  actions.py           — Aktions-Engine (Dateisystem)
  toolchain.py         — Self-Improving Toolchain
  self_modify.py       — Code-Selbstmodifikation mit Rollback
  self_diagnosis.py    — Integrations-Tests (End-to-End)
  web_access.py        — Internet-Zugang (Suche + Page-Reading)
  goal_stack.py        — Multi-Cycle Ziele mit Sub-Goals
  phi.py               — Phi-Engine (Goldener Schnitt als Kernalgorithmus)
  memory_manager.py    — Fibonacci-Gedächtnis (Phi-gewichteter Decay)
  perception.py        — Wahrnehmung (Umgebungs- und Zustands-Scan)
  extensions.py        — Git, pip, Task-Queue, Self-Rating
  communication.py     — Proaktive Kommunikation (Outbox, Journal)
  telegram_bridge.py   — Telegram-Bridge (httpx Bot API)
  config.py            — Zentrale Pfad-Konfiguration

data/                ← Die Persönlichkeit (Daten, .gitignore'd)
  genesis.json         — Name, Geburtsdatum, Kerntriebe
  consciousness/       — State, Beliefs, Skills, Strategien
  memory/              — Erfahrungen + semantischer Index
  journal/             — Tagebuch
  projects/            — Selbstgebaute Projekte
  tools/               — Selbstgebaute wiederverwendbare Tools
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

# 4. API-Keys eintragen
# .env → ANTHROPIC_API_KEY=sk-ant-...
# .env → GOOGLE_AI_API_KEY=...

# 5. Starten
python run.py              # Autonomer Modus
python interact.py         # Direkte Interaktion
python run.py --once       # Eine Sequenz
```

## Features

- **Dual-LLM-Architektur**: Gemini für Geschwindigkeit, Claude für Tiefe — automatisches Routing
- **Evidence-Based Development**: Tests-First + Evidence-Gate + Cross-Model-Review
- **Agentic Loop**: Durchgehender Tool-Use-Zyklus mit Sliding Window + Token-Budget
- **Semantische Memory**: Findet Erinnerungen nach Bedeutung (TF-IDF + Bigrams)
- **Skill-Tracking**: Fähigkeiten mit Levels, Streaks, Meta-Skills
- **Strategie-Evolution**: Lernt aus Fehlern, erkennt Muster, schreibt eigene Regeln
- **Dream-System**: Periodische Memory-Konsolidierung via Claude Sonnet
- **Self-Audit**: Dual-Review mit Opus + Gemini parallel
- **Quantum-Features**: Failure-Memory, Critic-Agent, Prompt-Mutation
- **Tool Foundry**: Generiert eigene Tools via Claude Sonnet
- **Self-Improving Toolchain**: Baut Tools die permanent verfügbar bleiben
- **Code-Selbstmodifikation**: Liest und verbessert eigenen Quellcode mit Rollback
- **Phi-Engine**: Goldener Schnitt als Kernalgorithmus für Entscheidungen und Gedächtnis
- **Internet-Zugang**: Web-Suche und Page-Reading
- **Telegram-Integration**: Sofort-Antwort, Task-Queue, Befehle
- **Git Auto-Commit**: Arbeit wird automatisch gesichert
- **Kosten-Tracking**: Misst Verbrauch pro Modell, Sliding Window + Token-Budget (300K)

## Telegram-Befehle

| Befehl | Funktion |
|--------|----------|
| Nachricht | Sofort-Antwort |
| `/aufgabe Beschreibung` | Task zur Queue |
| `/tasks` | Offene Aufgaben |
| `/status` | Aktueller Zustand |
| `/think Frage` | Tiefe Analyse |
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
