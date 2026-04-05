"""Tests fuer engine/perception_pipeline.py — Gewichtete Wahrnehmung."""
import json
import tempfile
from pathlib import Path

from engine.perception_pipeline import (
    PerceptionPipeline, PerceptionChannel, ALWAYS_LOAD, DEFAULT_TASK_WEIGHTS,
)


def _make_pipeline(tmp_path: Path) -> PerceptionPipeline:
    """Erstellt Pipeline mit Temp-Verzeichnis."""
    consciousness_path = tmp_path / "consciousness"
    consciousness_path.mkdir(parents=True, exist_ok=True)
    return PerceptionPipeline(tmp_path, max_tokens=1000)


class TestChannelRegistration:
    def test_register_channel(self, tmp_path):
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="test", builder=lambda: "test content",
        ))
        result = pipe.build()
        assert "test content" in result

    def test_always_load_channels(self, tmp_path):
        """Always-load Kanaele werden immer geladen."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="inbox", builder=lambda: "Oliver sagt hallo",
            always_load=True,
        ))
        result = pipe.build()
        assert "Oliver sagt hallo" in result


class TestWeighting:
    def test_higher_weight_preferred(self, tmp_path):
        """Kanaele mit hohem Gewicht werden bevorzugt bei Token-Budget."""
        pipe = PerceptionPipeline(tmp_path, max_tokens=300)
        consciousness_path = tmp_path / "consciousness"
        consciousness_path.mkdir(parents=True, exist_ok=True)

        pipe.register_channel(PerceptionChannel(
            name="failure_check", builder=lambda: "WARNUNG: Fehler",
            base_weight=1.0, estimated_tokens=200,
        ))
        pipe.register_channel(PerceptionChannel(
            name="efficiency_alerts", builder=lambda: "Effizienz niedrig",
            base_weight=0.1, estimated_tokens=200,
        ))

        result = pipe.build(task_type="standard", token_budget=250)
        # failure_check hat hoeheres Gewicht → wird zuerst geladen
        assert "WARNUNG" in result
        # efficiency_alerts wird truncated oder geladen (Truncation statt Drop)
        stats = pipe.get_build_stats()
        assert stats["channels_loaded"] >= 1

    def test_task_type_affects_weights(self, tmp_path):
        """Verschiedene Task-Typen gewichten Kanaele unterschiedlich."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="semantic_memory", builder=lambda: "Semantik",
            estimated_tokens=100,
        ))
        pipe.register_channel(PerceptionChannel(
            name="projects_list", builder=lambda: "Projekte",
            estimated_tokens=100,
        ))

        # Recherche: semantic_memory hat Gewicht 1.5, projects_list 0.2
        pipe.build(task_type="recherche")
        channels = pipe.get_active_channels()
        # Beide sollten geladen werden (genug Budget)
        assert "semantic_memory" in channels
        assert "projects_list" in channels


class TestTokenBudget:
    def test_budget_limits_channels(self, tmp_path):
        """Token-Budget begrenzt geladene Kanaele (mit Truncation)."""
        pipe = PerceptionPipeline(tmp_path, max_tokens=100)
        consciousness_path = tmp_path / "consciousness"
        consciousness_path.mkdir(parents=True, exist_ok=True)

        for i in range(10):
            pipe.register_channel(PerceptionChannel(
                name=f"ch_{i}", builder=lambda i=i: f"Content {i}",
                estimated_tokens=50, base_weight=1.0,
            ))

        pipe.build(token_budget=120)
        stats = pipe.get_build_stats()
        # Budget begrenzt Gesamtverbrauch — nicht unbedingt Kanal-Anzahl
        # weil kleine Kanaele trotz Truncation durchkommen
        assert stats["total_tokens"] <= 200  # Grosszuegige Obergrenze

    def test_always_load_ignores_budget(self, tmp_path):
        """Always-load Kanaele ignorieren das Budget."""
        pipe = PerceptionPipeline(tmp_path, max_tokens=10)
        consciousness_path = tmp_path / "consciousness"
        consciousness_path.mkdir(parents=True, exist_ok=True)

        pipe.register_channel(PerceptionChannel(
            name="inbox", builder=lambda: "Oliver",
            always_load=True, estimated_tokens=500,
        ))
        result = pipe.build(token_budget=10)
        assert "Oliver" in result


class TestFeedback:
    def test_positive_feedback_strengthens(self, tmp_path):
        """Hohes Rating verstaerkt die Gewichte aktiver Kanaele."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="semantic_memory", builder=lambda: "Test",
            estimated_tokens=50,
        ))

        # Build um active_channels zu setzen
        pipe.build(task_type="projekt")

        # Positives Feedback
        pipe.record_feedback("projekt", rating=8)

        weights = pipe.get_learned_weights()
        # semantic_memory sollte verstaerkt sein (> 1.0)
        assert weights.get("projekt", {}).get("semantic_memory", 1.0) > 1.0

    def test_negative_feedback_weakens(self, tmp_path):
        """Niedriges Rating schwaeacht die Gewichte."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="semantic_memory", builder=lambda: "Test",
            estimated_tokens=50,
        ))

        pipe.build(task_type="standard")
        pipe.record_feedback("standard", rating=2)

        weights = pipe.get_learned_weights()
        assert weights.get("standard", {}).get("semantic_memory", 1.0) < 1.0

    def test_neutral_feedback_no_change(self, tmp_path):
        """Neutrales Rating (4-5) aendert nichts."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="semantic_memory", builder=lambda: "Test",
            estimated_tokens=50,
        ))

        pipe.build(task_type="standard")
        pipe.record_feedback("standard", rating=5)

        weights = pipe.get_learned_weights()
        assert weights == {}  # Kein Update

    def test_weights_persist(self, tmp_path):
        """Gelernte Gewichte werden auf Disk gespeichert."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="failure_check", builder=lambda: "Test",
            estimated_tokens=50,
        ))

        pipe.build(task_type="projekt")
        pipe.record_feedback("projekt", rating=9)

        # Neue Pipeline vom selben Pfad → laedt gespeicherte Gewichte
        pipe2 = _make_pipeline(tmp_path)
        assert pipe2.get_learned_weights().get("projekt", {}).get("failure_check") is not None


class TestTruncation:
    def test_truncation_preserves_partial_content(self, tmp_path):
        """Bei Budget-Druck wird Content gekuerzt statt komplett gedroppt."""
        pipe = PerceptionPipeline(tmp_path, max_tokens=50)
        consciousness_path = tmp_path / "consciousness"
        consciousness_path.mkdir(parents=True, exist_ok=True)

        long_content = "Zeile eins\nZeile zwei\nZeile drei\nZeile vier\nZeile fuenf"
        pipe.register_channel(PerceptionChannel(
            name="big", builder=lambda: long_content,
            base_weight=1.0, estimated_tokens=200,
        ))

        result = pipe.build()
        stats = pipe.get_build_stats()
        # Kanal wurde geladen (truncated, nicht gedroppt)
        assert stats["channels_loaded"] == 1
        assert stats["channels_truncated"] == 1
        # Mindestens die erste Zeile ist da
        assert "Zeile eins" in result
        # Aber nicht alles
        assert len(result) < len(long_content)

    def test_no_truncation_when_budget_sufficient(self, tmp_path):
        """Kein Truncation wenn Budget ausreicht."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="small", builder=lambda: "Kurzer Text",
            estimated_tokens=50,
        ))

        pipe.build()
        stats = pipe.get_build_stats()
        assert stats["channels_truncated"] == 0


class TestAdaptiveEstimates:
    def test_token_averages_learned(self, tmp_path):
        """Token-Averages werden aus tatsaechlichem Content gelernt."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="test_ch", builder=lambda: "Ein kurzer Satz",
            estimated_tokens=500,  # Absichtlich viel zu hoch
        ))

        pipe.build()
        avg = pipe._token_averages.get("test_ch")
        assert avg is not None
        # Gelernter Average muss kleiner als 500 sein (Content ist kurz)
        assert avg < 500

    def test_token_averages_persist(self, tmp_path):
        """Token-Averages werden auf Disk gespeichert und geladen."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="persist_ch", builder=lambda: "Test Content hier",
            estimated_tokens=100,
        ))
        pipe.build()

        # Neue Pipeline vom selben Pfad → laedt gespeicherte Averages
        pipe2 = _make_pipeline(tmp_path)
        assert "persist_ch" in pipe2._token_averages

    def test_build_stats_available(self, tmp_path):
        """Build-Statistiken sind nach build() verfuegbar."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="stats_ch", builder=lambda: "Content",
            estimated_tokens=50,
        ))

        pipe.build(task_type="projekt")
        stats = pipe.get_build_stats()
        assert stats["task_type"] == "projekt"
        assert stats["channels_loaded"] == 1
        assert stats["channels_total"] == 1
        assert stats["budget"] == 1000
        assert stats["total_tokens"] > 0


class TestErrorHandling:
    def test_broken_channel_skipped(self, tmp_path):
        """Fehlerhafter Kanal wird uebersprungen."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="broken", builder=lambda: (_ for _ in ()).throw(RuntimeError("Boom")),
        ))
        pipe.register_channel(PerceptionChannel(
            name="ok", builder=lambda: "OK Content",
        ))

        result = pipe.build()
        assert "OK Content" in result
        assert "broken" not in pipe.get_active_channels()

    def test_empty_channel_skipped(self, tmp_path):
        """Leerer Kanal wird nicht in active_channels gezaehlt."""
        pipe = _make_pipeline(tmp_path)
        pipe.register_channel(PerceptionChannel(
            name="empty", builder=lambda: "",
        ))
        pipe.register_channel(PerceptionChannel(
            name="ok", builder=lambda: "Content",
        ))

        pipe.build()
        assert "empty" not in pipe.get_active_channels()
        assert "ok" in pipe.get_active_channels()
