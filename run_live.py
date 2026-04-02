"""
Live-Modus — Phi autonom beobachten und jederzeit eingreifen.

Phi arbeitet autonom im Hintergrund.
Du siehst alles was sie denkt und tut.
Tippe eine Nachricht um einzugreifen.

Nutzung:
    python run_live.py
"""

import os
import sys
import threading
import msvcrt

from dotenv import load_dotenv

if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from engine.consciousness import ConsciousnessEngine


def read_line_windows() -> str:
    """Liest eine Zeile von stdin auf Windows ohne zu blockieren."""
    chars = []
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\r":  # Enter
                print()  # Neue Zeile
                return "".join(chars)
            elif ch == "\x08":  # Backspace
                if chars:
                    chars.pop()
                    # Zeichen visuell loeschen
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            else:
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
        else:
            import time
            time.sleep(0.05)  # CPU schonen


def input_listener(engine):
    """Lauscht auf Eingaben von Oliver und injiziert sie als Nachrichten."""
    name = engine.genesis.get("name", "Phi")
    while engine.running:
        try:
            msg = read_line_windows()
            if not msg.strip():
                continue

            if msg.strip().lower() in ("exit", "quit", "stop"):
                print(f"\n  Stopp-Signal gesendet...")
                engine.running = False
                engine.wake_up()
                break

            # Nachricht in Inbox schreiben
            from datetime import datetime, timezone
            from engine.config import safe_json_write
            ts = datetime.now(timezone.utc)
            msg_data = {
                "from": "Oliver",
                "content": msg.strip(),
                "timestamp": ts.isoformat(),
                "read": False,
                "source": "live_console",
            }
            inbox_path = engine.communication.inbox_path
            filename = f"{ts.strftime('%Y%m%d_%H%M%S')}.json"
            safe_json_write(inbox_path / filename, msg_data)

            print(f"\n  >> Nachricht an {name}: {msg.strip()}")
            print(f"  >> {name} liest sie in der naechsten Sequenz.\n")

            engine.wake_up()

        except KeyboardInterrupt:
            engine.running = False
            engine.wake_up()
            break
        except Exception:
            break


def main():
    engine = ConsciousnessEngine()

    # Setup pruefen
    if not engine.is_born():
        print("\n  Noch nicht eingerichtet.")
        print("  Starte zuerst: python setup.py\n")
        return

    engine.load_state()
    name = engine.genesis.get("name", "Phi")

    # Telegram starten
    if engine.communication.telegram_active:
        def on_telegram_message(msg):
            engine.wake_up()
            threading.Thread(
                target=engine._instant_reply,
                args=(msg,),
                daemon=True,
            ).start()
        engine.communication.telegram.start_polling(on_message=on_telegram_message)

    print(f"\n{'=' * 50}")
    print(f"  {name} — Live-Modus")
    print(f"  Telegram: {'aktiv' if engine.communication.telegram_active else 'aus'}")
    print(f"{'=' * 50}")
    print(f"  Tippe eine Nachricht + Enter um einzugreifen.")
    print(f"  'stop' oder Ctrl+C zum Beenden.")
    print(f"{'=' * 50}\n")

    # Input-Thread starten (Windows-kompatibel)
    listener = threading.Thread(target=input_listener, args=(engine,), daemon=True)
    listener.start()

    # Autonomen Modus starten
    try:
        engine.run()
    finally:
        engine.communication.stop_telegram_listener()


if __name__ == "__main__":
    main()
