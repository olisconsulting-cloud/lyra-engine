"""
Sequenz-Intelligence — Infrastruktur-Schicht fuer Phi's Sequenz-Steuerung.

Koordiniert alle Sequenz-Systeme hinter einer Fassade:
- CheckpointManager: Resilienz bei Abbruechen
- SequencePlanner: Adaptive Planung + Evaluation
- MetaRuleEngine: Harte Guards aus Erfahrung

consciousness.py redet NUR mit SequenceIntelligence, nie direkt mit den Sub-Modulen.

Drei-Phasen-Interface:
  1. init_sequence()  — Sequenz-Start: State reset, Resume-Context
  2. before_step()    — Pro Step: Dashboard, Warnungen, Checkpoint-Check
     after_tool()     — Nach Tool-Call: Stuck-Detection, Decay
  3. finish()         — Sequenz-Ende: Status, Plan-Eval, Meta-Learning
"""

from dataclasses import dataclass, field
from pathlib import Path

from .checkpoint import CheckpointManager
from .sequence_planner import SequencePlanner
from .meta_rules import MetaRuleEngine


# === Datenklassen (Return-Types) ===

@dataclass
class SeqMetrics:
    """Zaehler fuer eine laufende Sequenz. Direkt mutierbar."""
    tool_calls: int = 0
    errors: int = 0
    files_written: int = 0
    tools_built: int = 0
    written_paths: list[str] = field(default_factory=list)
    step_count: int = 0
    tool_sequence: list[dict] = field(default_factory=list)
    modify_count: int = 0
    # Neuheits-Tracking fuer Fortschritts-Puls (nicht JSON-serialisierbar — nur RAM)
    read_paths: set[str] = field(default_factory=set)
    unique_tools: set[str] = field(default_factory=set)
    _last_pulse_snapshot: int = 0


@dataclass
class InitResult:
    """Ergebnis von init_sequence() — Prompt-Fragmente fuer Perception."""
    meta_injections: str = ""
    resume_context: str = ""
    planning_prompt: str = ""


@dataclass
class StepPrompt:
    """Ergebnis von before_step() — dynamische Prompt-Teile fuer diesen Step."""
    prompt_parts: list[str] = field(default_factory=list)
    should_checkpoint: bool = False
    should_graceful_finish: bool = False


@dataclass
class AfterToolResult:
    """Ergebnis von after_tool() — Guidance fuer result_str."""
    guidance: str = ""
    is_stuck: bool = False
    stuck_count: int = 0
    blocked: bool = False  # True → Tool wird nicht ausgefuehrt


@dataclass
class FinishResult:
    """Ergebnis von finish() — finaler Sequenz-Status."""
    finish_status: str = "completed"
    plan_eval: dict = field(default_factory=dict)
    stuck_patterns: list[str] = field(default_factory=list)
    metrics: SeqMetrics = field(default_factory=SeqMetrics)
    stagnation_detected: bool = False
    stagnation_tools: list = field(default_factory=list)


class SequenceIntelligence:
    """Fassade fuer alle Sequenz-Steuerungs-Systeme.

    Kapselt: Metriken, Stuck-Detection, Dashboard, Warnungen,
    Checkpoint-Timing, Plan-Management, Finish-Differenzierung.
    """

    def __init__(self, consciousness_path: Path):
        self._path = consciousness_path

        # Sub-Module (bleiben als eigenstaendige Dateien)
        self._checkpointer = CheckpointManager(consciousness_path)
        self._planner = SequencePlanner(consciousness_path)
        self._meta_rules = MetaRuleEngine(consciousness_path)

        # Per-Sequence State (reset in init_sequence)
        self._metrics = SeqMetrics()
        self._stuck_tracker: dict[str, dict] = {}
        self._token_warning_sent = False
        self._cached_plan: dict = {}
        self._plan_cache_dirty = False
        self._focus = ""
        self._stagnant_checks = 0  # Fortschritts-Puls: aufeinanderfolgende Checks ohne Neuheit

    # =========================================================
    # Phase 1: Sequenz-Start
    # =========================================================

    def init_sequence(self, focus: str, working_memory: str = "") -> InitResult:
        """Resettet State und liefert Prompt-Fragmente fuer die Perception.

        Args:
            focus: Aktueller Fokus aus goal_stack
            working_memory: Fuer build_planning_prompt

        Returns:
            InitResult mit meta_injections, resume_context, planning_prompt
        """
        # Metriken zuruecksetzen
        self._metrics = SeqMetrics()
        self._stuck_tracker = {}
        self._token_warning_sent = False
        self._stagnant_checks = 0
        self._plan_cache_dirty = False
        self._focus = focus

        # Plan-Cache laden
        self._cached_plan = self._planner.get_active_plan()

        # Prompt-Fragmente sammeln
        resume = self._checkpointer.build_resume_context()
        meta_inj = self._meta_rules.get_prompt_injections()

        plan_history = self._planner.get_plan_history()
        plan_prompt = self._planner.build_planning_prompt(
            focus, working_memory, plan_history
        )

        return InitResult(
            meta_injections=meta_inj or "",
            resume_context=resume or "",
            planning_prompt=plan_prompt or "",
        )

    # =========================================================
    # Phase 2: Pro-Step Intelligence
    # =========================================================

    def before_step(self, step: int, step_budget: int,
                    token_pct: float, focus: str = "") -> StepPrompt:
        """Baut dynamische Prompt-Teile und prueft Checkpoints/Warnungen.

        Args:
            step: Aktueller Step-Index (0-basiert)
            step_budget: Maximale Steps (hartes Limit)
            token_pct: Token-Verbrauch als Anteil (0.0 - 1.0)
            focus: Aktueller Fokus (fuer Guard-Checks)

        Returns:
            StepPrompt mit prompt_parts, should_checkpoint, should_graceful_finish
        """
        # Plan-Cache bei Bedarf auffrischen
        if self._plan_cache_dirty:
            self._cached_plan = self._planner.get_active_plan()
            self._plan_cache_dirty = False

        parts = []
        planned_max = self._cached_plan.get("max_steps", 0) if self._cached_plan else 0
        plan_info = f"/{planned_max}" if planned_max > 0 else ""
        token_pct_int = int(token_pct * 100)

        # Live-Dashboard: Kompakte Status-Zeile
        parts.append(
            f"\n[Step {step}{plan_info} | Token: {token_pct_int}% "
            f"| Fehler: {self._metrics.errors} | Dateien: {self._metrics.files_written}]"
        )

        # Weiche Warnung: 3 Steps vor Phi's geplantem Limit
        steps_remaining = step_budget - step
        if planned_max > 0 and step == planned_max - 3:
            parts.append(
                f"\n\nHINWEIS: Du hast dir {planned_max} Steps geplant, "
                f"du bist bei Step {step}. Bist du auf Kurs? "
                "Wenn dein Ergebnis gut genug ist, nutze finish_sequence. "
                "Wenn nicht, arbeite weiter — du hast noch Spielraum."
            )

        # Harte Warnung: 5 Steps vor absolutem Limit
        if steps_remaining == 5:
            parts.append(
                "\n\nACHTUNG: Noch 5 Steps bis zum harten Limit. "
                "Sichere deine Zwischenergebnisse und nutze finish_sequence."
            )

        # Planner-Checkpoint: Reminder bei checkpoint_at oder Budget-Warnung
        plan_reminder = self._planner.build_checkpoint_reminder(
            self._metrics.step_count
        )
        if plan_reminder:
            parts.append(plan_reminder)

        # Meta-Rule Guards: Harte Regeln pruefen
        guard_actions = self._meta_rules.check_guards(
            self._metrics.step_count,
            self._metrics.files_written,
            self._metrics.errors,
            focus or self._focus,
        )
        if "force_finish_partial" in guard_actions:
            parts.append(
                "\n\nMETA-REGEL AKTIV: Step-Limit fuer diesen Aufgabentyp erreicht. "
                "Schreibe JETZT dein Zwischenergebnis und nutze finish_sequence."
            )

        # Fortschritts-Puls: Erkennt Schleifen ohne neue Information
        if step > 0 and step % 5 == 0:
            novelty = len(self._metrics.read_paths) + len(set(self._metrics.written_paths))
            delta = novelty - self._metrics._last_pulse_snapshot
            self._metrics._last_pulse_snapshot = novelty

            if delta == 0:
                self._stagnant_checks += 1
            else:
                self._stagnant_checks = 0

            if self._stagnant_checks >= 3:  # 20 Steps ohne Neuheit (3 Checks * 5 Steps + 5 Offset)
                parts.append(
                    "\n\nHARTE REGEL: 20 Steps ohne Fortschritt. "
                    "Du MUSST jetzt finish_sequence aufrufen mit deinem bisherigen Stand. "
                    "Weitermachen ohne neuen Ansatz ist VERBOTEN."
                )
            elif self._stagnant_checks >= 2:  # 15 Steps ohne Neuheit (2 Checks * 5 Steps + 5 Offset)
                parts.append(
                    "\n\n⚠ FORTSCHRITTS-CHECK: In den letzten 15 Steps keine neuen "
                    "Dateien gelesen oder geschrieben. "
                    "REFLEKTIERE: Was blockiert dich? Aendere deinen Ansatz. "
                    "(1) Andere Dateien/Quellen suchen, "
                    "(2) Teilergebnis schreiben, oder (3) finish_sequence aufrufen."
                )

        # Token-Budget Warnung bei 80%
        if token_pct >= 0.80 and not self._token_warning_sent:
            self._token_warning_sent = True
            parts.append(
                f"\n\n⚠ TOKEN-BUDGET: {token_pct_int}% verbraucht. "
                "Schliesse deine aktuelle Aufgabe AB und nutze finish_sequence. "
                "Sichere Zwischenergebnisse JETZT."
            )

        return StepPrompt(
            prompt_parts=parts,
            should_checkpoint=self._checkpointer.should_checkpoint(
                self._metrics.step_count
            ),
            should_graceful_finish=(token_pct >= 0.95),
        )

    def after_tool(self, name: str, tool_input: dict,
                   result_str: str, is_error: bool) -> AfterToolResult:
        """Verarbeitet Tool-Ergebnis: Stuck-Detection + Metriken.

        Args:
            name: Tool-Name
            tool_input: Tool-Parameter
            result_str: Ergebnis-String (gekuerzt)
            is_error: True wenn Fehler

        Returns:
            AfterToolResult mit guidance (Stuck-Warnings, Datei-Hints)
        """
        # Metriken aktualisieren
        self._metrics.step_count += 1
        self._metrics.tool_sequence.append({"name": name})
        self._metrics.unique_tools.add(name)

        # Neuheits-Tracking: Gelesene Pfade erfassen
        if name in ("read_file", "list_directory", "read_own_code"):
            read_path = tool_input.get("path", "")
            if read_path:
                self._metrics.read_paths.add(read_path)

        # Stuck-Key: Tool + relevanter Input
        stuck_key, stuck_input = self._make_stuck_key(name, tool_input)
        stuck_info = self._stuck_tracker.get(stuck_key, {"count": 0, "last_error": ""})

        guidance = ""

        if is_error:
            # Fehler tracken
            stuck_info["count"] += 1
            stuck_info["last_error"] = result_str[:200]
            self._stuck_tracker[stuck_key] = stuck_info

            # Stuck-Warning ab 2 Fehlern
            if stuck_info["count"] >= 2:
                guidance += (
                    f"\n\n⚠ STUCK-WARNUNG: {name} mit '{stuck_input}' ist "
                    f"bereits {stuck_info['count']}x fehlgeschlagen. "
                    f"Letzter Fehler: {stuck_info['last_error'][:150]}\n"
                    "STOPP und denk nach: Ist der Pfad/Name korrekt? "
                    "Nutze list_directory um verfuegbare Dateien zu sehen."
                )

            # Bei 3+ read_file Fehlern: Verzeichnis-Listing
            if stuck_info["count"] >= 3 and name == "read_file":
                try:
                    parent = Path(stuck_input).parent
                    if parent.exists():
                        files = sorted(p.name for p in parent.iterdir() if p.is_file())[:15]
                        guidance += (
                            f"\n\n📂 Verfuegbare Dateien in {parent}:\n"
                            + "\n".join(f"  - {f}" for f in files)
                        )
                except Exception:
                    pass

            return AfterToolResult(
                guidance=guidance,
                is_stuck=stuck_info["count"] >= 2,
                stuck_count=stuck_info["count"],
            )

        else:
            # Erfolg: Diesen Key zuruecksetzen
            self._stuck_tracker.pop(stuck_key, None)

            # Decay: Jeder Erfolg reduziert alte Fehler-Counts
            stale_keys = []
            for k, v in self._stuck_tracker.items():
                v["count"] = max(0, v["count"] - 1)
                if v["count"] == 0:
                    stale_keys.append(k)
            for k in stale_keys:
                del self._stuck_tracker[k]

            return AfterToolResult(guidance="", is_stuck=False, stuck_count=0)

    @staticmethod
    def _make_stuck_key(name: str, tool_input: dict) -> tuple[str, str]:
        """Berechnet Stuck-Key aus Tool-Name + relevantem Input. DRY-Methode."""
        stuck_input = tool_input.get("path", tool_input.get("name", str(tool_input)[:80]))
        return f"{name}:{stuck_input}", stuck_input

    def check_blocked(self, name: str, tool_input: dict) -> AfterToolResult:
        """Prueft ob ein Tool blockiert ist (3+ Fehler mit gleichem Input).

        Wird VOR Tool-Ausfuehrung aufgerufen. Bei Block wird das Tool
        nicht ausgefuehrt — spart API-Call und verhindert Endlos-Schleifen.
        """
        stuck_key, stuck_input = self._make_stuck_key(name, tool_input)
        info = self._stuck_tracker.get(stuck_key, {"count": 0, "last_error": ""})
        if info["count"] >= 3:
            return AfterToolResult(
                guidance=(
                    f"BLOCKIERT: {name} mit '{stuck_input}' ist "
                    f"{info['count']}x gescheitert. Letzter Fehler: "
                    f"{info['last_error'][:100]}. "
                    "Anderer Ansatz noetig — dieses Tool+Input wird nicht mehr ausgefuehrt."
                ),
                is_stuck=True,
                stuck_count=info["count"],
                blocked=True,
            )
        return AfterToolResult(guidance="", is_stuck=False, stuck_count=0, blocked=False)

    def on_plan_updated(self) -> None:
        """Invalidiert Plan-Cache. Aufrufen nach update_sequence_plan."""
        self._plan_cache_dirty = True

    def get_refreshed_plan(self) -> dict:
        """Gibt gecachten Plan oder laedt neu bei Invalidierung."""
        if self._plan_cache_dirty:
            self._cached_plan = self._planner.get_active_plan()
            self._plan_cache_dirty = False
        return self._cached_plan

    # =========================================================
    # Phase 3: Sequenz-Ende
    # =========================================================

    def finish(self, summary: str, rating: int, step_count: int,
               seq_total: int, bottleneck: str = "",
               next_time: str = "") -> FinishResult:
        """Schliesst Sequenz ab: Plan-Eval + Meta-Learning + Checkpoint-Status.

        Args:
            summary: Zusammenfassung der Sequenz
            rating: Performance-Rating (1-10)
            step_count: Tatsaechlich genutzte Steps
            seq_total: Gesamt-Sequenznummer (fuer Meta-Rules)
            bottleneck: Was hat gebremst
            next_time: Was naechstes Mal anders machen

        Returns:
            FinishResult mit Status, Evaluation, Stuck-Patterns, Metriken
        """
        errors = self._metrics.errors
        files = self._metrics.files_written

        # Plan-Evaluation
        plan_eval = self._planner.evaluate_plan(
            summary, rating, step_count, errors
        )

        # Meta-Regeln aus Erfahrung ableiten
        self._meta_rules.learn_from_metacognition(
            bottleneck, next_time, seq_total,
            step_count, files, errors,
        )

        # Stuck-Patterns sammeln
        stuck_patterns = [k for k, v in self._stuck_tracker.items() if v["count"] >= 2]

        # Finish-Status ableiten
        if errors > 3 and files == 0:
            finish_status = "failed"
        elif rating >= 5 or files > 0:
            finish_status = "completed"
        else:
            finish_status = "paused"

        # Checkpoint mit differenziertem Status markieren
        self._checkpointer.mark_finished(
            status=finish_status,
            errors=errors,
            files_written=files,
            stuck_patterns=stuck_patterns,
        )

        # Stagnation erkennen fuer Lerneffekt
        stagnation = self._stagnant_checks >= 2
        stag_tools = list(self._metrics.unique_tools) if stagnation else []

        return FinishResult(
            finish_status=finish_status,
            plan_eval=plan_eval,
            stuck_patterns=stuck_patterns,
            metrics=self._metrics,
            stagnation_detected=stagnation,
            stagnation_tools=stag_tools,
        )

    # =========================================================
    # Accessors
    # =========================================================

    @property
    def metrics(self) -> SeqMetrics:
        """Aktuelle Sequenz-Metriken (direkt mutierbar)."""
        return self._metrics

    @property
    def stuck_patterns(self) -> list[str]:
        """Aktuell feststeckende Tool+Input Keys (count >= 2)."""
        return [k for k, v in self._stuck_tracker.items() if v["count"] >= 2]

    # =========================================================
    # Pass-throughs (fuer Tool-Dispatch + Perception)
    # =========================================================

    def save_plan(self, plan: dict) -> str:
        """Speichert neuen Sequenz-Plan."""
        result = self._planner.save_plan(plan)
        self._cached_plan = plan
        self._plan_cache_dirty = False
        return result

    def update_plan(self, updates: dict) -> str:
        """Aktualisiert laufenden Plan."""
        return self._planner.update_plan(updates)

    def get_plan_history(self) -> list:
        """Letzte Plan-Bewertungen."""
        return self._planner.get_plan_history()

    def get_avg_plan_score(self) -> float:
        """Durchschnittlicher Plan-Score."""
        return self._planner.get_avg_score()

    def build_planning_prompt(self, focus: str, working_memory: str,
                              last_plans: list = None) -> str:
        """Baut Planungs-Impuls fuer Perception."""
        return self._planner.build_planning_prompt(focus, working_memory, last_plans)

    def build_resume_context(self) -> str:
        """Resume-Kontext aus letztem Checkpoint."""
        return self._checkpointer.build_resume_context()

    def auto_checkpoint(self, step: int, engine) -> str:
        """Automatischer Checkpoint aus Engine-State."""
        return self._checkpointer.auto_save(step, engine)

    def clear_checkpoint(self) -> None:
        """Loescht Checkpoint (neuer Fokus)."""
        self._checkpointer.clear()

    @property
    def meta_rules(self) -> "MetaRuleEngine":
        """Oeffentlicher Zugang zu MetaRuleEngine fuer ToolMetaPatterns."""
        return self._meta_rules

    def get_meta_injections(self) -> str:
        """Meta-Regeln fuer System-Prompt."""
        return self._meta_rules.get_prompt_injections()

    def get_meta_stats(self) -> dict:
        """Meta-Regel-Statistiken."""
        return self._meta_rules.get_stats()
