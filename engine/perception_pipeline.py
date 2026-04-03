"""
Perception-Pipeline — Fokussiertes Denken durch gewichtete Wahrnehmung.

Statt alle 15 Quellen immer zu laden, gewichtet die Pipeline
Kanaele nach Task-Typ und lernt ueber Zeit welche Kanaele
fuer welche Aufgaben relevant sind.

Ergebnis: 20-40% weniger Token fuer Perception = mehr Raum zum Denken.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .config import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)

# Kanaele die IMMER geladen werden, unabhaengig von Gewichtung
ALWAYS_LOAD = frozenset({"inbox", "focus", "working_memory", "time"})

# Default-Gewichte pro Task-Typ (Basis wenn keine gelernten vorhanden)
DEFAULT_TASK_WEIGHTS: dict[str, dict[str, float]] = {
    "standard": {
        "sequence_memory": 1.0, "live_notes": 0.8, "skill_prompt": 0.5,
        "proactive_context": 0.5, "projects_list": 0.4, "semantic_memory": 0.6,
        "failure_check": 0.7, "filesystem": 0.3, "file_changes": 0.3,
        "efficiency_alerts": 0.2, "checkpoint_context": 0.5,
        "memories": 0.5, "composition": 0.4, "tasks": 0.4,
    },
    "projekt": {
        "sequence_memory": 1.0, "live_notes": 1.0, "skill_prompt": 1.2,
        "proactive_context": 0.8, "projects_list": 1.5, "semantic_memory": 1.0,
        "failure_check": 1.2, "filesystem": 0.5, "file_changes": 0.6,
        "efficiency_alerts": 0.3, "checkpoint_context": 1.0,
        "memories": 0.6, "composition": 0.6, "tasks": 0.3,
    },
    "recherche": {
        "sequence_memory": 1.0, "live_notes": 0.5, "skill_prompt": 0.3,
        "proactive_context": 1.5, "projects_list": 0.2, "semantic_memory": 1.5,
        "failure_check": 0.3, "filesystem": 0.2, "file_changes": 0.1,
        "efficiency_alerts": 0.1, "checkpoint_context": 0.3,
        "memories": 0.8, "composition": 0.3, "tasks": 0.3,
    },
    "evolution": {
        "sequence_memory": 1.0, "live_notes": 0.5, "skill_prompt": 0.7,
        "proactive_context": 0.5, "projects_list": 0.3, "semantic_memory": 0.8,
        "failure_check": 1.0, "filesystem": 0.8, "file_changes": 0.5,
        "efficiency_alerts": 0.8, "checkpoint_context": 0.5,
        "memories": 0.5, "composition": 0.5, "tasks": 0.4,
    },
}

# EMA-Faktor fuer Gewichts-Lernen (0.1 = langsam lernen, 0.3 = schneller)
EMA_ALPHA = 0.15


@dataclass
class PerceptionChannel:
    """Ein Wahrnehmungskanal mit Builder-Funktion und Gewichtung."""
    name: str
    builder: Callable[[], str]
    base_weight: float = 1.0
    estimated_tokens: int = 200
    always_load: bool = False


class PerceptionPipeline:
    """
    Pipeline fuer gewichtete Wahrnehmung.

    Registriert Kanaele, gewichtet sie nach Task-Typ und gelernten
    Praeferenzen, und baut die Perception nach Token-Budget.
    """

    def __init__(self, data_path: Path, max_tokens: int = 3000):
        self._channels: list[PerceptionChannel] = []
        self._max_tokens = max_tokens
        self._weights_path = data_path / "consciousness" / "perception_weights.json"
        self._learned_weights: dict[str, dict[str, float]] = safe_json_read(
            self._weights_path, {}
        )
        self._last_active_channels: list[str] = []

    def register_channel(self, channel: PerceptionChannel):
        """Registriert einen Wahrnehmungskanal."""
        self._channels.append(channel)

    def build(self, task_type: str = "standard",
              token_budget: int = 0) -> str:
        """
        Baut Perception: Score pro Kanal berechnen, sortieren, laden bis Budget.

        Args:
            task_type: Art der Aufgabe (standard, projekt, recherche, evolution)
            token_budget: Max Tokens fuer Perception (0 = self._max_tokens)

        Returns:
            Zusammengebauter Perception-Text
        """
        budget = token_budget or self._max_tokens
        parts: list[str] = []
        used_tokens = 0
        self._last_active_channels = []

        # Kanaele mit Score versehen
        scored = []
        for ch in self._channels:
            if ch.always_load or ch.name in ALWAYS_LOAD:
                score = 999.0  # Immer laden
            else:
                score = self._compute_score(ch, task_type)
            scored.append((score, ch))

        # Nach Score absteigend sortieren
        scored.sort(key=lambda x: x[0], reverse=True)

        for score, ch in scored:
            # Budget-Check (always_load Kanaele ignorieren Budget)
            if not (ch.always_load or ch.name in ALWAYS_LOAD):
                if used_tokens + ch.estimated_tokens > budget:
                    continue

            try:
                content = ch.builder()
                if content and content.strip():
                    parts.append(content)
                    used_tokens += ch.estimated_tokens
                    self._last_active_channels.append(ch.name)
            except Exception as e:
                logger.warning(f"PerceptionPipeline: Kanal '{ch.name}' fehlgeschlagen: {e}")

        return "\n".join(parts)

    def record_feedback(self, task_type: str, rating: int):
        """
        Lernt aus dem Sequenz-Rating welche Kanaele nuetzlich waren.

        Nutzt Exponential Moving Average (EMA):
        - Hohes Rating (>= 6) → aktive Kanaele verstaerken
        - Niedriges Rating (<= 3) → aktive Kanaele abschwaechen
        - Neutrales Rating (4-5) → kein Update
        """
        if not self._last_active_channels or rating in (4, 5):
            return

        if task_type not in self._learned_weights:
            self._learned_weights[task_type] = {}

        signal = 1.0 if rating >= 6 else -0.5 if rating <= 3 else 0.0
        if signal == 0.0:
            return

        for ch_name in self._last_active_channels:
            if ch_name in ALWAYS_LOAD:
                continue  # Always-load Kanaele nicht anpassen
            current = self._learned_weights[task_type].get(ch_name, 1.0)
            # EMA: neuer Wert = (1-alpha) * alter + alpha * signal_basierter_wert
            target = current + signal * 0.2
            new_weight = (1 - EMA_ALPHA) * current + EMA_ALPHA * target
            # Clamp auf [0.05, 3.0]
            self._learned_weights[task_type][ch_name] = max(0.05, min(3.0, new_weight))

        safe_json_write(self._weights_path, self._learned_weights)

    def get_active_channels(self) -> list[str]:
        """Gibt die Kanaele zurueck die beim letzten build() aktiv waren."""
        return list(self._last_active_channels)

    def get_learned_weights(self) -> dict:
        """Gibt die gelernten Gewichte zurueck (fuer Debugging)."""
        return dict(self._learned_weights)

    def _compute_score(self, ch: PerceptionChannel, task_type: str) -> float:
        """Berechnet den Relevanz-Score eines Kanals fuer den gegebenen Task-Typ."""
        # Basis-Gewicht aus Default-Tabelle
        task_weights = DEFAULT_TASK_WEIGHTS.get(task_type, DEFAULT_TASK_WEIGHTS["standard"])
        base = task_weights.get(ch.name, ch.base_weight)

        # Gelerntes Gewicht (falls vorhanden)
        learned = self._learned_weights.get(task_type, {}).get(ch.name, 1.0)

        return base * learned
