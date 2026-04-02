"""
Goal-Stack — Multi-Cycle Ziele mit Sub-Goals und Fortschritts-Tracking.

Echte Zielstruktur die ueber Zyklen hinweg arbeitet:
- Hauptziele zerlegen sich in Sub-Goals
- Jeder Zyklus arbeitet am naechsten offenen Sub-Goal
- Fortschritt wird getrackt und ist sichtbar
- Abhaengigkeiten zwischen Goals werden beachtet
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write


class GoalStack:
    """Verwaltet hierarchische Ziele mit Sub-Goals."""

    def __init__(self, goals_path: Path):
        self.goals_path = goals_path
        self.goals = self._load()

    def _load(self) -> dict:
        default = {"active": [], "completed": [], "abandoned": []}
        return safe_json_read(self.goals_path, default=default)

    def _save(self):
        safe_json_write(self.goals_path, self.goals)

    # === Ziel erstellen ===

    def _find_similar_goal(self, title: str) -> Optional[tuple[int, dict]]:
        """
        Prueft ob ein aehnliches aktives Ziel existiert (Wort-Overlap).

        Returns:
            (index, goal) Tuple oder None
        """
        # Stoppwoerter die keine Semantik tragen
        stop = {"und", "oder", "fuer", "mit", "der", "die", "das", "ein", "eine",
                "zu", "von", "in", "auf", "an", "bei", "nach", "aus", "um"}
        new_words = {w.lower().strip(":.-()") for w in title.split() if len(w) > 2} - stop

        if not new_words:
            return None

        for i, goal in enumerate(self.goals.get("active", [])):
            existing_words = {w.lower().strip(":.-()") for w in goal["title"].split() if len(w) > 2} - stop
            if not existing_words:
                continue
            # Jaccard-Aehnlichkeit: wie viel Overlap haben die Woerter?
            overlap = len(new_words & existing_words)
            union = len(new_words | existing_words)
            similarity = overlap / union if union else 0
            if similarity >= 0.4:  # 40% Wort-Overlap = wahrscheinlich gleich
                return (i, goal)
        return None

    def create_goal(self, title: str, description: str = "",
                    sub_goals: Optional[list[str]] = None) -> str:
        """
        Erstellt ein neues Ziel mit optionalen Sub-Goals.
        Prueft vorher ob ein aehnliches Ziel bereits existiert.

        Args:
            title: Ziel-Titel
            description: Detaillierte Beschreibung
            sub_goals: Liste von Sub-Goal Titeln

        Returns:
            Bestaetigungs-Nachricht
        """
        # Deduplizierung: Aehnliches Ziel vorhanden?
        similar = self._find_similar_goal(title)
        if similar:
            idx, existing_goal = similar
            # Sub-Goals in existierendes Ziel mergen statt nur abweisen
            merged_count = 0
            if sub_goals:
                existing_titles_lower = {
                    sg["title"].lower() for sg in existing_goal.get("sub_goals", [])
                }
                next_index = len(existing_goal.get("sub_goals", []))
                for sg_title in sub_goals:
                    if sg_title.lower() not in existing_titles_lower:
                        existing_goal.setdefault("sub_goals", []).append({
                            "index": next_index,
                            "title": sg_title,
                            "status": "pending",
                            "result": None,
                        })
                        next_index += 1
                        merged_count += 1
                if merged_count:
                    self._save()
            existing_sgs = [sg["title"] for sg in existing_goal.get("sub_goals", [])
                           if sg["status"] != "done"]
            merge_info = f" {merged_count} neue Sub-Goals gemerged." if merged_count else ""
            return (
                f"AEHNLICHES ZIEL EXISTIERT: '{existing_goal['title']}' (Index {idx}).{merge_info} "
                f"Offene Sub-Goals: {existing_sgs}. "
                f"Arbeite am bestehenden Ziel weiter!"
            )

        goal = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "description": description,
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "sub_goals": [],
            "progress_log": [],
        }

        # Sub-Goals anlegen
        if sub_goals:
            for i, sg_title in enumerate(sub_goals):
                goal["sub_goals"].append({
                    "index": i,
                    "title": sg_title,
                    "status": "pending",  # pending, in_progress, done
                    "result": None,
                })

        self.goals.setdefault("active", []).append(goal)
        self._save()
        return f"Ziel erstellt: '{title}' mit {len(goal['sub_goals'])} Sub-Goals"

    # === Sub-Goal bearbeiten ===

    def start_next_subgoal(self, goal_index: int = 0) -> Optional[dict]:
        """
        Findet und startet das naechste offene Sub-Goal.

        Returns:
            Das Sub-Goal dict oder None
        """
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            return None

        goal = active[goal_index]
        for sg in goal.get("sub_goals", []):
            # Stuck in_progress Sub-Goals reaktivieren (z.B. nach Crash)
            if sg["status"] == "in_progress":
                return sg
            if sg["status"] == "pending":
                sg["status"] = "in_progress"
                self._save()
                return sg

        return None

    def complete_subgoal(self, goal_index: int, subgoal_index: int,
                         result: str = "") -> str:
        """Markiert ein Sub-Goal als erledigt."""
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            valid = [f"{i}: {g['title']}" for i, g in enumerate(active)]
            return f"FEHLER: Goal-Index {goal_index} ungueltig. Aktive Goals: {valid}"

        goal = active[goal_index]
        sgs = goal.get("sub_goals", [])
        if subgoal_index < 0 or subgoal_index >= len(sgs):
            valid = [f"{sg['index']}: {sg['title']} [{sg['status']}]" for sg in sgs]
            return f"FEHLER: SubGoal-Index {subgoal_index} ungueltig. Sub-Goals: {valid}"

        sgs[subgoal_index]["status"] = "done"
        sgs[subgoal_index]["result"] = result
        sgs[subgoal_index]["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Log
        goal.setdefault("progress_log", []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": f"Sub-Goal {subgoal_index} erledigt: {sgs[subgoal_index]['title']}",
            "result": result[:200],
        })

        # Pruefen ob alle Sub-Goals done → Hauptziel abschliessen
        all_done = all(sg["status"] == "done" for sg in sgs)
        if all_done and sgs:
            return self.complete_goal(goal_index)

        self._save()
        return f"Sub-Goal erledigt: {sgs[subgoal_index]['title']}"

    # === Hauptziel abschliessen ===

    def complete_goal(self, goal_index: int) -> str:
        """Markiert ein Hauptziel als abgeschlossen."""
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            return "FEHLER: Goal-Index ungueltig."

        goal = active.pop(goal_index)
        goal["status"] = "completed"
        goal["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.goals.setdefault("completed", []).append(goal)
        self._save()
        return f"ZIEL ERREICHT: '{goal['title']}'"

    def abandon_goal(self, goal_index: int, reason: str = "") -> str:
        """Gibt ein Ziel auf."""
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            return "FEHLER: Goal-Index ungueltig."

        goal = active.pop(goal_index)
        goal["status"] = "abandoned"
        goal["abandoned_reason"] = reason
        self.goals.setdefault("abandoned", []).append(goal)
        self._save()
        return f"Ziel aufgegeben: '{goal['title']}'"

    # === Log ===

    def log_progress(self, goal_index: int, update: str) -> str:
        """Loggt Fortschritt fuer ein Ziel."""
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            return "FEHLER: Goal-Index ungueltig."

        active[goal_index].setdefault("progress_log", []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": update,
        })
        self._save()
        return f"Progress geloggt fuer: {active[goal_index]['title']}"

    # === Uebersicht ===

    def get_current_focus(self) -> str:
        """Was sollte Lyra JETZT tun? Naechstes offenes Sub-Goal."""
        active = self.goals.get("active", [])
        if not active:
            return "Keine aktiven Ziele. Setze ein neues Ziel!"

        for i, goal in enumerate(active):
            for sg in goal.get("sub_goals", []):
                if sg["status"] in ("pending", "in_progress"):
                    return (
                        f"FOKUS: {goal['title']}\n"
                        f"  Naechster Schritt: {sg['title']} [{sg['status']}]"
                    )

            # Ziel ohne Sub-Goals
            if not goal.get("sub_goals"):
                return f"FOKUS: {goal['title']} (keine Sub-Goals definiert)"

        return "Alle Sub-Goals erledigt — schliesse Ziele ab oder setze neue."

    def get_summary(self) -> str:
        """Komplette Ziel-Uebersicht."""
        active = self.goals.get("active", [])
        completed = self.goals.get("completed", [])

        lines = []

        if active:
            lines.append(f"AKTIVE ZIELE ({len(active)}):")
            for i, goal in enumerate(active):
                sgs = goal.get("sub_goals", [])
                done = sum(1 for sg in sgs if sg["status"] == "done")
                total = len(sgs)
                progress = f"[{done}/{total}]" if total else "[kein Plan]"
                lines.append(f"  {i}. {goal['title']} {progress}")

                for sg in sgs:
                    status_icon = {"pending": " ", "in_progress": ">", "done": "x"}
                    icon = status_icon.get(sg["status"], "?")
                    lines.append(f"     [{icon}] {sg['title']}")
        else:
            lines.append("Keine aktiven Ziele.")

        if completed:
            lines.append(f"\nERREICHT ({len(completed)}):")
            for g in completed[-5:]:
                lines.append(f"  + {g['title']}")

        return "\n".join(lines)
