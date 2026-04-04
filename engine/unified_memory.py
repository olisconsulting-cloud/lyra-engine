"""
Unified Memory — Assoziatives Denken ueber Memory-Grenzen.

Query-Layer ueber alle Memory-Systeme:
- SemanticMemory (TF-IDF basiert)
- MemoryManager (Fibonacci-Decay)
- FailureMemory (Fehler-Patterns)
- SkillLibrary (Bewaehrte Patterns)
- StrategyEvolution (Gelernte Regeln)

Kein eigener Speicher — nur ein intelligenter Query-Dispatcher
der Ergebnisse aus allen Systemen normalisiert und ranked.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryHit:
    """Ein Treffer aus einem Memory-System."""
    source: str       # z.B. "semantic", "experience", "failure"
    content: str
    score: float      # Normalisiert 0.0–1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class MemorySource:
    """Registriertes Memory-System mit Adapter."""
    name: str
    system: Any
    adapter: Callable  # (system, query, top_k) -> list[MemoryHit]
    weight: float = 1.0


class UnifiedMemory:
    """
    Query-Layer ueber alle Memory-Systeme.

    Jedes System wird mit einem Adapter registriert der die
    system-spezifische Query-Logik in normalisierte MemoryHits
    uebersetzt.
    """

    def __init__(self):
        self._sources: dict[str, MemorySource] = {}

    def register_source(self, name: str, system: Any,
                        adapter: Callable, weight: float = 1.0):
        """
        Registriert ein Memory-System mit Adapter.

        Args:
            name: Eindeutiger Name (z.B. "semantic")
            system: Das Memory-System-Objekt
            adapter: Funktion(system, query, top_k) -> list[MemoryHit]
            weight: Basis-Gewicht fuer Score-Anpassung
        """
        self._sources[name] = MemorySource(
            name=name, system=system, adapter=adapter, weight=weight,
        )

    def query(self, query: str, top_k: int = 10,
              sources: list[str] = None) -> list[MemoryHit]:
        """
        Sucht ueber alle (oder ausgewaehlte) Memory-Systeme.

        Returns:
            Liste von MemoryHits, sortiert nach Score (absteigend).
        """
        hits: list[MemoryHit] = []
        active_sources = sources or list(self._sources.keys())

        for source_name in active_sources:
            ms = self._sources.get(source_name)
            if not ms:
                continue
            try:
                source_hits = ms.adapter(ms.system, query, top_k)
                # Score mit Quell-Gewicht skalieren
                for hit in source_hits:
                    hit.score *= ms.weight
                    hit.source = source_name
                hits.extend(source_hits)
            except Exception as e:
                logger.warning(
                    f"UnifiedMemory: Quelle '{source_name}' fehlgeschlagen: {e}"
                )

        # Nach Score sortieren, Top-K zurueckgeben
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def get_context_for(self, focus: str, task_type: str = "standard",
                        max_tokens: int = 800,
                        sources: list[str] = None) -> str:
        """
        Baut einen kompakten Memory-Kontext fuer die Perception.

        Ersetzt die 3 separaten Memory-Abfragen in _build_perception:
        - memory.retrieve_relevant()
        - failure_memory.check()
        - semantic_memory.search()

        Args:
            sources: Nur diese Quellen abfragen (None = alle).
        """
        hits = self.query(focus, top_k=8, sources=sources)
        if not hits:
            return ""

        parts = ["RELEVANTE ERINNERUNGEN (Cross-Memory):"]
        used_tokens = 0
        for hit in hits:
            line = f"  - [{hit.source}|{hit.score:.2f}] {hit.content[:200]}"
            line_tokens = len(line) // 4  # Grobe Schaetzung
            if used_tokens + line_tokens > max_tokens:
                break
            parts.append(line)
            used_tokens += line_tokens

        return "\n".join(parts)

    def source_count(self) -> int:
        return len(self._sources)

    def get_source_names(self) -> list[str]:
        return list(self._sources.keys())


# === Standard-Adapter fuer Phi's Memory-Systeme ===

def semantic_adapter(semantic_memory, query: str, top_k: int) -> list[MemoryHit]:
    """Adapter fuer SemanticMemory (TF-IDF basiert)."""
    results = semantic_memory.search(query, top_k=top_k)
    hits = []
    for r in results:
        score = r.get("similarity", 0.0)
        if score > 0.01:
            hits.append(MemoryHit(
                source="semantic",
                content=r.get("content", "")[:300],
                score=min(1.0, score),
                metadata={"id": r.get("id", ""), "tokens": r.get("tokens", 0)},
            ))
    return hits


def experience_adapter(memory_manager, query: str, top_k: int) -> list[MemoryHit]:
    """Adapter fuer MemoryManager (Fibonacci-Decay)."""
    results = memory_manager.retrieve_relevant(top_k=top_k)
    hits = []
    for r in results:
        score = r.get("retrieval_score", 0.0)
        hits.append(MemoryHit(
            source="experience",
            content=r.get("content", "")[:300],
            score=min(1.0, score),
            metadata={"type": r.get("type", ""), "valence": r.get("valence", 0.0)},
        ))
    return hits


def failure_adapter(failure_memory, query: str, top_k: int) -> list[MemoryHit]:
    """Adapter fuer FailureMemory (Pattern-Matching)."""
    result = failure_memory.check(query)
    if result and result.strip():
        return [MemoryHit(
            source="failure",
            content=result[:400],
            score=0.8,  # Failures sind immer relevant wenn vorhanden
        )]
    return []


def skill_adapter(skill_library, query: str, top_k: int) -> list[MemoryHit]:
    """Adapter fuer SkillLibrary (Template-Matching)."""
    prompt = skill_library.build_skill_prompt(query)
    if prompt and prompt.strip():
        return [MemoryHit(
            source="skill",
            content=prompt[:400],
            score=0.7,  # Bewaehrte Patterns als Hintergrund
        )]
    return []


def strategy_adapter(strategy_evolution, query: str, top_k: int) -> list[MemoryHit]:
    """Adapter fuer StrategyEvolution (Gelernte Regeln)."""
    rules = strategy_evolution.get_active_rules()
    if rules and rules.strip():
        return [MemoryHit(
            source="strategy",
            content=rules[:400],
            score=0.6,  # Regeln als Hintergrund-Wissen
        )]
    return []
