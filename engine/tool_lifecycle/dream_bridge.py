"""
Dream-Bridge — Tool-Bewusstsein fuer die Dream-Konsolidierung.

dream.py:_gather_all_memory() liest Beliefs, Strategies, Skills, Failures,
Metacognition — aber ignoriert Tools komplett. Phi "traeumt" nie ueber
ihre Werkzeuge. Dieses Modul liefert kompakte Tool-Daten fuer den
Dream-Context, damit Phi sich ihrer Tools bewusst wird.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.toolchain import Toolchain
    from engine.tool_lifecycle.metrics import ToolMetrics

logger = logging.getLogger(__name__)

# Token-Budget: Dream-Context nicht sprengen
MAX_TOOL_MEMORY_CHARS = 1500


class ToolDreamBridge:
    """Liefert Tool-Oekosystem-Daten fuer die Dream-Konsolidierung."""

    def __init__(self, toolchain: "Toolchain", metrics: "ToolMetrics"):
        self.toolchain = toolchain
        self.metrics = metrics

    def gather_tool_memory(self) -> str:
        """Kompakter Ueberblick fuer Dream-Context.

        Enthaelt:
        - Oekosystem-Zusammenfassung (Anzahl, Avg Health)
        - Top 5 Tools (hoechster Health-Score)
        - Bottom 3 Tools (Archivierungs-Kandidaten)
        - Kuerzlich archivierte Tools + Gruende
        - Konsolidierungs-Hinweise

        Returns:
            Formatierter String, max ~500 Tokens.
        """
        parts = []
        registry = self.toolchain.registry.get("tools", {})
        report = self.metrics.get_report()

        # Oekosystem-Summary
        active = sum(1 for info in registry.values()
                     if info.get("status") != "archived")
        archived = sum(1 for info in registry.values()
                       if info.get("status") == "archived")

        parts.append(
            f"Aktiv: {active} | Archiviert: {archived} | "
            f"Avg Health: {report['avg_health']}/10 | "
            f"Nutzungen gesamt: {report['total_uses']} | "
            f"Erfolge: {report['total_successes']} | "
            f"Fehler: {report['total_failures']}"
        )

        # Top 5 Tools
        top = report.get("top_tools", [])
        if top:
            lines = []
            for t in top[:5]:
                lines.append(
                    f"  {t['name']}: Health {t['health_score']}/10, "
                    f"{t['uses']}x genutzt, {t['success_rate']:.0%} Erfolg"
                )
            parts.append("TOP TOOLS:\n" + "\n".join(lines))

        # Problemfaelle
        unhealthy = report.get("unhealthy_tools", [])
        if unhealthy:
            lines = []
            for t in unhealthy[:3]:
                lines.append(
                    f"  {t['name']}: Health {t['health_score']}/10, "
                    f"{t['total_calls']}x genutzt, {t['success_rate']:.0%} Erfolg"
                )
            parts.append("PROBLEM-TOOLS:\n" + "\n".join(lines))

        # Stale Tools
        stale = report.get("stale_tools", [])
        if stale:
            parts.append(f"VERALTET (>{14} Tage ungenutzt): {', '.join(stale[:5])}")

        # Kuerzlich archivierte
        recently_archived = self._get_recently_archived(registry, days=30)
        if recently_archived:
            lines = []
            for name, reason in recently_archived[:3]:
                lines.append(f"  {name}: {reason}")
            parts.append("KUERZLICH ARCHIVIERT:\n" + "\n".join(lines))

        result = "\n".join(parts)

        # Token-Budget einhalten
        if len(result) > MAX_TOOL_MEMORY_CHARS:
            result = result[:MAX_TOOL_MEMORY_CHARS] + "\n[... gekuerzt]"

        return result

    def _get_recently_archived(self, registry: dict,
                                days: int = 30) -> list[tuple[str, str]]:
        """Findet kuerzlich archivierte Tools mit Gruenden."""
        now = datetime.now(timezone.utc)
        results = []

        for name, info in registry.items():
            if info.get("status") != "archived":
                continue
            archived_date = info.get("archived_date", "")
            if not archived_date:
                continue
            try:
                dt = datetime.fromisoformat(archived_date)
                age = (now - dt).total_seconds() / 86400
                if age <= days:
                    reason = info.get("archived_reason", "kein Grund angegeben")
                    results.append((name, reason))
            except (ValueError, TypeError):
                continue

        return results
