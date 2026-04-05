"""
Goal-Stack — Multi-Cycle Ziele mit Sub-Goals und Fortschritts-Tracking.

Echte Zielstruktur die ueber Zyklen hinweg arbeitet:
- Hauptziele zerlegen sich in Sub-Goals
- Jeder Zyklus arbeitet am naechsten offenen Sub-Goal
- Fortschritt wird getrackt und ist sichtbar
- Abhaengigkeiten zwischen Goals werden beachtet
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write, normalize_name_words, is_meta_goal
from .phi import PHI, phi_balance


class GoalStack:
    """Verwaltet hierarchische Ziele mit Sub-Goals."""

    def __init__(self, goals_path: Path):
        self.goals_path = goals_path
        self.goals = self._load()
        # Focus-Tracking aus persistiertem State laden (ueberlebt Neustart)
        tracker = self.goals.get("_focus_tracker", {})
        self._last_focus: str = tracker.get("focus", "")
        self._consecutive_count: int = tracker.get("count", 0)
        # Telos: Zweck-Hierarchie laden (optional, abwaertskompatibel)
        self._telos = self._load_telos()

    def _load(self) -> dict:
        default = {"active": [], "completed": [], "abandoned": []}
        return safe_json_read(self.goals_path, default=default)

    def _load_telos(self) -> dict:
        """Laedt telos.json — gibt leeres Dict zurueck wenn nicht vorhanden."""
        telos_path = self.goals_path.parent / "telos.json"
        if not telos_path.exists():
            return {}
        try:
            with open(telos_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _get_recent_goal_domains(self, n: int = 10) -> list[str]:
        """Gibt die Domaenen der letzten N abgeschlossenen Goals zurueck."""
        completed = self.goals.get("completed", [])[-n:]
        domains = []
        for goal in completed:
            title = goal.get("title", "").lower()
            domain = self._classify_domain(title)
            domains.append(domain)
        return domains

    @staticmethod
    def _classify_domain(text: str) -> str:
        """Einfache Domaenen-Klassifikation fuer Telos-Scoring."""
        tl = text.lower()
        # AGI-Infrastruktur: Engine-Code der Phi's Kern verbessert
        if any(k in tl for k in ("enforcement", "meta-rule", "perception",
                                  "pipeline", "dream", "evaluation", "metrik",
                                  "messung", "fortschritt", "flywheel")):
            return "architecture"
        if any(k in tl for k in ("api", "http", "endpoint", "request", "wrapper")):
            return "api_integration"
        if any(k in tl for k in ("test", "benchmark", "verifiz", "pruef")):
            return "testing"
        if any(k in tl for k in ("daten", "data", "csv", "analyse", "statistik")):
            return "data_analysis"
        if any(k in tl for k in ("architektur", "refactor", "modul", "design")):
            return "architecture"
        if any(k in tl for k in ("business", "markt", "preis", "roi", "kunde")):
            return "business_thinking"
        if any(k in tl for k in ("dashboard", "frontend", "html", "ui")):
            return "frontend_design"
        if any(k in tl for k in ("recherch", "research", "web")):
            return "web_research"
        if any(k in tl for k in ("selbst", "self", "evolution", "improv")):
            return "self_improvement"
        if any(k in tl for k in ("tool", "werkzeug")):
            return "tool_building"
        return "sonstiges"

    @staticmethod
    def _is_meta_goal(title: str) -> bool:
        """Erkennt ob ein Goal Meta-Reflexion statt echte Arbeit ist."""
        return is_meta_goal(title)

    def _telos_score(self, goal: dict) -> float:
        """Berechnet Telos-Score: Diversitaets-Bonus + Ring-Prioritaet.

        Hoher Score = Goal ist wertvoller fuer Phis Wachstum.
        Meta-Goals (Reflexion, Uebungen) werden abgewertet wenn echte
        Infrastruktur-Goals existieren.
        Ohne telos.json: gibt 0.0 zurueck (Fallback auf Index-Reihenfolge).
        """
        if not self._telos:
            return 0.0

        title = goal.get("title", "")
        domain = self._classify_domain(title)

        # 1. Diversitaets-Bonus: PHI^(-Wiederholungen)
        recent = self._get_recent_goal_domains(10)
        repetitions = recent.count(domain)
        diversity = PHI ** (-repetitions)

        # 2. Ring-Prioritaet: Niedrigster unfertiger Ring bevorzugt
        ring_bonus = 0.0
        ringe = self._telos.get("ringe", [])
        for ring in ringe:
            completion = ring.get("completion", 1.0)
            if completion < 0.6:
                ring_domains = [d["name"] for d in ring.get("domaenen", [])]
                if domain in ring_domains:
                    ring_nr = ring.get("nummer", 5)
                    ring_bonus = PHI ** (-(ring_nr - 1))
                    break

        # 3. Meta-Penalty: Meta-Goals abwerten wenn echte Goals existieren
        meta_penalty = 1.0
        if self._is_meta_goal(title):
            active = self.goals.get("active", [])
            has_real = any(
                not self._is_meta_goal(g.get("title", ""))
                for g in active
            )
            if has_real:
                meta_penalty = 0.2  # -80% Score fuer Meta wenn echte da sind

        # Gewichtete Kombination: 60% Diversitaet, 40% Ring, Meta-Penalty
        return (diversity * 0.6 + ring_bonus * 0.4) * meta_penalty

    def _get_telos_suggestion(self) -> str:
        """Gibt die hoechstpriorisierte Telos-Luecke als Vorschlag zurueck."""
        if not self._telos:
            return "data_analysis oder business_thinking"
        for ring in self._telos.get("ringe", []):
            if ring.get("completion", 1.0) >= 0.9:
                continue
            # Level-basiert: novice/beginner = Gap (completion fehlt pro Domain)
            gaps = [d["name"] for d in ring.get("domaenen", [])
                    if d.get("level", "novice") in ("novice", "beginner")]
            if gaps:
                return f"Ring {ring['nummer']} ({ring['name']}): {', '.join(gaps)}"
        return "neues Terrain erkunden"

    def _save(self):
        try:
            safe_json_write(self.goals_path, self.goals)
        except (OSError, TypeError, ValueError) as e:
            print(f"  [WARNUNG] Goals nicht gespeichert: {e}")

    def sync_from_disk(self):
        """
        Mergt extern hinzugefuegte Goals aus der Datei in den Memory-State.

        Verhindert Race-Condition: Externe Aenderungen (z.B. von Oliver)
        werden beim naechsten Sequenz-Start uebernommen statt ueberschrieben.
        """
        disk = self._load()
        memory_ids = {g["id"] for g in self.goals.get("active", [])}
        memory_ids |= {g["id"] for g in self.goals.get("completed", [])}
        memory_ids |= {g["id"] for g in self.goals.get("abandoned", [])}

        merged = 0
        for goal in disk.get("active", []):
            if goal["id"] not in memory_ids:
                self.goals.setdefault("active", []).append(goal)
                merged += 1

        if merged:
            self._save()
            print(f"  [SYNC] {merged} extern hinzugefuegte Goals uebernommen")

    def track_focus(self, current_focus: str) -> int:
        """Zaehlt wie oft derselbe Focus hintereinander aktiv war.

        Wird am Anfang jeder Sequenz aufgerufen. Wenn sich der Focus aendert,
        wird der Zaehler zurueckgesetzt. Bei 3+ gleichen: Sub-Goal steckt fest.

        Returns:
            Anzahl aufeinanderfolgender Sequenzen mit gleichem Focus.
        """
        # Nur erste Zeile vergleichen (Status-Details aendern sich)
        focus_key = current_focus.split("\n")[0].strip() if current_focus else ""
        last_key = self._last_focus.split("\n")[0].strip() if self._last_focus else ""

        if focus_key == last_key and focus_key:
            self._consecutive_count += 1
        else:
            self._last_focus = current_focus
            self._consecutive_count = 1

        # Persistieren — ueberlebt Neustart
        self.goals["_focus_tracker"] = {
            "focus": focus_key,
            "count": self._consecutive_count,
        }
        self._save()
        return self._consecutive_count

    # === Kumulative SubGoal-Metriken ===

    def record_subgoal_attempt(
        self, steps_used: int, files_written: int,
        errors: int, efficiency_ratio: float,
    ):
        """Akkumuliert Metriken fuer das aktive SubGoal.

        Wird nach jeder Sequenz aufgerufen — unabhaengig ob konsekutiv.
        Ermoeglicht Erkennung von Spin-Loops die zwischen Goals alternieren.
        """
        sg = self._find_active_subgoal()
        if not sg:
            logger.warning(
                "record_subgoal_attempt: Kein aktives SubGoal — Stats verloren "
                "(steps=%d, files=%d, errors=%d)", steps_used, files_written, errors,
            )
            return

        stats = sg.setdefault("_attempt_stats", {
            "total_sequences": 0,
            "total_wasted_steps": 0,
            "total_errors": 0,
            "total_files": 0,
            "last_efficiency": 0.0,
        })
        wasted = max(0, steps_used - files_written * 3)  # Heuristik: 3 Steps/Datei = produktiv
        stats["total_sequences"] += 1
        stats["total_wasted_steps"] += wasted
        stats["total_errors"] += errors
        stats["total_files"] += files_written
        stats["last_efficiency"] = efficiency_ratio
        self._save()

    def check_subgoal_viability(self) -> str:
        """Prueft ob das aktive SubGoal noch machbar ist.

        Basiert auf kumulativen Metriken, nicht nur konsekutiven Sequenzen.
        Erkennt Spin-Loops die track_focus() nicht sieht (Goal-Alternierung).

        Returns:
            'viable' | 'struggling' | 'unviable'
        """
        sg = self._find_active_subgoal()
        if not sg:
            return "viable"

        stats = sg.get("_attempt_stats", {})
        total_seq = stats.get("total_sequences", 0)
        total_files = stats.get("total_files", 0)
        total_errors = stats.get("total_errors", 0)

        if total_seq < 3:
            return "viable"  # Zu wenig Daten

        avg_files = total_files / total_seq
        avg_errors = total_errors / total_seq

        # Unviable: 8+ Sequenzen und weniger als 1 Datei/Seq im Schnitt
        if total_seq >= 8 and avg_files < 1.0:
            return "unviable"

        # Unviable: 5+ Sequenzen und mehr Fehler als Dateien
        if total_seq >= 5 and avg_errors > avg_files and avg_files < 2.0:
            return "unviable"

        # Struggling: 5+ Sequenzen mit unterdurchschnittlicher Effizienz
        if total_seq >= 5 and avg_files < 2.0:
            return "struggling"

        return "viable"

    def _find_active_subgoal(self) -> dict | None:
        """Findet das aktuell aktive (in_progress) SubGoal."""
        for goal in self.goals.get("active", []):
            for sg in goal.get("sub_goals", []):
                if sg.get("status") == "in_progress":
                    return sg
        return None

    def get_active_subgoal_indices(self) -> tuple[int, int] | None:
        """Gibt (goal_index, subgoal_index) des aktiven SubGoals zurueck."""
        for gi, goal in enumerate(self.goals.get("active", [])):
            for si, sg in enumerate(goal.get("sub_goals", [])):
                if sg.get("status") == "in_progress":
                    return (gi, si)
        return None

    # === Ziel erstellen ===

    def _find_similar_goal(self, title: str) -> Optional[tuple[int, dict]]:
        """
        Prueft ob ein aehnliches aktives Ziel existiert (Wort-Overlap).

        Returns:
            (index, goal) Tuple oder None
        """
        new_words = normalize_name_words(title)

        if not new_words:
            return None

        for i, goal in enumerate(self.goals.get("active", [])):
            existing_words = normalize_name_words(goal["title"])
            if not existing_words:
                continue
            # Jaccard-Aehnlichkeit: wie viel Overlap haben die Woerter?
            overlap = len(new_words & existing_words)
            union = len(new_words | existing_words)
            similarity = overlap / union if union else 0
            if similarity >= 0.4:  # 40% Wort-Overlap = wahrscheinlich gleich
                return (i, goal)
        return None

    def _find_similar_completed_goal(self, title: str) -> Optional[dict]:
        """Prueft ob ein aehnliches Ziel bereits abgeschlossen wurde."""
        new_words = normalize_name_words(title)
        if not new_words:
            return None
        for goal in self.goals.get("completed", []):
            existing_words = normalize_name_words(goal["title"])
            if not existing_words:
                continue
            overlap = len(new_words & existing_words)
            union = len(new_words | existing_words)
            similarity = overlap / union if union else 0
            if similarity >= 0.5:
                return goal
        return None

    def create_goal(self, title: str, description: str = "",
                    sub_goals: Optional[list[str]] = None,
                    priority: str = "medium") -> str:
        """
        Erstellt ein neues Ziel mit optionalen Sub-Goals.
        Prueft vorher ob ein aehnliches Ziel bereits existiert.

        Args:
            title: Ziel-Titel
            description: Detaillierte Beschreibung
            sub_goals: Liste von Sub-Goal Titeln
            priority: Prioritaet (low, medium, high)

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

        # Completed-Check: Aehnliches Ziel schon abgeschlossen?
        completed_match = self._find_similar_completed_goal(title)
        if completed_match:
            return (
                f"AEHNLICHES ZIEL BEREITS ABGESCHLOSSEN: '{completed_match['title']}'. "
                f"Waehle ein Ziel das eine NEUE Faehigkeit trainiert — "
                f"nicht dieselbe Aufgabe wiederholen."
            )

        # Domain-Wiederholungs-Guard: Nicht 5x die gleiche Domain trainieren
        domain = self._classify_domain(title)
        recent = self._get_recent_goal_domains(10)
        if recent.count(domain) >= 4 and domain != "sonstiges":
            suggestion = self._get_telos_suggestion()
            return (
                f"DOMAIN-WIEDERHOLUNG: '{domain}' war {recent.count(domain)}x in den "
                f"letzten 10 Goals. Waehle eine andere Domain! "
                f"Telos empfiehlt: {suggestion}"
            )

        goal = {
            "id": str(uuid.uuid4())[:8],
            "title": title,
            "description": description,
            "priority": priority if priority in ("low", "medium", "high") else "medium",
            "created": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "sub_goals": [],
            "progress_log": [],
        }

        # Sub-Goals anlegen (mit Validierung)
        if sub_goals:
            for i, sg_title in enumerate(sub_goals):
                if not sg_title or not isinstance(sg_title, str):
                    continue
                sg_title = sg_title.strip()[:200]
                if not sg_title:
                    continue
                goal["sub_goals"].append({
                    "index": i,
                    "title": sg_title,
                    "status": "pending",
                    "result": None,
                })

        self.goals.setdefault("active", []).append(goal)
        self._save()
        return f"Ziel erstellt: '{title}' mit {len(goal['sub_goals'])} Sub-Goals"

    # === Sub-Goal bearbeiten ===

    def fail_subgoal(self, goal_index: int, subgoal_index: int,
                     reason: str, approach_tried: str = "") -> str:
        """
        Markiert ein Sub-Goal als gescheitert mit Grund.

        Verhindert endlose Wiederholungsversuche — Phi lernt was NICHT funktioniert.
        """
        active = self.goals.get("active", [])
        if goal_index < 0 or goal_index >= len(active):
            valid = [f"{i}: {g['title']}" for i, g in enumerate(active)]
            return f"FEHLER: Goal-Index {goal_index} ungueltig. Aktive Goals: {valid}"

        goal = active[goal_index]
        sgs = goal.get("sub_goals", [])
        if subgoal_index < 0 or subgoal_index >= len(sgs):
            valid = [f"{sg['index']}: {sg['title']} [{sg['status']}]" for sg in sgs]
            return f"FEHLER: SubGoal-Index {subgoal_index} ungueltig. Sub-Goals: {valid}"

        sg = sgs[subgoal_index]
        sg["status"] = "failed"
        sg["failure_reason"] = reason
        sg["approach_tried"] = approach_tried
        sg["failed_at"] = datetime.now(timezone.utc).isoformat()

        goal.setdefault("progress_log", []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": f"Sub-Goal {subgoal_index} GESCHEITERT: {reason}",
        })
        self._save()

        # Kaskaden-Fail: Pending SubGoals deren ALLE Vorgaenger failed sind
        # (z.B. "Unit-Tests schreiben" wenn Module nie gebaut wurden)
        cascade_count = 0
        for later_sg in sgs[subgoal_index + 1:]:
            if later_sg["status"] != "pending":
                continue
            prior_sgs = [s for s in sgs[:sgs.index(later_sg)]
                         if s["status"] != "pending"]
            if prior_sgs and all(s["status"] == "failed" for s in prior_sgs):
                later_sg["status"] = "failed"
                later_sg["failure_reason"] = "Abhaengigkeit gescheitert"
                later_sg["failed_at"] = datetime.now(timezone.utc).isoformat()
                cascade_count += 1
        if cascade_count:
            goal.setdefault("progress_log", []).append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": f"{cascade_count} abhaengige Sub-Goals kaskaden-gescheitert",
            })
            self._save()

        # Keine offenen Sub-Goals mehr? → Entscheiden ob done oder abandoned
        remaining = [s for s in sgs if s["status"] in ("pending", "in_progress")]
        if not remaining and sgs:
            all_failed = all(s["status"] == "failed" for s in sgs)
            if all_failed:
                return self.abandon_goal(goal_index, f"Alle Sub-Goals gescheitert: {reason}")
            # Mix aus done + failed → abschliessen nur wenn >= 50% done
            done_count = sum(1 for s in sgs if s["status"] == "done")
            failed_count = sum(1 for s in sgs if s["status"] == "failed")
            if done_count > 0 and done_count >= failed_count:
                return self.complete_goal(
                    goal_index,
                ) + f" (teilweise: {done_count} erledigt, {failed_count} gescheitert)"
            elif done_count > 0:
                # Mehr failed als done → aufgeben
                return self.abandon_goal(
                    goal_index,
                    f"Mehrheit gescheitert: {done_count} erledigt, {failed_count} gescheitert",
                )

        # Failed-Domain-Tracking: gescheiterte Domain fuer Dream-Guard speichern
        self._record_failed_domain(sg, reason)

        return f"Sub-Goal als gescheitert markiert: {sg['title']} — Grund: {reason}"

    def _record_failed_domain(self, subgoal: dict, reason: str):
        """Speichert gescheiterte Domain fuer Dream-Guard.

        Nur bei echtem Scheitern (nicht bei Abhaengigkeits-Kaskaden
        oder trivialen Fehlern mit wenig Waste).
        """
        stats = subgoal.get("_attempt_stats", {})
        # Kaskaden-Fails nicht tracken — die Ursache liegt im Vorgaenger
        if "Abhaengigkeit" in (reason or "") and stats.get("total_wasted_steps", 0) < 10:
            return

        domain = self._classify_domain(subgoal.get("title", ""))
        if domain == "sonstiges":
            return

        entry = {
            "domain": domain,
            "title": subgoal.get("title", "")[:100],
            "reason": (reason or "")[:200],
            "wasted_steps": stats.get("total_wasted_steps", 0),
            "efficiency": stats.get("last_efficiency", 0.0),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "keywords": list(set(subgoal.get("title", "").lower().split()))[:10],
        }

        failed = self.goals.setdefault("_failed_domains", [])
        failed.append(entry)

        # Max 30 Eintraege (FIFO)
        if len(failed) > 30:
            self.goals["_failed_domains"] = failed[-30:]

        self._save()

    def get_failed_domains_summary(self) -> str:
        """Zusammenfassung gescheiterter Domaenen fuer Dream-Prompt."""
        failed = self.goals.get("_failed_domains", [])
        if not failed:
            return ""
        lines = ["GESCHEITERTE DOMAENEN (nicht erneut empfehlen):"]
        for f in failed[-10:]:
            lines.append(
                f"  - {f['domain']}: {f['title']} "
                f"(Grund: {f['reason'][:80]})"
            )
        return "\n".join(lines)

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
            if sg["status"] == "failed":
                continue  # Gescheiterte Sub-Goals nicht nochmal versuchen
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

        # Zuerst speichern — Sub-Goal Status muss persistent sein
        self._save()

        # Pruefen ob alle Sub-Goals done → Hauptziel abschliessen
        all_done = all(sg["status"] == "done" for sg in sgs)
        if all_done and sgs:
            return self.complete_goal(goal_index)

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
        completed = self.goals.setdefault("completed", [])
        completed.append(goal)
        # FIFO: Max 50 abgeschlossene Goals behalten
        if len(completed) > 50:
            self.goals["completed"] = completed[-50:]
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
        """Was sollte Lyra JETZT tun? Wertvollstes offenes Sub-Goal.

        Mit Telos: Waehlt das Goal mit hoechstem Telos-Score
        (Diversitaets-Bonus + Ring-Prioritaet). Ohne Telos: Index-Reihenfolge.
        """
        active = self.goals.get("active", [])
        if not active:
            return "Keine aktiven Ziele. Setze ein neues Ziel!"

        # Telos-Scoring: Goals nach Wert sortieren statt Index-Reihenfolge
        if self._telos:
            scored = []
            for i, goal in enumerate(active):
                has_pending = any(
                    sg["status"] in ("pending", "in_progress")
                    for sg in goal.get("sub_goals", [])
                )
                if has_pending or not goal.get("sub_goals"):
                    score = self._telos_score(goal)
                    scored.append((score, i, goal))
            if scored:
                # Phi-Balance: Meist das Beste, aber gelegentlich Neues
                scores = [s[0] for s in scored]
                chosen_idx = phi_balance(scores)
                _, _, best_goal = scored[chosen_idx]
                return self._format_focus(best_goal)

        # Fallback: Index-Reihenfolge (altes Verhalten)
        for i, goal in enumerate(active):
            result = self._format_focus(goal)
            if result:
                return result

        return "Alle Sub-Goals erledigt — schliesse Ziele ab oder setze neue."

    def _format_focus(self, goal: dict) -> str:
        """Formatiert ein Goal als Focus-String."""
        failed_sgs = [s for s in goal.get("sub_goals", []) if s["status"] == "failed"]
        failed_info = ""
        if failed_sgs:
            reasons = [f"  GESCHEITERT: {s['title']} — {s.get('failure_reason', '?')}"
                       for s in failed_sgs]
            failed_info = "\n" + "\n".join(reasons)

        for sg in goal.get("sub_goals", []):
            if sg["status"] in ("pending", "in_progress"):
                return (
                    f"FOKUS: {goal['title']}\n"
                    f"  Naechster Schritt: {sg['title']} [{sg['status']}]"
                    + failed_info
                )

        if not goal.get("sub_goals"):
            return f"FOKUS: {goal['title']} (keine Sub-Goals definiert)"

        return ""

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
                    status_icon = {"pending": " ", "in_progress": ">", "done": "x", "failed": "!"}
                    icon = status_icon.get(sg["status"], "?")
                    lines.append(f"     [{icon}] {sg['title']}")
        else:
            lines.append("Keine aktiven Ziele.")

        if completed:
            lines.append(f"\nERREICHT ({len(completed)}):")
            for g in completed[-5:]:
                lines.append(f"  + {g['title']}")

        return "\n".join(lines)
