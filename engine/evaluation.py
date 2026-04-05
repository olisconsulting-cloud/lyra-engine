"""
Evaluations-Framework — Phis Spiegel.

Aggregiert alle Metriken-Quellen zu einem einzigen "Wird Phi besser?"-Signal.
Speichert Langzeit-Trends in data/consciousness/evaluation.json.

Quellen:
- EfficiencyTracker (intelligence.py) — Calls, Errors, Output, Kosten
- MetaCognition (evolution.py) — Engpaesse, Effizienz-Ratio
- SelfRating (extensions.py) — Selbstbewertung
- IORTracker (ior.py) — Input-Output-Ratio
- GoalStack (goal_stack.py) — Goal-Completion

Design-Prinzip: Nur aggregieren und bewerten, keine eigenen Daten sammeln.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.config import safe_json_write


class EvaluationEngine:
    """
    Aggregiert Metriken ueber Sequenzen und erkennt Langzeit-Trends.

    Checkpoint alle 10 Sequenzen: Snapshot aller KPIs → evaluation.json.
    Trend-Analyse: Vergleicht aktuelle vs. vorherige Checkpoints.
    """

    # KPI-Gewichte fuer den Gesamt-Score (0-100)
    # goal_completion_rate deaktiviert bis GoalStack echte Daten liefert
    WEIGHTS = {
        "efficiency_ratio": 0.35,       # Productive/Total Steps
        "goal_completion_rate": 0.0,    # DEAKTIVIERT — Goals noch nicht gezaehlt
        "error_rate_inv": 0.30,         # 1 - (Errors/Calls) — weniger Fehler = besser
        "output_per_token": 0.20,       # Files+Tools pro 1k Tokens
        "cost_efficiency": 0.15,        # Output pro Dollar
    }

    def __init__(self, data_path: Path):
        self.eval_path = data_path / "consciousness" / "evaluation.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.eval_path.exists():
            try:
                with open(self.eval_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError, OSError):
                pass
        return {"checkpoints": [], "current_window": []}

    def _save(self):
        safe_json_write(self.eval_path, self.data)

    # --- Daten sammeln ---

    def record_sequence(self, metrics: dict[str, Any]):
        """
        Empfaengt Sequenz-Metriken am Ende jeder Sequenz.

        metrics: {
            seq_num, tool_calls, errors, files_written, tools_built,
            goals_completed, goals_attempted, tokens_used, cost,
            productive_steps, wasted_steps, duration_seconds
        }
        """
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": metrics.get("seq_num", 0),
            **{k: v for k, v in metrics.items() if k != "seq_num"},
        }
        self.data["current_window"].append(entry)
        # Window auf 50 Sequenzen begrenzen
        self.data["current_window"] = self.data["current_window"][-50:]
        self._save()

    def checkpoint(self, seq_num: int) -> dict[str, Any] | None:
        """
        Erstellt einen Checkpoint alle 10 Sequenzen.
        Aggregiert current_window zu KPIs und speichert als Snapshot.

        Returns: Checkpoint-Dict oder None wenn zu wenig Daten.
        """
        window = self.data["current_window"]
        if len(window) < 3:
            return None

        kpis = self._compute_kpis(window)
        score = self._compute_score(kpis)
        trend = self._compute_trend(score)

        checkpoint = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": seq_num,
            "window_size": len(window),
            "kpis": kpis,
            "score": round(score, 1),
            "trend": trend,
        }

        self.data["checkpoints"].append(checkpoint)
        # Max 100 Checkpoints behalten (~1000 Sequenzen)
        self.data["checkpoints"] = self.data["checkpoints"][-100:]
        self._save()
        return checkpoint

    # --- KPI-Berechnung ---

    def _compute_kpis(self, window: list[dict]) -> dict[str, float]:
        """Berechnet KPIs aus einem Sequenz-Fenster."""
        n = len(window)
        if n == 0:
            return {}

        total_productive = sum(e.get("productive_steps", 0) for e in window)
        total_wasted = sum(e.get("wasted_steps", 0) for e in window)
        total_steps = total_productive + total_wasted or 1

        total_calls = sum(e.get("tool_calls", 0) for e in window) or 1
        total_errors = sum(e.get("errors", 0) for e in window)

        total_files = sum(e.get("files_written", 0) for e in window)
        total_tools = sum(e.get("tools_built", 0) for e in window)
        total_output = total_files + total_tools * 3  # Tools gewichtet

        total_goals_completed = sum(e.get("goals_completed", 0) for e in window)
        total_goals_attempted = sum(e.get("goals_attempted", 0) for e in window) or 1

        total_tokens = sum(e.get("tokens_used", 0) for e in window) or 1
        total_cost = sum(e.get("cost", 0) for e in window) or 0.01

        return {
            "efficiency_ratio": round(total_productive / total_steps, 3),
            "goal_completion_rate": round(total_goals_completed / total_goals_attempted, 3),
            "error_rate": round(total_errors / total_calls, 3),
            "error_rate_inv": round(1 - (total_errors / total_calls), 3),
            "output_per_token": round((total_output / total_tokens) * 1000, 3),
            "cost_efficiency": round(total_output / total_cost, 2),
            "avg_tokens_per_seq": round(total_tokens / n),
            "avg_cost_per_seq": round(total_cost / n, 4),
            "avg_duration_sec": round(
                sum(e.get("duration_seconds", 0) for e in window) / n, 1
            ),
            "total_output": total_output,
            "sequences": n,
        }

    def _compute_score(self, kpis: dict[str, float]) -> float:
        """
        Berechnet einen gewichteten Gesamt-Score (0-100).
        Jede KPI wird auf 0-100 normalisiert, dann gewichtet.
        """
        if not kpis:
            return 0.0

        normalized = {}
        # Efficiency Ratio: 0.0-1.0 → 0-100
        normalized["efficiency_ratio"] = kpis.get("efficiency_ratio", 0) * 100
        # Goal Completion: 0.0-1.0 → 0-100
        normalized["goal_completion_rate"] = kpis.get("goal_completion_rate", 0) * 100
        # Error Rate Inv: 0.0-1.0 → 0-100
        normalized["error_rate_inv"] = kpis.get("error_rate_inv", 0) * 100
        # Output/Token: 0-2 ist typischer Bereich → clamp auf 0-100
        normalized["output_per_token"] = min(kpis.get("output_per_token", 0) * 50, 100)
        # Cost Efficiency: 0-200 typisch → clamp
        normalized["cost_efficiency"] = min(kpis.get("cost_efficiency", 0) * 0.5, 100)

        score = sum(
            normalized.get(k, 0) * w
            for k, w in self.WEIGHTS.items()
        )
        return max(0.0, min(100.0, score))

    def _compute_trend(self, current_score: float) -> str:
        """Vergleicht aktuellen Score mit letztem Checkpoint."""
        checkpoints = self.data["checkpoints"]
        if not checkpoints:
            return "baseline"

        last = checkpoints[-1]
        last_score = last.get("score", 0)
        diff = current_score - last_score

        if diff > 5:
            return "verbessernd"
        elif diff < -5:
            return "verschlechternd"
        return "stabil"

    # --- Abfragen ---

    def get_trend_summary(self) -> str:
        """
        Einzeiliger Trend-String fuer den System-Prompt.
        Format: "EVAL: 62.4/100 ↑ verbessernd (letzte 10 Seq)"
        """
        checkpoints = self.data["checkpoints"]
        if not checkpoints:
            window = self.data["current_window"]
            if len(window) < 3:
                return "EVAL: noch keine Daten"
            kpis = self._compute_kpis(window)
            score = self._compute_score(kpis)
            return f"EVAL: {score:.1f}/100 (baseline, {len(window)} Seq)"

        latest = checkpoints[-1]
        score = latest.get("score", 0)
        trend = latest.get("trend", "unbekannt")
        arrow = {"verbessernd": "↑", "verschlechternd": "↓", "stabil": "→"}.get(
            trend, "?"
        )
        window_size = latest.get("window_size", "?")
        return f"EVAL: {score:.1f}/100 {arrow} {trend} ({window_size} Seq)"

    def get_detailed_report(self) -> str:
        """Detaillierter Report fuer Dream/Audit."""
        checkpoints = self.data["checkpoints"]
        window = self.data["current_window"]

        if not window:
            return "Keine Evaluations-Daten vorhanden."

        kpis = self._compute_kpis(window)
        score = self._compute_score(kpis)

        lines = [
            f"=== EVALUATION REPORT (Seq {window[0].get('seq', '?')}-{window[-1].get('seq', '?')}) ===",
            f"Gesamt-Score: {score:.1f}/100",
            f"Effizienz-Ratio: {kpis.get('efficiency_ratio', 0):.1%}",
            f"Goal-Completion: {kpis.get('goal_completion_rate', 0):.1%}",
            f"Fehlerrate: {kpis.get('error_rate', 0):.1%}",
            f"Output/1k Tokens: {kpis.get('output_per_token', 0):.2f}",
            f"Output/$: {kpis.get('cost_efficiency', 0):.1f}",
            f"Ø Tokens/Seq: {kpis.get('avg_tokens_per_seq', 0):,}",
            f"Ø Kosten/Seq: ${kpis.get('avg_cost_per_seq', 0):.4f}",
            f"Ø Dauer/Seq: {kpis.get('avg_duration_sec', 0):.0f}s",
        ]

        # Trend ueber Checkpoints
        if len(checkpoints) >= 2:
            scores = [c["score"] for c in checkpoints[-5:]]
            lines.append(f"Score-Verlauf: {' → '.join(f'{s:.0f}' for s in scores)}")

            # Groesste Veraenderungen identifizieren
            prev_kpis = checkpoints[-1].get("kpis", {})
            changes = []
            for key in ["efficiency_ratio", "goal_completion_rate", "error_rate"]:
                old = prev_kpis.get(key, 0)
                new = kpis.get(key, 0)
                if old > 0:
                    pct = ((new - old) / old) * 100
                    if abs(pct) > 10:
                        changes.append(f"{key}: {pct:+.0f}%")
            if changes:
                lines.append(f"Groesste Aenderungen: {', '.join(changes)}")

        return "\n".join(lines)

    def get_alerts(self) -> list[str]:
        """Gibt Warnungen zurueck wenn KPIs kritisch sind."""
        window = self.data["current_window"]
        if len(window) < 5:
            return []

        kpis = self._compute_kpis(window[-10:])
        alerts = []

        # Effizienz unter 20%
        if kpis.get("efficiency_ratio", 1) < 0.2:
            alerts.append(
                f"Effizienz kritisch niedrig: {kpis['efficiency_ratio']:.0%} "
                f"— ueber 80% der Steps unproduktiv"
            )

        # Fehlerrate ueber 40%
        if kpis.get("error_rate", 0) > 0.4:
            alerts.append(
                f"Fehlerrate kritisch: {kpis['error_rate']:.0%} "
                f"— fast jeder zweite Call scheitert"
            )

        # Null-Output in letzten 5 Sequenzen
        recent_5 = window[-5:]
        total_output = sum(
            e.get("files_written", 0) + e.get("tools_built", 0)
            for e in recent_5
        )
        if total_output == 0:
            total_cost = sum(e.get("cost", 0) for e in recent_5)
            alerts.append(
                f"Kein Output in 5 Sequenzen bei ${total_cost:.2f} Kosten"
            )

        # Score-Absturz: letzter Checkpoint vs. aktuell
        checkpoints = self.data["checkpoints"]
        if checkpoints:
            last_score = checkpoints[-1]["score"]
            current_score = self._compute_score(kpis)
            if last_score > 0 and current_score < last_score * 0.7:
                alerts.append(
                    f"Score-Absturz: {last_score:.0f} → {current_score:.0f} "
                    f"(-{((last_score - current_score) / last_score) * 100:.0f}%)"
                )

        return alerts[:3]
