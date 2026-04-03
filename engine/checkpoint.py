"""
Checkpoint-System — Resilienz bei Token-Budget-Abbruechen.

Schreibt alle N Steps einen Zwischenstand auf Disk.
Naechste Sequenz liest den Checkpoint und setzt exakt dort an.

Token-Budget wird zum Pause-Button statt zum Reset-Button.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import safe_json_read, safe_json_write


class CheckpointManager:
    """Verwaltet Zwischen-Checkpoints innerhalb einer Sequenz."""

    # Alle N Steps automatisch speichern
    CHECKPOINT_INTERVAL = 7

    def __init__(self, consciousness_path: Path):
        self.checkpoint_path = consciousness_path / "checkpoint.json"

    def should_checkpoint(self, step: int) -> bool:
        """Prueft ob ein Checkpoint faellig ist."""
        return step > 0 and step % self.CHECKPOINT_INTERVAL == 0

    def save(self, step: int, focus: str, sub_goal: str,
             files_read: list, files_written: list,
             findings: str, plan_goal: str = "") -> str:
        """Speichert einen Checkpoint mit aktuellem Arbeitsstand.

        Args:
            step: Aktueller Step-Zaehler
            focus: Aktueller Fokus/Goal
            sub_goal: Aktuelles Sub-Goal
            files_read: Liste gelesener Dateien (Pfade)
            files_written: Liste geschriebener Dateien (Pfade)
            findings: Bisherige Erkenntnisse (Freitext, max 500 Zeichen)
            plan_goal: Ziel aus dem Sequenz-Plan

        Returns:
            Bestaetigungstext
        """
        checkpoint = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "focus": focus[:200],
            "sub_goal": sub_goal[:200],
            "plan_goal": plan_goal[:200],
            "files_read": files_read[-10:],     # Letzte 10
            "files_written": files_written[-10:],
            "findings": findings[:500],
            "status": "active",
        }
        safe_json_write(self.checkpoint_path, checkpoint)
        return f"Checkpoint bei Step {step} gespeichert."

    def auto_save(self, step: int, engine) -> str:
        """Automatischer Checkpoint aus Engine-State.

        Extrahiert relevante Daten direkt aus der Engine.
        """
        focus = ""
        sub_goal = ""
        try:
            full_focus = engine.goal_stack.get_current_focus()
            if "FOKUS:" in full_focus:
                focus = full_focus.split("FOKUS:")[1].strip()[:200]
            # Aktuelles Sub-Goal
            active = engine.goal_stack.goals.get("active", [])
            if active:
                for sg in active[0].get("sub_goals", []):
                    if sg.get("status") == "in_progress":
                        sub_goal = sg.get("title", "")[:200]
                        break
        except Exception:
            pass

        # Plan-Ziel aus Sequenz-Planner
        plan_goal = ""
        if hasattr(engine, "planner"):
            plan = engine.planner.get_active_plan()
            plan_goal = plan.get("goal", "")

        # Bisherige Erkenntnisse aus Live-Notes
        findings = ""
        live_notes_path = engine.consciousness_path / "live_notes.md"
        if live_notes_path.exists():
            try:
                findings = live_notes_path.read_text(encoding="utf-8").strip()[-500:]
            except OSError:
                pass

        return self.save(
            step=step,
            focus=focus,
            sub_goal=sub_goal,
            files_read=[],  # Wird spaeter aus Tracking gefuellt
            files_written=list(getattr(engine, "_seq_written_paths", [])),
            findings=findings,
            plan_goal=plan_goal,
        )

    def load(self) -> dict:
        """Laedt den letzten Checkpoint (falls vorhanden und aktiv)."""
        if not self.checkpoint_path.exists():
            return {}
        data = safe_json_read(self.checkpoint_path, default={})
        if data.get("status") != "active":
            return {}
        return data

    def build_resume_context(self) -> str:
        """Baut Kontext-Text aus dem Checkpoint fuer die Perception.

        Differenziert zwischen completed/paused/failed und gibt der naechsten
        Sequenz die richtigen Hinweise mit.

        Returns:
            Resume-Text oder leerer String wenn kein Checkpoint.
        """
        if not self.checkpoint_path.exists():
            return ""
        data = safe_json_read(self.checkpoint_path, default={})
        status = data.get("status", "")

        # Nur aktive oder gescheiterte Checkpoints sind relevant
        if status == "completed":
            return ""
        if not status:
            return ""

        parts = []

        if status == "failed":
            parts.append("⚠ LETZTE SEQUENZ GESCHEITERT:")
            parts.append(f"  Fehler: {data.get('errors', '?')}, Dateien: {data.get('files_written', 0)}")
            if data.get("stuck_patterns"):
                patterns = ", ".join(data["stuck_patterns"][:3])
                parts.append(f"  Stuck bei: {patterns}")
            parts.append("  → ANDERER ANSATZ noetig! Nicht das Gleiche nochmal versuchen.")
            parts.append("  → Pruefe erst mit list_directory ob die Dateien existieren.")
        elif status == "paused":
            parts.append("CHECKPOINT (Fortsetzen — letztes Mal Limit erreicht):")
            parts.append(f"  Unterbrochen bei Step {data.get('step', '?')}")
            if data.get("plan_goal"):
                parts.append(f"  Plan-Ziel: {data['plan_goal'][:150]}")
            if data.get("findings"):
                parts.append(f"  Bisherige Erkenntnisse: {data['findings'][:300]}")
            if data.get("files_written") and isinstance(data["files_written"], list):
                files = ", ".join(Path(p).name for p in data["files_written"][:5])
                parts.append(f"  Geschriebene Dateien: {files}")
            parts.append("  → Setze GENAU hier an. Lies nicht alles nochmal von vorne.")
        else:
            # status == "active" — mitten drin abgebrochen
            parts.append("CHECKPOINT (Fortsetzen der letzten Sequenz):")
            parts.append(f"  Unterbrochen bei Step {data.get('step', '?')}")
            if data.get("plan_goal"):
                parts.append(f"  Plan-Ziel: {data['plan_goal'][:150]}")
            if data.get("sub_goal"):
                parts.append(f"  Sub-Goal: {data['sub_goal'][:150]}")
            if data.get("findings"):
                parts.append(f"  Bisherige Erkenntnisse: {data['findings'][:300]}")
            parts.append("  → Setze GENAU hier an. Lies nicht alles nochmal von vorne.")

        return "\n".join(parts)

    def mark_finished(self, status: str = "completed", errors: int = 0,
                      files_written: int = 0, stuck_patterns: list = None):
        """Markiert den Checkpoint mit differenziertem Status.

        Status-Typen:
          completed — Phi hat finish_sequence selbst aufgerufen, Ergebnis erreicht
          paused    — Hartes Limit erreicht aber Fortschritt gemacht
          failed    — Viele Fehler, kein Fortschritt, anderer Ansatz noetig

        Args:
            status: "completed", "paused", oder "failed"
            errors: Anzahl Fehler in dieser Sequenz
            files_written: Anzahl geschriebener Dateien
            stuck_patterns: Liste von Stuck-Keys die erkannt wurden
        """
        if self.checkpoint_path.exists():
            data = safe_json_read(self.checkpoint_path, default={})
            data["status"] = status
            data["errors"] = errors
            data["files_written"] = files_written
            if stuck_patterns:
                data["stuck_patterns"] = stuck_patterns[:5]
            safe_json_write(self.checkpoint_path, data)

    def mark_completed(self):
        """Abwaertskompatibel: Markiert als completed."""
        self.mark_finished("completed")

    def clear(self):
        """Loescht den Checkpoint (neuer Fokus, kein Resume noetig)."""
        if self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
            except OSError:
                pass
