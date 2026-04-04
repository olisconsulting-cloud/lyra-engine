"""
Meta-Patterns fuer Tools — Verhindert Tool-Sprawl an der Quelle.

Nutzt das bestehende MetaRuleEngine-Interface (record_pattern):
Bei 3x gleichem Muster wird automatisch eine harte Regel erstellt.

Drei Tool-spezifische Patterns:
1. Version-Sprawl: Aehnliche Tools statt update_tool
2. Failure-Loop: Gleiches Tool scheitert wiederholt
3. Orphan-Creation: Tools werden erstellt aber nie benutzt
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.meta_rules import MetaRuleEngine

logger = logging.getLogger(__name__)


# Schwellenwerte
SIMILARITY_THRESHOLD = 0.5  # Ab wann "aehnlich" zu bestehendem Tool
FAILURE_THRESHOLD = 3        # Konsekutive Failures bis Blockade
ORPHAN_SEQUENCES = 10        # Sequenzen ohne Nutzung nach Erstellung


class ToolMetaPatterns:
    """Erkennt wiederkehrende Tool-Probleme und erzwingt Regeln."""

    # Max Eintraege im Failure-Tracker (Memory-Leak verhindern)
    MAX_TRACKED_TOOLS = 50

    def __init__(self, meta_rules: "MetaRuleEngine"):
        self.meta_rules = meta_rules
        # Zaehler fuer konsekutive Failures pro Tool (begrenzt)
        self._consecutive_failures: dict[str, int] = {}

    def cleanup_stale_entries(self, active_tools: set[str]) -> None:
        """Entfernt Failure-Eintraege fuer nicht mehr existierende Tools."""
        stale = set(self._consecutive_failures.keys()) - active_tools
        for name in stale:
            del self._consecutive_failures[name]
        # Hard-Limit: Wenn trotzdem zu viele, aelteste entfernen
        if len(self._consecutive_failures) > self.MAX_TRACKED_TOOLS:
            # Tools mit 0 Failures zuerst entfernen
            zeros = [k for k, v in self._consecutive_failures.items() if v == 0]
            for k in zeros:
                del self._consecutive_failures[k]
                if len(self._consecutive_failures) <= self.MAX_TRACKED_TOOLS:
                    break

    def check_version_sprawl(self, new_tool_name: str,
                              existing_tools: dict) -> None:
        """Erkennt Version-Sprawl: Aehnliche Tools statt update_tool.

        Wird nach create_tool aufgerufen. Prueft ob der neue Tool-Name
        einem bestehenden Tool aehnelt (z.B. checker_v2, checker_v3).

        Args:
            new_tool_name: Name des gerade erstellten Tools
            existing_tools: Dict aller registrierten Tools
        """
        base_name = self._extract_base_name(new_tool_name)

        similar_count = 0
        for name in existing_tools:
            if name == new_tool_name:
                continue
            if self._extract_base_name(name) == base_name:
                similar_count += 1

        # Ab 3 aehnlichen Tools: Pattern aufzeichnen
        if similar_count >= 2:
            self.meta_rules.record_pattern(
                "tool_version_sprawl",
                f"3+ aehnliche Tools: {base_name}* — "
                f"NUTZE update_tool() ODER combine_tools() statt Neuanlage. "
                f"Versionssuffix (_v2, _v3) ist ein Anti-Pattern."
            )
            logger.info(
                f"Tool-Version-Sprawl erkannt: {new_tool_name} "
                f"({similar_count} aehnliche Tools)"
            )

    def check_failure_loop(self, tool_name: str, was_error: bool) -> None:
        """Erkennt Failure-Loops: Gleiches Tool scheitert wiederholt.

        Wird nach jeder use_tool-Ausfuehrung aufgerufen.

        Args:
            tool_name: Name des genutzten Tools
            was_error: True wenn Ausfuehrung fehlschlug
        """
        if was_error:
            self._consecutive_failures[tool_name] = \
                self._consecutive_failures.get(tool_name, 0) + 1
        else:
            # Reset bei Erfolg
            self._consecutive_failures[tool_name] = 0
            return

        count = self._consecutive_failures[tool_name]

        if count >= FAILURE_THRESHOLD:
            self.meta_rules.record_pattern(
                f"tool_failure_loop_{tool_name}",
                f"Tool '{tool_name}' ist {count}x hintereinander fehlgeschlagen. "
                f"STOPPE Nutzung dieses Tools. Optionen:\n"
                f"1. Tool mit update_tool() reparieren\n"
                f"2. Tool archivieren und Alternative suchen\n"
                f"3. Fehlerursache analysieren bevor erneuter Versuch"
            )
            logger.warning(
                f"Tool-Failure-Loop: {tool_name} {count}x fehlgeschlagen"
            )

    def check_orphan_creation(self, tool_name: str,
                               uses: int,
                               created_iso: str) -> None:
        """Erkennt Orphan-Erstellungen: Tools ohne Nutzung nach Erstellung.

        Wird periodisch geprueft (z.B. im Dream-Zyklus).

        Args:
            tool_name: Name des Tools
            uses: Nutzungszaehler des Tools
            created_iso: ISO-Timestamp der Erstellung
        """
        if uses > 0:
            return

        if not created_iso:
            return

        # Alter in Tagen berechnen
        from datetime import datetime, timezone
        try:
            created_dt = datetime.fromisoformat(created_iso)
            age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
        except (ValueError, TypeError):
            return

        # Mindestens 3 Tage alt und 0 Nutzungen → Orphan
        if age_days >= 3:
            self.meta_rules.record_pattern(
                "tool_orphan_creation",
                f"Tool '{tool_name}' wurde vor {age_days:.0f} Tagen "
                f"erstellt aber nie benutzt. "
                f"ERSTELLE TOOLS NUR MIT KONKRETEM NUTZUNGSPLAN. "
                f"Jedes Tool muss innerhalb weniger Tage mindestens 1x genutzt werden."
            )
            logger.info(
                f"Orphan-Tool erkannt: {tool_name} "
                f"(0 Nutzungen nach {age_days:.0f} Tagen)"
            )

    @staticmethod
    def _extract_base_name(tool_name: str) -> str:
        """Extrahiert Basis-Namen ohne Versionssuffix.

        Beispiele:
            enhanced_file_checker_v2 → enhanced_file_checker
            api_tool_v3_fixed → api_tool
            simple_checker → simple_checker
        """
        import re
        # Entferne gaengige Suffixe: _v2, _v3, _final, _fixed, _improved, _enhanced
        cleaned = re.sub(
            r'(_v\d+|_final|_fixed|_improved|_enhanced|_unified|_new)$',
            '', tool_name
        )
        # Wiederhole fuer mehrfache Suffixe (_v3_fixed)
        cleaned = re.sub(
            r'(_v\d+|_final|_fixed|_improved|_enhanced|_unified|_new)$',
            '', cleaned
        )
        return cleaned
