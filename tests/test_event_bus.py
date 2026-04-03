"""Tests fuer engine/event_bus.py — Event-Bus fuer Echtzeit-Kommunikation."""
import pytest
from engine.event_bus import EventBus, Events, Event


class TestEvent:
    """Event-Datenklasse Tests."""

    def test_event_timestamp_auto(self):
        """Timestamp wird automatisch gesetzt."""
        event = Event(type="test")
        assert event.timestamp != ""
        assert "T" in event.timestamp  # ISO-Format

    def test_event_explicit_timestamp(self):
        """Expliziter Timestamp wird beibehalten."""
        event = Event(type="test", timestamp="2026-01-01T00:00:00")
        assert event.timestamp == "2026-01-01T00:00:00"

    def test_event_default_data(self):
        """Data ist leeres Dict wenn nicht angegeben."""
        event = Event(type="test")
        assert event.data == {}

    def test_event_with_data(self):
        """Event mit Daten."""
        event = Event(type="test", data={"tool": "write_file"}, source="test")
        assert event.data["tool"] == "write_file"
        assert event.source == "test"


class TestEvents:
    """Vordefinierte Event-Typen."""

    def test_event_types_are_strings(self):
        """Alle Event-Typen sind Strings."""
        assert isinstance(Events.TOOL_SUCCEEDED, str)
        assert isinstance(Events.TOOL_FAILED, str)
        assert isinstance(Events.SEQUENCE_STARTED, str)
        assert isinstance(Events.SEQUENCE_FINISHED, str)
        assert isinstance(Events.FILE_WRITTEN, str)
        assert isinstance(Events.SPIN_DETECTED, str)
        assert isinstance(Events.GOAL_COMPLETED, str)

    def test_event_types_unique(self):
        """Alle Event-Typen sind einzigartig."""
        types = [
            Events.TOOL_SUCCEEDED, Events.TOOL_FAILED,
            Events.SEQUENCE_STARTED, Events.SEQUENCE_FINISHED,
            Events.FILE_WRITTEN, Events.SPIN_DETECTED,
            Events.GOAL_COMPLETED, Events.STEP_COMPLETED,
            Events.BELIEF_UPDATED,
        ]
        assert len(types) == len(set(types))


class TestEventBus:
    """EventBus Kern-Tests."""

    def test_subscribe_and_emit(self):
        """Handler wird bei passendem Event aufgerufen."""
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(Events.TOOL_SUCCEEDED, handler)
        bus.emit_simple(Events.TOOL_SUCCEEDED, tool="write_file")

        assert len(received) == 1
        assert received[0].data["tool"] == "write_file"

    def test_subscribe_wrong_type(self):
        """Handler wird NICHT bei falschem Event-Typ aufgerufen."""
        bus = EventBus()
        received = []

        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: received.append(e))
        bus.emit_simple(Events.TOOL_FAILED, tool="read_file")

        assert len(received) == 0

    def test_multiple_handlers(self):
        """Mehrere Handler fuer denselben Event-Typ."""
        bus = EventBus()
        count = [0, 0]

        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: count.__setitem__(0, count[0] + 1))
        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: count.__setitem__(1, count[1] + 1))
        bus.emit_simple(Events.TOOL_SUCCEEDED)

        assert count == [1, 1]

    def test_subscribe_all(self):
        """Globaler Handler empfaengt alle Events."""
        bus = EventBus()
        received = []

        bus.subscribe_all(lambda e: received.append(e.type))
        bus.emit_simple(Events.TOOL_SUCCEEDED)
        bus.emit_simple(Events.TOOL_FAILED)
        bus.emit_simple(Events.FILE_WRITTEN)

        assert received == [
            Events.TOOL_SUCCEEDED,
            Events.TOOL_FAILED,
            Events.FILE_WRITTEN,
        ]

    def test_handler_error_does_not_propagate(self):
        """Fehler in Handler bricht NICHT den emit-Aufruf."""
        bus = EventBus()
        second_called = [False]

        def bad_handler(event: Event):
            raise ValueError("Absichtlicher Fehler")

        def good_handler(event: Event):
            second_called[0] = True

        bus.subscribe(Events.TOOL_SUCCEEDED, bad_handler)
        bus.subscribe(Events.TOOL_SUCCEEDED, good_handler)

        # Kein raise — Bus faengt den Fehler
        bus.emit_simple(Events.TOOL_SUCCEEDED)
        assert second_called[0] is True

    def test_emit_simple_returns_event(self):
        """emit_simple gibt das erstellte Event zurueck."""
        bus = EventBus()
        event = bus.emit_simple(Events.TOOL_SUCCEEDED, source="test", tool="x")

        assert isinstance(event, Event)
        assert event.type == Events.TOOL_SUCCEEDED
        assert event.source == "test"
        assert event.data["tool"] == "x"


class TestEventLog:
    """Event-Log Tests."""

    def test_get_recent_all(self):
        """Letzte Events abrufen."""
        bus = EventBus()
        bus.emit_simple(Events.TOOL_SUCCEEDED, tool="a")
        bus.emit_simple(Events.TOOL_FAILED, tool="b")
        bus.emit_simple(Events.FILE_WRITTEN, path="c")

        recent = bus.get_recent(limit=10)
        assert len(recent) == 3
        assert recent[0]["type"] == Events.TOOL_SUCCEEDED
        assert recent[2]["type"] == Events.FILE_WRITTEN

    def test_get_recent_filtered(self):
        """Events nach Typ filtern."""
        bus = EventBus()
        bus.emit_simple(Events.TOOL_SUCCEEDED, tool="a")
        bus.emit_simple(Events.TOOL_FAILED, tool="b")
        bus.emit_simple(Events.TOOL_SUCCEEDED, tool="c")

        successes = bus.get_recent(event_type=Events.TOOL_SUCCEEDED)
        assert len(successes) == 2

    def test_event_log_rolling_window(self):
        """Log behaelt maximal MAX_EVENT_LOG Eintraege."""
        bus = EventBus()
        for i in range(250):
            bus.emit_simple(Events.STEP_COMPLETED, step=i)

        recent = bus.get_recent(limit=300)
        assert len(recent) == 200  # MAX_EVENT_LOG

    def test_event_log_stores_data_keys(self):
        """Log speichert Daten-Keys statt volle Daten (Speicher-Effizienz)."""
        bus = EventBus()
        bus.emit_simple(Events.TOOL_SUCCEEDED, tool="write_file", result_preview="OK")

        log_entry = bus.get_recent()[0]
        assert "data_keys" in log_entry
        assert "tool" in log_entry["data_keys"]
        assert "result_preview" in log_entry["data_keys"]


class TestHandlerManagement:
    """Handler-Verwaltung."""

    def test_handler_count(self):
        """Handler-Zaehlung."""
        bus = EventBus()
        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: None)
        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: None)
        bus.subscribe(Events.TOOL_FAILED, lambda e: None)

        assert bus.handler_count(Events.TOOL_SUCCEEDED) == 2
        assert bus.handler_count(Events.TOOL_FAILED) == 1
        assert bus.handler_count() == 3  # Gesamt

    def test_handler_count_with_global(self):
        """Globale Handler werden mitgezaehlt."""
        bus = EventBus()
        bus.subscribe_all(lambda e: None)
        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: None)

        assert bus.handler_count() == 2

    def test_clear_handlers(self):
        """Alle Handler entfernen."""
        bus = EventBus()
        bus.subscribe(Events.TOOL_SUCCEEDED, lambda e: None)
        bus.subscribe_all(lambda e: None)
        bus.clear_handlers()

        assert bus.handler_count() == 0
