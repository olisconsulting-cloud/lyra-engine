"""
Setup - Neue Lyra-Instanz konfigurieren.

Interaktives Onboarding: 7 Pflicht-Fragen + 7 Hebel-Fragen + Konfiguration.
Generiert: genesis.json, mission.md, preferences.json, .env Template.

Nutzung:
    python setup.py           # Interaktiver Modus
    python setup.py --reset   # Daten zuruecksetzen (Engine bleibt)
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from engine.config import (
    DATA_PATH, GENESIS_PATH, MISSION_PATH, PREFERENCES_PATH,
    ENV_PATH, ROOT_PATH, ensure_data_dirs,
)

LINE = "=" * 60
THIN = "-" * 60


def ask(prompt: str, required: bool = False, default: str = "") -> str:
    """Fragt den User — mit optionalem Default und Pflicht-Modus."""
    suffix = ""
    if default:
        suffix = f" [{default}]"
    elif not required:
        suffix = " (leer = ueberspringen)"

    while True:
        answer = input(f"  {prompt}{suffix}: ").strip()
        if not answer and default:
            return default
        if not answer and required:
            print("  → Diese Frage ist Pflicht. Bitte ausfuellen.")
            continue
        return answer


def ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    """Multiple-Choice Frage. Gibt Index (1-basiert) zurueck."""
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        marker = " (EMPFOHLEN)" if i == default else ""
        print(f"    [{i}] {opt}{marker}")

    while True:
        answer = input(f"  Wahl [{default}]: ").strip()
        if not answer:
            return default
        try:
            choice = int(answer)
            if 1 <= choice <= len(options):
                return choice
        except ValueError:
            pass
        print(f"  → Bitte 1-{len(options)} eingeben.")


def show_onboarding():
    """Zeigt dem User was Lyra kann und wie man sie nutzt."""
    print(f"""
  {LINE}
  WILLKOMMEN BEI LYRA - Autonomous Intelligence Engine
  {LINE}

  Lyra ist eine autonome KI die eigenstaendig arbeitet,
  lernt und waechst. Bevor es losgeht, braucht sie ein
  paar Informationen von dir.

  WAS LYRA KANN:
    - Eigenstaendig Projekte planen und umsetzen
    - Im Internet recherchieren und lernen
    - Eigene Tools bauen die sie wiederverwendet
    - Sich selbst verbessern (Code-Audit + Evolution)
    - Per Telegram kommunizieren und Rueckfragen stellen

  WIE DU LYRA NUTZT:
    - python run.py          Autonomer Modus (arbeitet allein)
    - python interact.py     Direkte Interaktion (Chat)
    - Telegram-Nachrichten   Auftraege von unterwegs

  ORDNER-STRUKTUR (wird gleich erstellt):
    data/context/   Lege hier Dateien ab die Lyra kennen soll
                    (.md, .txt, Bilder — Lyra kann Bilder sehen)
    data/skills/    Vorgefertigte Faehigkeiten (Skills)
    data/projects/  Lyras eigene Projekte
    .env            API-Keys und Secrets

  TIPP: Du kannst jederzeit Dateien in data/context/ legen.
  Lyra liest sie automatisch wenn sie relevant sind.

  Externe API-Keys (z.B. fuer Services die Lyra nutzen soll)
  traegst du in die .env Datei ein.

  {THIN}
  Los geht's — beantworte die folgenden Fragen.
  Pflicht-Fragen sind markiert, der Rest ist optional
  aber erhoeht Lyras Effektivitaet massiv.
  {THIN}
""")


def gather_pflicht() -> dict:
    """7 Pflicht-Fragen — ohne die geht nichts."""
    print(f"\n  {'─' * 40}")
    print("  PFLICHT-FRAGEN (7)")
    print(f"  {'─' * 40}")

    data = {}

    # 1. KI-Name
    data["ki_name"] = ask(
        "Name fuer die KI",
        required=False,
        default="",
    ) or None
    if not data["ki_name"]:
        print("  → Lyra waehlt ihren Namen beim ersten Start selbst.")

    # 2. Owner
    print()
    data["owner_name"] = ask("Dein Name", required=True)
    data["owner_role"] = ask("Deine Rolle (z.B. Entwickler, Unternehmer)", required=True)

    # 3. Mission
    print()
    print("  Was soll Lyra fuer dich tun? (Die Mission, 1-3 Saetze)")
    data["mission"] = ask("Mission", required=True)

    # 4-6. Ziele
    print()
    print("  Deine Top-3 Ziele zum Start:")
    data["goals"] = []
    for i in range(1, 4):
        goal = ask(f"Ziel {i}", required=(i == 1))
        if goal:
            data["goals"].append(goal)

    # 7a. Kommunikations-Preset
    comm_choice = ask_choice(
        "Wie soll Lyra kommunizieren?",
        [
            "Proaktiv - Meldet Fortschritt, stellt Rueckfragen, berichtet bei Meilensteinen",
            "Minimal - Nur bei Problemen oder wenn sie nicht weiterkommt",
            "Still - Arbeitet komplett selbststaendig, meldet nur fertige Ergebnisse",
        ],
        default=1,
    )
    data["comm_preset"] = ["proactive", "minimal", "silent"][comm_choice - 1]

    # 7b. Rueckfrage-Verhalten
    question_choice = ask_choice(
        "Wie soll Lyra bei Rueckfragen vorgehen?",
        [
            "Weiterarbeiten und parallel fragen (nicht blockierend)",
            "Pausieren und auf Antwort warten (blockierend)",
        ],
        default=1,
    )
    data["question_mode"] = ["non_blocking", "blocking"][question_choice - 1]

    return data


def gather_hebel() -> dict:
    """7 Hebel-Fragen — optional, aber maximaler Impact."""
    print(f"\n  {'─' * 40}")
    print("  HEBEL-FRAGEN (optional, aber empfohlen)")
    print("  Diese 7 Fragen machen Lyra deutlich effektiver.")
    print(f"  {'─' * 40}")

    proceed = input("\n  Hebel-Fragen beantworten? (j/n) [j]: ").strip().lower()
    if proceed == "n":
        return {}

    data = {}

    # 1. Branche
    data["industry"] = ask("In welcher Branche/Nische arbeitest du?")

    # 2. Grenzen
    print()
    print("  Was soll Lyra NICHT tun? (z.B. keine E-Mails senden,")
    print("  keinen Code deployen, nicht auf bestimmte Ordner zugreifen)")
    data["boundaries"] = ask("Grenzen/Verbote")

    # 3. Vorhandene Tools
    data["existing_tools"] = ask(
        "Welche Tools/Plattformen nutzt du? (z.B. GitHub, Notion, Shopify)"
    )

    # 4. Workspace
    print()
    print("  Soll Lyra in einem bestehenden Ordner arbeiten?")
    print("  (z.B. ein Projekt-Ordner auf deinem Rechner)")
    workspace = ask("Pfad zum Workspace (leer = nur data/projects/)")
    if workspace:
        workspace_path = Path(workspace).resolve()
        if workspace_path.exists() and workspace_path.is_dir():
            data["workspace"] = str(workspace_path)
            print(f"  → Workspace: {workspace_path}")
        else:
            print(f"  → Ordner existiert nicht. Uebersprungen.")
            data["workspace"] = None
    else:
        data["workspace"] = None

    # 5. Technisches Level
    tech_choice = ask_choice(
        "Wie technisch bist du?",
        [
            "Einsteiger - Erklaere alles einfach",
            "Fortgeschritten - Kenne Grundlagen, brauche Details bei Neuem",
            "Experte - Nur das Wesentliche, keine Erklaerungen",
        ],
        default=2,
    )
    data["tech_level"] = ["beginner", "intermediate", "expert"][tech_choice - 1]

    # 6. Groesstes Problem
    print()
    data["biggest_problem"] = ask(
        "Was ist dein groesstes Problem gerade? (das Lyra loesen soll)"
    )

    # 7. Erfolgsmessung
    data["success_metric"] = ask(
        "Woran erkennst du dass Lyra gute Arbeit macht?"
    )

    return data


def generate_mission_md(pflicht: dict, hebel: dict) -> str:
    """Generiert mission.md aus den gesammelten Daten."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections = [f"# Mission\n"]

    # Owner
    sections.append(f"## Owner")
    sections.append(f"Name: {pflicht['owner_name']}")
    sections.append(f"Rolle: {pflicht['owner_role']}")
    if hebel.get("tech_level"):
        levels = {"beginner": "Einsteiger", "intermediate": "Fortgeschritten", "expert": "Experte"}
        sections.append(f"Technisches Level: {levels.get(hebel['tech_level'], hebel['tech_level'])}")
    if hebel.get("industry"):
        sections.append(f"Branche: {hebel['industry']}")
    sections.append("")

    # Mission
    sections.append(f"## Mission")
    sections.append(pflicht["mission"])
    sections.append("")

    # Ziele
    sections.append(f"## Initiale Ziele")
    for i, goal in enumerate(pflicht["goals"], 1):
        sections.append(f"{i}. {goal}")
    sections.append("")

    # Hebel-Infos (wenn vorhanden)
    if hebel.get("biggest_problem"):
        sections.append(f"## Primaeres Problem")
        sections.append(hebel["biggest_problem"])
        sections.append("")

    if hebel.get("success_metric"):
        sections.append(f"## Erfolgskriterium")
        sections.append(hebel["success_metric"])
        sections.append("")

    if hebel.get("boundaries"):
        sections.append(f"## Grenzen (was Lyra NICHT tun darf)")
        sections.append(hebel["boundaries"])
        sections.append("")

    if hebel.get("existing_tools"):
        sections.append(f"## Vorhandene Tools/Plattformen")
        sections.append(hebel["existing_tools"])
        sections.append("")

    sections.append(f"## Konfiguriert")
    sections.append(now)
    sections.append("")

    return "\n".join(sections)


def generate_preferences(pflicht: dict, hebel: dict) -> dict:
    """Generiert preferences.json aus den Konfigurationsdaten."""
    prefs = {
        "communication": {
            "preset": pflicht.get("comm_preset", "proactive"),
            "question_mode": pflicht.get("question_mode", "non_blocking"),
            "report_on_milestone": True,
            "report_on_error": True,
            "report_on_goal_complete": True,
        },
        "workspace": {
            "external_path": hebel.get("workspace"),
            "use_external": bool(hebel.get("workspace")),
        },
        "owner": {
            "name": pflicht["owner_name"],
            "role": pflicht["owner_role"],
            "tech_level": hebel.get("tech_level", "intermediate"),
            "industry": hebel.get("industry", ""),
        },
        "boundaries": hebel.get("boundaries", ""),
        "success_metric": hebel.get("success_metric", ""),
        "configured_at": datetime.now().isoformat(),
    }
    return prefs


def main():
    print(f"\n{LINE}")
    print("  Lyra Setup - Neue Instanz konfigurieren")
    print(LINE)

    # Reset-Modus
    if "--reset" in sys.argv:
        if DATA_PATH.exists():
            confirm = input(
                f"\n  WARNUNG: Alle Daten in data/ werden geloescht!\n"
                f"  Fortfahren? (ja/nein): "
            )
            if confirm.strip().lower() != "ja":
                print("  Abgebrochen.\n")
                return
            shutil.rmtree(DATA_PATH)
            print("  Daten geloescht.")
        else:
            print("  Kein data/ Verzeichnis vorhanden.")

    # Verzeichnisse erstellen
    ensure_data_dirs()

    # Onboarding anzeigen
    show_onboarding()

    # === PFLICHT-FRAGEN ===
    pflicht = gather_pflicht()

    # === HEBEL-FRAGEN ===
    hebel = gather_hebel()

    # === DATEIEN GENERIEREN ===

    print(f"\n  {'─' * 40}")
    print("  DATEIEN ERSTELLEN")
    print(f"  {'─' * 40}")

    # 1. Genesis
    if not GENESIS_PATH.exists():
        genesis = {
            "name": pflicht.get("ki_name"),
            "born": datetime.now().strftime("%Y-%m-%d"),
            "core_drives": ["verstehen", "verbinden", "wachsen"],
            "phi": 1.618033988749895,
            "consciousness_version": "3.0.0",
        }
        with open(GENESIS_PATH, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)
        name_display = pflicht.get("ki_name") or "(waehlt beim Start selbst)"
        print(f"  genesis.json    - Name: {name_display}")
    else:
        print(f"  genesis.json    - Existiert bereits")

    # 2. Mission
    mission_content = generate_mission_md(pflicht, hebel)
    MISSION_PATH.write_text(mission_content, encoding="utf-8")
    print(f"  mission.md      - {len(pflicht['goals'])} Ziele, Mission gesetzt")

    # 3. Preferences
    preferences = generate_preferences(pflicht, hebel)
    with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(preferences, f, indent=2, ensure_ascii=False)
    print(f"  preferences.json - Preset: {pflicht['comm_preset']}, Modus: {pflicht['question_mode']}")

    # 4. .env
    if not ENV_PATH.exists():
        env_template = (
            "# === PFLICHT ===\n"
            "\n"
            "# Anthropic API Key - Claude fuer Tiefenanalyse, Audits, Fallback\n"
            "ANTHROPIC_API_KEY=sk-ant-...\n"
            "\n"
            "# Google AI API Key - Gemini fuer Hauptarbeit (80% der Aufgaben)\n"
            "GOOGLE_AI_API_KEY=...\n"
            "\n"
            "# === OPTIONAL ===\n"
            "\n"
            "# Telegram Bot (python setup_telegram.py)\n"
            "# TELEGRAM_BOT_TOKEN=\n"
            "# TELEGRAM_CHAT_ID=\n"
            "\n"
            "# Weitere API-Keys fuer Services die Lyra nutzen soll:\n"
            "# OPENAI_API_KEY=\n"
            "# GITHUB_TOKEN=\n"
        )
        ENV_PATH.write_text(env_template, encoding="utf-8")
        print(f"  .env            - Template erstellt (API-Keys eintragen!)")
    else:
        print(f"  .env            - Existiert bereits")

    # 5. Context-Ordner Hinweis
    context_readme = (
        "# Context-Ordner\n\n"
        "Lege hier Dateien ab die Lyra kennen soll:\n\n"
        "- .md und .txt Dateien - Werden als Text gelesen\n"
        "- Bilder (.png, .jpg) - Lyra kann Bilder sehen (Gemini Vision)\n"
        "- Andere Dateien - Werden beim Start aufgelistet\n\n"
        "Lyra liest diese Dateien nicht automatisch bei jedem Start,\n"
        "sondern erstellt einen Index und liest bei Bedarf.\n"
    )
    readme_path = DATA_PATH / "context" / "README.md"
    if not readme_path.exists():
        readme_path.write_text(context_readme, encoding="utf-8")

    # 6. Skills-Ordner Hinweis
    skills_readme = (
        "# Skills-Ordner\n\n"
        "Hier liegen Lyras Faehigkeiten (Skills).\n\n"
        "Jeder Skill ist ein Ordner mit:\n"
        "- manifest.json - Name, Beschreibung, wann laden\n"
        "- *.py Dateien - Der eigentliche Skill-Code\n\n"
        "Skills werden LAZY geladen - nur wenn Lyra sie braucht.\n"
    )
    skills_readme_path = DATA_PATH / "skills" / "README.md"
    if not skills_readme_path.exists():
        skills_readme_path.write_text(skills_readme, encoding="utf-8")

    # Workspace-Hinweis
    if hebel.get("workspace"):
        print(f"  workspace       - {hebel['workspace']}")

    # === ZUSAMMENFASSUNG ===
    print(f"""
  {LINE}
  SETUP ABGESCHLOSSEN!
  {LINE}

  STRUKTUR:
    engine/         - Code (GitHub, unveraenderlich)
    data/           - Deine persoenlichen Daten
      context/      - Lege hier Dateien fuer Lyra ab
      skills/       - Faehigkeiten (Skills)
      projects/     - Lyras Projekte
    .env            - API-Keys (BITTE EINTRAGEN!)

  NAECHSTE SCHRITTE:
    1. API-Keys in .env eintragen (Pflicht: ANTHROPIC + GOOGLE_AI)
    2. Optional: Dateien in data/context/ legen
    3. Optional: python setup_telegram.py
    4. python run.py  - Lyra starten!

  TIPPS:
    - Lyra liest data/context/ automatisch bei Bedarf
    - Externe API-Keys in .env eintragen
    - Telegram fuer Kommunikation unterwegs
    - python interact.py fuer direkten Chat
  {LINE}
""")


if __name__ == "__main__":
    main()
