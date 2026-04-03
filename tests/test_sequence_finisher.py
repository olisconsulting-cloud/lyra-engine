"""Tests fuer engine/sequence_finisher.py — End-of-Sequence Verarbeitung."""
from engine.sequence_finisher import SequenceFinisher
from engine.event_bus import EventBus, Events


class MockMemory:
    def __init__(self):
        self.experiences = []
        self.reflections = []

    def store_experience(self, exp):
        self.experiences.append(exp)

    def store_reflection(self, ref):
        self.reflections.append(ref)


class MockSelfRating:
    def __init__(self):
        self.ratings = []

    def add_rating(self, rating, reason, seq_num):
        self.ratings.append({"rating": rating, "reason": reason, "seq": seq_num})


class MockMetaCognition:
    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)

    def analyze_patterns(self):
        return []


class MockStrategies:
    def __init__(self):
        self.validations = []

    def validate_against_outcome(self, beliefs, summary, rating):
        self.validations.append({"beliefs": beliefs, "rating": rating})

    def record_process_pattern(self, pattern):
        pass


class MockCommunication:
    telegram_active = False

    def __init__(self):
        self.journal = []

    def write_journal(self, text):
        self.journal.append(text)

    def send_message(self, msg):
        pass


class TestFinish:
    def _make_finisher(self, **extra_subs):
        bus = EventBus()
        memory = MockMemory()
        rating = MockSelfRating()
        metacog = MockMetaCognition()
        strategies = MockStrategies()
        comm = MockCommunication()

        subs = {
            "memory": memory,
            "self_rating": rating,
            "metacognition": metacog,
            "strategies": strategies,
            "communication": comm,
        }
        subs.update(extra_subs)

        finisher = SequenceFinisher(event_bus=bus, **subs)
        return finisher, bus, memory, rating, metacog, strategies, comm

    def test_basic_finish(self):
        finisher, bus, memory, rating, metacog, strategies, comm = self._make_finisher()

        result = finisher.finish(
            tool_input={
                "summary": "Test abgeschlossen",
                "performance_rating": 7,
                "bottleneck": "Langsame API",
                "next_time_differently": "Caching nutzen",
                "new_beliefs": ["Tests sind wichtig"],
            },
            seq_metrics={"errors": 1, "files_written": 3, "step_count": 10},
            beliefs={"formed_from_experience": []},
            sequences_total=42,
        )
        assert "abgeschlossen" in result

    def test_experience_stored(self):
        finisher, bus, memory, *_ = self._make_finisher()

        finisher.finish(
            tool_input={"summary": "Test", "performance_rating": 8},
            seq_metrics={"errors": 0, "files_written": 2, "step_count": 5},
            beliefs={"formed_from_experience": []},
            sequences_total=1,
        )
        assert len(memory.experiences) == 1
        assert memory.experiences[0]["type"] == "sequenz_abschluss"

    def test_rating_recorded(self):
        finisher, bus, memory, rating, *_ = self._make_finisher()

        finisher.finish(
            tool_input={"summary": "Gut", "performance_rating": 9},
            seq_metrics={"errors": 0, "files_written": 1, "step_count": 3},
            beliefs={"formed_from_experience": []},
            sequences_total=5,
        )
        assert len(rating.ratings) == 1
        assert rating.ratings[0]["rating"] == 9

    def test_metacognition_recorded(self):
        finisher, bus, memory, rating, metacog, *_ = self._make_finisher()

        finisher.finish(
            tool_input={
                "summary": "OK",
                "performance_rating": 6,
                "bottleneck": "Token-Limit",
                "next_time_differently": "Frueher beenden",
                "key_decision": "Sonnet statt Opus",
            },
            seq_metrics={"errors": 2, "files_written": 1, "step_count": 15},
            beliefs={"formed_from_experience": []},
            sequences_total=10,
        )
        assert len(metacog.records) == 1
        assert metacog.records[0]["bottleneck"] == "Token-Limit"

    def test_beliefs_updated(self):
        finisher, *_ = self._make_finisher()
        beliefs = {"formed_from_experience": ["Alt"]}

        finisher.finish(
            tool_input={
                "summary": "OK",
                "performance_rating": 7,
                "new_beliefs": ["Neu1", "Neu2"],
            },
            seq_metrics={"errors": 0, "files_written": 0, "step_count": 5},
            beliefs=beliefs,
            sequences_total=1,
        )
        assert "Neu1" in beliefs["formed_from_experience"]
        assert "Neu2" in beliefs["formed_from_experience"]
        assert "Alt" in beliefs["formed_from_experience"]

    def test_beliefs_dedup(self):
        """Doppelte Beliefs werden nicht hinzugefuegt."""
        finisher, *_ = self._make_finisher()
        beliefs = {"formed_from_experience": ["Existiert"]}

        finisher.finish(
            tool_input={
                "summary": "OK",
                "performance_rating": 7,
                "new_beliefs": ["Existiert", "Neu"],
            },
            seq_metrics={"errors": 0, "files_written": 0, "step_count": 5},
            beliefs=beliefs,
            sequences_total=1,
        )
        assert beliefs["formed_from_experience"].count("Existiert") == 1

    def test_beliefs_max_30(self):
        """Max 30 Beliefs behalten."""
        finisher, *_ = self._make_finisher()
        beliefs = {"formed_from_experience": [f"Belief {i}" for i in range(29)]}

        finisher.finish(
            tool_input={
                "summary": "OK",
                "performance_rating": 7,
                "new_beliefs": ["Neu1", "Neu2", "Neu3"],
            },
            seq_metrics={"errors": 0, "files_written": 0, "step_count": 5},
            beliefs=beliefs,
            sequences_total=1,
        )
        assert len(beliefs["formed_from_experience"]) <= 30

    def test_event_emitted(self):
        finisher, bus, *_ = self._make_finisher()
        events = []
        bus.subscribe(Events.SEQUENCE_FINISHED, lambda e: events.append(e))

        finisher.finish(
            tool_input={"summary": "OK", "performance_rating": 7},
            seq_metrics={"errors": 0, "files_written": 1, "step_count": 5},
            beliefs={"formed_from_experience": []},
            sequences_total=42,
        )
        assert len(events) == 1
        assert events[0].data["seq_num"] == 42

    def test_journal_written(self):
        finisher, bus, memory, rating, metacog, strategies, comm = self._make_finisher()

        finisher.finish(
            tool_input={"summary": "Projekt fertig", "performance_rating": 8},
            seq_metrics={"errors": 0, "files_written": 2, "step_count": 5},
            beliefs={"formed_from_experience": []},
            sequences_total=10,
        )
        assert len(comm.journal) == 1
        assert "Projekt fertig" in comm.journal[0]

    def test_partial_failure_continues(self):
        """Wenn ein Subsystem fehlt, laufen die anderen trotzdem."""
        bus = EventBus()
        # Nur Memory, kein Rating oder Metacognition
        finisher = SequenceFinisher(event_bus=bus, memory=MockMemory())

        result = finisher.finish(
            tool_input={"summary": "OK", "performance_rating": 5},
            seq_metrics={"errors": 0, "files_written": 0, "step_count": 3},
            beliefs={"formed_from_experience": []},
            sequences_total=1,
        )
        assert "abgeschlossen" in result
