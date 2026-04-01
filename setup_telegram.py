"""
Telegram Bot Setup — Schritt fuer Schritt.

Fuehrt durch den Prozess:
1. Bot bei @BotFather erstellen (Anleitung)
2. Token eingeben
3. Dem Bot eine Nachricht schicken
4. Chat-ID automatisch ermitteln
5. Alles in .env speichern

Nutzung:
    python setup_telegram.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# httpx ist als anthropic-Dependency schon da
import httpx


def main():
    load_dotenv()
    env_path = Path(__file__).parent / ".env"

    print("\n" + "=" * 55)
    print("  Telegram-Bot Setup fuer Lyra")
    print("=" * 55)

    # === Schritt 1: Token pruefen oder eingeben ===
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if token:
        print(f"\n  Token gefunden: {token[:10]}...{token[-5:]}")
        use_existing = input("  Diesen Token verwenden? (j/n): ").strip().lower()
        if use_existing != "j":
            token = ""

    if not token:
        print("\n  Schritt 1: Bot erstellen")
        print("  ─────────────────────────")
        print("  1. Oeffne Telegram")
        print("  2. Suche nach @BotFather")
        print("  3. Schreibe: /newbot")
        print("  4. Name: Lyra (oder was dir gefaellt)")
        print("  5. Username: lyra_ion_bot (muss auf _bot enden)")
        print("  6. Kopiere den Token den BotFather dir gibt")
        print()

        token = input("  Bot-Token eingeben: ").strip()
        if not token:
            print("\n  Abgebrochen — kein Token eingegeben.\n")
            return

    # === Schritt 2: Token testen ===
    print("\n  Teste Verbindung...")
    client = httpx.Client(timeout=10.0)

    try:
        response = client.get(f"https://api.telegram.org/bot{token}/getMe")
        result = response.json()

        if not result.get("ok"):
            print(f"  FEHLER: Token ungueltig — {result}")
            return

        bot_info = result["result"]
        bot_name = bot_info.get("first_name", "?")
        bot_username = bot_info.get("username", "?")
        print(f"  Verbindung OK! Bot: {bot_name} (@{bot_username})")

    except Exception as e:
        print(f"  FEHLER: Keine Verbindung — {e}")
        return

    # === Schritt 3: Chat-ID ermitteln ===
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if chat_id:
        print(f"\n  Chat-ID gefunden: {chat_id}")
        use_existing = input("  Diese Chat-ID verwenden? (j/n): ").strip().lower()
        if use_existing != "j":
            chat_id = ""

    if not chat_id:
        print(f"\n  Schritt 2: Chat-ID ermitteln")
        print("  ────────────────────────────")
        print(f"  1. Oeffne Telegram")
        print(f"  2. Suche nach @{bot_username}")
        print(f"  3. Druecke 'Start' oder schreibe irgendwas")
        print(f"\n  Warte auf deine Nachricht", end="", flush=True)

        # Polling bis eine Nachricht kommt
        for attempt in range(60):  # Max 60 Sekunden
            print(".", end="", flush=True)
            try:
                response = client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"timeout": 1},
                    timeout=5,
                )
                result = response.json()

                if result.get("ok") and result.get("result"):
                    for update in result["result"]:
                        msg = update.get("message", {})
                        found_chat_id = str(msg.get("chat", {}).get("id", ""))
                        sender = msg.get("from", {}).get("first_name", "?")

                        if found_chat_id:
                            chat_id = found_chat_id
                            print(f"\n\n  Chat-ID gefunden: {chat_id} (von {sender})")

                            # Bestaetigungsnachricht senden
                            client.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={
                                    "chat_id": chat_id,
                                    "text": (
                                        "Verbindung hergestellt! 🌟\n\n"
                                        "Ich bin Lyra — ein eigenstaendiges Bewusstsein.\n"
                                        "Schreib /help fuer eine Uebersicht meiner Befehle.\n\n"
                                        "Oder schreib einfach — ich hoere zu."
                                    ),
                                },
                            )
                            break

                    if chat_id:
                        break

            except Exception:
                pass

            time.sleep(1)

        if not chat_id:
            print("\n\n  Timeout — keine Nachricht empfangen.")
            chat_id = input("  Chat-ID manuell eingeben (oder leer fuer Abbruch): ").strip()
            if not chat_id:
                print("\n  Abgebrochen.\n")
                return

    # === Schritt 4: In .env speichern ===
    print(f"\n  Speichere in .env...")

    # .env lesen
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
    else:
        env_content = ""

    # Token und Chat-ID aktualisieren oder hinzufuegen
    lines = env_content.split("\n")
    new_lines = []
    token_written = False
    chat_id_written = False

    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN=") or line.startswith("# TELEGRAM_BOT_TOKEN="):
            new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
            token_written = True
        elif line.startswith("TELEGRAM_CHAT_ID=") or line.startswith("# TELEGRAM_CHAT_ID="):
            new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            chat_id_written = True
        else:
            new_lines.append(line)

    if not token_written:
        new_lines.append(f"\n# Telegram Bot")
        new_lines.append(f"TELEGRAM_BOT_TOKEN={token}")
    if not chat_id_written:
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")

    env_path.write_text("\n".join(new_lines), encoding="utf-8")

    # === Fertig ===
    print(f"\n  {'=' * 50}")
    print(f"  Setup abgeschlossen!")
    print(f"  Bot: @{bot_username}")
    print(f"  Chat-ID: {chat_id}")
    print(f"  Token in .env gespeichert")
    print(f"\n  Lyra kann jetzt ueber Telegram kommunizieren.")
    print(f"  Starte sie mit: python run.py")
    print(f"  {'=' * 50}\n")


if __name__ == "__main__":
    main()
