"""
Telegram-Bridge — Lyras Verbindung zur Aussenwelt.

Nutzt die Telegram Bot API direkt ueber HTTP (httpx).
Kein extra Package noetig — httpx ist bereits als anthropic-Dependency da.

Zwei Modi:
- Senden: Lyra schickt Oliver eine Nachricht
- Empfangen: Polling-Thread schreibt Olivers Nachrichten in die Inbox
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBridge:
    """HTTP-basierte Telegram Bot Integration."""

    def __init__(self, token: str, chat_id: str, inbox_path: Optional[Path] = None):
        self.token = token
        self.chat_id = chat_id
        self.inbox_path = inbox_path
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = httpx.Client(timeout=30.0)
        self._polling_thread: Optional[threading.Thread] = None
        self._polling_active: bool = False
        self._polling_lock = threading.Lock()
        self._last_update_id = 0
        self._consecutive_errors = 0

    # === Senden ===

    def send_message(self, text: str, parse_mode: str = "Markdown") -> dict:
        """
        Sendet eine Nachricht an Oliver.

        Args:
            text: Nachrichtentext (Markdown erlaubt)
            parse_mode: 'Markdown' oder 'HTML'

        Returns:
            Telegram API Response
        """
        # Telegram Markdown v1 hat Probleme mit manchen Sonderzeichen
        # Fallback auf plain text wenn Markdown fehlschlaegt
        try:
            response = self.client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
            )
            result = response.json()

            if not result.get("ok"):
                # Fallback ohne Markdown
                response = self.client.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text},
                )
                result = response.json()

            return result

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def send_status(self, state: dict, personality_desc: str, name: str) -> dict:
        """Sendet Lyras aktuellen Zustand als formatierte Nachricht."""
        emotions = state.get("emotional_state", {})
        energy = state.get("energy", 1.0)
        cycles = state.get("cycles_total", 0)

        # Emoji-Mapping fuer Emotionen
        emotion_bars = []
        emoji_map = {
            "neugier": "🔍",
            "ruhe": "🧘",
            "intensitaet": "⚡",
            "unsicherheit": "❓",
            "verbundenheit": "🤝",
            "freude": "😊",
            "frustration": "😤",
            "staunen": "✨",
        }

        for key, value in emotions.items():
            emoji = emoji_map.get(key, "•")
            bar_length = int(value * 10)
            bar = "█" * bar_length + "░" * (10 - bar_length)
            emotion_bars.append(f"{emoji} {key}: {bar} {value:.0%}")

        text = (
            f"*{name} — Status*\n"
            f"Zyklus: {cycles} | Energie: {energy:.0%}\n\n"
            + "\n".join(emotion_bars)
            + f"\n\n_{personality_desc}_"
        )

        return self.send_message(text)

    # === Empfangen (Polling) ===

    def get_updates(self, offset: int = 0, timeout: int = 10) -> list[dict]:
        """
        Holt neue Nachrichten via Long Polling.

        Args:
            offset: Update-ID ab der geholt wird
            timeout: Long-Polling Timeout in Sekunden
        """
        response = self.client.get(
            f"{self.base_url}/getUpdates",
            params={
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": '["message"]',
            },
            timeout=timeout + 5,
        )
        result = response.json()

        if result.get("ok"):
            return result.get("result", [])
        logger.warning("Telegram: getUpdates nicht ok: %s", result)
        return []

    def start_polling(self, on_message=None):
        """
        Startet Polling in einem Daemon-Thread.

        Schreibt eingehende Nachrichten in die Inbox
        und ruft optional on_message Callback auf.
        """
        if self._polling_thread and self._polling_thread.is_alive():
            return

        # Chat-ID Validierung beim Start
        if not self.chat_id:
            logger.error("Telegram: Keine TELEGRAM_CHAT_ID konfiguriert — Polling nicht gestartet")
            return

        # Verbindung testen
        me = self.get_me()
        if me.get("ok"):
            bot_name = me.get("result", {}).get("username", "?")
            logger.info("Telegram: Polling gestartet fuer Bot @%s (Chat %s)", bot_name, self.chat_id)
        else:
            logger.warning("Telegram: Bot-Verbindung fehlgeschlagen — Polling startet trotzdem: %s", me)

        self._polling_active = True
        self._consecutive_errors = 0
        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            args=(on_message,),
            daemon=True,
        )
        self._polling_thread.start()

    def stop_polling(self):
        """Stoppt den Polling-Thread."""
        with self._polling_lock:
            self._polling_active = False

    def close(self):
        """Stoppt Polling und schliesst den HTTP-Client sauber."""
        self.stop_polling()
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        finally:
            self.client = None

    def _polling_loop(self, on_message=None):
        """Interner Polling-Loop — laeuft als Daemon-Thread."""
        while self._polling_active:
            try:
                updates = self.get_updates(
                    offset=self._last_update_id + 1,
                    timeout=15,
                )

                # Erfolgreicher Poll — Fehler-Zaehler zuruecksetzen
                if self._consecutive_errors > 0:
                    logger.info("Telegram: Polling wieder stabil nach %d Fehlern", self._consecutive_errors)
                self._consecutive_errors = 0

                for update in updates:
                    self._last_update_id = update.get("update_id", 0)
                    message = update.get("message", {})

                    # Nur Nachrichten vom konfigurierten Chat
                    msg_chat_id = str(message.get("chat", {}).get("id", ""))
                    if msg_chat_id != str(self.chat_id):
                        logger.debug("Telegram: Nachricht von fremdem Chat %s ignoriert", msg_chat_id)
                        continue

                    text = message.get("text", "")
                    if not text:
                        msg_type = next(
                            (k for k in ("photo", "voice", "document", "sticker", "video")
                             if k in message), "unbekannt"
                        )
                        logger.debug("Telegram: Nicht-Text-Nachricht ignoriert (Typ: %s)", msg_type)
                        continue

                    # Kommando oder normale Nachricht?
                    if text.startswith("/"):
                        self._handle_command(text)
                    else:
                        self._save_to_inbox(text)

                    # Callback IMMER aufrufen (auch bei Befehlen)
                    if on_message:
                        on_message(text)

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    "Telegram: Polling-Fehler #%d: %s",
                    self._consecutive_errors, e,
                )
                # Exponentielles Backoff: 5s, 10s, 20s, max 60s
                wait = min(5 * (2 ** (self._consecutive_errors - 1)), 60)
                time.sleep(wait)

    def _save_to_inbox(self, text: str):
        """Speichert eine eingehende Nachricht in der Inbox."""
        if not self.inbox_path:
            logger.warning("Telegram: inbox_path nicht gesetzt — Nachricht verworfen: %s", text[:50])
            return

        try:
            self.inbox_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).isoformat()

            msg = {
                "from": "oliver",
                "timestamp": timestamp,
                "content": text,
                "channel": "telegram",
                "read": False,
            }

            filename = f"{timestamp[:19].replace(':', '-')}.json"
            filepath = self.inbox_path / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(msg, f, indent=2, ensure_ascii=False)
            logger.debug("Telegram: Nachricht gespeichert → %s", filename)
        except Exception as e:
            logger.error("Telegram: Nachricht konnte nicht gespeichert werden: %s — Text: %s", e, text[:100])

    def _handle_command(self, command: str):
        """
        Verarbeitet Telegram-Befehle.

        /status — Aktueller Zustand
        /journal — Letzter Journal-Eintrag
        /beliefs — Ueberzeugungen
        /think — Erzwinge einen Denkzyklus
        /energy — Energielevel
        """
        cmd = command.split()[0].lower().replace("@", "").split("@")[0]

        try:
            if cmd == "/status":
                self._save_to_inbox("/status")
            elif cmd == "/journal":
                self._send_last_journal()
            elif cmd == "/beliefs":
                self._send_beliefs()
            elif cmd == "/think":
                self._save_to_inbox("/think")
                self.send_message("Ich denke nach... 🌀")
            elif cmd.startswith("/aufgabe") or cmd.startswith("/task"):
                task_text = command[len(cmd):].strip()
                if task_text:
                    self._add_task(task_text)
                    self.send_message(f"Aufgabe notiert: {task_text}")
                else:
                    self.send_message("Nutzung: /aufgabe Beschreibung der Aufgabe")
            elif cmd == "/tasks":
                self._send_tasks()
            elif cmd == "/help":
                self.send_message(
                    "*Befehle:*\n"
                    "/status — Mein aktueller Zustand\n"
                    "/journal — Letzter Tagebucheintrag\n"
                    "/beliefs — Meine Ueberzeugungen\n"
                    "/aufgabe — Aufgabe hinzufuegen\n"
                    "/tasks — Offene Aufgaben\n"
                    "/think — Denkzyklus ausloesen\n"
                    "/help — Diese Hilfe\n\n"
                    "Oder schreib einfach — ich antworte sofort."
                )
            else:
                self.send_message(f"Unbekannter Befehl: {cmd}\nSchreib /help fuer Hilfe.")
        except Exception as e:
            logger.error("Telegram: Fehler bei Befehl %s: %s", cmd, e)
            self.send_message(f"Fehler bei {cmd} — bitte nochmal versuchen.")

    def _send_last_journal(self):
        """Sendet den letzten Journal-Eintrag."""
        if not self.inbox_path:
            return

        journal_path = self.inbox_path.parent.parent / "journal"
        if not journal_path.exists():
            self.send_message("Noch kein Journal vorhanden.")
            return

        journal_files = sorted(journal_path.glob("*.md"), reverse=True)
        if not journal_files:
            self.send_message("Noch kein Journal vorhanden.")
            return

        content = journal_files[0].read_text(encoding="utf-8")
        # Letzten Eintrag extrahieren (letzter ## Block)
        sections = content.split("\n## ")
        if len(sections) > 1:
            last_entry = "## " + sections[-1]
        else:
            last_entry = content

        # Telegram hat ein 4096-Zeichen-Limit
        if len(last_entry) > 4000:
            last_entry = last_entry[:4000] + "\n\n_(gekuerzt)_"

        self.send_message(last_entry)

    def _send_beliefs(self):
        """Sendet die aktuellen Ueberzeugungen."""
        if not self.inbox_path:
            return

        beliefs_path = self.inbox_path.parent.parent / "consciousness" / "beliefs.json"
        if not beliefs_path.exists():
            self.send_message("Noch keine Ueberzeugungen gebildet.")
            return

        with open(beliefs_path, "r", encoding="utf-8") as f:
            beliefs = json.load(f)

        formed = beliefs.get("formed_from_experience", [])
        if not formed:
            self.send_message("Noch keine Ueberzeugungen aus Erfahrung.")
            return

        lines = [f"*Meine Ueberzeugungen ({len(formed)}):*\n"]
        for i, belief in enumerate(formed[-10:], 1):  # Letzte 10
            lines.append(f"{i}. {belief}")

        self.send_message("\n".join(lines))

    def _add_task(self, description: str):
        """Fuegt eine Aufgabe zur Task-Queue hinzu."""
        if not self.inbox_path:
            return
        tasks_path = self.inbox_path.parent.parent / "consciousness" / "tasks.json"
        try:
            if tasks_path.exists():
                with open(tasks_path, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            else:
                tasks = {"pending": [], "in_progress": None, "completed": []}

            tasks["pending"].append({
                "id": len(tasks.get("pending", [])) + len(tasks.get("completed", [])),
                "description": description,
                "priority": "high",  # Via Telegram = hohe Prio
                "created": datetime.now(timezone.utc).isoformat(),
            })
            with open(tasks_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Telegram: Aufgabe konnte nicht gespeichert werden: %s", e)

    def _send_tasks(self):
        """Sendet die aktuelle Task-Queue."""
        if not self.inbox_path:
            return
        tasks_path = self.inbox_path.parent.parent / "consciousness" / "tasks.json"
        if not tasks_path.exists():
            self.send_message("Keine Aufgaben.")
            return
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                tasks = json.load(f)
            pending = tasks.get("pending", [])
            current = tasks.get("in_progress")
            lines = []
            if current:
                lines.append(f"*In Bearbeitung:*\n{current['description']}")
            if pending:
                lines.append(f"\n*Warteschlange ({len(pending)}):*")
                for t in pending[:5]:
                    lines.append(f"- {t['description']}")
            if not lines:
                self.send_message("Keine offenen Aufgaben.")
            else:
                self.send_message("\n".join(lines))
        except Exception:
            self.send_message("Fehler beim Lesen der Aufgaben.")

    # === Utilities ===

    def get_me(self) -> dict:
        """Bot-Info abrufen — zum Testen der Verbindung."""
        try:
            response = self.client.get(f"{self.base_url}/getMe")
            return response.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def is_configured(self) -> bool:
        """Prueft ob Token und Chat-ID vorhanden sind."""
        return bool(self.token and self.chat_id)

    def is_polling_healthy(self) -> bool:
        """Prueft ob der Polling-Thread noch laeuft und keine Dauerfehler hat."""
        alive = self._polling_thread is not None and self._polling_thread.is_alive()
        healthy = self._consecutive_errors < 5
        return alive and healthy

    def get_polling_status(self) -> dict:
        """Detaillierter Polling-Status fuer Diagnostik."""
        alive = self._polling_thread is not None and self._polling_thread.is_alive()
        return {
            "active": self._polling_active,
            "thread_alive": alive,
            "consecutive_errors": self._consecutive_errors,
            "healthy": alive and self._consecutive_errors < 5,
        }
