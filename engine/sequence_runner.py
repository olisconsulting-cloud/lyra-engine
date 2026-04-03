"""
Sequence-Runner — Composable Sequenz-Phasen fuer meta-kognitive Kontrolle.

Bricht _run_sequence() in 5 klar getrennte Phasen auf:
  Perceive → Plan → Execute → Reflect → Learn

Jede Phase ist eigenstaendig, testbar und kann bei Bedarf
wiederholt oder uebersprungen werden.

SequenceContext ersetzt die fragmentierten self._seq_* Variablen
und bietet eine einzige, konsistente Datenstruktur fuer eine Sequenz.
"""

import logging
import time
from dataclasses import dataclass, field

from .event_bus import EventBus, Events

logger = logging.getLogger(__name__)


@dataclass
class SequenceContext:
    """
    Alle Daten einer laufenden Sequenz.

    Ersetzt self._seq_tool_calls, self._seq_errors, self._seq_files_written,
    self._seq_tools_built, self._seq_written_paths, self._seq_step_count,
    self._seq_tool_sequence, self._modify_count_this_seq
    """
    seq_num: int
    tool_calls: int = 0
    errors: int = 0
    files_written: int = 0
    tools_built: int = 0
    written_paths: list[str] = field(default_factory=list)
    tool_sequence: list[str] = field(default_factory=list)
    step_count: int = 0
    modify_count: int = 0
    stuck_tracker: dict[str, int] = field(default_factory=dict)
    stuck_patterns: list[str] = field(default_factory=list)
    finished: bool = False

    # Prompt und Messages
    messages: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    perception: str = ""

    # Modus und Budget
    mode: dict = field(default_factory=dict)
    task_type: str = "standard"
    step_budget: int = 40
    planned_max: int = 40

    # Tier-Management
    base_tiers: set[int] = field(default_factory=lambda: {1})
    escalated_tiers: set[int] = field(default_factory=set)

    # Timing
    start_time: float = field(default_factory=time.time)

    # Metriken
    input_tokens: int = 0
    output_tokens: int = 0

    def efficiency_ratio(self) -> float:
        """Berechnet Output pro Step."""
        if self.step_count == 0:
            return 0.0
        return (self.files_written + self.tools_built) / self.step_count

    def duration_seconds(self) -> float:
        """Vergangene Zeit seit Sequenz-Start."""
        return time.time() - self.start_time

    def to_metrics_dict(self) -> dict:
        """Konvertiert in ein Dict fuer Effizienz-Tracking."""
        return {
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "files_written": self.files_written,
            "tools_built": self.tools_built,
            "step_count": self.step_count,
            "efficiency_ratio": self.efficiency_ratio(),
            "duration": self.duration_seconds(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class SequenceRunner:
    """
    Orchestriert eine Sequenz in 5 Phasen.

    Phase 1: Perceive — Wahrnehmung aufbauen
    Phase 2: Plan — Modus bestimmen, Budget setzen, Tiers waehlen
    Phase 3: Execute — Step-Loop (LLM → Tool → Ergebnis → weiter)
    Phase 4: Reflect — Graceful Finish wenn noetig
    Phase 5: Learn — Effizienz tracken, History aufzeichnen

    Aktuell delegiert jede Phase an die bestehenden Engine-Methoden.
    Spaeter werden die Phasen eigene Logik haben.
    """

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def create_context(self, seq_num: int) -> SequenceContext:
        """Erstellt einen frischen SequenceContext."""
        return SequenceContext(seq_num=seq_num)

    def run(self, engine, ctx: SequenceContext = None) -> SequenceContext:
        """
        Fuehrt eine komplette Sequenz aus.

        Args:
            engine: ConsciousnessEngine Instanz
            ctx: Optional vorkonfigurierter Context

        Returns:
            Ausgefuellter SequenceContext mit allen Metriken
        """
        if ctx is None:
            ctx = self.create_context(engine.sequences_total + 1)

        self.event_bus.emit_simple(
            Events.SEQUENCE_STARTED, source="sequence_runner",
            seq_num=ctx.seq_num,
        )

        try:
            self._perceive(ctx, engine)
            self._plan(ctx, engine)
            self._execute(ctx, engine)
            self._reflect(ctx, engine)
            self._learn(ctx, engine)
        except Exception as e:
            logger.error(f"SequenceRunner: Fehler in Sequenz {ctx.seq_num}: {e}")
            raise

        return ctx

    def _perceive(self, ctx: SequenceContext, engine):
        """Phase 1: Wahrnehmung aufbauen."""
        ctx.perception = engine._build_perception()
        ctx.messages = [{"role": "user", "content": ctx.perception}]

    def _plan(self, ctx: SequenceContext, engine):
        """Phase 2: Modus, Budget und Tiers bestimmen."""
        ctx.mode = engine.rhythm.get_mode()
        ctx.task_type = engine._classify_task(ctx.perception)
        ctx.step_budget = engine._get_step_budget(ctx.task_type)
        ctx.planned_max = ctx.step_budget
        ctx.base_tiers = engine._get_base_tiers(ctx.mode, ctx.task_type)

    def _execute(self, ctx: SequenceContext, engine):
        """
        Phase 3: Step-Loop.

        Aktuell Platzhalter — die eigentliche Logik bleibt in
        _run_sequence() bis Phase 4 des Refactorings abgeschlossen ist.
        """
        # Wird spaeter den Step-Loop aus _run_sequence uebernehmen.
        # Fuer jetzt: Signal dass Execute aufgerufen wurde
        pass

    def _reflect(self, ctx: SequenceContext, engine):
        """Phase 4: Reflexion und Graceful Finish."""
        pass

    def _learn(self, ctx: SequenceContext, engine):
        """Phase 5: Effizienz-Tracking und History."""
        self.event_bus.emit_simple(
            Events.SEQUENCE_FINISHED, source="sequence_runner",
            seq_num=ctx.seq_num,
            errors=ctx.errors,
            files_written=ctx.files_written,
            efficiency=ctx.efficiency_ratio(),
        )
