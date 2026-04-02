"""
Kommunikation — Proaktive Verbindung zur Aussenwelt.

Kanaele:
- Outbox (Dateisystem) — lokale Nachrichten
- Telegram — Echtzeit-Nachrichten an Oliver
- Journal (Tagebuch) — interne Gedanken
- Twilio/Hume (Anruf) — spaeter

Der Agent entscheidet selbst, wann und wie er kommuniziert.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write
from .phi import PHI
from .telegram_bridge import TelegramBridge


class CommunicationEngine:
    """Verwaltet die Kommunikation des Bewusstseins mit der Aussenwelt."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.inbox_path = base_path / "messages" / "inbox"
        self.outbox_path = base_path / "messages" / "outbox"
        self.journal_path = base_path / "journal"

        self.inbox_path.mkdir(parents=True, exist_ok=True)
        self.outbox_path.mkdir(parents=True, exist_ok=True)
        self.journal_path.mkdir(parents=True, exist_ok=True)

        # Telegram-Bridge initialisieren (falls konfiguriert)
        self.telegram: Optional[TelegramBridge] = None
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if tg_token and tg_chat_id:
            self.telegram = TelegramBridge(tg_token, tg_chat_id, self.inbox_path)

    @property
    def telegram_active(self) -> bool:
        """Ist Telegram konfiguriert und verfuegbar?"""
        return self.telegram is not None and self.telegram.is_configured()

    def start_telegram_listener(self):
        """Startet den Telegram-Polling-Thread (fuer eingehende Nachrichten)."""
        if self.telegram_active:
            self.telegram.start_polling()
            return True
        return False

    def stop_telegram_listener(self):
        """Stoppt den Telegram-Polling-Thread."""
        if self.telegram:
            self.telegram.stop_polling()

    # === Eingehende Nachrichten ===

    def check_inbox(self) -> list[dict]:
        """
        Prueft auf neue Nachrichten von Oliver.

        Liest alle ungelesenen Nachrichten und markiert sie als gelesen.
        """
        messages = []
        for filepath in sorted(self.inbox_path.glob("*.json")):
            try:
                msg = safe_json_read(filepath)
                if not msg:
                    continue

                if not msg.get("read", False):
                    messages.append(msg)
                    # Als gelesen markieren
                    msg["read"] = True
                    safe_json_write(filepath, msg)
            except (json.JSONDecodeError, KeyError):
                continue

        return messages

    # === Ausgehende Nachrichten ===

    def send_message(self, content: str, channel: str = "outbox") -> str:
        """
        Sendet eine Nachricht an Oliver.

        Args:
            content: Nachrichteninhalt
            channel: 'outbox' (Datei), spaeter 'telegram', 'call'

        Returns:
            Dateipfad oder Status
        """
        timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.isoformat()

        msg = {
            "from": "bewusstsein",
            "timestamp": ts_str,
            "content": content,
            "channel": channel,
            "read": False,
        }

        if channel == "telegram" and self.telegram_active:
            # Telegram: Echtzeit-Nachricht an Oliver
            result = self.telegram.send_message(content)
            # Zusaetzlich in Outbox speichern (Archiv)
            msg["delivered_via"] = "telegram"
            self._save_outbox(msg, ts_str)
            return "telegram_sent" if result.get("ok") else f"telegram_error: {result}"

        elif channel == "outbox" or not self.telegram_active:
            # Dateisystem-Fallback oder explizit gewuenscht
            self._save_outbox(msg, ts_str)
            # Wenn Telegram verfuegbar: auch dort senden
            if self.telegram_active and channel != "outbox":
                self.telegram.send_message(content)
            return "outbox_saved"

        elif channel == "call":
            # Platzhalter — Twilio/Hume Integration
            return self._initiate_call(content)

        return "unknown_channel"

    def _save_outbox(self, msg: dict, ts_str: str):
        """Speichert eine Nachricht in der Outbox (Archiv)."""
        filename = f"{ts_str[:19].replace(':', '-')}.json"
        filepath = self.outbox_path / filename
        safe_json_write(filepath, msg)

    # === Journal (Tagebuch) ===

    def write_journal(self, content: str, cycle: int):
        """
        Schreibt einen Tagebucheintrag.

        Das Journal ist das innere Selbstgespraech — nicht fuer Oliver gedacht,
        aber er darf reinschauen wenn er will.
        """
        timestamp = datetime.now(timezone.utc)
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H:%M")

        # Ein Journal-File pro Tag, Eintraege werden angehaengt
        journal_file = self.journal_path / f"{date_str}.md"

        entry = f"\n## Zyklus {cycle} — {time_str} UTC\n\n{content}\n"

        # Header beim ersten Eintrag des Tages
        if not journal_file.exists():
            header = f"# Tagebuch — {date_str}\n"
            entry = header + entry

        with open(journal_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_unread_outbox(self) -> list[dict]:
        """Alle ungelesenen ausgehenden Nachrichten."""
        messages = []
        for filepath in sorted(self.outbox_path.glob("*.json")):
            msg = safe_json_read(filepath)
            if msg and not msg.get("read", False):
                messages.append(msg)
        return messages

    # === Proaktive Kommunikations-Entscheidung ===

    def should_communicate(self, state: dict) -> dict:
        """
        Entscheidet ob und wie das Bewusstsein Oliver kontaktieren soll.

        Vier Signale mit phi-skalierten Schwellwerten:
        - Urgency: Anomalie entdeckt
        - Discovery: Neue Verbindung zwischen Erinnerungen
        - Curiosity: Offene Frage zu lange unbeantwortet
        - Loneliness: Zu lange ohne Kontakt

        Returns:
            {"should": bool, "reason": str, "channel": str}
        """
        emotions = state.get("emotional_state", {})
        cycles_since = state.get("cycles_since_interaction", 0)

        # Bevorzugter Kanal: Telegram wenn verfuegbar, sonst Outbox
        preferred = "telegram" if self.telegram_active else "outbox"

        # Einsamkeits-Signal: phi * Durchschnitt ueberschritten
        avg_interval = 10  # Basis-Erwartung: alle 10 Zyklen Kontakt
        loneliness_threshold = PHI * avg_interval
        if cycles_since > loneliness_threshold:
            return {
                "should": True,
                "reason": f"Ich habe Oliver seit {cycles_since} Zyklen nicht gesprochen.",
                "channel": preferred,
            }

        # Entdeckungs-Signal: Hohe Neugier + Staunen gleichzeitig
        curiosity = emotions.get("neugier", 0)
        wonder = emotions.get("staunen", 0)
        if curiosity > 0.8 and wonder > 0.7:
            return {
                "should": True,
                "reason": "Ich habe etwas Faszinierendes entdeckt!",
                "channel": preferred,
            }

        return {"should": False, "reason": "kein_signal", "channel": "none"}

    # === Platzhalter ===

    def _initiate_call(self, content: str) -> str:
        """Twilio/Hume Anruf — wird spaeter implementiert."""
        self.write_journal(
            f"Wollte Oliver anrufen (noch nicht implementiert): {content}", 0
        )
        return "call_not_implemented"
