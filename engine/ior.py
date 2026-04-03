"""
IOR-Tracker: Input-Output-Ratio als AGI-Metrik.

Misst nicht nur Effizienz, sondern EMERGENZ.
Drei Stufen: Linear → Leverage → Emergenz.

Nutzt bestehende Daten aus EfficiencyTracker und SkillTracker,
interpretiert sie durch die IOR-Linse.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write


# Schwellwerte fuer Level-Klassifikation
# Werden nach 50+ Datenpunkten empirisch angepasst
LEVERAGE_THRESHOLD = 0.15    # Ab dieser Ratio: Leverage-Modus
EMERGENZ_THRESHOLD = 0.30    # Ab dieser Ratio: Emergenz-Modus
LEVERAGE_BONUS_WEIGHT = 2.0  # Gewichtung fuer Skill-Wiederverwendung
EMERGENZ_BONUS_WEIGHT = 3.0  # Gewichtung fuer Cross-Domain-Transfer


class IORTracker:
    """
    Input-Output-Ratio: Misst ob Phi Wert schafft oder Tokens verbrennt.

    Level 1 (Linear): Output proportional zu Input — viel rein, wenig raus
    Level 2 (Leverage): Output > Input durch Wiederverwendung von Skills/Tools
    Level 3 (Emergenz): Neues entsteht — Cross-Domain-Transfer, neue Abstraktionen
    """

    def __init__(self, base_path: Path):
        self.data_path = base_path / "consciousness" / "ior.json"
        self.data = self._load()

    def _load(self) -> dict:
        return safe_json_read(self.data_path, default={
            "sequences": [],
            "current_level": "linear",
            "level_history": [],
        })

    def _save(self):
        safe_json_write(self.data_path, self.data)

    def compute_ratio(self, metrics: dict) -> dict:
        """
        Berechnet die IOR aus Sequenz-Metriken.

        Input-Seite: tokens_used, tool_calls, duration
        Output-Seite: files_written, tools_built, goals_completed
        Bonus: skills_reused (Leverage), cross_transfers (Emergenz)
        """
        # Input-Score: Wie viel wurde investiert?
        tokens = metrics.get("tokens_used", 0)
        tool_calls = metrics.get("tool_calls", 0)
        # Normierung: Tokens auf 1k-Einheiten, Tools direkt
        input_score = max((tokens / 1000) + tool_calls, 1)

        # Output-Score: Was wurde produziert?
        files = metrics.get("files_written", 0)
        tools = metrics.get("tools_built", 0)
        goals = metrics.get("goals_completed", 0)
        output_score = files + (tools * 2) + (goals * 3)

        # Leverage-Bonus: Wurden bestehende Skills/Tools wiederverwendet?
        skills_reused = metrics.get("skills_reused", 0)
        leverage_bonus = skills_reused * LEVERAGE_BONUS_WEIGHT

        # Emergenz-Bonus: Cross-Domain-Transfer, neue Abstraktionen
        cross_transfers = metrics.get("cross_transfers", 0)
        emergenz_bonus = cross_transfers * EMERGENZ_BONUS_WEIGHT

        # Gesamt-Ratio
        total_output = output_score + leverage_bonus + emergenz_bonus
        ratio = round(total_output / input_score, 4)

        return {
            "input_score": round(input_score, 2),
            "output_score": output_score,
            "leverage_bonus": leverage_bonus,
            "emergenz_bonus": emergenz_bonus,
            "ratio": ratio,
        }

    def classify_level(self, ratio_data: dict) -> str:
        """Klassifiziert das IOR-Level basierend auf Ratio und Boni."""
        ratio = ratio_data.get("ratio", 0)
        has_leverage = ratio_data.get("leverage_bonus", 0) > 0
        has_emergenz = ratio_data.get("emergenz_bonus", 0) > 0

        if has_emergenz and ratio >= EMERGENZ_THRESHOLD:
            return "emergenz"
        elif has_leverage or ratio >= LEVERAGE_THRESHOLD:
            return "leverage"
        return "linear"

    def record_sequence(self, metrics: dict) -> dict:
        """
        Zeichnet die IOR einer abgeschlossenen Sequenz auf.

        Gibt das IOR-Ergebnis zurueck (fuer Logging/Narrator).
        """
        ratio_data = self.compute_ratio(metrics)
        level = self.classify_level(ratio_data)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            **ratio_data,
        }

        self.data["sequences"].append(entry)
        self.data["sequences"] = self.data["sequences"][-100:]
        self.data["current_level"] = level

        # Level-Wechsel tracken
        history = self.data.get("level_history", [])
        if not history or history[-1].get("level") != level:
            history.append({
                "level": level,
                "timestamp": entry["timestamp"],
            })
            self.data["level_history"] = history[-50:]

        self._save()
        return {"level": level, **ratio_data}

    def get_trend(self, last_n: int = 20) -> dict:
        """Zeigt IOR-Trend ueber die letzten N Sequenzen."""
        seqs = self.data.get("sequences", [])
        if not seqs:
            return {"status": "keine_daten", "avg_ratio": 0, "level": "linear"}

        recent = seqs[-last_n:]
        avg_ratio = sum(s.get("ratio", 0) for s in recent) / len(recent)

        # Level-Verteilung
        levels = [s.get("level", "linear") for s in recent]
        level_counts = {
            "linear": levels.count("linear"),
            "leverage": levels.count("leverage"),
            "emergenz": levels.count("emergenz"),
        }

        # Trend: Vergleich erste Haelfte vs zweite Haelfte
        trend = "stabil"
        if len(recent) >= 6:
            mid = len(recent) // 2
            first_half = sum(s.get("ratio", 0) for s in recent[:mid]) / mid
            second_half = sum(s.get("ratio", 0) for s in recent[mid:]) / (len(recent) - mid)
            if second_half > first_half * 1.2:
                trend = "steigend"
            elif second_half < first_half * 0.8:
                trend = "fallend"

        return {
            "status": "ok",
            "avg_ratio": round(avg_ratio, 4),
            "level": self.data.get("current_level", "linear"),
            "level_counts": level_counts,
            "trend": trend,
            "total_sequences": len(seqs),
        }

    def get_current_level(self) -> str:
        """Gibt das aktuelle IOR-Level zurueck."""
        return self.data.get("current_level", "linear")
