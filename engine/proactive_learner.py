"""
Proaktives Lernen — Intern-first, Internet als Fallback.

Vor jeder Sequenz prueft das System:
1. Skill-Library → Habe ich ein bewaehrtes Vorgehen?
2. Semantic Memory → Habe ich relevante Erinnerungen?
3. Web-Cache → Habe ich das schon mal recherchiert?
4. Falls nichts: Schlage konkrete web_search vor (Phi entscheidet selbst)

Kein automatisches Recherchieren — nur Empfehlungen.
Phi behaelt die Kontrolle ueber Tool-Aufrufe.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)


class WebCache:
    """Cached Web-Recherche-Ergebnisse fuer 24 Stunden."""

    CACHE_TTL_HOURS = 24

    def __init__(self, data_path: Path):
        self.cache_path = data_path / "web_cache"
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_path / "index.json"

    def _query_key(self, query: str) -> str:
        """Stabiler Cache-Key aus Query."""
        normalized = " ".join(query.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def get(self, query: str) -> Optional[dict]:
        """Holt gecachtes Ergebnis (falls vorhanden und nicht abgelaufen)."""
        key = self._query_key(query)
        entry_path = self.cache_path / f"{key}.json"
        if not entry_path.exists():
            return None
        try:
            data = safe_json_read(entry_path, default={})
            cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
            if datetime.now(timezone.utc) - cached_at > timedelta(hours=self.CACHE_TTL_HOURS):
                return None  # Abgelaufen
            return data
        except (ValueError, OSError):
            return None

    def store(self, query: str, results: list, source: str = "web_search"):
        """Speichert Recherche-Ergebnis im Cache."""
        key = self._query_key(query)
        entry = {
            "query": query[:200],
            "results": results[:5],  # Max 5 Ergebnisse
            "source": source,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "access_count": 0,
        }
        safe_json_write(self.cache_path / f"{key}.json", entry)

    def get_stats(self) -> dict:
        """Cache-Statistiken."""
        entries = list(self.cache_path.glob("*.json"))
        # index.json nicht mitzaehlen
        return {
            "cached_queries": len(entries) - (1 if self.index_path.exists() else 0),
            "cache_path": str(self.cache_path),
        }


class ProactiveLearner:
    """Orchestriert intern-first Wissenssuche mit Internet-Fallback.

    Prueft systematisch alle Wissensquellen und gibt eine Empfehlung
    fuer die Perception — Phi entscheidet selbst ob es recherchiert.
    """

    def __init__(self, data_path: Path):
        self.web_cache = WebCache(data_path)
        # Externe Referenzen werden bei build_context() uebergeben
        self._research_budget_per_seq = 3  # Max 3 Recherche-Vorschlaege pro Sequenz

    def build_context(self, focus: str, goal_type: str,
                      skill_library, semantic_memory) -> str:
        """Baut den proaktiven Lern-Kontext fuer die Perception.

        Prueft in Reihenfolge:
        1. Skill-Library (bewaehrtes Vorgehen)
        2. Semantic Memory (relevante Erinnerungen)
        3. Web-Cache (fruhere Recherchen)
        4. Falls nichts: Recherche-Vorschlag

        Args:
            focus: Aktueller Goal-Fokus
            goal_type: Klassifizierter Goal-Typ
            skill_library: SkillLibrary-Instanz
            semantic_memory: SemanticMemory-Instanz

        Returns:
            Kontext-Text fuer Perception oder leerer String.
        """
        if not focus or len(focus) < 10:
            return ""

        parts = []
        has_internal_knowledge = False

        # 1. Skill-Library: Bewaehrtes Vorgehen
        skill = skill_library.get_best_skill(goal_type)
        if skill and skill.get("success_count", 0) >= 1:
            has_internal_knowledge = True
            # Skill-Prompt wird separat in Perception gebaut — hier nur Status

        # 2. Semantic Memory: Relevante Erinnerungen
        relevant = semantic_memory.search(focus, top_k=2, goal_type=goal_type)
        high_relevance = [m for m in relevant if m.get("similarity", 0) > 0.1]
        if high_relevance:
            has_internal_knowledge = True

        # 3. Web-Cache: Fruehere Recherchen zum gleichen Thema
        cache_hit = self.web_cache.get(focus[:100])
        if cache_hit:
            results = cache_hit.get("results", [])
            if results:
                has_internal_knowledge = True
                parts.append("FRUEHERE RECHERCHE (gecacht):")
                for r in results[:3]:
                    if isinstance(r, dict):
                        parts.append(f"  - {r.get('title', '')[:80]}: {r.get('snippet', '')[:120]}")
                    elif isinstance(r, str):
                        parts.append(f"  - {r[:150]}")

        # 4. Falls kein internes Wissen: Recherche-Vorschlag
        if not has_internal_knowledge:
            suggestion = self._suggest_research(focus, goal_type)
            if suggestion:
                parts.append(suggestion)

        return "\n".join(parts)

    def _suggest_research(self, focus: str, goal_type: str) -> str:
        """Generiert einen konkreten Recherche-Vorschlag."""
        # Konkrete Suchanfrage aus dem Fokus ableiten
        search_templates = {
            "recherche": "Nutze web_search fuer aktuelle Daten: \"{focus_short}\"",
            "tool_building": "Falls du unsicher bist: web_search \"Python {focus_short} best practices\"",
            "bug_fix": "Bei unbekannten Fehlern: web_search \"{focus_short} Python solution\"",
            "analyse": "Fuer Hintergrundinformationen: web_search \"{focus_short}\"",
            "documentation": "Fuer Format-Standards: web_search \"{focus_short} template\"",
            "testing": "Fuer Test-Patterns: web_search \"Python testing {focus_short}\"",
        }

        template = search_templates.get(goal_type)
        if not template:
            return ""

        # Fokus auf Kernbegriffe kuerzen
        focus_short = self._extract_core_terms(focus)
        if not focus_short:
            return ""

        search_query = template.format(focus_short=focus_short)

        return (
            f"\nKEIN INTERNES WISSEN zu diesem Thema gefunden.\n"
            f"  Vorschlag: {search_query}\n"
            f"  Nur recherchieren wenn noetig — nicht bei jedem Goal.\n"
            f"  Nach der Recherche: Ergebnisse mit write_file festhalten."
        )

    @staticmethod
    def _extract_core_terms(focus: str) -> str:
        """Extrahiert die wichtigsten Begriffe aus dem Fokus-String."""
        # Strukturelle Praefixe entfernen
        for prefix in ("FOKUS:", "Naechster Schritt:", "Sub-Goal:"):
            if prefix in focus:
                focus = focus.split(prefix)[-1]

        # Stoppwoerter und Filler entfernen
        stop = {"und", "oder", "fuer", "mit", "der", "die", "das", "ein",
                "eine", "zu", "von", "in", "auf", "an", "bei", "nach",
                "was", "wie", "wer", "den", "dem", "des"}
        words = [w for w in focus.lower().split() if len(w) >= 3 and w not in stop]
        return " ".join(words[:5])

    def store_research_result(self, query: str, results: list):
        """Speichert ein Recherche-Ergebnis im Web-Cache.

        Wird aufgerufen nachdem Phi web_search genutzt hat.
        """
        self.web_cache.store(query, results)

    def get_stats(self) -> dict:
        """Statistiken ueber das proaktive Lernsystem."""
        return {
            "web_cache": self.web_cache.get_stats(),
            "research_budget": self._research_budget_per_seq,
        }
