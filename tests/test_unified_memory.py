"""Tests fuer engine/unified_memory.py — Assoziatives Denken."""
from engine.unified_memory import UnifiedMemory, MemoryHit


class MockSemanticMemory:
    def search(self, query, top_k=5):
        return [
            {"content": "Python TF-IDF Implementierung", "similarity": 0.85, "id": "s1"},
            {"content": "Web-Scraping mit BeautifulSoup", "similarity": 0.45, "id": "s2"},
        ]


class MockMemoryManager:
    def retrieve_relevant(self, top_k=5):
        return [
            {"content": "Projekt X erfolgreich abgeschlossen", "retrieval_score": 0.7, "type": "sequenz_abschluss", "valence": 0.5},
        ]


class MockFailureMemory:
    def check(self, focus):
        if "scraping" in focus.lower():
            return "WARNUNG: web_read hat 3x bei dieser URL versagt"
        return ""


class MockSkillLibrary:
    def build_skill_prompt(self, goal_type):
        if goal_type == "recherche":
            return "BEWAEHRTES VORGEHEN: Definieren → Sammeln → Synthetisieren"
        return ""


class MockStrategyEvolution:
    def get_active_rules(self):
        return "REGEL: Bei file_not_found erst list_directory nutzen"


class TestRegistration:
    def test_register_source(self):
        um = UnifiedMemory()
        um.register_source("test", object(), adapter=lambda s, q, k: [])
        assert um.source_count() == 1
        assert "test" in um.get_source_names()

    def test_register_multiple(self):
        um = UnifiedMemory()
        um.register_source("a", object(), adapter=lambda s, q, k: [])
        um.register_source("b", object(), adapter=lambda s, q, k: [])
        assert um.source_count() == 2


class TestQuery:
    def test_query_single_source(self):
        um = UnifiedMemory()

        def adapter(sys, query, top_k):
            return [MemoryHit(source="test", content="Treffer", score=0.9)]

        um.register_source("test", object(), adapter=adapter)
        hits = um.query("python")
        assert len(hits) == 1
        assert hits[0].score == 0.9

    def test_query_multiple_sources(self):
        """Cross-Domain Query liefert Ergebnisse aus allen Quellen."""
        um = UnifiedMemory()

        def adapter_a(sys, q, k):
            return [MemoryHit(source="a", content="Von A", score=0.8)]

        def adapter_b(sys, q, k):
            return [MemoryHit(source="b", content="Von B", score=0.6)]

        um.register_source("a", object(), adapter=adapter_a)
        um.register_source("b", object(), adapter=adapter_b)

        hits = um.query("test", top_k=10)
        assert len(hits) == 2
        # Sortiert nach Score
        assert hits[0].content == "Von A"
        assert hits[1].content == "Von B"

    def test_query_with_source_filter(self):
        """Nur ausgewaehlte Quellen abfragen."""
        um = UnifiedMemory()

        def adapter_a(sys, q, k):
            return [MemoryHit(source="a", content="A", score=0.9)]

        def adapter_b(sys, q, k):
            return [MemoryHit(source="b", content="B", score=0.8)]

        um.register_source("a", object(), adapter=adapter_a)
        um.register_source("b", object(), adapter=adapter_b)

        hits = um.query("test", sources=["a"])
        assert len(hits) == 1
        assert hits[0].source == "a"

    def test_query_top_k_limit(self):
        """Top-K limitiert die Ergebnisse."""
        um = UnifiedMemory()

        def adapter(sys, q, k):
            return [MemoryHit(source="x", content=f"Hit {i}", score=1.0 - i * 0.1) for i in range(10)]

        um.register_source("x", object(), adapter=adapter)
        hits = um.query("test", top_k=3)
        assert len(hits) == 3

    def test_weight_affects_score(self):
        """Quell-Gewicht skaliert den Score."""
        um = UnifiedMemory()

        def adapter(sys, q, k):
            return [MemoryHit(source="x", content="Hit", score=1.0)]

        um.register_source("x", object(), adapter=adapter, weight=0.5)
        hits = um.query("test")
        assert hits[0].score == 0.5

    def test_broken_source_skipped(self):
        """Fehlerhafter Adapter wird uebersprungen."""
        um = UnifiedMemory()

        def bad_adapter(sys, q, k):
            raise RuntimeError("Kaputt")

        def good_adapter(sys, q, k):
            return [MemoryHit(source="good", content="OK", score=0.7)]

        um.register_source("bad", object(), adapter=bad_adapter)
        um.register_source("good", object(), adapter=good_adapter)

        hits = um.query("test")
        assert len(hits) == 1
        assert hits[0].source == "good"


class TestWithMocks:
    """Tests mit Phi-aehnlichen Mock-Systemen."""

    def _build_unified(self):
        from engine.unified_memory import (
            semantic_adapter, experience_adapter, failure_adapter,
            skill_adapter, strategy_adapter,
        )
        um = UnifiedMemory()
        um.register_source("semantic", MockSemanticMemory(), adapter=semantic_adapter)
        um.register_source("experience", MockMemoryManager(), adapter=experience_adapter)
        um.register_source("failure", MockFailureMemory(), adapter=failure_adapter)
        um.register_source("skill", MockSkillLibrary(), adapter=skill_adapter)
        um.register_source("strategy", MockStrategyEvolution(), adapter=strategy_adapter)
        return um

    def test_cross_domain_scraping_query(self):
        """'Web-Scraping' findet Treffer in mehreren Memory-Systemen."""
        um = self._build_unified()
        hits = um.query("web scraping recherche", top_k=10)

        sources = [h.source for h in hits]
        # Semantic findet "Web-Scraping mit BeautifulSoup"
        assert "semantic" in sources
        # Failure findet "web_read hat 3x versagt"
        assert "failure" in sources
        # Strategy hat eine Regel
        assert "strategy" in sources

    def test_get_context_for(self):
        """get_context_for baut kompakten Kontext."""
        um = self._build_unified()
        context = um.get_context_for("web scraping recherche")
        assert "Cross-Memory" in context
        assert len(context) > 0

    def test_semantic_adapter_filters_low_scores(self):
        """Semantic Adapter filtert Scores <= 0.01."""
        from engine.unified_memory import semantic_adapter

        class LowScoreMemory:
            def search(self, query, top_k=5):
                return [{"content": "Irrelevant", "similarity": 0.001}]

        hits = semantic_adapter(LowScoreMemory(), "test", 5)
        assert len(hits) == 0

    def test_failure_adapter_empty_when_no_match(self):
        """Failure Adapter gibt nichts zurueck wenn kein Match."""
        from engine.unified_memory import failure_adapter
        hits = failure_adapter(MockFailureMemory(), "python coding", 5)
        assert len(hits) == 0

    def test_skill_adapter_empty_when_no_match(self):
        """Skill Adapter gibt nichts zurueck wenn kein passendes Skill."""
        from engine.unified_memory import skill_adapter
        hits = skill_adapter(MockSkillLibrary(), "unbekannter_typ", 5)
        assert len(hits) == 0
