"""
Sequence-Finisher — Saubere End-of-Sequence Verarbeitung.

Extrahiert die 12 verschiedenen Finish-Aktionen aus
_handle_finish_sequence() in benannte, testbare Methoden.

Aktionen in Reihenfolge:
1. Beliefs validieren und updaten
2. Prozess-Metriken berechnen
3. Experience speichern
4. Self-Rating aufzeichnen
5. Metacognition Record
6. Meta-Alerts verarbeiten
7. Reflexion speichern
8. Journal schreiben
9. Working/Sequence Memory updaten
10. Telegram-Report senden
11. Plan evaluieren + Skill extrahieren
12. Meta-Regeln + Checkpoint + Git + State speichern
"""

import logging
from typing import Optional

from .event_bus import EventBus, Events

logger = logging.getLogger(__name__)


class SequenceFinisher:
    """
    Verarbeitet das Ende einer Sequenz.

    Nimmt Referenzen auf alle benoetigten Subsysteme und fuehrt
    die 12 Finish-Aktionen in definierter Reihenfolge aus.
    """

    def __init__(self, event_bus: EventBus, **subsystems):
        """
        Args:
            event_bus: EventBus fuer Events
            **subsystems: Benoetigte Subsysteme als Keyword-Argumente:
                strategies, metacognition, self_rating, memory,
                planner, skill_library, meta_rules, checkpointer,
                git, communication, goal_stack, semantic_memory,
                failure_memory, efficiency
        """
        self.event_bus = event_bus
        self._subs = subsystems

    def _get(self, name: str):
        """Holt ein Subsystem. Gibt None zurueck wenn nicht vorhanden."""
        return self._subs.get(name)

    def finish(self, tool_input: dict, seq_metrics: dict,
               beliefs: dict, sequences_total: int) -> str:
        """
        Fuehrt alle 12 Finish-Aktionen aus.

        Args:
            tool_input: Die finish_sequence Parameter (summary, rating, beliefs, etc.)
            seq_metrics: Sequenz-Metriken (errors, files_written, step_count, etc.)
            beliefs: Aktuelles Beliefs-Dict (wird in-place modifiziert)
            sequences_total: Aktuelle Sequenz-Nummer

        Returns:
            Status-String
        """
        summary = tool_input.get("summary", "Keine Zusammenfassung")
        rating = tool_input.get("performance_rating", 5)
        bottleneck = tool_input.get("bottleneck", "")
        next_time = tool_input.get("next_time_differently", "")

        errors = []

        # 1. Beliefs
        try:
            self._update_beliefs(tool_input, beliefs)
        except Exception as e:
            errors.append(f"beliefs: {e}")

        # 2-3. Metriken + Experience
        try:
            self._store_experience(tool_input, seq_metrics, sequences_total)
        except Exception as e:
            errors.append(f"experience: {e}")

        # 4. Rating
        try:
            self._record_rating(rating, summary, sequences_total)
        except Exception as e:
            errors.append(f"rating: {e}")

        # 5-6. Metacognition + Alerts
        try:
            self._record_metacognition(
                tool_input, seq_metrics, sequences_total
            )
        except Exception as e:
            errors.append(f"metacognition: {e}")

        # 7. Reflexion
        try:
            self._store_reflection(summary, sequences_total)
        except Exception as e:
            errors.append(f"reflection: {e}")

        # 8-9. Journal + Memory
        try:
            self._update_journal_and_memory(
                tool_input, summary, sequences_total
            )
        except Exception as e:
            errors.append(f"journal: {e}")

        # 10. Telegram
        try:
            self._send_report(tool_input, summary, bottleneck, next_time, seq_metrics)
        except Exception as e:
            errors.append(f"telegram: {e}")

        # 11. Plan-Evaluation + Skill-Extraktion
        try:
            self._evaluate_and_learn(
                tool_input, seq_metrics, summary, rating, sequences_total
            )
        except Exception as e:
            errors.append(f"plan_eval: {e}")

        # Event feuern
        self.event_bus.emit_simple(
            Events.SEQUENCE_FINISHED, source="sequence_finisher",
            seq_num=sequences_total,
            rating=rating,
            errors=seq_metrics.get("errors", 0),
            files_written=seq_metrics.get("files_written", 0),
            summary=summary[:200],
        )

        if errors:
            logger.warning(f"SequenceFinisher: {len(errors)} Teilfehler: {errors}")

        return "Sequenz abgeschlossen. State gespeichert."

    def _update_beliefs(self, tool_input: dict, beliefs: dict):
        """Aktion 1: Neue Beliefs validieren und hinzufuegen."""
        new_beliefs = tool_input.get("new_beliefs", [])
        if not new_beliefs or not isinstance(new_beliefs, list):
            return

        formed = beliefs.get("formed_from_experience", [])
        for belief in new_beliefs:
            if not isinstance(belief, str) or not belief.strip():
                continue
            # Duplikat-Check
            if belief not in formed:
                formed.append(belief)

        # Max 30 Beliefs behalten
        beliefs["formed_from_experience"] = formed[-30:]

        # Dual-Loop Validierung
        strategies = self._get("strategies")
        if strategies:
            summary = tool_input.get("summary", "")
            rating = tool_input.get("performance_rating", 5)
            strategies.validate_against_outcome(new_beliefs, summary, rating)

    def _store_experience(self, tool_input: dict, seq_metrics: dict,
                          sequences_total: int):
        """Aktion 2-3: Metriken berechnen und Experience speichern."""
        memory = self._get("memory")
        if not memory:
            return

        summary = tool_input.get("summary", "")
        rating = tool_input.get("performance_rating", 5)
        steps = seq_metrics.get("step_count", 0)
        errors = seq_metrics.get("errors", 0)

        # Valence berechnen: Rating 1→-0.29, 5→0.29, 10→1.0
        valence = (rating - 1) / 7 - 0.29 if rating <= 5 else (rating - 5) / 5
        if errors > 2:
            valence -= 0.1

        efficiency = seq_metrics.get("efficiency_ratio", 0.0)

        memory.store_experience({
            "type": "sequenz_abschluss",
            "content": summary[:500],
            "valence": max(-1.0, min(1.0, valence)),
            "emotions": {},
            "tags": ["sequenz", f"rating_{rating}"],
            "process_metrics": {
                "steps": steps,
                "errors": errors,
                "output": seq_metrics.get("files_written", 0),
                "efficiency_ratio": efficiency,
                "key_decision": tool_input.get("key_decision", ""),
            },
        })

    def _record_rating(self, rating: int, summary: str, sequences_total: int):
        """Aktion 4: Self-Rating aufzeichnen."""
        self_rating = self._get("self_rating")
        if self_rating and rating:
            self_rating.add_rating(rating, summary[:100], sequences_total)

    def _record_metacognition(self, tool_input: dict, seq_metrics: dict,
                              sequences_total: int):
        """Aktion 5-6: Metacognition Record + Meta-Alerts."""
        metacog = self._get("metacognition")
        if not metacog:
            return

        bottleneck = tool_input.get("bottleneck", "")
        next_time = tool_input.get("next_time_differently", "")
        steps = seq_metrics.get("step_count", 0)
        files = seq_metrics.get("files_written", 0)

        # Wasted/Productive Steps schaetzen
        errors = seq_metrics.get("errors", 0)
        wasted = min(errors * 2, steps)
        productive = max(0, steps - wasted)

        metacog.record(
            bottleneck=bottleneck,
            next_time=next_time,
            seq_num=sequences_total,
            wasted_steps=wasted,
            productive_steps=productive,
            key_decision=tool_input.get("key_decision", ""),
        )

        # Meta-Alerts: Patterns analysieren
        strategies = self._get("strategies")
        if strategies:
            patterns = metacog.analyze_patterns()
            if patterns:
                for pattern in patterns:
                    strategies.record_process_pattern(pattern)

    def _store_reflection(self, summary: str, sequences_total: int):
        """Aktion 7: Reflexion speichern."""
        memory = self._get("memory")
        if memory:
            memory.store_reflection({
                "content": summary[:500],
                "insights": [],
                "cycle": sequences_total,
                "triggered_by": "finish_sequence",
            })

    def _update_journal_and_memory(self, tool_input: dict, summary: str,
                                   sequences_total: int):
        """Aktion 8-9: Journal + Working/Sequence Memory."""
        comm = self._get("communication")
        if comm:
            comm.write_journal(f"Sequenz {sequences_total}: {summary[:200]}")

    def _send_report(self, tool_input: dict, summary: str, bottleneck: str,
                     next_time: str, seq_metrics: dict):
        """Aktion 10: Telegram-Report senden."""
        comm = self._get("communication")
        if not comm or not getattr(comm, "telegram_active", False):
            return

        rating = tool_input.get("performance_rating", 5)
        stars = "★" * rating + "☆" * (10 - rating)
        report = (
            f"Sequenz abgeschlossen\n"
            f"Rating: {stars}\n"
            f"Steps: {seq_metrics.get('step_count', '?')} | "
            f"Fehler: {seq_metrics.get('errors', 0)} | "
            f"Dateien: {seq_metrics.get('files_written', 0)}\n"
            f"{summary[:200]}"
        )
        try:
            comm.send_message(report)
        except Exception as e:
            logger.warning(f"SequenceFinisher: Telegram fehlgeschlagen: {e}")

    def _evaluate_and_learn(self, tool_input: dict, seq_metrics: dict,
                            summary: str, rating: int, sequences_total: int):
        """Aktion 11: Plan evaluieren + Skill extrahieren."""
        planner = self._get("planner")
        skill_library = self._get("skill_library")
        semantic_memory = self._get("semantic_memory")
        goal_stack = self._get("goal_stack")

        if planner:
            plan_eval = planner.evaluate_plan(
                summary, rating,
                seq_metrics.get("step_count", 0),
                seq_metrics.get("errors", 0),
            )
            plan_score = plan_eval.get("score", 0) if plan_eval else 0

            # Skill-Extraktion bei guter Performance
            if skill_library and plan_score >= 5 and rating >= 5:
                plan = planner.get_active_plan() or {}
                goal_type = ""
                if semantic_memory and goal_stack:
                    focus = goal_stack.get_current_focus()
                    goal_type = semantic_memory.classify_goal_type(focus)

                skill_library.extract_from_sequence(
                    plan_goal=plan.get("goal", summary[:100]),
                    plan_score=plan_score,
                    summary=summary,
                    tool_sequence=seq_metrics.get("tool_sequence", []),
                    goal_type=goal_type,
                    rating=rating,
                )
