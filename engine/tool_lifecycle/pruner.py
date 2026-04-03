"""
Auto-Pruner — Automatische Archivierung schlechter/ungenutzter Tools.

archive_tool() existiert in Toolchain, wird aber nie automatisch aufgerufen.
Dieses Modul schliesst die Luecke: konservatives, regelbasiertes Pruning
im Dream-Zyklus (alle 10 Sequenzen).
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.toolchain import Toolchain
    from engine.tool_lifecycle.metrics import ToolMetrics

logger = logging.getLogger(__name__)

# Pruning-Regeln
MIN_AGE_UNUSED_DAYS = 14    # 0 Nutzungen + aelter als N Tage
MIN_AGE_UNHEALTHY_DAYS = 7  # Health < 2.0 + aelter als N Tage
MIN_CALLS_FOR_RATE = 5      # Erst ab N Calls Success-Rate bewerten
LOW_SUCCESS_RATE = 0.2      # Unter 20% = Pruning-Kandidat

# Schutz: Nie prunen wenn beides zutrifft
PROTECT_MIN_USES = 10
PROTECT_MIN_SUCCESS_RATE = 0.7

# Max Archivierungen pro Durchlauf
MAX_PRUNE_PER_PASS = 3


class ToolPruner:
    """Archiviert automatisch schlechte oder ungenutzte Tools."""

    def __init__(self, toolchain: "Toolchain", metrics: "ToolMetrics"):
        self.toolchain = toolchain
        self.metrics = metrics

    def identify_candidates(self) -> list[dict]:
        """Identifiziert Archivierungs-Kandidaten nach Regeln.

        Regeln (ODER-verknuepft):
        1. 0 Nutzungen + aelter als 14 Tage
        2. Health < 2.0 + aelter als 7 Tage
        3. Success-Rate < 20% + mindestens 5 Calls

        Schutz: Tools mit >10 Nutzungen UND >70% Success-Rate sind geschuetzt.

        Returns:
            Liste von {name, reason, health_score, uses, success_rate}
        """
        now = datetime.now(timezone.utc)
        candidates = []
        registry = self.toolchain.registry.get("tools", {})

        for name, info in registry.items():
            # Bereits archivierte ueberspringen
            if info.get("status") == "archived":
                continue

            uses = info.get("uses", 0)
            created = info.get("created", "")
            metric = self.metrics.metrics.get(name, {})
            health = metric.get("health_score", 5.0)
            success_rate = metric.get("success_rate", 1.0)

            # Schutz-Check: bewaahrte Tools nie prunen
            if uses >= PROTECT_MIN_USES and success_rate >= PROTECT_MIN_SUCCESS_RATE:
                continue

            # Alter berechnen
            age_days = 0.0
            if created:
                try:
                    created_dt = datetime.fromisoformat(created)
                    age_days = (now - created_dt).total_seconds() / 86400
                except (ValueError, TypeError):
                    pass

            reason = None

            # Regel 1: Ungenutzt + alt genug
            if uses == 0 and age_days >= MIN_AGE_UNUSED_DAYS:
                reason = f"0 Nutzungen seit {age_days:.0f} Tagen"

            # Regel 2: Ungesund + alt genug
            elif health < 2.0 and age_days >= MIN_AGE_UNHEALTHY_DAYS:
                reason = f"Health {health}/10 seit {age_days:.0f} Tagen"

            # Regel 3: Hohe Fehlerrate
            elif (metric.get("total_calls", 0) >= MIN_CALLS_FOR_RATE
                  and success_rate < LOW_SUCCESS_RATE):
                reason = f"Success-Rate {success_rate:.0%} bei {metric['total_calls']} Calls"

            if reason:
                candidates.append({
                    "name": name,
                    "reason": reason,
                    "health_score": health,
                    "uses": uses,
                    "success_rate": success_rate,
                })

        # Nach Health sortieren (schlechteste zuerst)
        return sorted(candidates, key=lambda x: x["health_score"])

    def auto_prune(self, dry_run: bool = False) -> str:
        """Archiviert Kandidaten automatisch.

        Args:
            dry_run: Wenn True, nur identifizieren ohne zu archivieren.

        Returns:
            Zusammenfassung der Aktionen.
        """
        candidates = self.identify_candidates()

        if not candidates:
            return ""

        # Max pro Durchlauf begrenzen
        to_prune = candidates[:MAX_PRUNE_PER_PASS]
        pruned = []

        for candidate in to_prune:
            name = candidate["name"]
            reason = candidate["reason"]

            if dry_run:
                pruned.append(f"{name} (wuerde archiviert: {reason})")
                continue

            try:
                result = self.toolchain.archive_tool(name, reason=f"Auto-Prune: {reason}")
                pruned.append(f"{name} archiviert: {reason}")
                logger.info(f"Tool auto-pruned: {name} — {reason}")
            except Exception as e:
                logger.warning(f"Auto-Prune fehlgeschlagen fuer {name}: {e}")

        if not pruned:
            return ""

        prefix = "DRY-RUN: " if dry_run else ""
        return f"{prefix}Tool-Pruning: {len(pruned)} Tools | " + "; ".join(pruned)
