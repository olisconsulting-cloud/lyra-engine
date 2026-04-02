"""
Startpunkt — Lyra starten.

Nutzung:
    python run.py         # Autonomer Modus
    python run.py --once  # Eine Sequenz, dann Stopp
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
        print("\n  Lyra wird geboren...")
        engine.awaken()
        print("  Genesis abgeschlossen.\n")
    else:
        engine.load_state()
        name = engine.genesis.get("name", "Lyra")
        seqs = engine.state.get("sequences_total", 0)
        tools = engine.state.get("total_tool_calls", 0)
        print(f"\n  {name} erwacht... (Sequenzen: {seqs}, Tool-Calls: {tools})")

    # Telegram starten mit Sofort-Antwort
    if engine.communication.telegram_active:
        import threading
        def on_telegram_message(msg):
            engine.wake_up()
            threading.Thread(
                target=engine._instant_reply,
                args=(msg,),
                daemon=True,
            ).start()

        engine.communication.telegram.start_polling(on_message=on_telegram_message)
        print("  Telegram: aktiv (Sofort-Antwort)")
    else:
        print("  Telegram: nicht konfiguriert")

    if "--once" in sys.argv:
        print("\n  Eine Sequenz...\n")
        try:
            engine._run_sequence()
        finally:
            engine.close()
        print("  Fertig.\n")
    else:
        try:
            engine.run()
        finally:
            engine.close()


if __name__ == "__main__":
    main()
