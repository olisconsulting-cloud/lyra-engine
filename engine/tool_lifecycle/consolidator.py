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

        # Neuen Namen generieren — Kollision bei iterativer Konsolidierung vermeiden
        if basis.startswith("unified_"):
            # Bereits konsolidiert: Versionssuffix anhaengen
            import time
            new_name = f"{basis}_{int(time.time()) % 10000}"
        else:
            new_name = f"unified_{basis}"

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

            # Pre-Validate: Neues Tool muss in Registry sein bevor wir archivieren
            if new_name not in self.toolchain.registry.get("tools", {}):
                logger.error(f"Neues Tool {new_name} nicht in Registry — Archive abgebrochen")
                return f"Konsolidierung unsicher: {new_name} nicht registriert"

            # Alte Tools archivieren (Alias ZUERST, dann archivieren)
            archived = []
            for old_name in [basis, other]:
                if old_name == new_name:
                    continue
                try:
                    # Alias zuerst setzen — bei Fehler bleibt Tool aktiv
                    self.toolchain.add_alias(old_name, new_name)
                    self.toolchain.archive_tool(
                        old_name,
                        reason=f"Konsolidiert in {new_name}"
                    )
                    archived.append(old_name)
                except Exception as e:
                    logger.warning(f"Archivierung von {old_name} fehlgeschlagen: {e}")
                    # Rollback: Alias entfernen wenn Archive fehlschlaegt
                    self.toolchain.registry.get("aliases", {}).pop(old_name, None)

            # Metriken transferieren (akkumuliertes Wissen bewahren)
            self._transfer_metrics(basis, other, new_name)

            summary = (
                f"Konsolidiert: {basis} + {other} → {new_name} | "
                f"Archiviert: {', '.join(archived)}"
            )
            logger.info(summary)
            return summary

        except Exception as e:
            logger.error(f"Konsolidierung fehlgeschlagen: {e}")
            return f"Konsolidierung fehlgeschlagen: {e}"

    def _transfer_metrics(self, tool_a: str, tool_b: str, new_name: str) -> None:
        """Transferiert Metriken von Quell-Tools zum konsolidierten Tool.

        Bewahrt akkumuliertes Wissen: Uses summieren, Health-Score
        als gewichteten Durchschnitt initialisieren.
        """
        try:
            m_a = self.metrics.metrics.get(tool_a, {})
            m_b = self.metrics.metrics.get(tool_b, {})

            calls_a = m_a.get("total_calls", 0)
            calls_b = m_b.get("total_calls", 0)
            total = calls_a + calls_b

            if total == 0:
                return

            # Gewichteter Durchschnitt der Health-Scores
            health_a = m_a.get("health_score", 5.0)
            health_b = m_b.get("health_score", 5.0)
            avg_health = (health_a * calls_a + health_b * calls_b) / total

            # Goal-Kontexte vereinigen
            ctx_a = m_a.get("goal_contexts", {})
            ctx_b = m_b.get("goal_contexts", {})
            merged_ctx = dict(ctx_a)
            for k, v in ctx_b.items():
                merged_ctx[k] = merged_ctx.get(k, 0) + v

            self.metrics.metrics[new_name] = {
                "total_calls": total,
                "successes": m_a.get("successes", 0) + m_b.get("successes", 0),
                "failures": m_a.get("failures", 0) + m_b.get("failures", 0),
                "success_rate": round(
                    (m_a.get("successes", 0) + m_b.get("successes", 0)) / total, 3
                ),
                "last_used": max(
                    m_a.get("last_used", ""), m_b.get("last_used", "")
                ),
                "last_success": max(
                    m_a.get("last_success", "") or "",
                    m_b.get("last_success", "") or ""
                ),
                "failure_reasons": (
                    m_a.get("failure_reasons", [])[-5:]
                    + m_b.get("failure_reasons", [])[-5:]
                ),
                "recent_calls": [],  # Frisch starten fuer Stability
                "goal_contexts": merged_ctx,
                "health_score": round(avg_health, 1),
            }
            self.metrics._save()
        except Exception as e:
            logger.warning(f"Metriken-Transfer fehlgeschlagen: {e}")

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
