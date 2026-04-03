"""
Adaptive Sequenz-Planung — Phi plant vor jeder Sequenz was es erreichen will.

Jede Sequenz bekommt einen konkreten Plan mit:
- Was soll erreicht werden? (Ziel)
- Nach welchem Step pruefen? (Checkpoint)
- Wann ist finish_sequence richtig? (Exit-Kriterium)
- Max wieviele Steps? (Budget)

Am Sequenz-Ende wird der Plan gegen das Ergebnis geprueft.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import safe_json_read, safe_json_write


class SequencePlanner:
    """Plant und evaluiert Sequenzen fuer besseren Fokus und frueheres Finish."""

    def __init__(self, consciousness_path: Path):
        self.plan_path = consciousness_path / "sequence_plan.json"
        self.history_path = consciousness_path / "plan_history.json"

    def build_planning_prompt(self, focus: str, working_memory: str,
                              last_plans: list = None) -> str:
        """Baut den Planungs-Impuls fuer den Sequenz-Start.

        Wird in die Perception injiziert damit Phi seinen eigenen Plan schreibt.
        """
        # Letzte Plan-Bewertungen als Kontext (was hat funktioniert?)
        history_context = ""
        if last_plans:
            recent = last_plans[-3:]
            lessons = []
            for p in recent:
                score = p.get("score", "?")
                lesson = p.get("lesson", "")
                if lesson:
                    lessons.append(f"  - Plan-Score {score}: {lesson[:100]}")
            if lessons:
                history_context = (
                    "\nLETZTE PLAN-BEWERTUNGEN:\n"
                    + "\n".join(lessons)
                )

        return (
            "\nSEQUENZ-PLANUNG (Pflicht!):\n"
            "Bevor du mit der Arbeit beginnst, schreibe deinen Plan "
            "mit dem Tool 'write_sequence_plan':\n"
            "- goal: Was willst du in DIESER Sequenz konkret erreichen? (1 Satz)\n"
            "- exit_criteria: Woran erkennst du dass du fertig bist? (1 Satz)\n"
            "- max_steps: Wieviele Steps brauchst du realistisch? (Zahl, max 30)\n"
            "- checkpoint_at: Nach welchem Step pruefst du ob du auf Kurs bist? (Zahl)\n"
            "Plane KLEIN und KONKRET. Lieber eine Sache fertig als drei angefangen."
            + history_context
        )

    def save_plan(self, plan: dict) -> str:
        """Speichert den aktuellen Sequenz-Plan."""
        plan["timestamp"] = datetime.now(timezone.utc).isoformat()
        plan["status"] = "active"
        safe_json_write(self.plan_path, plan)
        return (
            f"Plan gespeichert: {plan.get('goal', '?')[:80]} "
            f"(Exit: {plan.get('exit_criteria', '?')[:60]}, "
            f"Max {plan.get('max_steps', '?')} Steps)"
        )

    def get_active_plan(self) -> dict:
        """Laedt den aktuellen Plan (falls vorhanden)."""
        if not self.plan_path.exists():
            return {}
        return safe_json_read(self.plan_path, default={})

    def build_checkpoint_reminder(self, current_step: int) -> str:
        """Prueft ob ein Checkpoint-Reminder faellig ist.

        Returns:
            Reminder-Text oder leerer String.
        """
        plan = self.get_active_plan()
        if not plan or plan.get("status") != "active":
            return ""

        checkpoint_at = plan.get("checkpoint_at", 0)
        if checkpoint_at and current_step == checkpoint_at:
            return (
                f"\n=== CHECKPOINT (Step {current_step}) ===\n"
                f"Dein Plan: {plan.get('goal', '?')[:100]}\n"
                f"Exit-Kriterium: {plan.get('exit_criteria', '?')[:100]}\n"
                "Frage dich: Bin ich auf Kurs? Wenn ja, weiter. "
                "Wenn nein, passe deinen Ansatz an oder nutze finish_sequence."
            )

        # Budget-Warnung wenn nah am geplanten Limit
        max_steps = plan.get("max_steps", 30)
        if current_step == max_steps - 2:
            return (
                f"\n=== BUDGET-WARNUNG (Step {current_step}/{max_steps}) ===\n"
                "Du bist fast am geplanten Step-Limit. "
                "Sichere deine Ergebnisse und nutze finish_sequence."
            )

        return ""

    def evaluate_plan(self, summary: str, rating: int,
                      steps_used: int, errors: int) -> dict:
        """Bewertet den Plan gegen das Ergebnis.

        Returns:
            Bewertung mit Score und Lesson-Learned.
        """
        plan = self.get_active_plan()
        if not plan:
            return {"score": 0, "lesson": "Kein Plan vorhanden"}

        max_steps = plan.get("max_steps", 30)
        planned_goal = plan.get("goal", "")

        # Score berechnen (0-10)
        score = 5  # Basis

        # Hat Phi sein eigenes Ziel erreicht?
        if rating >= 7:
            score += 2
        elif rating <= 3:
            score -= 2

        # Steps-Effizienz: Unter Budget = gut, ueber Budget = schlecht
        if steps_used <= max_steps:
            score += 1
        else:
            score -= 1

        # Fehlerrate
        if errors == 0:
            score += 1
        elif errors > 3:
            score -= 1

        # Hat Phi finish_sequence selbst aufgerufen (nicht Token-Budget)?
        if "Token-Budget" not in summary and "Max Steps" not in summary:
            score += 1

        score = max(1, min(10, score))

        # Lesson extrahieren
        if score >= 7:
            lesson = f"Guter Plan. Ziel '{planned_goal[:50]}' in {steps_used} Steps erreicht."
        elif score >= 4:
            lesson = f"Plan teilweise umgesetzt. {errors} Fehler, {steps_used}/{max_steps} Steps."
        else:
            lesson = f"Plan gescheitert. Ziel war: '{planned_goal[:50]}'. Naechstes Mal kleiner planen."

        evaluation = {
            "plan_goal": planned_goal[:100],
            "score": score,
            "steps_planned": max_steps,
            "steps_used": steps_used,
            "errors": errors,
            "rating": rating,
            "lesson": lesson,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Plan als abgeschlossen markieren
        plan["status"] = "completed"
        plan["evaluation"] = evaluation
        safe_json_write(self.plan_path, plan)

        # History anhaengen (max 20 Eintraege)
        history = safe_json_read(self.history_path, default={"plans": []})
        history["plans"].append(evaluation)
        history["plans"] = history["plans"][-20:]
        safe_json_write(self.history_path, history)

        return evaluation

    def get_plan_history(self) -> list:
        """Laedt die letzten Plan-Bewertungen."""
        data = safe_json_read(self.history_path, default={"plans": []})
        return data.get("plans", [])

    def get_avg_score(self) -> float:
        """Durchschnittlicher Plan-Score der letzten 10 Plaene."""
        history = self.get_plan_history()
        recent = history[-10:]
        if not recent:
            return 0.0
        scores = [p.get("score", 5) for p in recent]
        return round(sum(scores) / len(scores), 1)
