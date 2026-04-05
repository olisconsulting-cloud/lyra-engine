"""
Behavior Actuator — Schliesst den Prediction-Error-Loop.

Das fehlende Glied zwischen Erkenntnis und Verhaltensaenderung.
Statt Erkenntnisse als Prompt-Text zu formulieren (den das LLM ignoriert),
werden sie in harte Code-Parameter uebersetzt, die consciousness.py erzwingt.

Basiert auf Fristons Free Energy Principle:
  1. Vorhersage (LLM plant Steps)
  2. Abgleich mit Realitaet (MetaCognition misst)
  3. Differenz berechnen (PredictionError)
  4. Modell anpassen (BehaviorActuator aendert Parameter)  ← DAS HIER
  5. Zurueck zu 1

Meta-Learning: ActuatorMeta bewertet ob Parameteraenderungen helfen.
  - Keine Verbesserung nach 10 Seq → Revert
  - Verbesserung → Learning-Rate beschleunigen
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)

# === Konstanten ===

# Hartes Step-Limit aus consciousness.py (fuer Prompt-Kontext)
MAX_STEPS_PER_SEQUENCE = 60

# Wie viele Pattern-Hits bevor Parameter angepasst wird
ADJUSTMENT_THRESHOLD = 3

# Sequenzen Cooldown nach Adjustment bevor Decay erlaubt ist
ADJUSTMENT_COOLDOWN = 5

# Default-Werte aus Bootstrap (getunte Erfahrungswerte) mit hardcoded Fallback
from .bootstrap import load_actuator_defaults
DEFAULTS = load_actuator_defaults()

# Grenzen fuer Parameter (Sicherheit gegen Spiral)
# output_checkpoint min=15: Phi braucht ~8 Steps zum Lesen + ~4 Planung + ~3 Schreiben
BOUNDS = {
    "step_budget_modifier": (0.3, 1.0),
    "research_depth_limit": (5, 30),
    "output_checkpoint_step": (15, 25),
}

# Wie stark Parameter pro Anpassung geaendert werden
ADJUSTMENT_STEP = {
    "step_budget_modifier": 0.1,       # -10% pro Trigger
    "research_depth_limit": 3,         # -3 Steps pro Trigger
    "output_checkpoint_step": 2,       # -2 Steps pro Trigger (frueher pruefen)
}

# Decay bei Erfolg: Parameter relaxiert zurueck Richtung Default
SUCCESS_DECAY = {
    "step_budget_modifier": 0.03,      # +3% pro erfolgreicher Sequenz
    "research_depth_limit": 1,         # +1 Step pro Erfolg
    "output_checkpoint_step": 0.5,     # +0.5 Step pro Erfolg (langsam)
}



# === Pattern-Mapping ===
# Welche MetaCognition-Bottlenecks auf welche Parameter wirken

PATTERN_MAP = {
    "finish_too_late": {
        "target": "step_budget_modifier",
        "direction": "decrease",      # Weniger Steps erlauben
        "keywords": [
            "finish_sequence", "max steps", "max_steps", "abgebrochen",
            "timeout", "zu spaet", "kein explizites", "token-limit",
            "limit erreicht", "hartes limit",
        ],
    },
    "zero_output": {
        "target": "output_checkpoint_step",
        "direction": "decrease",      # Frueher pruefen
        "keywords": [
            "kein output", "keine datei", "zero output", "nichts geschrieben",
            "ohne output", "ohne ergebnis", "keine dateien",
        ],
    },
    "research_overrun": {
        "target": "research_depth_limit",
        "direction": "decrease",      # Research kuerzer halten
        "keywords": [
            "recherche", "research", "token budget", "token-budget",
            "erschoepft", "ausgegangen", "zu viel gelesen",
        ],
    },
}


# === Kern-Klasse ===


class BehaviorActuator:
    """Uebersetzt Prediction-Errors in harte Parameteraenderungen.

    Laedt/speichert State aus actuator_state.json.
    Wird von consciousness.py nach jeder Sequenz gefuettert.
    Parameter werden vor jeder Sequenz abgefragt.
    """

    def __init__(self, consciousness_path: Path):
        self._path = consciousness_path
        self._state_path = consciousness_path / "actuator_state.json"
        self._state = self._load()
        self._meta = ActuatorMeta(self._state)

    # === Public API: Parameter abfragen ===

    @property
    def step_budget_modifier(self) -> float:
        """Multiplikator fuer Step-Budget (Bounds-geclampt)."""
        val = self._state["parameters"].get(
            "step_budget_modifier", DEFAULTS["step_budget_modifier"]
        )
        lo, hi = BOUNDS["step_budget_modifier"]
        return max(lo, min(hi, val))

    @property
    def research_depth_limit(self) -> int:
        """Max Steps fuer Research-Tasks (Bounds-geclampt)."""
        val = int(self._state["parameters"].get(
            "research_depth_limit", DEFAULTS["research_depth_limit"]
        ))
        lo, hi = BOUNDS["research_depth_limit"]
        return max(lo, min(hi, val))

    @property
    def output_checkpoint_step(self) -> int:
        """Ab welchem Step Output geprueft wird (Bounds-geclampt)."""
        val = int(self._state["parameters"].get(
            "output_checkpoint_step", DEFAULTS["output_checkpoint_step"]
        ))
        lo, hi = BOUNDS["output_checkpoint_step"]
        return max(lo, min(hi, val))

    def get_parameter_summary(self) -> str:
        """Kompakte Zusammenfassung fuer System-Prompt / Logging."""
        params = self._state["parameters"]
        parts = []
        for key, default in DEFAULTS.items():
            val = params.get(key, default)
            if val != default:
                # Nur angepasste Parameter zeigen
                parts.append(f"{key}={val:.2f}" if isinstance(val, float) else f"{key}={val}")
        if not parts:
            return ""
        return "Actuator: " + ", ".join(parts)

    def get_prompt_context(self) -> str:
        """Baut Prompt-Kontext fuer Phi: zeigt aktive Anpassungen.

        Wird in den Planning-Prompt eingefuegt, damit Phi weiss
        dass sein Verhalten angepasst wurde und WARUM.
        """
        params = self._state["parameters"]
        lines = []

        sbm = params.get("step_budget_modifier", 1.0)
        if sbm < 1.0:
            effective = int(MAX_STEPS_PER_SEQUENCE * sbm)
            lines.append(
                f"ACTUATOR: Dein effektives Step-Budget ist {effective} "
                f"(Modifier: {sbm:.0%}). Grund: Wiederholte Ueberschreitungen. "
                f"Plane kompakter."
            )

        ocp = params.get("output_checkpoint_step", DEFAULTS["output_checkpoint_step"])
        if ocp < DEFAULTS["output_checkpoint_step"]:
            lines.append(
                f"ACTUATOR: Output-Checkpoint bei Step {ocp}. "
                f"Wenn bis dahin keine Datei geschrieben → Sequenz wird beendet."
            )

        rdl = params.get("research_depth_limit", DEFAULTS["research_depth_limit"])
        if rdl < DEFAULTS["research_depth_limit"]:
            lines.append(
                f"ACTUATOR: Research-Limit bei {rdl} Steps. "
                f"Recherche frueh zusammenfassen."
            )

        return "\n".join(lines)

    # === Public API: Goal-Aktionen ===

    def get_pending_goal_actions(self) -> list[dict]:
        """Gibt ausstehende Goal-Aktionen zurueck und leert die Queue.

        Wird von consciousness.py beim Sequenz-Start konsumiert.
        Jede Aktion wird nur einmal zurueckgegeben (einmal lesen = verbraucht).
        """
        actions = self._state.pop("pending_goal_actions", [])
        if actions:
            self._save()
        return actions

    # === Public API: Dream-Integration ===

    def learn_from_dream(self, dream_result: dict):
        """Empfaengt Dream-Insights und leitet Parameter- und Goal-Signale ab.

        Dream-Insights sind INPUT, kein Override.
        ActuatorMeta behaelt das letzte Wort (kann reverten).
        Bereits revertierte Aenderungen werden nicht wiederholt.

        Args:
            dream_result: Geparstes Dream-Ergebnis (aus dream_log.json).
                Relevante Keys: actuator_recommendations, goal_recommendations
        """
        # Goal-Recommendations speichern (werden beim naechsten Sequenz-Start konsumiert)
        goal_recs = dream_result.get("goal_recommendations", [])
        if goal_recs:
            valid_actions = {"abort", "simplify", "decompose", "continue"}
            pending = [
                rec for rec in goal_recs[:5]
                if rec.get("action") in valid_actions and rec.get("action") != "continue"
            ]
            if pending:
                self._state.setdefault("pending_goal_actions", []).extend(pending)
                self._save()
                logger.info(
                    "Actuator: %d Goal-Empfehlungen gespeichert: %s",
                    len(pending),
                    [f"{r['action']}:{r.get('subgoal', '?')[:30]}" for r in pending],
                )

        recommendations = dream_result.get("actuator_recommendations", [])
        if not recommendations:
            return

        current_seq = (
            self._state["efficiency_history"][-1].get("sequence", 0)
            if self._state.get("efficiency_history") else 0
        )

        applied = 0
        for rec in recommendations[:3]:
            param = rec.get("parameter", "")
            direction = rec.get("direction", "")
            reason = rec.get("reason", "")

            if param not in DEFAULTS or direction not in ("increase", "decrease"):
                continue

            # Guard: Kuerzlich revertierte Aenderung nicht wiederholen
            if self._was_recently_reverted(param, direction):
                logger.info(
                    "Actuator: Dream-Empfehlung ignoriert (kuerzlich revertiert): "
                    "%s %s — %s", param, direction, reason,
                )
                continue

            self._adjust_parameter(
                param, direction,
                trigger=f"dream:{reason[:50]}",
                seq_num=current_seq,
            )
            applied += 1

        if applied:
            self._state["_last_adjustment_seq"] = current_seq
            self._save()
            logger.info("Actuator: %d Dream-Empfehlungen angewandt", applied)

    def _was_recently_reverted(self, param: str, direction: str) -> bool:
        """Prueft ob ActuatorMeta eine aehnliche Aenderung kuerzlich revertiert hat."""
        recent_changes = self._state.get("change_history", [])[-10:]
        for change in recent_changes:
            if not change.get("reverted"):
                continue
            if change.get("parameter") != param:
                continue
            # Gleiche Richtung wie revertiert? Dann nicht wiederholen.
            old = change.get("old_value")
            new = change.get("new_value")
            if old is None or new is None:
                continue
            was_decrease = new < old
            if (direction == "decrease" and was_decrease) or \
               (direction == "increase" and not was_decrease):
                return True
        return False

    # === Public API: Feedback verarbeiten ===

    def process_prediction_error(
        self, bottleneck: str, next_time: str,
        seq_num: int, steps_used: int, files_written: int,
        efficiency_ratio: float,
        failure_context: dict | None = None,
    ):
        """Verarbeitet MetaCognition-Feedback nach einer Sequenz.

        Identifiziert Pattern, zaehlt Hits, passt Parameter an
        wenn ADJUSTMENT_THRESHOLD erreicht.

        Args:
            bottleneck: Bottleneck-Text aus finish_sequence
            next_time: Was naechstes Mal anders
            seq_num: Aktuelle Sequenz-Nummer
            steps_used: Wie viele Steps tatsaechlich genutzt
            files_written: Wie viele Dateien geschrieben
            efficiency_ratio: Produktive Steps / Gesamt-Steps
        """
        bl = bottleneck.lower() if bottleneck else ""
        nt = next_time.lower() if next_time else ""
        combined = f"{bl} {nt}"

        adjusted_this_call = False
        for pattern_id, config in PATTERN_MAP.items():
            if any(kw in combined for kw in config["keywords"]):
                if self._record_hit(pattern_id, config, seq_num, steps_used,
                                    files_written, failure_context):
                    adjusted_this_call = True

        # Datenbasierte Erkennung (unabhaengig von Bottleneck-Text)
        # Immer pruefen — auch wenn Keywords gematcht haben
        if files_written == 0 and steps_used > 10:
            if self._record_hit("zero_output", PATTERN_MAP["zero_output"],
                                seq_num, steps_used, files_written, failure_context):
                adjusted_this_call = True

        if steps_used >= 50:  # Nah am harten Limit von 60
            if self._record_hit("finish_too_late", PATTERN_MAP["finish_too_late"],
                                seq_num, steps_used, files_written, failure_context):
                adjusted_this_call = True

        # Erfolg? Parameter zurueck Richtung Default relaxieren
        # NICHT wenn in diesem Aufruf gerade ein Parameter gesenkt wurde (H2-Fix)
        # NICHT wenn innerhalb des Cooldowns nach letzter Anpassung
        last_adj = self._state.get("_last_adjustment_seq", 0)
        cooldown_ok = seq_num - last_adj >= ADJUSTMENT_COOLDOWN
        if files_written > 0 and efficiency_ratio > 0.3 and not adjusted_this_call and cooldown_ok:
            self._decay_toward_defaults(seq_num)

        # Effizienz fuer Meta-Learning speichern
        self._state["efficiency_history"].append({
            "sequence": seq_num,
            "efficiency": efficiency_ratio,
            "steps": steps_used,
            "files": files_written,
        })
        # Nur letzte 50 behalten
        self._state["efficiency_history"] = self._state["efficiency_history"][-50:]

        # Meta-Learning: Aeltere Aenderungen evaluieren
        self._meta.evaluate_pending(seq_num)

        self._save()

    # === Internes ===

    def _record_hit(self, pattern_id: str, pattern_config: dict,
                    seq_num: int, steps_used: int, files_written: int,
                    failure_context: dict | None = None) -> bool:
        """Zaehlt Pattern-Hit und passt Parameter an wenn Threshold erreicht.

        Ueberspringt Anpassung wenn Fehler-Kategorie zeigt dass Parameter-
        Tuning nicht helfen wird (z.B. CAPABILITY, INPUT_ERROR, LOGIC_ERROR).

        Returns:
            True wenn ein Parameter angepasst wurde.
        """
        hits = self._state.setdefault("pattern_hits", {})
        hits[pattern_id] = hits.get(pattern_id, 0) + 1
        count = hits[pattern_id]

        logger.info(
            "Actuator: Pattern '%s' Hit #%d (Seq %d, %d Steps, %d Files)",
            pattern_id, count, seq_num, steps_used, files_written,
        )

        # Anpassung bei Threshold (und dann alle N weitere Hits)
        if count >= ADJUSTMENT_THRESHOLD and (count - ADJUSTMENT_THRESHOLD) % ADJUSTMENT_THRESHOLD == 0:
            # Guard: Non-Process-Fehler → Skip (Parameter-Tuning hilft nicht)
            if failure_context and self._should_skip_adjustment(failure_context):
                dominant = failure_context.get("dominant", "unknown")
                logger.info(
                    "Actuator: SKIP '%s' — dominanter Fehler ist %s "
                    "(nicht-prozessual, Parameter-Tuning hilft nicht)",
                    pattern_id, dominant,
                )
                self._state.setdefault("skipped_adjustments", []).append({
                    "pattern": pattern_id, "sequence": seq_num, "reason": dominant,
                })
                self._state["skipped_adjustments"] = self._state["skipped_adjustments"][-50:]
                return False

            target = pattern_config["target"]
            direction = pattern_config["direction"]
            self._adjust_parameter(target, direction, pattern_id, seq_num)
            self._state["_last_adjustment_seq"] = seq_num
            return True
        return False

    @staticmethod
    def _should_skip_adjustment(failure_context: dict) -> bool:
        """True wenn dominanter Fehlertyp zeigt dass Parameter-Tuning nicht hilft.

        CAPABILITY (fehlende Lib), INPUT_ERROR (falscher Pfad),
        LOGIC_ERROR (Bug) → brauchen Code/Umgebungs-Fixes, nicht weniger Steps.
        UNKNOWN und NONE → koennten Prozess-Fehler sein → nicht skippen.
        """
        dominant = failure_context.get("dominant", "none")
        return dominant in ("capability", "input_error", "logic_error")

    def _adjust_parameter(self, param: str, direction: str,
                          trigger: str, seq_num: int):
        """Passt einen Parameter an und protokolliert fuer Meta-Learning."""
        params = self._state["parameters"]
        old_val = params.get(param, DEFAULTS[param])
        step = ADJUSTMENT_STEP[param]
        lo, hi = BOUNDS[param]

        if direction == "decrease":
            new_val = max(lo, old_val - step)
        else:
            new_val = min(hi, old_val + step)

        # Keine Aenderung noetig (schon am Limit)
        if new_val == old_val:
            return

        params[param] = new_val

        # Aktuelle Effizienz als Baseline fuer Meta-Learning
        recent = self._state.get("efficiency_history", [])[-10:]
        avg_eff = sum(e["efficiency"] for e in recent) / len(recent) if recent else 0.0

        self._state["change_history"].append({
            "parameter": param,
            "old_value": old_val,
            "new_value": new_val,
            "trigger": trigger,
            "sequence": seq_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "efficiency_before": avg_eff,
            "efficiency_after": 0.0,
            "evaluated": False,
            "reverted": False,
        })
        # Nur letzte 50 behalten
        self._state["change_history"] = self._state["change_history"][-50:]

        logger.info(
            "Actuator: %s angepasst %.2f → %.2f (Trigger: %s, Seq %d)",
            param, old_val, new_val, trigger, seq_num,
        )

    def _decay_toward_defaults(self, seq_num: int):
        """Relaxiert alle Parameter leicht zurueck Richtung Defaults."""
        params = self._state["parameters"]
        for param, default in DEFAULTS.items():
            current = params.get(param, default)
            if current == default:
                continue

            decay = SUCCESS_DECAY[param]
            if current < default:
                new_val = min(default, current + decay)
            else:
                new_val = max(default, current - decay)

            if new_val != current:
                # Integer-Parameter als int speichern (M1-Fix)
                if isinstance(default, int):
                    params[param] = int(round(new_val))
                else:
                    params[param] = round(new_val, 3)

    # === Persistence ===

    def _load(self) -> dict:
        """Laedt actuator_state.json oder erstellt Default-Struktur."""
        default = {
            "version": 1,
            "parameters": dict(DEFAULTS),
            "pattern_hits": {},
            "change_history": [],
            "efficiency_history": [],
            "skipped_adjustments": [],
        }
        data = safe_json_read(self._state_path, default=default)
        # Migration: Fehlende Keys nachfuellen
        for key in default:
            if key not in data:
                data[key] = default[key]
        for key in DEFAULTS:
            if key not in data.get("parameters", {}):
                data["parameters"][key] = DEFAULTS[key]
        # Migration: Parameter auf aktuelle Bounds clampen
        # (verhindert Todes-Spirale wenn Bounds angehoben wurden)
        for key, (lo, hi) in BOUNDS.items():
            val = data["parameters"].get(key)
            if val is not None and (val < lo or val > hi):
                old = val
                data["parameters"][key] = max(lo, min(hi, val))
                logger.info(
                    "Actuator-Migration: %s geclampt %s → %s (Bounds: %s-%s)",
                    key, old, data["parameters"][key], lo, hi,
                )
        return data

    def _save(self):
        """Speichert State atomar."""
        safe_json_write(self._state_path, self._state)

    def get_stats(self) -> dict:
        """Statistiken fuer Logging/Dashboard."""
        params = self._state["parameters"]
        hits = self._state.get("pattern_hits", {})
        changes = self._state.get("change_history", [])
        return {
            "parameters": dict(params),
            "total_hits": sum(hits.values()),
            "total_changes": len(changes),
            "reverts": sum(1 for c in changes if c.get("reverted")),
            "patterns": dict(hits),
        }


# === Meta-Learning ===


class ActuatorMeta:
    """Bewertet ob Parameteraenderungen tatsaechlich helfen.

    Vergleicht Durchschnitts-Effizienz vor vs. nach einer Aenderung.
    Revertiert Aenderungen die nach 10 Sequenzen keine Verbesserung zeigen.
    Beschleunigt Learning-Rate bei Verbesserungen.

    Das ist Arrow 4: Das System lernt WIE es lernt.
    """

    # Nach wie vielen Sequenzen wird eine Aenderung evaluiert
    EVAL_WINDOW = 10
    # Mindest-Verbesserung damit eine Aenderung behalten wird
    MIN_IMPROVEMENT = 0.03  # 3% Effizienz-Steigerung

    def __init__(self, state: dict):
        self._state = state

    def evaluate_pending(self, current_seq: int):
        """Evaluiert alle unevaluierten Aenderungen die alt genug sind."""
        changes = self._state.get("change_history", [])
        efficiency_history = self._state.get("efficiency_history", [])

        for change in changes:
            if change.get("evaluated"):
                continue

            change_seq = change.get("sequence", 0)
            if current_seq - change_seq < self.EVAL_WINDOW:
                continue  # Noch nicht alt genug

            # Effizienz nach der Aenderung berechnen (nur Eval-Window, nicht alles)
            after_entries = [
                e for e in efficiency_history
                if e["sequence"] > change_seq
            ][:self.EVAL_WINDOW]
            if len(after_entries) < 5:
                continue  # Zu wenig Daten nach der Aenderung

            avg_after = sum(e["efficiency"] for e in after_entries) / len(after_entries)
            avg_before = change.get("efficiency_before", 0.0)

            change["efficiency_after"] = avg_after
            change["evaluated"] = True

            improvement = avg_after - avg_before

            if improvement < self.MIN_IMPROVEMENT:
                # Keine Verbesserung → Revert
                self._revert_change(change)
                logger.info(
                    "ActuatorMeta: REVERT %s (%.2f → %.2f, Verbesserung: %.1f%% < %.1f%%)",
                    change["parameter"], change["old_value"], change["new_value"],
                    improvement * 100, self.MIN_IMPROVEMENT * 100,
                )
            else:
                logger.info(
                    "ActuatorMeta: BEHALTEN %s (Verbesserung: +%.1f%%)",
                    change["parameter"], improvement * 100,
                )

    def _revert_change(self, change: dict):
        """Revertiert eine Parameteraenderung die nicht geholfen hat."""
        param = change["parameter"]
        old_val = change["old_value"]
        params = self._state["parameters"]

        # Reverten wenn Parameter noch nah am geaenderten Wert steht
        # (Decay koennte ihn leicht verschoben haben)
        current = params.get(param, DEFAULTS.get(param))
        new_val = change["new_value"]

        # Pruefen: Ist der aktuelle Wert naeher am new_value als am old_value?
        dist_to_new = abs(current - new_val)
        dist_to_old = abs(current - old_val)
        if dist_to_new <= dist_to_old:
            # Bounds pruefen bei Revert
            lo, hi = BOUNDS.get(param, (old_val, old_val))
            reverted_val = max(lo, min(hi, old_val))
            params[param] = reverted_val
            change["reverted"] = True

            # Pattern-Hits zuruecksetzen damit der Threshold neu zaehlt (M5-Fix)
            # Dream-Trigger ("dream:reason") haben keine eigenen Pattern-Hits → Skip
            trigger = change.get("trigger", "")
            if trigger and not trigger.startswith("dream:"):
                hits = self._state.get("pattern_hits", {})
                hits[trigger] = max(0, hits.get(trigger, 0) - ADJUSTMENT_THRESHOLD)

            logger.info("ActuatorMeta: %s revertiert auf %.2f", param, reverted_val)
        else:
            # Parameter wurde zwischenzeitlich weiter angepasst → nicht reverten
            change["reverted"] = False
            logger.info(
                "ActuatorMeta: %s Skip-Revert (aktuell %.2f, zu weit von %.2f)",
                param, current, new_val,
            )
