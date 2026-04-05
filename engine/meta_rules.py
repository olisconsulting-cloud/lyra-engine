"""
Meta-Regeln — Harte System-Regeln aus wiederholten Mustern.

Unterschied zu Strategies/Prompts:
- Strategies = Soft-Hinweise im Prompt (Phi kann sie ignorieren)
- Meta-Regeln = Harte Guards im Code (System erzwingt sie)

Wenn Metacognition 3x denselben Bottleneck erkennt,
wird automatisch ein Guard eingebaut der das Verhalten aendert.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)


class MetaRuleEngine:
    """Erzwingt Verhaltensregeln die aus Erfahrung gelernt wurden."""

    def __init__(self, consciousness_path: Path):
        self.rules_path = consciousness_path / "meta_rules.json"
        self.rules = self._load_rules()

    def _load_rules(self) -> dict:
        """Laedt Meta-Regeln: Bootstrap-Defaults + Instanz-Overrides."""
        from .bootstrap import load_meta_rules
        return load_meta_rules(self.rules_path)

    def _save_rules(self):
        """Persistiert Meta-Regeln."""
        safe_json_write(self.rules_path, self.rules)

    # === Muster erkennen und Regeln ableiten ===

    def record_pattern(self, pattern_id: str, description: str):
        """Zaehlt ein beobachtetes Muster hoch.

        Bei 3+ Vorkommen wird automatisch eine Meta-Regel erstellt.
        """
        counts = self.rules.setdefault("pattern_counts", {})
        counts[pattern_id] = counts.get(pattern_id, 0) + 1
        count = counts[pattern_id]

        # Ab 3 Vorkommen: Regel erstellen
        if count == 3:
            self._create_rule_from_pattern(pattern_id, description)
            logger.info(f" Meta-Regel erstellt: {pattern_id} (nach {count}x)")

        self._save_rules()

    def _create_rule_from_pattern(self, pattern_id: str, description: str):
        """Erstellt eine harte Regel aus einem wiederkehrenden Muster."""
        # Vordefinierte Regel-Templates
        rule_templates = {
            "token_budget_research": {
                "type": "step_limit",
                "condition": "goal_type == 'recherche'",
                "action": "max_steps = 20, force_finish_with_partial",
                "prompt_injection": (
                    "HARTE REGEL: Bei Recherche-Aufgaben maximal 20 Steps. "
                    "Nach 15 Steps MUSS ein Zwischenergebnis geschrieben werden. "
                    "Lieber ein unvollstaendiges Ergebnis als gar keins."
                ),
            },
            "no_finish_sequence": {
                "type": "enforcement",
                "condition": "3x kein finish_sequence aufgerufen",
                "action": "force_finish_at_80_percent",
                "prompt_injection": (
                    "HARTE REGEL: Du MUSST finish_sequence selbst aufrufen. "
                    "In den letzten Sequenzen wurde es nie explizit genutzt. "
                    "Plane dein finish_sequence von Anfang an ein."
                ),
            },
            "zero_output_loop": {
                "type": "detection",
                "condition": "3x keine Dateien geschrieben",
                "action": "force_write_or_finish",
                "prompt_injection": (
                    "HARTE REGEL: Jede Sequenz MUSS mindestens eine Datei schreiben "
                    "oder ein konkretes Ergebnis produzieren. "
                    "Reines Lesen ohne Output ist nicht erlaubt."
                ),
            },
            "same_subgoal_stuck": {
                "type": "reflection",
                "condition": "3x gleiches Sub-Goal ohne Fortschritt",
                "action": "reflect_and_learn",
                "prompt_injection": (
                    "HARTE REGEL: Du arbeitest zum dritten Mal am gleichen Ziel "
                    "ohne Fortschritt. BEVOR du weitermachst:\n"
                    "1. REFLEKTIERE: Was genau blockiert dieses Ziel?\n"
                    "2. ANALYSIERE: Was hast du bisher versucht und warum hat es nicht funktioniert?\n"
                    "3. LERNE: Was ist die Ursache des Problems?\n"
                    "4. ENTSCHEIDE: Neuer Ansatz ODER Ziel als gescheitert markieren "
                    "(fail_subgoal) mit klarer Begruendung.\n"
                    "Schreibe deine Analyse in finish_sequence unter 'bottleneck' "
                    "und 'next_time_differently'."
                ),
            },
            "recurring_engine_warning": {
                "type": "self_diagnosis",
                "condition": "Gleiche Warnung in 3+ Sequenzen",
                "action": "investigate_engine_source",
                "prompt_injection": (
                    "HARTE REGEL: Eine Warnung tritt wiederholt auf. "
                    "Warnungen sind KEIN Naturgesetz — sie kommen aus deinem Engine-Code.\n"
                    "AKTION:\n"
                    "1. read_own_code('engine/security.py') um die Warnung zu verstehen\n"
                    "2. Pruefe ob die Warnung ein False Positive ist\n"
                    "3. Falls ja: modify_own_code um den Check zu verbessern\n"
                    "4. Falls nein: Passe deinen Code an um die Warnung zu vermeiden\n"
                    "Du KANNST deinen eigenen Engine-Code verbessern. Tu es."
                ),
            },
        }

        # Passende Regel finden oder generische erstellen
        template = rule_templates.get(pattern_id, {
            "type": "generic",
            "condition": f"Muster '{pattern_id}' 3x erkannt",
            "action": "prompt_warning",
            "prompt_injection": f"WARNUNG: Wiederkehrendes Muster erkannt: {description[:150]}",
        })

        rule = {
            "id": pattern_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "description": description[:200],
            "active": True,
            **template,
        }

        # Duplikate vermeiden
        existing_ids = {r["id"] for r in self.rules.get("rules", [])}
        if pattern_id not in existing_ids:
            self.rules.setdefault("rules", []).append(rule)

    # === Regeln anwenden ===

    def get_active_rules(self) -> list:
        """Gibt alle aktiven Meta-Regeln zurueck."""
        return [r for r in self.rules.get("rules", []) if r.get("active")]

    def get_prompt_injections(self) -> str:
        """Baut System-Prompt-Ergaenzungen aus aktiven Regeln.

        Returns:
            Text fuer System-Prompt oder leerer String.
        """
        active = self.get_active_rules()
        if not active:
            return ""

        lines = ["\n=== META-REGELN (aus Erfahrung gelernt — NICHT ignorieren) ==="]
        for rule in active:
            injection = rule.get("prompt_injection", "")
            if injection:
                lines.append(f"- {injection}")
        return "\n".join(lines)

    def check_guards(self, step: int, files_written: int,
                     errors: int, focus: str) -> list[str]:
        """Prueft ob harte Guards greifen und gibt Aktionen zurueck.

        Returns:
            Liste von Aktions-Strings (leer wenn nichts greift).
        """
        actions = []
        for rule in self.get_active_rules():
            rule_type = rule.get("type", "")

            if rule_type == "step_limit" and "recherche" in focus.lower():
                # Recherche-Tasks: Hartes Step-Limit
                if step >= 20:
                    actions.append("force_finish_partial")

            elif rule_type == "detection" and rule["id"] == "zero_output_loop":
                # Deaktiviert: BehaviorActuator uebernimmt diesen Check
                # mit adaptivem output_checkpoint_step (harter Abbruch statt Warnung)
                pass

        return actions

    # === Regeln aus MetaCognition ableiten ===

    def learn_from_metacognition(self, bottleneck: str, next_time: str,
                                  seq_num: int, steps: int,
                                  files_written: int, errors: int):
        """Analysiert Metacognition-Daten und leitet Muster ab.

        Wird nach jeder Sequenz aufgerufen.
        Robustes Matching: mehrere Synonyme pro Pattern, damit Counts steigen.
        """
        bl = bottleneck.lower()

        # Token-Budget: bei JEDER Token-Erschoepfung (nicht nur Recherche)
        if any(w in bl for w in ("token", "budget", "token-limit", "erschoepft", "ausgegangen")):
            self.record_pattern(
                "token_budget_research",
                "Token-Budget geht aus bevor Aufgabe abgeschlossen"
            )

        # Kein finish_sequence: breitere Erkennung
        if any(w in bl for w in ("finish_sequence", "max steps", "max_steps",
                                  "abgebrochen", "timeout", "abbruch",
                                  "kein explizites", "token-limit")):
            self.record_pattern(
                "no_finish_sequence",
                "finish_sequence wird nicht rechtzeitig aufgerufen"
            )

        # Keine Dateien geschrieben (datenbasiert, unabhaengig von Bottleneck-Text)
        if files_written == 0 and steps > 10:
            self.record_pattern(
                "zero_output_loop",
                f"Sequenz {seq_num}: {steps} Steps ohne Output"
            )

        # Fehlerrate zu hoch (datenbasiert)
        if errors > 3:
            self.record_pattern(
                "high_error_rate",
                f"Sequenz {seq_num}: {errors} Fehler bei {steps} Steps"
            )

        # Wiederkehrende Security-Warnungen / Engine-Probleme
        if any(w in bl for w in ("security", "warnung", "warning", "exec(",
                                  "blockiert", "false positive")):
            self.record_pattern(
                "recurring_engine_warning",
                f"Sequenz {seq_num}: Security-Warnung als Bottleneck"
            )

    def check_subgoal_stuck(self, subgoal_title: str, consecutive_count: int):
        """Prueft ob ein Sub-Goal festhaengt.

        Args:
            subgoal_title: Name des Sub-Goals
            consecutive_count: Wie viele Sequenzen schon daran gearbeitet
        """
        if consecutive_count >= 3:
            self.record_pattern(
                "same_subgoal_stuck",
                f"Sub-Goal '{subgoal_title[:50]}' seit {consecutive_count} Sequenzen blockiert"
            )

    # === Verwaltung ===

    def deactivate_rule(self, rule_id: str):
        """Deaktiviert eine Regel (z.B. nach erfolgreicher Korrektur)."""
        for rule in self.rules.get("rules", []):
            if rule["id"] == rule_id:
                rule["active"] = False
                break
        self._save_rules()

    def get_stats(self) -> dict:
        """Statistiken ueber das Meta-Regel-System."""
        rules = self.rules.get("rules", [])
        return {
            "total_rules": len(rules),
            "active_rules": sum(1 for r in rules if r.get("active")),
            "patterns_tracked": len(self.rules.get("pattern_counts", {})),
        }
