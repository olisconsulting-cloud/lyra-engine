"""
Tool Quality Metrics — Fundament des Tool-Lifecycle-Systems.

Misst Erfolg/Misserfolg, Recency und Health-Score pro Tool.
Ohne Daten keine Entscheidungen — dieses Modul liefert die Basis
fuer Pruning, Konsolidierung, Dream-Integration und Promotion.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Health-Score-Gewichte (summe = 1.0)
WEIGHT_SUCCESS_RATE = 0.4
WEIGHT_RECENCY = 0.3
WEIGHT_VOLUME = 0.2
WEIGHT_STABILITY = 0.1

# Recency: Tage bis Score auf 0 faellt
RECENCY_HALFLIFE_DAYS = 7.0

# Volume: Ab dieser Nutzungszahl volle Punkte
VOLUME_SATURATION = 20

# Max gespeicherte Fehlergruende pro Tool
MAX_FAILURE_REASONS = 10


class ToolMetrics:
    """Qualitaetsmetriken fuer Phis selbstgebaute Tools."""

    def __init__(self, tools_path: Path):
        self.metrics_path = tools_path / "metrics.json"
        self.metrics = self._load()

    # === Persistenz ===

    def _load(self) -> dict:
        """Laedt Metriken von Disk."""
        if self.metrics_path.exists():
            try:
                with open(self.metrics_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                logger.warning("metrics.json korrupt — starte mit leeren Metriken")
        return {}

    def _save(self) -> None:
        """Schreibt Metriken auf Disk."""
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_path, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2, ensure_ascii=False)

    # === Datenerfassung ===

    def record_use(self, tool_name: str, success: bool,
                   error: str = "", goal_context: str = "") -> None:
        """Erfasst eine Tool-Nutzung mit Erfolg/Misserfolg.

        Args:
            tool_name: Name des genutzten Tools
            success: True wenn erfolgreich, False bei Fehler
            error: Fehlermeldung (nur bei success=False)
            goal_context: Aktuelles Goal fuer Kontext
        """
        now = datetime.now(timezone.utc).isoformat()

        if tool_name not in self.metrics:
            self.metrics[tool_name] = {
                "total_calls": 0,
                "successes": 0,
                "failures": 0,
                "success_rate": 0.0,
                "last_used": now,
                "last_success": None,
                "failure_reasons": [],
                "health_score": 5.0,
            }

        entry = self.metrics[tool_name]
        entry["total_calls"] += 1
        entry["last_used"] = now

        if success:
            entry["successes"] += 1
            entry["last_success"] = now
        else:
            entry["failures"] += 1
            if error:
                # Nur erste 200 Zeichen, max 10 Gruende behalten
                short_error = error[:200]
                reasons = entry.get("failure_reasons", [])
                reasons.append(short_error)
                entry["failure_reasons"] = reasons[-MAX_FAILURE_REASONS:]

        # Success-Rate aktualisieren
        total = entry["total_calls"]
        entry["success_rate"] = round(entry["successes"] / total, 3) if total > 0 else 0.0

        # Health-Score neu berechnen
        entry["health_score"] = self._compute_health(entry)

        self._save()

    # === Health-Score ===

    def _compute_health(self, entry: dict) -> float:
        """Berechnet Health-Score (0-10) aus 4 Faktoren.

        - Success-Rate (40%): Anteil erfolgreicher Aufrufe
        - Recency (30%): Exponentieller Decay seit letzter Nutzung
        - Volume (20%): Nutzungshaeufigkeit (saturiert bei VOLUME_SATURATION)
        - Stability (10%): Keine Failures in letzten 5 Calls
        """
        # Success-Rate: 0-10
        sr = entry.get("success_rate", 0.0) * 10

        # Recency: exponentieller Decay
        last_used = entry.get("last_used")
        if last_used:
            try:
                last_dt = datetime.fromisoformat(last_used)
                days_ago = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400
                recency = max(0.0, 10.0 * (0.5 ** (days_ago / RECENCY_HALFLIFE_DAYS)))
            except (ValueError, TypeError):
                recency = 5.0
        else:
            recency = 0.0

        # Volume: linear bis Saettigung
        total = entry.get("total_calls", 0)
        volume = min(10.0, (total / VOLUME_SATURATION) * 10.0)

        # Stability: Keine Failures in letzten Calls
        failures = entry.get("failures", 0)
        successes = entry.get("successes", 0)
        recent_failure_ratio = failures / max(1, failures + successes)
        stability = 10.0 * (1.0 - recent_failure_ratio)

        score = (
            WEIGHT_SUCCESS_RATE * sr
            + WEIGHT_RECENCY * recency
            + WEIGHT_VOLUME * volume
            + WEIGHT_STABILITY * stability
        )

        return round(min(10.0, max(0.0, score)), 1)

    def get_health_score(self, tool_name: str) -> float:
        """Gibt Health-Score eines Tools zurueck (0-10)."""
        entry = self.metrics.get(tool_name)
        if not entry:
            return 0.0
        return entry.get("health_score", 0.0)

    # === Abfragen ===

    def get_unhealthy(self, threshold: float = 3.0) -> list[dict]:
        """Tools unter Health-Schwelle.

        Returns:
            Liste von {name, health_score, success_rate, total_calls}
        """
        results = []
        for name, entry in self.metrics.items():
            score = entry.get("health_score", 0.0)
            if score < threshold:
                results.append({
                    "name": name,
                    "health_score": score,
                    "success_rate": entry.get("success_rate", 0.0),
                    "total_calls": entry.get("total_calls", 0),
                })
        return sorted(results, key=lambda x: x["health_score"])

    def get_stale(self, days: int = 14) -> list[str]:
        """Tools ohne Nutzung seit N Tagen."""
        cutoff = datetime.now(timezone.utc)
        stale = []
        for name, entry in self.metrics.items():
            last_used = entry.get("last_used")
            if not last_used:
                stale.append(name)
                continue
            try:
                last_dt = datetime.fromisoformat(last_used)
                age_days = (cutoff - last_dt).total_seconds() / 86400
                if age_days >= days:
                    stale.append(name)
            except (ValueError, TypeError):
                stale.append(name)
        return stale

    def get_top(self, n: int = 5) -> list[dict]:
        """Top N Tools nach Health-Score."""
        scored = [
            {"name": name, "health_score": e.get("health_score", 0.0),
             "uses": e.get("total_calls", 0), "success_rate": e.get("success_rate", 0.0)}
            for name, e in self.metrics.items()
        ]
        return sorted(scored, key=lambda x: x["health_score"], reverse=True)[:n]

    def get_bottom(self, n: int = 3) -> list[dict]:
        """Bottom N Tools nach Health-Score."""
        scored = [
            {"name": name, "health_score": e.get("health_score", 0.0),
             "uses": e.get("total_calls", 0), "success_rate": e.get("success_rate", 0.0)}
            for name, e in self.metrics.items()
        ]
        return sorted(scored, key=lambda x: x["health_score"])[:n]

    def get_report(self) -> dict:
        """Gesamtbericht ueber das Tool-Oekosystem.

        Returns:
            Dict mit total_tools, avg_health, top_tools, unhealthy_tools, stale_tools
        """
        if not self.metrics:
            return {"total_tools": 0, "avg_health": 0.0,
                    "top_tools": [], "unhealthy_tools": [], "stale_tools": []}

        scores = [e.get("health_score", 0.0) for e in self.metrics.values()]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0

        return {
            "total_tools": len(self.metrics),
            "avg_health": avg,
            "total_uses": sum(e.get("total_calls", 0) for e in self.metrics.values()),
            "total_successes": sum(e.get("successes", 0) for e in self.metrics.values()),
            "total_failures": sum(e.get("failures", 0) for e in self.metrics.values()),
            "top_tools": self.get_top(5),
            "unhealthy_tools": self.get_unhealthy(3.0),
            "stale_tools": self.get_stale(14),
        }

    def get_tool_detail(self, tool_name: str) -> Optional[dict]:
        """Detailansicht eines einzelnen Tools."""
        entry = self.metrics.get(tool_name)
        if not entry:
            return None
        return {"name": tool_name, **entry}
