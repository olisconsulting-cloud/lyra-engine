"""
Auto-Consolidator — Vereinigt aehnliche Tools automatisch.

ToolCurator.suggest_consolidation() findet Gruppen aehnlicher Tools.
ToolFoundry.combine_tools() kann zwei Tools mergen.
Dieses Modul verbindet beide: findet Gruppen, waehlt die Basis,
merged, archiviert die Alten, setzt Aliases.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.evolution import ToolCurator, ToolFoundry
    from engine.toolchain import Toolchain
    from engine.tool_lifecycle.metrics import ToolMetrics

logger = logging.getLogger(__name__)

# Max Konsolidierungen pro Dream-Zyklus
MAX_CONSOLIDATIONS_PER_PASS = 1

# Mindest-Gruppengroesse fuer Konsolidierung
MIN_GROUP_SIZE = 2


class ToolConsolidator:
    """Konsolidiert aehnliche Tools automatisch im Dream-Zyklus."""

    def __init__(self, curator: "ToolCurator", foundry: "ToolFoundry",
                 toolchain: "Toolchain", metrics: "ToolMetrics"):
        self.curator = curator
        self.foundry = foundry
        self.toolchain = toolchain
        self.metrics = metrics

    def find_consolidation_groups(self) -> list[dict]:
        """Findet Gruppen aehnlicher Tools, angereichert mit Health-Scores.

        Nutzt curator.suggest_consolidation() als Basis, fuegt
        Health-Metriken hinzu und sortiert nach Konsolidierungs-Potential.

        Returns:
            Liste von {tools: [...], basis: str, health_scores: {}, priority: float}
        """
        raw_groups = self.curator.suggest_consolidation()
        enriched = []

        for group in raw_groups:
            tool_names = group.get("tools", [])
            if len(tool_names) < MIN_GROUP_SIZE:
                continue

            # Health-Scores sammeln
            health_scores = {}
            for name in tool_names:
                health_scores[name] = self.metrics.get_health_score(name)

            # Basis = Tool mit hoechstem Health-Score
            basis = max(tool_names, key=lambda n: health_scores.get(n, 0.0))

            # Prioritaet: mehr Tools in Gruppe + niedrigere Avg Health der Nicht-Basis
            others_health = [
                health_scores[n] for n in tool_names if n != basis
            ]
            avg_others = sum(others_health) / len(others_health) if others_health else 5.0
            priority = len(tool_names) * (10.0 - avg_others)

            enriched.append({
                "tools": tool_names,
                "basis": basis,
                "health_scores": health_scores,
                "priority": round(priority, 1),
            })

        # Nach Prioritaet sortieren (hoechste zuerst)
        return sorted(enriched, key=lambda x: x["priority"], reverse=True)

    def consolidate_group(self, group: dict) -> str:
        """Konsolidiert eine Gruppe aehnlicher Tools.

        Ablauf:
        1. Waehlt Basis-Tool (hoechster Health-Score)
        2. Kombiniert paarweise mit ToolFoundry
        3. Archiviert alte Tools
        4. Setzt Aliases fuer alte Namen

        Args:
            group: Dict mit tools, basis, health_scores

        Returns:
            Zusammenfassung der Konsolidierung.
        """
        tool_names = group["tools"]
        basis = group["basis"]
        others = [n for n in tool_names if n != basis]

        if not others:
            return "Keine Tools zum Konsolidieren."

        # Neuen Namen generieren: "unified_" + Basis
        new_name = basis if basis.startswith("unified_") else f"unified_{basis}"

        # Nur mit dem ersten "anderen" Tool kombinieren
        # (bei 3+ Tools: iterativ in mehreren Dream-Zyklen)
        other = others[0]

        try:
            result = self.foundry.combine_tools(
                basis, other, new_name, self.toolchain
            )

            if "FEHLER" in result:
                logger.warning(f"Konsolidierung fehlgeschlagen: {result}")
                return f"Konsolidierung fehlgeschlagen: {result[:200]}"

            # Alte Tools archivieren
            archived = []
            for old_name in [basis, other]:
                if old_name != new_name:
                    try:
                        self.toolchain.archive_tool(
                            old_name,
                            reason=f"Konsolidiert in {new_name}"
                        )
                        # Alias setzen
                        self.toolchain.add_alias(old_name, new_name)
                        archived.append(old_name)
                    except Exception as e:
                        logger.warning(f"Archivierung von {old_name} fehlgeschlagen: {e}")

            summary = (
                f"Konsolidiert: {basis} + {other} → {new_name} | "
                f"Archiviert: {', '.join(archived)}"
            )
            logger.info(summary)
            return summary

        except Exception as e:
            logger.error(f"Konsolidierung fehlgeschlagen: {e}")
            return f"Konsolidierung fehlgeschlagen: {e}"

    def auto_consolidate(self, max_groups: int = MAX_CONSOLIDATIONS_PER_PASS) -> str:
        """Konsolidiert automatisch im Dream-Zyklus.

        Konservativ: Max 1 Gruppe pro Durchlauf.

        Returns:
            Zusammenfassung oder leerer String.
        """
        groups = self.find_consolidation_groups()

        if not groups:
            return ""

        results = []
        for group in groups[:max_groups]:
            result = self.consolidate_group(group)
            if result:
                results.append(result)

        return " | ".join(results) if results else ""
