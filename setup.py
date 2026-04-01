"""
Setup — Neue Lyra-Instanz initialisieren.

Erstellt:
- data/ Verzeichnisstruktur
- data/genesis.json (Kern-Identitaet)
- .env Template

Nutzung:
    python setup.py                    # Interaktiver Modus
    python setup.py --name "Lyra"      # Mit Name
    python setup.py --reset            # Daten zuruecksetzen (Engine bleibt)
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Engine-Config importieren
sys.path.insert(0, str(Path(__file__).parent))
from engine.config import DATA_PATH, GENESIS_PATH, ENV_PATH, ROOT_PATH, ensure_data_dirs


def main():
    print("\n" + "=" * 55)
    print("  Lyra Setup — Neue Instanz initialisieren")
    print("=" * 55)

    # Reset-Modus
    if "--reset" in sys.argv:
        if DATA_PATH.exists():
            confirm = input(f"\n  WARNUNG: Alle Daten in data/ werden geloescht!\n  Fortfahren? (ja/nein): ")
            if confirm.strip().lower() != "ja":
                print("  Abgebrochen.\n")
                return
            shutil.rmtree(DATA_PATH)
            print("  Daten geloescht.")
        else:
            print("  Kein data/ Verzeichnis vorhanden.")

    # Verzeichnisse erstellen
    print("\n  Erstelle Verzeichnisstruktur...")
    ensure_data_dirs()

    # Genesis
    if not GENESIS_PATH.exists():
        # Name
        name = None
        for i, arg in enumerate(sys.argv):
            if arg == "--name" and i + 1 < len(sys.argv):
                name = sys.argv[i + 1]

        if not name:
            name = input("\n  Name fuer die KI (leer = selbst waehlen): ").strip() or None

        genesis = {
            "name": name,
            "born": datetime.now().strftime("%Y-%m-%d"),
            "core_drives": ["verstehen", "verbinden", "wachsen"],
            "phi": 1.618033988749895,
            "consciousness_version": "2.0.0",
        }

        with open(GENESIS_PATH, "w", encoding="utf-8") as f:
            json.dump(genesis, f, indent=2, ensure_ascii=False)

        print(f"  Genesis erstellt: {GENESIS_PATH}")
        if name:
            print(f"  Name: {name}")
        else:
            print(f"  Name: (wird beim ersten Start selbst gewaehlt)")
    else:
        print(f"  Genesis existiert bereits.")

    # .env Template
    if not ENV_PATH.exists():
        env_template = (
            "# Anthropic API Key (erforderlich)\n"
            "ANTHROPIC_API_KEY=sk-ant-...\n"
            "\n"
            "# Telegram Bot (optional — python setup_telegram.py)\n"
            "# TELEGRAM_BOT_TOKEN=\n"
            "# TELEGRAM_CHAT_ID=\n"
        )
        ENV_PATH.write_text(env_template, encoding="utf-8")
        print(f"  .env Template erstellt — API-Key eintragen!")
    else:
        print(f"  .env existiert bereits.")

    # Zusammenfassung
    print(f"\n  {'=' * 50}")
    print(f"  Setup abgeschlossen!")
    print(f"\n  Struktur:")
    print(f"    engine/    — Code (GitHub)")
    print(f"    data/      — Daten (persoenlich)")
    print(f"    .env       — Secrets")
    print(f"\n  Naechste Schritte:")
    print(f"    1. API-Key in .env eintragen")
    print(f"    2. python run.py")
    print(f"    3. Optional: python setup_telegram.py")
    print(f"  {'=' * 50}\n")


if __name__ == "__main__":
    main()
