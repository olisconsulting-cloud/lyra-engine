"""SkillEnricher — Reichert Skills mit Cross-System-Wissen an.

Bei jeder Skill-Extraktion werden anti_patterns aus FailureMemory
eingebettet, damit Phi bei aehnlichen Goals die Fehler sieht.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .quantum import FailureMemory

logger = logging.getLogger(__name__)


class SkillEnricher:
    """Verbindet SkillLibrary mit FailureMemory bei der Extraktion."""

    def __init__(self, failure_memory: FailureMemory) -> None:
        self.failure_memory = failure_memory

    def enrich(self, skill: dict, focus: str) -> dict:
        """Fuegt anti_patterns aus FailureMemory zum Skill hinzu.

        Args:
            skill: Neuer Skill-Dict (vor dem Speichern).
            focus: Aktueller Goal-Focus als Suchbegriff.

        Returns:
            Angereicherter Skill-Dict.
        """
        try:
            warning = self.failure_memory.check(focus)
            if warning:
                skill["anti_patterns"] = warning
                logger.info("Skill angereichert mit anti_patterns fuer: %s", focus[:60])
        except Exception as e:
            logger.warning("SkillEnricher fehlgeschlagen: %s", e)
        return skill
