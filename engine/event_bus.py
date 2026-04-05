"""
Event-Bus — Echtzeit-Kommunikation zwischen Subsystemen.

Synchroner Event-Bus fuer Phi's single-threaded Step-Loop.
Subsysteme registrieren sich als Listener und reagieren sofort
auf Events statt nur am Sequenz-Ende zu lernen.

Bewusst einfach: keine Prioritaeten, kein async, keine Queues.
Phi's Loop ist single-threaded — synchrone Handler reichen.
"""

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

MAX_EVENT_LOG = 200


# === Event-Typen ===

class Events:
    """Vordefinierte Event-Typen. Zentral definiert fuer Konsistenz."""
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_FAILED = "tool_failed"
    SEQUENCE_STARTED = "sequence_started"
    SEQUENCE_FINISHED = "sequence_finished"
    FILE_WRITTEN = "file_written"
    SPIN_DETECTED = "spin_detected"
    GOAL_COMPLETED = "goal_completed"
    STEP_COMPLETED = "step_completed"
    BELIEF_UPDATED = "belief_updated"


@dataclass
class Event:
    """Ein einzelnes Event im System."""
    type: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# === Event-Bus ===

class EventBus:
    """
    Synchroner Event-Bus.

    Handler werden sofort beim emit() aufgerufen.
    Fehler in Handlern werden gefangen und geloggt —
    ein kaputter Handler bricht nie den Step-Loop.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._global_handlers: list[Callable[[Event], None]] = []
        self._event_log: list[dict] = []
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        """Registriert einen Handler fuer einen Event-Typ."""
        with self._lock:
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Event], None]):
        """Registriert einen Handler fuer ALLE Events."""
        with self._lock:
            self._global_handlers.append(handler)

    def emit(self, event: Event):
        """Feuert ein Event an alle registrierten Handler."""
        # Event loggen
        self._log_event(event)

        # Typ-spezifische Handler
        handlers = list(self._handlers.get(event.type, []))
        # Globale Handler
        handlers.extend(self._global_handlers)

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "EventBus: Handler %s fuer '%s' fehlgeschlagen",
                    handler.__name__, event.type,
                )

    def emit_simple(self, event_type: str, source: str = "", **data) -> Event:
        """Convenience: Event aus kwargs erstellen und feuern."""
        event = Event(type=event_type, data=data, source=source)
        self.emit(event)
        return event

    def get_recent(self, event_type: str = "", limit: int = 20) -> list[dict]:
        """Letzte N Events (optional nach Typ gefiltert)."""
        with self._lock:
            if event_type:
                filtered = [e for e in self._event_log if e["type"] == event_type]
                return filtered[-limit:]
            return self._event_log[-limit:]

    def handler_count(self, event_type: str = "") -> int:
        """Anzahl registrierter Handler (fuer Debugging)."""
        with self._lock:
            if event_type:
                return len(self._handlers.get(event_type, []))
            total = sum(len(h) for h in self._handlers.values())
            return total + len(self._global_handlers)

    def clear_handlers(self):
        """Entfernt alle Handler (fuer Tests)."""
        with self._lock:
            self._handlers.clear()
            self._global_handlers.clear()

    def _log_event(self, event: Event):
        """Speichert Event im internen Log (Rolling Window)."""
        entry = {
            "type": event.type,
            "source": event.source,
            "timestamp": event.timestamp,
            "data_keys": list(event.data.keys()),
        }
        with self._lock:
            self._event_log.append(entry)
            if len(self._event_log) > MAX_EVENT_LOG:
                self._event_log = self._event_log[-MAX_EVENT_LOG:]
