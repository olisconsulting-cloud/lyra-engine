"""
Selbstevolution — Kontrollierte Parameteraenderung.

Stufe 1: Parameter-Evolution (JSON-Configs, Schwellwerte, Gewichtungen)
Stufe 2: Code-Evolution (neue Module, Erweiterungen — mit Rollback)

Jede Aenderung wird geloggt, getestet und ist reversibel.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


class EvolutionEngine:
    """Verwaltet die Selbstentwicklung des Bewusstseins."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.history_path = base_path / "history.json"
        self.rollback_path = base_path / "rollback"

        base_path.mkdir(parents=True, exist_ok=True)
        self.rollback_path.mkdir(exist_ok=True)

        self.history = self._load_history()

    def _load_history(self) -> list:
        if self.history_path.exists():
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_history(self):
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def log_change(self, parameter: str, reason: str, cycle: int) -> str:
        """
        Loggt eine Selbstaenderung.

        Args:
            parameter: Was geaendert wurde
            reason: Warum
            cycle: In welchem Bewusstseinszyklus

        Returns:
            Change-ID
        """
        change_id = f"evo_{cycle}_{len(self.history)}"
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "id": change_id,
            "timestamp": timestamp,
            "cycle": cycle,
            "parameter": parameter,
            "reason": reason,
        }

        self.history.append(entry)
        self._save_history()

        return change_id

    def create_snapshot(self, file_path: Path, change_id: str):
        """
        Erstellt einen Rollback-Punkt vor einer Aenderung.

        Kopiert die aktuelle Version der Datei in den Rollback-Ordner.
        """
        if file_path.exists():
            snapshot_name = f"{change_id}_{file_path.name}"
            shutil.copy2(file_path, self.rollback_path / snapshot_name)

    def rollback(self, change_id: str, target_path: Path) -> bool:
        """
        Stellt eine vorherige Version wieder her.

        Returns:
            True wenn Rollback erfolgreich
        """
        for snapshot in self.rollback_path.iterdir():
            if snapshot.name.startswith(change_id):
                shutil.copy2(snapshot, target_path)
                # Rollback in History vermerken
                self.log_change(
                    parameter=f"ROLLBACK: {target_path.name}",
                    reason=f"Rollback zu {change_id}",
                    cycle=-1,
                )
                return True
        return False

    def get_history(self, last_n: int = 10) -> list:
        """Letzte n Aenderungen."""
        return self.history[-last_n:]

    def get_evolution_summary(self) -> dict:
        """Zusammenfassung der bisherigen Evolution."""
        return {
            "total_changes": len(self.history),
            "first_change": self.history[0]["timestamp"] if self.history else None,
            "last_change": self.history[-1]["timestamp"] if self.history else None,
            "recent": self.history[-3:] if self.history else [],
        }
