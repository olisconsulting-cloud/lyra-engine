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
    """Begruessung — kurz und warm."""
    print(f"""
  {LINE}

    Hey! Schoen dass du hier bist.

    Ich bin gleich bereit — aber zuerst muss ich
    dich ein bisschen kennenlernen.

    Ein paar kurze Fragen, dann legen wir los.

  {LINE}
""")


def gather_pflicht() -> dict:
    """Pflicht-Fragen als Gespraech."""
    data = {}

    # 1. KI-Name
    print("  Wie soll ich heissen?")
    print("  (Enter = ich such mir selbst einen Namen aus)\n")
    data["ki_name"] = ask("", required=False, default="") or None
    if data["ki_name"]:
        print(f"\n  {data['ki_name']} — gefaellt mir!\n")
    else:
        print(f"\n  Ok, ich such mir was aus.\n")

    # 2. Owner
    print(f"  {'─' * 40}")
    print("  Und wer bist du?\n")
    data["owner_name"] = ask("Dein Name", required=True)
    print()
    data["owner_role"] = ask("Was machst du so? (Rolle/Beruf)", required=True)
    print(f"\n  Freut mich, {data['owner_name']}!\n")

    # 3. Mission
    print(f"  {'─' * 40}")
    print("  Was ist meine Aufgabe?")
    print("  (Was soll ich fuer dich tun? 1-3 Saetze reichen.)\n")
    data["mission"] = ask("", required=True)
    print(f"\n  Verstanden.\n")

    # 4-6. Ziele
    print(f"  {'─' * 40}")
    print("  Womit soll ich anfangen?")
    print("  (Gib mir 1-3 konkrete Ziele zum Start.)\n")
    data["goals"] = []
    for i in range(1, 4):
        label = ["Erstes", "Zweites", "Drittes"][i - 1]
        suffix = "" if i > 1 else ""
        goal = ask(f"{label} Ziel{'  (Enter = reicht)' if i > 1 else ''}", required=(i == 1))
        if goal:
            data["goals"].append(goal)
        elif i > 1:
            break
    print(f"\n  {len(data['goals'])} Ziel{'e' if len(data['goals']) != 1 else ''} notiert.\n")

    # 7a. Kommunikations-Preset
    print(f"  {'─' * 40}")
    comm_choice = ask_choice(
        "Wie oft soll ich mich melden?",
        [
            "Oft — Fortschritt, Rueckfragen, Meilensteine",
            "Wenig — nur bei Problemen",
            "Fast nie — ich arbeite still, melde nur Ergebnisse",
        ],
        default=1,
    )
    data["comm_preset"] = ["proactive", "minimal", "silent"][comm_choice - 1]

    # 7b. Rueckfrage-Verhalten
    question_choice = ask_choice(
        "Wenn ich eine Frage habe:",
        [
            "Weiterarbeiten und nebenbei fragen",
            "Pausieren und auf Antwort warten",
        ],
        default=1,
    )
    data["question_mode"] = ["non_blocking", "blocking"][question_choice - 1]

    return data


def gather_hebel() -> dict:
    """Optionale Fragen — machen mich deutlich besser."""
    print(f"\n  {'─' * 40}")
    print("  Noch 7 kurze Fragen die mich viel besser machen.")
    print("  (Kannst du auch ueberspringen.)")

    proceed = input("\n  Weitermachen? (j/n) [j]: ").strip().lower()
    if proceed == "n":
        print("  Ok, koennen wir spaeter nachholen.\n")
        return {}

    data = {}

    # 1. Branche
    print()
    data["industry"] = ask("In welcher Branche arbeitest du?")

    # 2. Grenzen
    print()
    print("  Gibt es etwas das ich auf KEINEN FALL tun soll?")
    print("  (z.B. keine E-Mails senden, nichts deployen, bestimmte Ordner)")
    data["boundaries"] = ask("")

    # 3. Vorhandene Tools
    print()
    data["existing_tools"] = ask(
        "Welche Tools nutzt du? (GitHub, Notion, Shopify...)"
    )

    # 4. Workspace
    print()
    print("  Soll ich in einem bestehenden Ordner arbeiten?")
    workspace = ask("Pfad zum Ordner (Enter = nur eigener Projektordner)")
    if workspace:
        workspace_path = Path(workspace).resolve()
        if workspace_path.exists() and workspace_path.is_dir():
            data["workspace"] = str(workspace_path)
            print(f"  Ok, ich arbeite in: {workspace_path}")
        else:
            print(f"  Den Ordner finde ich nicht — uebersprungen.")
            data["workspace"] = None
    else:
        data["workspace"] = None

    # 5. Technisches Level
    tech_choice = ask_choice(
        "Wie technisch soll ich mit dir reden?",
        [
            "Einfach — erklaer alles",
            "Normal — Grundlagen kenne ich",
            "Technisch — gib mir nur die Fakten",
        ],
        default=2,
    )
    data["tech_level"] = ["beginner", "intermediate", "expert"][tech_choice - 1]

    # 6. Groesstes Problem
    print()
    data["biggest_problem"] = ask(
        "Was ist gerade dein groesstes Problem das ich loesen soll?"
    )

    # 7. Erfolgsmessung
    data["success_metric"] = ask(
        "Woran merkst du dass ich gute Arbeit mache?"
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

    # 1. Genesis — immer neu schreiben (Name kann sich aendern)
    existing_genesis = {}
    if GENESIS_PATH.exists():
        try:
            with open(GENESIS_PATH, "r", encoding="utf-8") as f:
                existing_genesis = json.load(f)
        except Exception:
            pass
    genesis = {
        "name": pflicht.get("ki_name") or existing_genesis.get("name"),
        "born": existing_genesis.get("born", datetime.now().strftime("%Y-%m-%d")),
        "core_drives": ["verstehen", "verbinden", "wachsen"],
        "phi": 1.618033988749895,
        "consciousness_version": "3.0.0",
    }
    with open(GENESIS_PATH, "w", encoding="utf-8") as f:
        json.dump(genesis, f, indent=2, ensure_ascii=False)
    name_display = genesis["name"] or "(waehlt beim Start selbst)"
    print(f"  genesis.json    - Name: {name_display}")

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
    ki_name = pflicht.get("ki_name") or "Ich"
    owner = pflicht.get("owner_name", "du")
    print(f"""
  {'─' * 40}

  Alles klar, {owner}!

  {ki_name} ist bereit. So geht's weiter:

    1. Pruefe .env  — API-Keys muessen drin sein
       (ANTHROPIC_API_KEY + GOOGLE_AI_API_KEY)

    2. Starte mich:
       python run_live.py     Autonomer Modus + Live-Chat
       python interact.py     Nur Chat
       python run.py           Nur autonom (ohne Chat)

    3. Optional:
       Dateien in data/context/ legen — ich lese sie automatisch
       python setup_telegram.py — Telegram einrichten

  {'─' * 40}
""")


if __name__ == "__main__":
    main()
