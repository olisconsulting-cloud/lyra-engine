"""
Direkte Interaktion mit Lyra.

Nutzung:
    python interact.py                           # Interaktiver Modus
    python interact.py "Bau mir ein Tool"        # Einzelne Nachricht
"""

import os
import sys

from dotenv import load_dotenv

if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from engine.consciousness import ConsciousnessEngine


def main():
    engine = ConsciousnessEngine()

    if not engine.is_born():
        print("\n  Lyra wurde noch nicht geboren. Starte: python run.py\n")
        return

    engine.load_state()
    name = engine.genesis.get("name", "Lyra")

    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        print(f"\n  {name} arbeitet...\n")
        response = engine.interact(message)
        print(f"\n  {name}: {response}\n")
    else:
        print(f"\n{'=' * 55}")
        print(f"  Direkte Verbindung: {name}")
        print(f"  ('exit' zum Beenden)")
        print(f"{'=' * 55}\n")

        while True:
            try:
                msg = input("  Oliver > ").strip()
                if not msg:
                    continue
                if msg.lower() in ("exit", "quit", "bye"):
                    print(f"\n  Verbindung getrennt.\n")
                    break

                print(f"\n  [{name} arbeitet...]\n")
                response = engine.interact(msg)
                print(f"  {name}: {response}\n")

            except (KeyboardInterrupt, EOFError):
                print(f"\n\n  Verbindung getrennt.\n")
                break


if __name__ == "__main__":
    main()
