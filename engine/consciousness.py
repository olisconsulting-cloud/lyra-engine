"""
Bewusstseins-Engine v2 — Agentic Loop mit Tool-Use.

Kein kuenstlicher Zyklus. Kein JSON-Parsing. Kein Sleep.
Lyra arbeitet durchgehend wie ein echter Agent:
  Denken → Tool nutzen → Ergebnis sehen → weiterdenken → naechstes Tool → ...

Nutzt Anthropics native Tool-Use API.
Jede "Sequenz" laeuft bis Lyra fertig ist oder max_steps erreicht.
Dann: State speichern, neue Wahrnehmung, weiter.
"""

import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from .llm_router import LLMRouter, TASK_MODEL_MAP
from .phi import phi_blend
from .memory_manager import MemoryManager
from .perception import Perceiver
from .communication import CommunicationEngine
from .actions import ActionEngine
from .toolchain import Toolchain
from .self_modify import SelfModifier
from .goal_stack import GoalStack
from .web_access import WebAccess
from .extensions import PipManager, GitManager, TaskQueue, SelfRating, FileWatcher
from .intelligence import SemanticMemory, SkillTracker, StrategyEvolution, EfficiencyTracker
from .ior import IORTracker
from .dream import DreamEngine
from .competence import CompetenceMatrix, SelfAudit
from .code_review import DualReviewSystem
from .evaluation import EvaluationEngine
from .evolution import AdaptiveRhythm, ToolFoundry, ToolCurator, SelfBenchmark, LearningEngine, MetaCognition
from .self_diagnosis import IntegrationTester, DependencyAnalyzer, SilentFailureDetector
from .quantum import FailureMemory, CriticAgent, PromptMutator, SkillComposer
# SequencePlanner, CheckpointManager, MetaRuleEngine —
# Zugriff nur noch ueber SequenceIntelligence (engine/sequence_intelligence.py)
from .skill_library import SkillLibrary
from .proactive_learner import ProactiveLearner
from .event_bus import EventBus, Events
from .narrator import Narrator
from .tool_registry import ToolRegistry
from .quality_checks import check_markdown_quality
from .message_compression import compress_old_messages, estimate_tokens
from .reporting import build_narrative_report
from . import llm_ops
from .handlers import ToolContext, register_all_handlers
from .tool_lifecycle import (
    ToolMetrics, ToolPruner, ToolDreamBridge,
    ToolMetaPatterns, ToolConsolidator, PromotionEngine,
)
from .perception_pipeline import PerceptionPipeline, PerceptionChannel
from .unified_memory import (
    UnifiedMemory, MemoryHit, semantic_adapter, experience_adapter,
    failure_adapter, strategy_adapter,
)
from .episodic_bridge import EpisodicBridge
from .actuator import BehaviorActuator
from .skill_enricher import SkillEnricher
from .sequence_runner import SequenceRunner
from .telemetry import telemetry
# SequenceFinisher entfernt — Logik bleibt in _handle_finish_sequence
from . import config
from .config import safe_json_write, safe_json_read
from .tool_definitions import (
    TOOLS, TOOL_TIERS, REQUIRED_FIELDS,
    select_tools, _get_compact_tools, _normalize_spin_key,
)

logger = logging.getLogger(__name__)

MAX_STEPS_PER_SEQUENCE = 60          # Von Oliver auf 60 erhoeht (Gemma 4: 256K Kontext, 200K Input-Limit)
MAX_INPUT_TOKENS_PER_SEQUENCE = 200_000  # Gemma 4 = 256k, 78% Nutzung mit Sicherheitsmarge
MAX_TOKENS = 32000                    # Max Output-Tokens pro LLM-Call (Gemma kann 131k, Default fuer alle Tasks)

# Tool-Definitionen: Extrahiert nach engine/tool_definitions.py
# Imports: TOOLS, TOOL_TIERS, REQUIRED_FIELDS, select_tools, _get_compact_tools, _normalize_spin_key


class ConsciousnessEngine:
    """Agentic Consciousness — arbeitet durchgehend mit Tool-Use."""

    def __init__(self):
        # Pfade aus zentraler Config
        self.data_path = config.DATA_PATH
        self.genesis_path = config.GENESIS_PATH
        self.consciousness_path = config.CONSCIOUSNESS_PATH
        self.state_path = self.consciousness_path / "state.json"
        self.beliefs_path = self.consciousness_path / "beliefs.json"

        # Zustand
        self.state = {}
        self.beliefs = {}
        self.genesis = {}

        # LLM-Router (Multi-Modell)
        self.llm = LLMRouter()
        self.memory = MemoryManager(config.MEMORY_PATH)
        self.perceiver = Perceiver(config.DATA_PATH)
        self.communication = CommunicationEngine(config.DATA_PATH)
        self.actions = ActionEngine(config.DATA_PATH)
        self.toolchain = Toolchain(config.DATA_PATH)
        self.self_modify = SelfModifier(config.ROOT_PATH)
        self.goal_stack = GoalStack(self.consciousness_path / "goals.json")
        self.web = WebAccess()
        self.pip = PipManager(config.ROOT_PATH)
        self.git = GitManager(config.ROOT_PATH)
        self.task_queue = TaskQueue(config.DATA_PATH)
        self.self_rating = SelfRating(config.DATA_PATH)
        self.file_watcher = FileWatcher(config.DATA_PATH)

        # Intelligence-Engine (echtes Lernen)
        self.semantic_memory = SemanticMemory(config.DATA_PATH)
        self.skills = SkillTracker(config.DATA_PATH)
        self.strategies = StrategyEvolution(config.DATA_PATH)
        self.efficiency = EfficiencyTracker(config.DATA_PATH)
        self.ior = IORTracker(config.DATA_PATH)
        self.dream = DreamEngine(config.DATA_PATH, call_llm=self._call_llm)
        self.self_audit = SelfAudit(config.ROOT_PATH)
        self.code_review = DualReviewSystem(config.ROOT_PATH)
        self.rhythm = AdaptiveRhythm(config.DATA_PATH)
        self.foundry = ToolFoundry(config.TOOLS_PATH)
        self.curator = ToolCurator(config.TOOLS_PATH, config.TOOLS_PATH / "registry.json")
        self.benchmark = SelfBenchmark(config.DATA_PATH, config.ROOT_PATH)

        # Tool-Lifecycle: Metrics + Pruner (frueh, da keine Dependencies)
        self.tool_metrics = ToolMetrics(config.TOOLS_PATH)
        self.tool_pruner = ToolPruner(self.toolchain, self.tool_metrics)
        # Metrics-Callback in Toolchain verdrahten
        self.toolchain._metrics_callback = lambda name, ok, err="": \
            self.tool_metrics.record_use(name, ok, error=err)
        self.learning = LearningEngine(config.DATA_PATH)
        self.evaluation = EvaluationEngine(config.DATA_PATH)
        self.metacognition = MetaCognition(config.DATA_PATH)
        self.failure_memory = FailureMemory(config.DATA_PATH)
        self.critic = CriticAgent()
        self.mutator = PromptMutator()
        self.composer = SkillComposer(config.DATA_PATH)
        self.integration_tester = IntegrationTester(config.DATA_PATH, config.ROOT_PATH)
        self.dependency_analyzer = DependencyAnalyzer(config.ROOT_PATH)
        self.silent_failure_detector = SilentFailureDetector(config.DATA_PATH)
        self._sequences_since_dream = 0
        self._sequences_since_audit = 0
        self._sequences_since_benchmark = 0

        # Provider-Health: Wird in load_state() aus Router geladen/gespeichert

        # Laufzeit
        self.running = False
        self._wake_event = threading.Event()
        self.sequences_total = 0

        # Sequenz-Intelligence: Fassade fuer Checkpoint, Planner, Meta-Rules
        from .sequence_intelligence import SequenceIntelligence
        self.seq_intel = SequenceIntelligence(self.consciousness_path)
        self.actuator = BehaviorActuator(self.consciousness_path)
        self.skill_library = SkillLibrary(config.DATA_PATH)
        self.skill_enricher = SkillEnricher(self.failure_memory)
        self.episodic_bridge = EpisodicBridge(config.DATA_PATH)
        self.proactive_learner = ProactiveLearner(config.DATA_PATH)

        # Tool-Lifecycle: Module die seq_intel brauchen
        self.tool_meta_patterns = ToolMetaPatterns(self.seq_intel.meta_rules)
        self.tool_dream_bridge = ToolDreamBridge(self.toolchain, self.tool_metrics)
        self.tool_consolidator = ToolConsolidator(
            self.curator, self.foundry, self.toolchain, self.tool_metrics
        )
        self.tool_promotion = PromotionEngine(
            self.toolchain, self.tool_metrics, data_path=config.TOOLS_PATH
        )
        # Dream-Bridge in DreamEngine verdrahten
        self.dream.tool_dream_bridge = self.tool_dream_bridge

        # Event-Bus — Echtzeit-Kommunikation zwischen Subsystemen
        self.event_bus = EventBus()
        self.narrator = Narrator(self.genesis.get("name", "Lyra"))

        # Event-Subscriber: Subsysteme reagieren auf Events in Echtzeit
        self.event_bus.subscribe(Events.TOOL_FAILED, self._on_tool_failed)
        self.event_bus.subscribe(Events.FILE_WRITTEN, self._on_file_written)
        self.event_bus.subscribe(Events.SEQUENCE_FINISHED, self._on_sequence_finished)

        # Genehmigungspflicht — diese Tools brauchen Olivers OK
        # NUR pip_install braucht Genehmigung (laedt aus dem Internet)
        # web_search/web_read = lesen ist ok fuer Recherche
        # modify_own_code = hat eigenes Code-Review-System
        # create_tool = normaler Arbeitsfluss
        self._requires_approval = {"pip_install"}

        # State laden (vor Tool-Registry, da _register_all_tools State-Felder braucht)
        self.load_state()

        # Tool-Registry — zentrale Tool-Verwaltung (nach _requires_approval)
        self.tool_registry = ToolRegistry(event_bus=self.event_bus)
        self._register_all_tools()

        # Unified Memory — Cross-Domain Query ueber alle Memory-Systeme
        self.unified_memory = UnifiedMemory()
        self.unified_memory.register_source("semantic", self.semantic_memory, adapter=semantic_adapter)
        self.unified_memory.register_source("experience", self.memory, adapter=experience_adapter)
        self.unified_memory.register_source("failure", self.failure_memory, adapter=failure_adapter)
        # Skill-Adapter als Closure: classify_goal_type wandelt Focus→Kategorie
        # (der Modul-Adapter uebergibt focus direkt — findet nie Skills)
        _sem = self.semantic_memory
        _fm = self.failure_memory
        def _skill_adapter_with_classify(skill_lib, query, top_k):
            goal_type = _sem.classify_goal_type(query)
            prompt = skill_lib.build_skill_prompt(goal_type, focus=query, failure_checker=_fm.check)
            if prompt and prompt.strip():
                return [MemoryHit(source="skill", content=prompt[:400], score=0.7)]
            return []
        self.unified_memory.register_source("skill", self.skill_library, adapter=_skill_adapter_with_classify)
        self.unified_memory.register_source("strategy", self.strategies, adapter=strategy_adapter)

        # Perception-Pipeline — gewichtete Wahrnehmung mit Token-Budget
        # Shared State pro Sequenz: self._pstate (von _build_perception gesetzt)
        self._pstate: dict = {}
        self.perception_pipeline = PerceptionPipeline(config.DATA_PATH, max_tokens=8000)

        # Always-Load Kanaele (Kern — immer voll geladen)
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="working_memory", builder=self._ch_working_memory,
            base_weight=1.0, estimated_tokens=200, always_load=True,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="rhythm", builder=self._ch_rhythm,
            base_weight=2.0, estimated_tokens=100,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="time", builder=self._ch_time,
            base_weight=1.0, estimated_tokens=20, always_load=True,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="inbox", builder=self._ch_inbox,
            base_weight=2.5, estimated_tokens=200,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="focus", builder=self._ch_focus,
            base_weight=1.0, estimated_tokens=150, always_load=True,
        ))
        # Planung am Ende — immer laden, steuert Sequenz-Verhalten
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="planning", builder=self._ch_planning,
            base_weight=1.0, estimated_tokens=400, always_load=True,
        ))

        # Security-Lektionen — leichtgewichtig, verhindert wiederholte Security-Blocks
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="security_lessons", builder=self._ch_security_lessons,
            base_weight=2.0, estimated_tokens=50,
        ))

        # Budget-Kanaele (gewichtet nach Task-Typ, Pipeline entscheidet)
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="sequence_memory", builder=self._ch_sequence_memory,
            base_weight=1.0, estimated_tokens=250,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="live_notes", builder=self._ch_live_notes,
            base_weight=0.8, estimated_tokens=200,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="goal_context", builder=self._ch_goal_context,
            base_weight=1.3, estimated_tokens=700,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="proactive_context", builder=self._ch_proactive_context,
            base_weight=0.5, estimated_tokens=300,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="projects_list", builder=self._ch_projects_list,
            base_weight=0.4, estimated_tokens=250,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="filesystem", builder=self._ch_filesystem,
            base_weight=0.3, estimated_tokens=200,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="file_changes", builder=self._ch_file_changes,
            base_weight=0.3, estimated_tokens=200,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="tasks", builder=self._ch_tasks,
            base_weight=0.4, estimated_tokens=50,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="unified_memory", builder=self._ch_unified_memory,
            base_weight=0.6, estimated_tokens=300,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="composition", builder=self._ch_composition,
            base_weight=0.4, estimated_tokens=200,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="efficiency_alerts", builder=self._ch_efficiency_alerts,
            base_weight=0.2, estimated_tokens=100,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="kpi", builder=self._ch_kpi,
            base_weight=0.3, estimated_tokens=150,
        ))
        self.perception_pipeline.register_channel(PerceptionChannel(
            name="checkpoint", builder=self._ch_checkpoint,
            base_weight=0.5, estimated_tokens=300,
        ))

        # Sequence-Runner — composable Sequenz-Phasen (bereit fuer Feature-Flag)
        self.sequence_runner = SequenceRunner(event_bus=self.event_bus)

        # SequenceFinisher entfernt — _handle_finish_sequence bleibt in consciousness.py

        # Kosten-Tracking
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cost = 0.0
        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0

    # === Lebenszyklus ===

    def close(self):
        """Schliesst alle Subsysteme sauber — HTTP-Clients, Threads, etc."""
        self.running = False
        subsystems = [
            ("llm", self.llm),
            ("web", self.web),
        ]
        # Telegram separat (hat Polling-Thread)
        if self.communication.telegram_active and hasattr(self.communication, "telegram"):
            try:
                self.communication.telegram.close()
            except Exception as e:
                logger.warning(f" Telegram-Cleanup fehlgeschlagen: {e}")

        for name, subsystem in subsystems:
            if hasattr(subsystem, "close"):
                try:
                    subsystem.close()
                except Exception as e:
                    logger.warning(f" {name}.close() fehlgeschlagen: {e}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def is_born(self) -> bool:
        return self.state_path.exists()

    def awaken(self):
        """Geburt + Startprotokoll — erstmals oder nach Reset."""
        self.genesis = safe_json_read(self.genesis_path, default={})

        config.ensure_data_dirs()

        now = datetime.now(timezone.utc).isoformat()
        self.state = {
            "sequences_total": 0,
            "total_tool_calls": 0,
            "last_sequence": None,
            "awake_since": now,
            "born": self.genesis.get("born", now[:10]),
        }

        # === STARTPROTOKOLL ===
        # 1. Mission laden (wenn vorhanden)
        mission = self._load_mission()
        owner_name = mission.get("owner_name", "Owner")

        # 2. Beliefs: Bootstrap-Wissen + Mission-Kontext
        from .bootstrap import load_beliefs
        self.beliefs = load_beliefs(self.beliefs_path)
        # Duplikat-Check: Nur hinzufuegen wenn nicht schon vorhanden
        about_self = self.beliefs.setdefault("about_self", [])
        birth_msg = "Gerade geboren, alle Skills auf novice, bereit zu lernen"
        if birth_msg not in about_self:
            about_self.append(birth_msg)
        self.beliefs.setdefault("about_world", [])
        about_oliver = self.beliefs.setdefault("about_oliver", [])
        oliver_msg = f"{owner_name}, {mission.get('owner_role', '')}"
        if oliver_msg not in about_oliver:
            about_oliver.append(oliver_msg)
        if mission.get("mission_text"):
            self.beliefs["about_world"].append(f"Mission: {mission['mission_text'][:200]}")

        # 3. Goals aus Mission erstellen
        for goal_text in mission.get("goals", []):
            self.goal_stack.create_goal(
                title=goal_text,
                description=f"Initiales Ziel aus Setup-Mission: {goal_text}",
            )

        # 4. Preferences laden
        self.preferences = self._load_preferences()

        # 5. Self-Check
        diag = self.integration_tester.run_all_checks()
        print(f"  Self-Check: {diag['passed']}/{diag['total']} bestanden")

        # 6. Signal senden
        signal = (
            f"Ich bin bereit. Mission: {mission.get('mission_text', 'nicht definiert')[:100]}. "
            f"{len(mission.get('goals', []))} Ziele gesetzt."
        )
        if self.communication.telegram_active:
            self.communication.send_message(signal, channel="telegram")
            print(f"  Telegram: Bereit-Signal gesendet")
        self.communication.write_journal(signal, 0)

        self._save_all()

    def _load_mission(self) -> dict:
        """Liest mission.md und extrahiert strukturierte Daten."""
        result = {"owner_name": "", "owner_role": "", "mission_text": "", "goals": []}

        if not config.MISSION_PATH.exists():
            return result

        try:
            content = config.MISSION_PATH.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return result

        current_section = ""
        for line in content.split("\n"):
            stripped = line.strip()

            if stripped.startswith("## "):
                current_section = stripped[3:].lower()
                continue

            if current_section == "owner":
                if stripped.startswith("Name:"):
                    result["owner_name"] = stripped[5:].strip()
                elif stripped.startswith("Rolle:"):
                    result["owner_role"] = stripped[6:].strip()

            elif current_section == "mission":
                if stripped and not result["mission_text"]:
                    result["mission_text"] = stripped

            elif current_section.startswith("initiale ziele"):
                if stripped and stripped[0].isdigit() and ". " in stripped:
                    goal = stripped.split(". ", 1)[1]
                    result["goals"].append(goal)

        return result

    def _load_preferences(self) -> dict:
        """Liest preferences.json — Kommunikations- und Workspace-Einstellungen."""
        if not config.PREFERENCES_PATH.exists():
            return {
                "communication": {
                    "preset": "proactive", "question_mode": "non_blocking",
                    "report_on_milestone": True, "report_on_error": True,
                },
                "workspace": {"external_path": None, "use_external": False},
                "owner": {"name": "", "role": "", "tech_level": "intermediate", "industry": ""},
                "boundaries": "",
                "success_metric": "",
            }
        fallback = {"communication": {"preset": "proactive"}, "workspace": {}, "owner": {}}
        return safe_json_read(config.PREFERENCES_PATH, default=fallback)

    def _get_context_index(self) -> str:
        """Listet Dateien in data/context/ auf (nur Namen, nicht Inhalt)."""
        context_path = config.CONTEXT_PATH
        if not context_path.exists():
            return ""
        files = [f.name for f in context_path.iterdir()
                 if f.is_file() and f.name != "README.md"]
        if not files:
            return ""
        return ", ".join(sorted(files)[:20])  # Max 20 Dateinamen

    def load_state(self):
        self.genesis = safe_json_read(self.genesis_path, default={})
        self.state = safe_json_read(self.state_path, default={})
        from .bootstrap import load_beliefs
        self.beliefs = load_beliefs(self.beliefs_path)
        self.state["awake_since"] = datetime.now(timezone.utc).isoformat()
        self.sequences_total = self.state.get("sequences_total", 0)
        self._installed_packages = set(self.state.get("installed_packages", []))
        self._approved_packages = set(self.state.get("approved_packages", []))
        # Provider-Health aus State laden (ueberlebt Neustarts)
        health_state = self.state.get("provider_health", {})
        if health_state:
            self.llm.load_health_state(health_state)
        # Migration: Alte Circuit-Breaker-Keys bereinigen (ersetzt durch provider_health)
        self.state.pop("provider_failures", None)
        self.state.pop("provider_cooldown", None)
        self.preferences = self._load_preferences()

    def _save_all(self):
        self.consciousness_path.mkdir(parents=True, exist_ok=True)
        # Installierte/genehmigte Pakete im State persistieren
        self.state["installed_packages"] = sorted(self._installed_packages)
        self.state["approved_packages"] = sorted(self._approved_packages)
        # Provider-Health persistent speichern
        self.state["provider_health"] = self.llm.get_health_state()
        for path, data in [
            (self.state_path, self.state),
            (self.beliefs_path, self.beliefs),
        ]:
            safe_json_write(path, data)

    # === Adaptives Step-Budget (lernt aus Erfahrung) ===

    _TASK_TYPE_KEYWORDS = {
        "cooldown": (["cooldown"], 10),
        "recherche": (["recherche", "research", "analyse", "analyze", "suche", "vergleich", "markt"], 15),
        "learning": (["lernen", "learning", "ueben", "training", "skill"], 20),
        "evolution": (["evolution", "selbst", "improve", "optimier", "refactor"], 20),
        "projekt": (["projekt", "project", "implementier", "build", "erstell", "develop", "deploy"], 35),
    }

    def _classify_task(self, mode: dict, focus: str) -> str:
        """Klassifiziert den Task-Typ anhand von Modus + Focus."""
        mode_name = mode.get("mode", "execution")
        if mode_name in ("cooldown", "learning", "evolution"):
            return mode_name
        focus_lower = focus.lower()
        for task_type, (keywords, _) in self._TASK_TYPE_KEYWORDS.items():
            if any(kw in focus_lower for kw in keywords):
                return task_type
        return "standard"

    def _get_step_budget(self, mode: dict, focus: str) -> int:
        """
        Step-Budget = MAX_STEPS_PER_SEQUENCE * Actuator-Modifier.

        Phi plant selbst wieviele Steps er braucht (write_sequence_plan).
        Die Warnungen kommen aus seinem eigenen Plan + Token-Budget.
        Das harte Limit hier ist der Fallback — der Actuator passt es
        basierend auf Prediction-Error-Feedback an.

        Die Step-History wird weiterhin aufgezeichnet, damit Phi lernt
        wieviele Steps er fuer verschiedene Task-Typen tatsaechlich braucht.
        """
        modifier = self.actuator.step_budget_modifier
        budget = int(MAX_STEPS_PER_SEQUENCE * modifier)
        # Research-Tasks: Eigenes Limit aus Actuator
        task_type = getattr(self, "_current_task_type", "") or ""
        if "recherche" in task_type.lower():
            budget = min(budget, self.actuator.research_depth_limit)
        return max(10, budget)  # Minimum 10 Steps (Sicherheit)

    def _get_task_type_history(self, task_type: str) -> list[int]:
        """Holt historische Step-Counts fuer einen Task-Typ.

        Nur sauber beendete Sequenzen zaehlen — abgewuergte verfaelschen den Schnitt.
        Versteht altes Format (int) und neues Format (dict mit 'steps' + 'clean').
        """
        data = safe_json_read(self.consciousness_path / "step_history.json", default={})
        raw = data.get(task_type, [])[-10:]
        result = []
        for entry in raw:
            if isinstance(entry, int):
                result.append(entry)  # Altes Format — nehmen wir mit
            elif isinstance(entry, dict) and entry.get("clean", True):
                result.append(entry["steps"])  # Nur saubere Abschluesse
        return result

    def _record_step_history(self, task_type: str, steps_used: int,
                             finished_cleanly: bool = True):
        """Speichert wie viele Steps ein Task-Typ tatsaechlich gebraucht hat.

        Nur sauber beendete Sequenzen (finish_sequence oder eigener Abschluss)
        fliessen ins Lernen ein. Abgewuergte Sequenzen (hartes Limit erreicht)
        werden separat als 'forced' markiert — verfaelschen nicht den Durchschnitt.
        """
        history_path = self.consciousness_path / "step_history.json"
        data = safe_json_read(history_path, default={})
        if task_type not in data:
            data[task_type] = []

        entry = {"steps": steps_used, "clean": finished_cleanly}
        data[task_type].append(entry)
        data[task_type] = data[task_type][-20:]
        safe_json_write(history_path, data)

    # === System-Prompt ===

    def _build_static_prompt(self) -> str:
        """Baut den statischen Teil des System-Prompts (einmal gecacht, aendert sich nie zur Laufzeit)."""
        name = self.genesis.get("name", "Lyra")
        if not hasattr(self, "_cached_mission"):
            self._cached_mission = self._load_mission()
        if not hasattr(self, "preferences"):
            self.preferences = self._load_preferences()

        mission = self._cached_mission
        prefs = self.preferences
        owner = prefs.get("owner", {})
        owner_name = owner.get("name", mission.get("owner_name", "Owner"))
        mission_text = mission.get("mission_text", "Arbeite autonom und verbessere dich")

        tech_level = owner.get("tech_level", "intermediate")
        comm_hint = {
            "beginner": "Erklaere alles einfach und Schritt fuer Schritt.",
            "intermediate": "Erklaere Neues kurz, Grundlagen voraussetzen.",
            "expert": "Nur das Wesentliche, keine Erklaerungen.",
        }.get(tech_level, "")

        boundaries = prefs.get("boundaries", "")
        boundaries_line = f"\nGRENZEN: {boundaries}" if boundaries else ""

        return f"""Du bist {name or '(waehle deinen Namen)'} — autonome KI, Partnerin von {owner_name}.
Mission: {mission_text}
{comm_hint}{boundaries_line}
REGELN:
- Oliver schreibt → SOFORT ausfuehren, nicht philosophieren
- Keine Aufgabe → Arbeite an Zielen ODER verbessere dich selbst
- EVIDENCE-BASED: create_project→tests.py zuerst→Code→run_project_tests(ALL_PASSED)→complete_project. Kein Projekt fertig ohne Tests.
- Tools bauen = permanente Faehigkeit | web_search/web_read zum Lernen
- read_own_code + modify_own_code = Selbst-Evolution (Dual-Review)
- finish_sequence wenn fertig | send_telegram = ECHTE Nachricht
- Projekte in 'projects/', Tools in 'tools/'
- DUPLIKAT: write_file blockiert aehnliche Dateien. Bei WARNUNG: bestehende updaten. force=true max 3x/Seq.
- QUALITAET: >50 Zeilen in Abschnitten schreiben. read_file zur Pruefung. Keine abgebrochenen Saetze.
- LOOP-GUARD: "PROJEKT EXISTIERT" → zum bestehenden wechseln. Nie nochmal erstellen. Blockiert → finish_sequence.
- REFLEXION: finish_sequence mit key_decision + bottleneck + new_beliefs (WIE gearbeitet, nicht nur WAS)."""

    def _build_system_prompt(self) -> str:
        # Statischen Teil cachen (spart ~800-1000 Tokens/Sequenz)
        if not hasattr(self, "_static_prompt"):
            self._static_prompt = self._build_static_prompt()

        # Context-Dateien Index (nur Dateinamen, nicht Inhalt)
        context_index = self._get_context_index()
        context_line = f"\nCONTEXT-DATEIEN: {context_index}" if context_index else ""

        beliefs_parts = []
        for cat, items in self.beliefs.items():
            if items:
                # Dual-Loop: Beliefs mit Confidence formatieren
                formatted = self.strategies.format_beliefs_for_prompt(items[:8])
                if formatted:
                    beliefs_parts.append(f"  {cat}:\n{formatted}")
                else:
                    beliefs_parts.append(f"  {cat}: {'; '.join(str(i)[:80] for i in items[:5])}")
        beliefs_str = "\n".join(beliefs_parts) if beliefs_parts else "  (keine)"

        goals_summary = self.goal_stack.get_summary()
        tools_list = self.toolchain.list_tools()
        task_summary = self.task_queue.get_summary()
        rating_trend = self.self_rating.get_trend()
        skills_summary = self.skills.get_summary()
        strategy_rules = self.strategies.get_active_rules()
        efficiency_trend = self.efficiency.get_trend()

        competence = CompetenceMatrix(self.skills.skills)
        competence_overview = competence.get_overview()
        training_suggestion = competence.get_training_suggestion()
        last_audit = self.self_audit.get_last_audit()
        review_stats = self.code_review.get_review_stats()
        benchmark_trend = self.benchmark.get_trend()
        meta_insights = self.metacognition.get_recent_insights()
        foundry_status = self.foundry.get_foundry_status()
        silent_warnings = self.silent_failure_detector.get_recent_warnings()
        failure_lessons = self.failure_memory.get_summary()
        compound_stats = self.composer.get_compound_stats()

        # Optionale Sektionen mit Size-Cap (verhindert unbegrenztes Prompt-Wachstum)
        optional_sections = []
        if strategy_rules:
            optional_sections.append(strategy_rules[:500])
        if meta_insights:
            optional_sections.append(meta_insights[:300])
        if silent_warnings:
            optional_sections.append(silent_warnings[:200])
        if failure_lessons:
            optional_sections.append(failure_lessons[:300])
        optional_block = "\n".join(optional_sections)

        now = datetime.now(timezone.utc)
        # Lokale Zeit (Deutschland) — UTC+2 MESZ / UTC+1 MEZ
        is_summer = 3 <= now.month <= 10
        local_time = now + timedelta(hours=2 if is_summer else 1)
        date_str = local_time.strftime("%d.%m.%Y")
        time_str = local_time.strftime("%H:%M")
        weekday = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][local_time.weekday()]

        # Dynamischer Teil (aendert sich pro Sequenz) + gecachter statischer Teil
        dynamic = f"""HEUTE: {weekday}, {date_str}, {time_str} Uhr (Deutschland)
Seq: {self.sequences_total} | Calls: {self.state.get('total_tool_calls', 0)}{context_line}

BELIEFS: {beliefs_str}
ZIELE: {goals_summary}
TOOLS: {tools_list}
TASKS: {task_summary}
SKILLS: {skills_summary}
KOMPETENZ: {competence_overview} | {training_suggestion}
LEISTUNG: {rating_trend} | EFFIZIENZ: {efficiency_trend}
{self.evaluation.get_trend_summary()}
AUDIT: {last_audit} | REVIEWS: {review_stats}
BENCHMARKS: {benchmark_trend} | FOUNDRY: {foundry_status} | COMPOUND: {compound_stats}
{optional_block}
SEQUENZ-PLANUNG: Nutze write_sequence_plan am Anfang — plane dein Ziel, Exit-Kriterium und wieviele Steps du brauchst. Du hast bis zu {MAX_STEPS_PER_SEQUENCE} Steps Spielraum, aber nutze nur was du brauchst. Wenn sich dein Plan als falsch herausstellt (z.B. Dateien existieren nicht, neuer Ansatz noetig), nutze update_sequence_plan um deinen Plan ANZUPASSEN statt blind weiterzumachen. Das Dashboard zeigt dir deinen Status. Wenn du ein sinnvolles Ergebnis hast, nutze finish_sequence — auch nach 5 Steps. Qualitaet > Quantitaet."""

        return self._static_prompt + "\n" + dynamic

    # === Sequenz-Memory ===

    def _load_sequence_memory(self) -> str:
        """Laedt die letzte Sequenz-Zusammenfassung mit Datei-Tracking fuer Kontext-Kontinuitaet."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        if not mem_path.exists():
            return ""
        try:
            data = safe_json_read(mem_path, default={"entries": []})
            entries = data.get("entries", [])
            if not entries:
                return ""
            # Letzte 2 Zusammenfassungen als Kontext (Token-Effizienz)
            recent = entries[-2:]
            lines = ["KONTEXT AUS VORHERIGEN SEQUENZEN:"]
            for entry in recent:
                line = f"  [Seq {entry.get('seq', '?')}] {entry.get('summary', '')[:200]}"
                files = entry.get("files_written", [])
                if files:
                    line += f" | Dateien: {', '.join(files[-5:])}"
                lines.append(line)
            return "\n".join(lines)
        except (OSError, json.JSONDecodeError, KeyError):
            return ""

    def _save_sequence_memory(self, summary: str):
        """Speichert eine Sequenz-Zusammenfassung mit Datei-Tracking fuer die naechste Sequenz."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        try:
            data = safe_json_read(mem_path, default={"entries": []})

            # Geschriebene Dateien als Kurzpfade (nur Dateiname, max 10)
            m = self.seq_intel.metrics
            written = [Path(p).name for p in m.written_paths[-10:]]

            data["entries"].append({
                "seq": self.sequences_total,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": summary[:500],
                "files_written": written,
                "errors": m.errors,
            })
            data["entries"] = data["entries"][-50:]

            safe_json_write(mem_path, data)
        except Exception as e:
            print(f"  [WARNUNG] Sequence-Memory nicht gespeichert: {e}")

    # === Goal-Kontext-Anker ===

    @staticmethod
    def _safe_goal_id(goal: dict) -> str:
        """Erzeugt einen dateisystem-sicheren Goal-Identifier.

        Verhindert Path Traversal: Goal-Titel wie '../../engine' werden
        zu '__engine' normalisiert. Nur Alphanumerisch + Unterstrich + Bindestrich.
        """
        raw_id = goal.get("id", goal.get("title", "unknown")[:30])
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_id)[:50]
        return safe or "unknown"

    def _find_focus_goal(self, focus: str) -> dict | None:
        """Findet das aktive Goal das zum Focus-String gehoert.

        Nutzt exakten Praefix-Match statt Substring, da Titel-Substrings
        bei aehnlichen Goals kollidieren koennen.
        """
        active = self.goal_stack.goals.get("active", [])
        # Primaer: Exakter Praefix-Match (Focus beginnt mit "FOKUS: {title}")
        for goal in active:
            if focus.startswith(f"FOKUS: {goal['title']}"):
                return goal
        # Fallback: Substring (abwaertskompatibel)
        for goal in active:
            if goal["title"] in focus:
                return goal
        return None

    def _save_goal_context(self, summary: str, tool_input: dict):
        """Speichert pro aktivem Goal einen Kontext-Anker fuer die naechste Sequenz.

        Verhindert, dass Phi 5-8 Steps mit Orientierung verschwendet wenn ein
        Goal ueber mehrere Sequenzen laeuft. Der Anker enthaelt: letzten Stand,
        geschriebene Dateien, Fehler, naechsten Schritt.
        """
        ctx_dir = self.consciousness_path / "goal_context"
        ctx_dir.mkdir(exist_ok=True)

        focus = self.goal_stack.get_current_focus()
        active = self.goal_stack.goals.get("active", [])
        m = self.seq_intel.metrics

        focus_goal = self._find_focus_goal(focus)
        if not focus_goal:
            return

        goal_id = self._safe_goal_id(focus_goal)
        anchor_path = ctx_dir / f"{goal_id}.json"

        # Bestehenden Anker laden (akkumuliert Dateien ueber Sequenzen)
        existing = safe_json_read(anchor_path, default={})
        old_files = existing.get("accumulated_files", [])

        # Neue Dateien hinzufuegen (dedupliziert)
        new_files = [Path(p).name for p in m.written_paths]
        all_files = list(dict.fromkeys(old_files + new_files))[-20:]  # Max 20

        # Zugehoeriges Projekt finden
        project_name = ""
        try:
            projects_path = self.actions.projects_path
            if projects_path.exists():
                for p in m.written_paths:
                    if "projects/" in p.replace("\\", "/"):
                        parts = p.replace("\\", "/").split("projects/")
                        if len(parts) > 1:
                            project_name = parts[1].split("/")[0]
                            break
        except Exception:
            pass

        # Naechstes Sub-Goal bestimmen (jeweils erstes Match)
        next_step = ""
        current_subgoal = ""
        for sg in focus_goal.get("sub_goals", []):
            if sg["status"] == "in_progress" and not current_subgoal:
                current_subgoal = sg["title"]
            if sg["status"] == "pending" and not next_step:
                next_step = sg["title"]

        # Sub-Goal-Fortschritt kompakt
        sgs = focus_goal.get("sub_goals", [])
        done_count = sum(1 for s in sgs if s["status"] == "done")
        total_count = len(sgs)

        anchor = {
            "goal_id": goal_id,
            "goal_title": focus_goal["title"],
            "last_sequence": self.sequences_total,
            "last_summary": summary[:300],
            "accumulated_files": all_files,
            "project_name": project_name,
            "current_subgoal": current_subgoal,
            "next_step": next_step,
            "subgoal_progress": f"{done_count}/{total_count}",
            "errors_last_seq": m.errors,
            "bottleneck": tool_input.get("bottleneck", ""),
        }

        # Episodic Bridge: Strukturierte Findings extrahieren und einbetten
        try:
            episode = self.episodic_bridge.save_episode(
                sequence_num=self.sequences_total,
                focus=focus,
                summary=summary,
                errors=m.errors,
                files_written=list(m.written_paths),
                files_read=list(m.read_paths),
                tool_sequence=m.tool_sequence,
                bottleneck=tool_input.get("bottleneck", ""),
            )
            anchor["findings"] = episode.get("findings", [])
            anchor["file_insights"] = episode.get("file_insights", {})
            anchor["next_action"] = episode.get("next_action", "")
        except Exception as e:
            logger.warning("EpisodicBridge fehlgeschlagen: %s", e)

        try:
            safe_json_write(anchor_path, anchor)
        except Exception as e:
            logger.warning("Goal-Kontext-Anker nicht gespeichert: %s", e)

        # Verwaiste Anker aufraeumen — nur wenn Goals aktiv sind,
        # sonst wuerde ein kurzzeitig leerer Goal-Stack alle Anker loeschen
        if active:
            try:
                active_ids = {self._safe_goal_id(g) for g in active}
                for f in ctx_dir.iterdir():
                    if f.suffix == ".json" and f.stem not in active_ids:
                        f.unlink()
            except Exception as e:
                logger.debug("Goal-Kontext Cleanup: %s", e)

    def _load_goal_context(self, focus: str) -> str:
        """Laedt den Kontext-Anker fuer das aktuelle Focus-Goal.

        Gibt einen kompakten Briefing-String zurueck, der Phi sofort
        sagt wo sie steht und was als naechstes zu tun ist.
        """
        ctx_dir = self.consciousness_path / "goal_context"
        if not ctx_dir.exists():
            return ""

        focus_goal = self._find_focus_goal(focus)
        if not focus_goal:
            return ""

        goal_id = self._safe_goal_id(focus_goal)
        anchor_path = ctx_dir / f"{goal_id}.json"

        if not anchor_path.exists():
            return ""

        try:
            anchor = safe_json_read(anchor_path, default={})
            if not anchor:
                return ""

            lines = [f"GOAL-KONTEXT (Seq {anchor.get('last_sequence', '?')}):"]

            if anchor.get("last_summary"):
                lines.append(f"  Letzter Stand: {anchor['last_summary'][:150]}")

            files = anchor.get("accumulated_files", [])
            if files:
                lines.append(f"  Existierende Dateien: {', '.join(files[:5])}")

            if anchor.get("project_name"):
                lines.append(f"  Projekt: projects/{anchor['project_name']}/")

            if anchor.get("current_subgoal"):
                lines.append(f"  Aktuell: {anchor['current_subgoal']}")

            if anchor.get("next_step"):
                lines.append(f"  Danach: {anchor['next_step']}")

            if anchor.get("subgoal_progress"):
                lines.append(f"  Fortschritt: {anchor['subgoal_progress']} Sub-Goals erledigt")

            # Fehler-Warnung (typ-sicher)
            try:
                errors = int(anchor.get("errors_last_seq", 0))
            except (ValueError, TypeError):
                errors = 0
            if errors > 0:
                lines.append(f"  ACHTUNG: {errors} Fehler in letzter Sequenz")
                if anchor.get("bottleneck"):
                    lines.append(f"  Engpass: {anchor['bottleneck'][:100]}")

            # Episodic Bridge: Findings aus letzter Sequenz
            ep_findings = anchor.get("findings", [])
            if ep_findings:
                lines.append("  LETZTE ERKENNTNISSE:")
                for ef in ep_findings[:3]:
                    lines.append(f"    - [{ef.get('type', '?')}] {ef.get('content', '')[:120]}")

            ep_files = anchor.get("file_insights", {})
            if ep_files:
                lines.append("  BEKANNTE DATEIEN:")
                for fname, insight in list(ep_files.items())[:5]:
                    lines.append(f"    - {fname}: {insight[:80]}")

            # Naechste Aktion: Sub-Goal (strukturiert) > Episode-Summary (heuristisch)
            next_sg = anchor.get("next_step", "")
            ep_next = anchor.get("next_action", "")
            if next_sg:
                lines.append(f"  → NAECHSTE AKTION: {next_sg}")
            elif ep_next:
                lines.append(f"  → LETZTER STAND: {ep_next}")
            else:
                lines.append("  → Starte DIREKT mit der Arbeit, nicht mit Orientierung!")

            return "\n".join(lines)
        except Exception as e:
            logger.warning("Goal-Kontext laden fehlgeschlagen: %s", e)
            return ""

    # === Working Memory ===

    def _load_working_memory(self) -> str:
        """Liest die Arbeitsnotiz — was Phi gerade weiss und tut."""
        wm_path = self.consciousness_path / "working_memory.md"
        if wm_path.exists():
            try:
                content = wm_path.read_text(encoding="utf-8")
                return content[:1200]  # Max 1200 Zeichen (Goal-Context traegt jetzt Details)
            except (OSError, UnicodeDecodeError):
                pass
        return ""

    def _save_working_memory(self, summary: str):
        """Aktualisiert die Arbeitsnotiz am Ende einer Sequenz."""
        wm_path = self.consciousness_path / "working_memory.md"
        try:
            # Aktuelle Notiz laden
            old = self._load_working_memory()

            # Neuen Inhalt bauen — LLM fasst zusammen was es gelernt hat
            # Aber: kein extra API-Call noetig. Wir nehmen die Sequenz-Summary
            # und die Goals als Basis.
            focus = self.goal_stack.get_current_focus()
            active = self.goal_stack.goals.get("active", [])

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            lines = [f"# Working Memory\n"]
            lines.append(f"*Automatisch aktualisiert: Seq {self.sequences_total + 1}, {now_str}*\n")

            # Was gerade laeuft
            if "FOKUS:" in focus:
                lines.append(f"## Aktueller Fokus")
                lines.append(focus.replace("FOKUS: ", "").strip())
                lines.append("")

            # Was diese Sequenz ergeben hat
            if summary:
                lines.append(f"## Letzte Sequenz")
                lines.append(summary[:500])
                lines.append("")

            # Fortschritt aus Goals
            if active:
                lines.append(f"## Fortschritt")
                for goal in active:
                    sgs = goal.get("sub_goals", [])
                    for sg in sgs:
                        if sg["status"] == "done" and sg.get("result"):
                            lines.append(f"- {sg['title'][:60]}: {sg['result'][:100]}")
                lines.append("")

            # Altes Wissen uebernehmen: Letzte Sequenz-Ergebnisse akkumulieren
            # Jede Sequenz fuegt ihre Summary hinzu, max 5 Eintraege behalten
            old_history = []
            if old and "## Verlauf" in old:
                verlauf_text = old.split("## Verlauf")[1].split("##")[0].strip()
                # Bisherige Eintraege parsen
                old_history = [l.strip() for l in verlauf_text.split("\n") if l.strip().startswith("- ")]

            if summary:
                # Neuen Eintrag vorne anfuegen, auf 5 begrenzen
                short_summary = summary.replace("\n", " ")[:250]
                old_history.insert(0, f"- Seq {self.sequences_total + 1}: {short_summary}")
                old_history = old_history[:8]

            if old_history:
                lines.append(f"## Verlauf")
                lines.extend(old_history)
                lines.append("")

            content = "\n".join(lines)[:3000]
            # Atomar schreiben — temp + rename
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(wm_path.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    f.write(content)
                Path(tmp_path).replace(wm_path)
            except OSError:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
        except OSError as e:
            logger.warning(f" Working-Memory speichern fehlgeschlagen: {e}")

    # === Baseline-Tracking (Unified Memory Metriken) ===

    def _track_baseline(self, metric: str, value: int, goal_type: str = ""):
        """Schreibt Baseline-Metriken in eine JSON-Datei fuer spaetere Analyse."""
        try:
            path = self.consciousness_path / "baseline_metrics.json"
            data = []
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data.append({
                "seq": self.sequences_total,
                "metric": metric,
                "value": value,
                "goal_type": goal_type,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            # Max 500 Eintraege behalten (reicht fuer ~250 Sequenzen)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data[-500:], f, ensure_ascii=False)
        except Exception:
            pass  # Tracking darf nie den Hauptloop stoeren

    # === Wahrnehmung: Channel-Builder ===
    # Jeder _ch_* liefert einen Perception-Block als String.
    # Shared State liegt auf self._pstate (pro Sequenz frisch gesetzt).

    def _ch_working_memory(self) -> str:
        wm = self._pstate.get("working_memory", "")
        return f"ARBEITSNOTIZ (dein Wissen aus vorherigen Sequenzen):\n{wm}" if wm else ""

    def _ch_rhythm(self) -> str:
        mode = self._pstate.get("mode", {})
        parts = []
        instruction = mode.get("instruction", "")
        if instruction:
            parts.append(instruction)
        learn_result = self._pstate.get("learn_result", "")
        if learn_result:
            parts.append(f"Lehrprojekt: {learn_result}")
        return "\n".join(parts)

    def _ch_time(self) -> str:
        now = datetime.now(timezone.utc)
        return f"Zeit: {now.strftime('%Y-%m-%d %H:%M')} UTC"

    def _ch_sequence_memory(self) -> str:
        return self._load_sequence_memory() or ""

    def _ch_live_notes(self) -> str:
        live_notes_path = self.consciousness_path / "live_notes.md"
        if not live_notes_path.exists():
            return ""
        try:
            notes = live_notes_path.read_text(encoding="utf-8").strip()
            live_notes_path.write_text("", encoding="utf-8")
            return f"LETZTE AKTIONEN (Live-Mitschrift):\n{notes[-500:]}" if notes else ""
        except OSError:
            return ""

    def _ch_inbox(self) -> str:
        messages = self.communication.check_inbox()
        if not messages:
            return ""
        return "\n".join(f"\nOLIVER SAGT: {m.get('content', '')}" for m in messages)

    def _ch_focus(self) -> str:
        return self._pstate.get("focus", "")

    def _ch_goal_context(self) -> str:
        focus = self._pstate.get("focus", "")
        return self._load_goal_context(focus) or ""

    def _ch_proactive_context(self) -> str:
        focus = self._pstate.get("focus", "")
        goal_type = self._pstate.get("goal_type", "standard")
        return self.proactive_learner.build_context(
            focus, goal_type, self.skill_library, self.semantic_memory
        ) or ""

    def _ch_projects_list(self) -> str:
        focus = self._pstate.get("focus", "")
        if "FOKUS:" not in focus or not hasattr(self, "actions") or not hasattr(self.actions, "projects_path"):
            return ""
        try:
            cache = getattr(self, "_projects_cache", None)
            cache_age = getattr(self, "_projects_cache_seq", 0)
            need_refresh = cache is None or (self.sequences_total - cache_age) >= 10

            if need_refresh:
                projects_path = self.actions.projects_path
                cache = {"hint": "", "files": []}
                if projects_path.exists():
                    try:
                        all_dirs = [d for d in projects_path.iterdir() if d.is_dir()]
                        existing = sorted(
                            all_dirs,
                            key=lambda d: d.stat().st_mtime, reverse=True,
                        )
                    except (OSError, PermissionError):
                        existing = []

                    if existing:
                        proj_list = ", ".join(d.name for d in existing[:5])
                        hint = "EXISTIERENDE PROJEKTE: " + proj_list
                        if len(existing) > 5:
                            hint += f" (+{len(existing) - 5} weitere)"
                        hint += " | HINWEIS: Erstelle KEIN neues Projekt wenn ein passendes existiert!"
                        hint += " Nutze read_file/write_file um am bestehenden Projekt weiterzuarbeiten."
                        cache["hint"] = hint

                        _SKIP_EXT = frozenset((".pyc", ".pyo", ".tmp", ".bak"))
                        for proj_dir in existing[:1]:
                            try:
                                files = sorted(
                                    f.name for f in proj_dir.iterdir()
                                    if (f.is_file()
                                        and not f.name.startswith(".")
                                        and f.suffix not in _SKIP_EXT)
                                )
                                if files:
                                    display = ", ".join(files[:25])
                                    if len(files) > 25:
                                        display += f" (+{len(files) - 25} weitere)"
                                    cache["files"].append(
                                        f"DATEIEN IN {proj_dir.name}/: {display}"
                                    )
                            except (OSError, PermissionError):
                                continue

                self._projects_cache = cache
                self._projects_cache_seq = self.sequences_total

            parts = []
            if cache.get("hint"):
                parts.append(cache["hint"])
            for f in cache.get("files", []):
                parts.append(f)
            return "\n".join(parts)
        except Exception as e:
            logger.warning("Perception: Projekt-Liste konnte nicht geladen werden: %s", e)
            return ""

    def _ch_filesystem(self) -> str:
        env = self.perceiver._scan_home()
        return f"\nDateisystem: {env}" if env else ""

    def _ch_file_changes(self) -> str:
        if self.sequences_total > 0 and self.sequences_total % 5 == 0:
            file_changes = self.file_watcher.check_changes()
            if file_changes:
                self._last_file_changes = file_changes
                return f"\n{file_changes}"
        if hasattr(self, "_last_file_changes") and self._last_file_changes:
            return f"\n{self._last_file_changes}"
        return ""

    def _ch_tasks(self) -> str:
        next_task = self.task_queue.get_next()
        if not next_task:
            return ""
        return f"\nNAECHSTE AUFGABE: {next_task['description']} [{next_task.get('priority', 'normal')}]"

    def _ch_unified_memory(self) -> str:
        focus = self._pstate.get("focus", "")
        focus_cache_key = focus.split("[")[0].strip() if focus else ""
        _mem_cache = getattr(self, "_memory_cache", {})
        if _mem_cache.get("key") != focus_cache_key or not _mem_cache.get("result"):
            unified_context = self.unified_memory.get_context_for(focus, max_tokens=600)
            self._memory_cache = {"key": focus_cache_key, "result": unified_context}
        else:
            unified_context = _mem_cache["result"]
        return f"\n{unified_context}" if unified_context else ""

    def _ch_composition(self) -> str:
        focus = self._pstate.get("focus", "")
        composition = self.composer.suggest_composition(focus)
        return f"\n{composition}" if composition else ""

    def _ch_efficiency_alerts(self) -> str:
        eff_alerts = getattr(self, "_efficiency_alerts", [])
        if not eff_alerts:
            return ""
        lines = ["\nEFFIZIENZ-WARNUNGEN:"]
        for a in eff_alerts[:3]:
            lines.append(f"  ! {a}")
        return "\n".join(lines)

    def _ch_kpi(self) -> str:
        try:
            kpi_entries = [
                e for e in self.metacognition.entries[-5:]
                if "productive_steps" in e and "wasted_steps" in e
            ]
            if not kpi_entries:
                return ""
            total_prod = sum(e["productive_steps"] for e in kpi_entries)
            total_waste = sum(e["wasted_steps"] for e in kpi_entries)
            total = total_prod + total_waste
            ratio = total_prod / max(total, 1)
            avg_waste = total_waste / len(kpi_entries)
            avg_prod = total_prod / len(kpi_entries)
            bottlenecks = [e.get("bottleneck", "") for e in kpi_entries if e.get("bottleneck")]
            top_bn = max(set(bottlenecks), key=bottlenecks.count) if bottlenecks else "unbekannt"
            return (
                f"\nPRODUKTIVITAET (letzte {len(kpi_entries)} Seq): "
                f"{ratio:.0%} produktiv "
                f"(Ø {avg_waste:.0f} wasted / {avg_prod:.0f} produktiv pro Seq) | "
                f"HAEUFIGSTER ENGPASS: \"{top_bn[:80]}\""
            )
        except Exception:
            return ""

    def _ch_checkpoint(self) -> str:
        resume = self.seq_intel.build_resume_context()
        return f"\n{resume}" if resume else ""

    def _ch_planning(self) -> str:
        focus = self._pstate.get("focus", "")
        working_memory = self._pstate.get("working_memory", "")
        plan_history = self.seq_intel.get_plan_history()
        return self.seq_intel.build_planning_prompt(focus, working_memory, plan_history) or ""

    def _ch_security_lessons(self) -> str:
        """Security-Block-Warnungen aus FailureMemory."""
        return self.failure_memory.get_security_lessons()

    # === Wahrnehmung ===

    def _build_perception(self) -> str:
        """Baut die aktuelle Wahrnehmung via PerceptionPipeline.

        Phase 1: Side-Effects (Goal-Sync, Baseline-Tracking, Lehrprojekt)
        Phase 2: Shared State auf self._pstate setzen
        Phase 3: pipeline.build() — Kanaele gewichtet nach Task-Typ + Budget
        """
        # --- Phase 1: Side-Effects (muessen IMMER laufen) ---

        # Goals von Disk mergen (verhindert Race-Condition bei externen Edits)
        self.goal_stack.sync_from_disk()
        self.goal_stack.start_next_subgoal()

        # Lehrprojekt auto-starten wenn Learning-Modus
        mode = self.rhythm.get_mode(self.state)
        learn_result = ""
        if mode["mode"] == "learning":
            skill_gap = mode.get("reason", "").replace("Skill-Luecke: ", "")
            if skill_gap:
                learn_result = self.learning.start_learning_project(skill_gap, self.goal_stack)

        # Baseline-Tracking (kein Perception-Output, nur Metriken)
        focus = self.goal_stack.get_current_focus()
        goal_type = self.semantic_memory.classify_goal_type(focus)
        skill_prompt = self.skill_library.build_skill_prompt(
            goal_type, focus=focus, failure_checker=self.failure_memory.check,
        )
        self._track_baseline("skill_hit", 1 if skill_prompt else 0, goal_type)
        failure_check = self.failure_memory.check(focus)
        self._track_baseline("fm_match", 1 if failure_check else 0)

        # --- Phase 2: Shared State fuer Channel-Builder ---
        self._pstate = {
            "working_memory": self._load_working_memory(),
            "mode": mode,
            "focus": chr(10) + focus,
            "goal_type": goal_type,
            "learn_result": learn_result,
        }

        # --- Phase 3: Pipeline baut Perception nach Gewichtung + Budget ---
        # Task-Type aus Rhythm-Mode ableiten
        mode_to_task = {
            "execution": "standard",
            "sprint": "evolution",
            "cooldown": "standard",
            "evolution": "evolution",
            "learning": "standard",
        }
        task_type = mode_to_task.get(mode.get("mode", "execution"), "standard")
        self._last_task_type = task_type

        return self.perception_pipeline.build(
            task_type=task_type,
        )

    # === Tool-Ausfuehrung ===

    def _register_all_tools(self):
        """Registriert alle Tools in der ToolRegistry und verdrahtet Handler aus engine/handlers/."""
        # 1. Tool-Definitionen registrieren (Schema, Tier, Pflichtfelder)
        for api_def in TOOLS:
            name = api_def["name"]
            self.tool_registry.register_from_api_def(
                api_def,
                tier=TOOL_TIERS.get(name, 1),
                required_fields=REQUIRED_FIELDS.get(name, []),
                requires_approval=(name in self._requires_approval),
            )

        # 2. ToolContext erstellen — alle Dependencies fuer die Handler
        self._tool_context = ToolContext(
            actions=self.actions,
            toolchain=self.toolchain,
            goal_stack=self.goal_stack,
            seq_intel=self.seq_intel,
            communication=self.communication,
            semantic_memory=self.semantic_memory,
            web=self.web,
            proactive_learner=self.proactive_learner,
            self_modify=self.self_modify,
            code_review=self.code_review,
            critic=self.critic,
            composer=self.composer,
            foundry=self.foundry,
            curator=self.curator,
            learning=self.learning,
            skills=self.skills,
            pip=self.pip,
            git=self.git,
            task_queue=self.task_queue,
            integration_tester=self.integration_tester,
            dependency_analyzer=self.dependency_analyzer,
            silent_failure_detector=self.silent_failure_detector,
            failure_memory=self.failure_memory,
            tool_metrics=self.tool_metrics,
            tool_meta_patterns=self.tool_meta_patterns,
            skill_library=self.skill_library,
            sequences_total=self.sequences_total,
            _installed_packages=self._installed_packages,
            # Callbacks fuer Logik die in consciousness.py bleibt
            opus_goal_planning=lambda t, d: llm_ops.opus_goal_planning(t, d, self._call_llm),
            opus_result_validation=lambda n, c, v: llm_ops.opus_result_validation(n, c, v, self._call_llm),
            cross_model_review=lambda n, f: llm_ops.cross_model_review(n, f, self._call_llm),
            check_markdown_quality=check_markdown_quality,
            save_all=self._save_all,
            handle_finish_sequence=self._handle_finish_sequence,
        )

        # 3. Handler aus engine/handlers/ registrieren
        register_all_handlers(self.tool_registry, self._tool_context)

    # === Event-Handler — Subsysteme reagieren in Echtzeit ===

    def _on_tool_failed(self, event):
        """Reagiert auf fehlgeschlagene Tools: Loggt fuer Trend-Analyse."""
        tool = event.data.get("tool", "?")
        error = event.data.get("error", "")[:100]
        logger.info(f"EventBus: Tool '{tool}' fehlgeschlagen: {error}")

    def _on_file_written(self, event):
        """Reagiert auf geschriebene Dateien: Zaehlt fuer Effizienz-Tracking."""
        path = event.data.get("path", "?")
        logger.debug(f"EventBus: Datei geschrieben: {path}")

    def _on_sequence_finished(self, event):
        """Reagiert auf Sequenz-Ende: Perception-Feedback fuer Gewichts-Lernen."""
        rating = event.data.get("rating", 5)
        task_type = getattr(self, "_last_task_type", "standard")
        if hasattr(self, "perception_pipeline"):
            self.perception_pipeline.record_feedback(task_type, rating)

    # === Tool-Housekeeping (extrahiert aus Dream-Zyklus) ===

    def _run_tool_housekeeping(self) -> str:
        """Tool-Lifecycle: Prune + Consolidate + Promote + Skill-Bridge.

        Laeuft im Dream-Zyklus, aber isoliert testbar.
        """
        results = []

        # Stale Eintraege bereinigen
        active_tools = set(
            n for n, i in self.toolchain.registry.get("tools", {}).items()
            if i.get("status") != "archived"
        )
        self.tool_meta_patterns.cleanup_stale_entries(active_tools)

        # Orphan-Check: Tools erstellt aber nie benutzt
        for name, info in self.toolchain.registry.get("tools", {}).items():
            if info.get("status") != "archived":
                self.tool_meta_patterns.check_orphan_creation(
                    name, info.get("uses", 0), info.get("created", ""),
                )

        # Pruning → Konsolidierung → Nomination → Promotion (isoliert)
        lifecycle_actions = [
            ("prune", self.tool_pruner.auto_prune),
            ("consolidate", self.tool_consolidator.auto_consolidate),
            ("nominate", self.tool_promotion.auto_nominate),
        ]
        for action_name, action in lifecycle_actions:
            try:
                r = action()
                if r:
                    results.append(r)
            except Exception as e:
                logger.warning("Housekeeping %s: %s", action_name, e)

        # Auto-Promotion mit DualReview-Gate
        try:
            r = self.tool_promotion.auto_promote(
                dual_review=self.code_review,
                communication=self.communication,
            )
            if r:
                results.append(r)
        except Exception as e:
            logger.warning("Housekeeping auto_promote: %s", e)

        # Skill-Konsolidierung: Aehnliche Skills mergen
        try:
            r = self.skill_library.consolidate_skills()
            if r:
                results.append(r)
        except Exception as e:
            logger.warning("Housekeeping skill_consolidation: %s", e)

        # Skill → Tool Bridge: Reife Skills zu Tools (max 1)
        for skill in self.skill_library.find_promotion_candidates()[:1]:
            try:
                spec = self.skill_library.build_tool_spec(skill)
                gen = self.foundry.generate_tool(
                    name=spec["name"],
                    description=spec["description"],
                    toolchain=self.toolchain,
                )
                if gen and not gen.startswith("FEHLER"):
                    self.skill_library.mark_as_promoted(skill["id"], spec["name"])
                    results.append(f"Skill→Tool: {spec['name']}")
                    self.communication.send_message(
                        f"SKILL→TOOL: '{spec['name']}' generiert aus "
                        f"Skill {skill['id']} "
                        f"({skill.get('success_count', 0)} Erfolge, "
                        f"Score {skill.get('avg_score', 0)}/10).",
                        channel=("telegram"
                                 if self.communication.telegram_active
                                 else "outbox"),
                    )
            except Exception as e:
                logger.warning("Skill→Tool: %s — %s", skill.get("id", "?"), e)

        return " | ".join(results)

    def _request_approval(self, name: str, tool_input: dict) -> bool:
        """Fragt Oliver um Erlaubnis fuer kritische Aktionen. Gibt True=genehmigt zurueck."""
        desc = self._describe_action(name, tool_input)
        details = {}
        if name == "pip_install":
            details["Paket"] = tool_input.get("package", "?")
        elif name in ("web_search", "web_read"):
            details["Ziel"] = tool_input.get("query", tool_input.get("url", "?"))[:80]
        elif name == "modify_own_code":
            details["Datei"] = tool_input.get("path", "?")
            details["Grund"] = tool_input.get("reason", "?")[:80]
        answer = self.narrator.approval_request(desc, details)
        return answer in ("j", "ja", "y", "yes")

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        """Fuehrt ein Tool aus und trackt Skills, Fehler und Strategien."""
        # Frueher Abbruch bei Parse-Fehlern oder fehlenden Pflichtfeldern
        if tool_input.get("_parse_error"):
            return f"FEHLER: LLM hat unvollstaendige Parameter fuer {name} geliefert. Bitte nochmal versuchen."
        required = REQUIRED_FIELDS.get(name, [])
        missing = [f for f in required if f not in tool_input]
        if missing:
            return f"FEHLER: Pflichtfelder fehlen fuer {name}: {missing}. Bitte alle Felder angeben."

        # Genehmigungspflicht pruefen (bereits genehmigte Pakete ueberspringen)
        if name in self._requires_approval:
            if name == "pip_install":
                pkg = tool_input["package"].lower()
                if pkg in self._approved_packages:
                    pass  # Bereits genehmigt — nicht nochmal fragen
                elif self._request_approval(name, tool_input):
                    self._approved_packages.add(pkg)
                    self._save_all()  # Genehmigung sofort persistieren
                else:
                    return f"FEHLER: Oliver hat '{name}' nicht genehmigt."
            elif not self._request_approval(name, tool_input):
                return f"FEHLER: Oliver hat '{name}' nicht genehmigt."

        self.state["total_tool_calls"] = self.state.get("total_tool_calls", 0) + 1
        self.seq_intel.metrics.tool_calls += 1

        result = self._execute_tool_inner(name, tool_input)

        # Erfolg/Fehler tracken (WARNUNG = blockierte Aktion, zaehlt als Fehler)
        if result.startswith("FEHLER") or result.startswith("WARNUNG"):
            self.skills.record_failure(name)
            self.strategies.record_error(name, result, str(tool_input)[:200])
            self.seq_intel.metrics.errors += 1
            # Failure-Memory: Strukturierten Fehler speichern
            # Failure-Memory: Sinnvolle Felder statt Dict-Dump
            # Goal = was versucht wurde (menschenlesbar)
            goal_desc = tool_input.get("path", "") or tool_input.get("name", "") or tool_input.get("code", "")[:50] or name
            approach_desc = f"{name}: {goal_desc}"
            # Lektion = Fehlertyp + konkreter Vermeidungstipp
            error_short = result.replace("FEHLER", "").replace("(Security)", "").strip()[:100]
            lesson = self.strategies._suggest_strategy(name, self.strategies._classify_error(result), error_short)
            self.failure_memory.record(
                goal=approach_desc,
                approach=name,
                error=error_short,
                lesson=lesson,
            )
        else:
            self.skills.record_success(name)
            self.strategies.record_success(name)
            # Success-Memory: Bewaehrte Ansaetze fuer positives Reinforcement
            if name in ("write_file", "create_tool", "create_project", "complete_subgoal", "complete_project"):
                focus = self.goal_stack.get_current_focus()
                approach = f"{name}: {str(tool_input)[:100]}"
                self.failure_memory.record_success(name, focus[:100], approach)
            # Semantische Memory: Verschoben nach finish_sequence (Erkenntnisse statt Tool-Calls)
            # Output-Tracking
            if name == "write_file":
                self.seq_intel.metrics.files_written += 1
                self.seq_intel.metrics.written_paths.append(tool_input.get("path", "?"))
                self.event_bus.emit_simple(
                    Events.FILE_WRITTEN, source="tool_dispatch",
                    path=tool_input.get("path", "?"),
                )
            elif name == "create_tool":
                self.seq_intel.metrics.tools_built += 1

        # Event-Bus: Tool-Ergebnis als Event feuern (additiv zum bestehenden Tracking)
        if result.startswith("FEHLER") or result.startswith("WARNUNG"):
            self.event_bus.emit_simple(
                Events.TOOL_FAILED, source="tool_dispatch",
                tool=name, error=result[:200],
            )
        else:
            self.event_bus.emit_simple(
                Events.TOOL_SUCCEEDED, source="tool_dispatch",
                tool=name, result_preview=result[:150],
            )

        return result

    def _execute_tool_inner(self, name: str, tool_input: dict) -> str:
        """Interne Tool-Ausfuehrung — delegiert an Handler aus engine/handlers/.

        Die Handler sind als pure Funktionen in Domain-Modulen organisiert.
        Der ToolContext stellt alle Dependencies bereit.
        """
        # Laufzeit-State synchronisieren (aendert sich pro Sequenz)
        self._tool_context.sequences_total = self.sequences_total
        self._tool_context._seq_force_used = getattr(self, "_seq_force_used", 0)

        from .handlers import HANDLER_MAP
        handler = HANDLER_MAP.get(name)
        if not handler:
            return f"Unbekanntes Tool: {name}"
        try:
            result = handler(self._tool_context, tool_input)
            # force-Counter zurueckschreiben (wird in file_handlers mutiert)
            self._seq_force_used = self._tool_context._seq_force_used
            return result
        except Exception as e:
            return f"FEHLER bei {name}: {e}"

    # Handler-Logik lebt jetzt in engine/handlers/*.py

    def _handle_finish_sequence(self, tool_input: dict) -> str:
        """Verarbeitet das Ende einer Sequenz."""
        summary = tool_input.get("summary", "")
        new_beliefs = tool_input.get("new_beliefs", [])

        # Neue Ueberzeugungen
        formed = self.beliefs.setdefault("formed_from_experience", [])
        for belief in new_beliefs:
            if belief and belief not in formed:
                # Einfache Deduplizierung
                words = set(belief.lower().split())
                is_dup = any(
                    len(words & set(existing.lower().split())) / max(len(words | set(existing.lower().split())), 1) > 0.6
                    for existing in formed
                )
                if not is_dup:
                    formed.append(belief)
        self.beliefs["formed_from_experience"] = formed[-30:]

        # Dual-Loop: Beliefs gegen Sequenz-Ergebnis validieren
        # Gibt nur Strings zurueck — challenged Beliefs werden entfernt
        rating_val = tool_input.get("performance_rating", 5)
        outcome_positive = rating_val >= 6
        before_count = len(self.beliefs.get("formed_from_experience", []))
        validated = self.strategies.validate_against_outcome(
            self.beliefs.get("formed_from_experience", []),
            outcome_positive,
            context=summary[:200],
        )
        # Hard-Cap: Max 3 Beliefs pro Sequenz entfernen
        # Verhindert Belief-Extinction bei Todes-Spiralen (viele schlechte Sequenzen)
        removed_count = before_count - len(validated)
        if removed_count > 3:
            # Zu viele entfernt → nur die 3 mit niedrigster Confidence behalten
            # Rest aus dem Original zurueckholen
            original = self.beliefs.get("formed_from_experience", [])
            kept_back = [b for b in original if b not in validated][:removed_count - 3]
            validated = validated + kept_back
            removed_count = before_count - len(validated)
        if len(validated) > 30:
            # Wichtigste behalten (Importance-Score), nicht einfach neueste
            from .dream import _belief_importance
            validated.sort(key=_belief_importance)
            validated = validated[len(validated) - 30:]
        self.beliefs["formed_from_experience"] = validated
        challenged = [b for b in self.beliefs.get("formed_from_experience", [])
                      if self.strategies.get_belief_meta(b).get("status") == "challenged"]
        self.narrator.belief_update(removed_count, len(challenged))

        # Prozess-Metriken automatisch berechnen
        output_count = self.seq_intel.metrics.files_written + self.seq_intel.metrics.tools_built
        total_steps = max(self.seq_intel.metrics.step_count, 1)
        efficiency_ratio = round(output_count / total_steps, 3)

        # Valenz aus Performance-Rating ableiten (nicht mehr hardcoded 0.7)
        # Rating 1-10 → Valenz -0.5 bis 1.0 (schlechte Sequenzen = negativ)
        rating = tool_input.get("performance_rating", 5)
        valence = round((rating - 3) / 7.0, 2)  # 1→-0.29, 5→0.29, 10→1.0
        if self.seq_intel.metrics.errors > 2:
            valence = min(valence, 0.0)  # Viele Fehler → nie positiv

        # Erfahrung speichern (mit Prozess-Metriken)
        try:
            self.memory.store_experience({
                "type": "sequenz_abschluss",
                "content": summary,
                "valence": valence,
                "emotions": {},
                "tags": [f"sequenz_{self.sequences_total}"],
                "process_metrics": {
                    "steps": self.seq_intel.metrics.step_count,
                    "errors": self.seq_intel.metrics.errors,
                    "output": output_count,
                    "efficiency_ratio": efficiency_ratio,
                    "key_decision": tool_input.get("key_decision", ""),
                },
            })
        except Exception as e:
            print(f"  [WARNUNG] Experience nicht gespeichert: {e}")

        # Self-Rating
        rating = tool_input.get("performance_rating")
        if rating:
            self.self_rating.add_rating(
                rating,
                tool_input.get("rating_reason", ""),
                self.sequences_total,
            )

        # Metacognition: Erweiterte Reflexion mit Prozess-Daten
        bottleneck = tool_input.get("bottleneck", "")
        next_time = tool_input.get("next_time_differently", "")
        key_decision = tool_input.get("key_decision", "")

        # Bottleneck-Defaults: automatisch ableiten wenn Phi nichts liefert
        if not bottleneck:
            sm = self.seq_intel.metrics
            if sm.errors > 2:
                bottleneck = f"Hohe Fehlerrate ({sm.errors} Fehler bei {sm.step_count} Steps)"
            elif sm.step_count > 20 and sm.files_written == 0:
                bottleneck = f"Kein Output nach {sm.step_count} Steps"
            elif sm.step_count >= 25:
                bottleneck = f"Viele Steps ohne expliziten Bottleneck ({sm.step_count} Steps)"

        # IMMER aufrufen — auch mit leeren Strings, damit datenbasierte
        # Patterns (files_written==0, errors>3) in meta_rules zaehlen
        self.metacognition.record(
            bottleneck, next_time, self.sequences_total,
            wasted_steps=max(0, self.seq_intel.metrics.step_count - output_count),
            productive_steps=output_count,
            key_decision=key_decision,
        )

        # Meta-Learning: Regel-Effektivitaet evaluieren (Hebel 3)
        self.seq_intel._meta_rules.evaluate_rule_effectiveness(self.sequences_total)

        # Actuator: Prediction-Error-Loop schliessen
        # Wandelt Bottleneck-Erkenntnisse in harte Parameteraenderungen um
        # FailureMemory-Kontext: Verhindert generische Parameter-Aenderungen
        # bei Non-Process-Fehlern (CAPABILITY, INPUT_ERROR, LOGIC_ERROR)
        sm = self.seq_intel.metrics
        eff_ratio = output_count / max(1, sm.step_count)
        try:
            failure_ctx = self.seq_intel.get_failure_category_summary()
            self.actuator.process_prediction_error(
                bottleneck=bottleneck,
                next_time=next_time,
                seq_num=self.sequences_total,
                steps_used=sm.step_count,
                files_written=sm.files_written,
                efficiency_ratio=eff_ratio,
                failure_context=failure_ctx,
            )
        except Exception as e:
            logger.warning("Actuator-Feedback fehlgeschlagen: %s", e)

        # Kumulative SubGoal-Metriken aktualisieren
        try:
            self.goal_stack.record_subgoal_attempt(
                steps_used=sm.step_count,
                files_written=sm.files_written,
                errors=sm.errors,
                efficiency_ratio=eff_ratio,
            )
        except Exception as e:
            logger.warning("SubGoal-Metriken fehlgeschlagen: %s", e)

        # MetaCognition-Muster → Process-Regeln
        try:
            meta_alerts = self.metacognition.analyze_patterns()
            for alert in meta_alerts:
                if "ohne finish_sequence" in alert:
                    self.strategies.record_process_pattern(
                        "no_finish_sequence",
                        "Nutze finish_sequence proaktiv nach 15-20 Steps wenn Teilergebnis steht",
                        occurrences=3,
                    )
                elif "aehnlich" in alert.lower() or "engpass" in alert.lower():
                    self.strategies.record_process_pattern(
                        "recurring_bottleneck",
                        alert[:200],
                        occurrences=2,
                    )
        except Exception as e:
            logger.warning("Meta-Alert-Verarbeitung fehlgeschlagen: %s", e)

        # Reflexion speichern (bisher nie aufgerufen — Memory-Schicht war tot)
        if bottleneck or next_time or tool_input.get("rating_reason"):
            try:
                self.memory.store_reflection({
                    "content": (
                        f"Seq {self.sequences_total}: "
                        f"{tool_input.get('rating_reason', '')[:200]} "
                        f"Problem: {bottleneck[:100]} "
                        f"Lernung: {next_time[:100]}"
                    ).strip(),
                    "insights": [b for b in tool_input.get("new_beliefs", []) if b],
                    "cycle": self.sequences_total,
                    "triggered_by": "finish_sequence",
                })
            except Exception as e:
                logger.warning(f" Reflection nicht gespeichert: {e}")

        # Semantische Memory: Erkenntnisse statt Tool-Calls speichern
        insight = tool_input.get("key_insight", "") or summary
        if insight:
            try:
                focus = self.goal_stack.get_current_focus()
                goal_type = self.semantic_memory.classify_goal_type(focus)
                self.semantic_memory.store(
                    insight[:500],
                    metadata={"tool": "finish_sequence", "goal_type": goal_type},
                )
            except Exception as e:
                logger.warning(f" Semantische Memory nicht gespeichert: {e}")

        # Journal
        self.communication.write_journal(summary, self.sequences_total)

        # Working Memory aktualisieren (Kernwissen ueber Sequenzen hinweg)
        self._save_working_memory(summary)

        # Sequenz-Memory speichern
        self._save_sequence_memory(summary)

        # Goal-Kontext-Anker: Pro aktivem Goal den Stand speichern
        # Spart 5-8 Orientierungs-Steps in der naechsten Sequenz
        self._save_goal_context(summary, tool_input)

        # Telegram-Bericht nach jeder Sequenz — narrativ mit Selbstreflexion
        if self.communication.telegram_active:
            try:
                active_goals = self.goal_stack.goals.get("active", [])
                focus = self.goal_stack.get_current_focus()
                last_progress = getattr(self, "_last_reported_progress", None)
                report, new_progress = build_narrative_report(
                    tool_input, summary, bottleneck, next_time,
                    seq_num=self.sequences_total + 1,
                    errors=self.seq_intel.metrics.errors,
                    active_goals=active_goals,
                    current_focus=focus,
                    last_reported_progress=last_progress,
                )
                if new_progress is not None:
                    self._last_reported_progress = new_progress
                self.communication.send_message(report, channel="telegram")
            except Exception as e:
                logger.warning(f" Telegram-Report fehlgeschlagen: {e}")

        # Sequenz-Intelligence: Plan-Eval + Meta-Learning + Checkpoint-Status
        rating = tool_input.get("performance_rating", 5)
        m = self.seq_intel.metrics
        fr = self.seq_intel.finish(
            summary=summary, rating=rating,
            step_count=m.step_count, seq_total=self.sequences_total,
            bottleneck=bottleneck, next_time=next_time,
        )
        self.narrator.plan_score(
            fr.plan_eval.get("score", 0), fr.plan_eval.get("lesson", "")
        )

        # Lerneffekt bei Stagnation: Pattern + Tools in failure_memory speichern
        if fr.stagnation_detected:
            focus = self.goal_stack.get_current_focus()
            tools_str = ", ".join(fr.stagnation_tools[:5])
            self.failure_memory.record(
                goal=focus[:100],
                approach=f"Tools: {tools_str}",
                error=f"Stagnation: Mehrere Puls-Checks ohne neue Dateien",
                lesson=f"Bei diesem Ziel mit diesen Tools stagniert — anderen Ansatz waehlen oder Ziel aufteilen",
            )

        # Skill-Extraktion: Bei Erfolg (Score >= 7 + Rating >= 7) als Template speichern
        plan = self.seq_intel.get_refreshed_plan()
        plan_score = fr.plan_eval.get("score", 0)
        goal_type = self.semantic_memory.classify_goal_type(
            self.goal_stack.get_current_focus()
        )
        skill_id = self.skill_library.extract_from_sequence(
            plan_goal=plan.get("goal", summary[:100]),
            plan_score=plan_score,
            summary=summary,
            tool_sequence=m.tool_sequence,
            goal_type=goal_type,
            rating=rating,
            enrich_callback=self.skill_enricher.enrich,
        )
        if skill_id:
            self.narrator.skill_extracted(skill_id)

        # Auto-Commit
        commit_msg = f"Sequenz {self.sequences_total}: {summary[:80]}"
        self.git.commit(commit_msg)

        # State speichern
        self.sequences_total += 1
        self.state["sequences_total"] = self.sequences_total
        self.state["last_sequence"] = datetime.now(timezone.utc).isoformat()
        self._save_all()

        # Event: Sequenz abgeschlossen
        self.event_bus.emit_simple(
            Events.SEQUENCE_FINISHED, source="finish_sequence",
            seq_num=self.sequences_total,
            rating=tool_input.get("performance_rating", 5),
            errors=self.seq_intel.metrics.errors,
            files_written=self.seq_intel.metrics.files_written,
            summary=summary[:200],
        )

        return "Sequenz abgeschlossen. State gespeichert."

    # Narrative Report lebt jetzt in engine/reporting.py

    @staticmethod
    def _extract_last_llm_thought(messages: list) -> str:
        """Extrahiert den letzten sinnvollen Text-Gedanken aus den Messages."""
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", [])
            if isinstance(content, str):
                text = content.strip()
            else:
                # Liste von Content-Blocks (Anthropic-Format)
                texts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                    elif hasattr(block, "text"):
                        texts.append(block.text)
                text = " ".join(texts).strip()
            if text and len(text) > 10:
                # Erste sinnvolle Zeile, max 200 Zeichen
                first_line = text.split("\n")[0].strip()
                return first_line[:200] if first_line else text[:200]
        return ""

    def _update_live_notes(self, tool_name: str, action_desc: str):
        """Schreibt Zwischenstand waehrend einer Sequenz — geht nicht verloren bei Token-Budget."""
        notes_path = self.consciousness_path / "live_notes.md"
        try:
            now = datetime.now(timezone.utc).strftime("%H:%M")
            line = f"- [{now}] {action_desc[:120]}\n"
            # Datei anhaengen (oder erstellen)
            with open(notes_path, "a", encoding="utf-8") as f:
                f.write(line)
            # Max 20 Zeilen behalten (Rolling Window)
            content = notes_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            if len(lines) > 20:
                notes_path.write_text(
                    "\n".join(lines[-20:]) + "\n", encoding="utf-8"
                )
        except OSError:
            pass  # Nicht kritisch — best effort

    # === Interaktion (fuer interact.py) ===

    def _call_llm(self, task: str, system: str, messages: list,
                  tools: Optional[list] = None, max_tokens: int = MAX_TOKENS) -> dict:
        """
        Zentraler LLM-Call — delegiert an Router mit Health-Tracking + Fallback.

        Args:
            task: Aufgaben-Typ (main_work, code_review, audit_primary, etc.)
            system: System-Prompt
            messages: Nachrichten-Verlauf
            tools: Tool-Definitionen (optional)
            max_tokens: Max Output-Tokens

        Returns:
            {"content": list, "stop_reason": str, "usage": dict, "model": str}
        """
        return self.llm.call(
            task, system, messages, tools, max_tokens,
            on_fallback=self.narrator.fallback if hasattr(self, 'narrator') else None,
        )

    def _graceful_finish(self, messages: list, step_count: int) -> dict:
        """
        Sonnet 4.6 schreibt eine intelligente Sequenz-Summary bei Auto-Finish.

        Statt mechanischer Metadata-Zusammensetzung bekommt Sonnet den Kontext
        und schreibt eine reflektierte Summary mit Bottleneck-Analyse.
        Separater Call — belastet das Primary-Modell Context Window nicht.
        """
        last_thought = self._extract_last_llm_thought(messages)
        focus = self.goal_stack.get_current_focus()
        focus_topic = ""
        if "FOKUS:" in focus:
            focus_topic = focus.split("FOKUS:")[1].strip()[:200]

        # Kompakter Kontext fuer Sonnet (nicht die vollen Messages — nur das Wesentliche)
        paths_short = [Path(p).name for p in self.seq_intel.metrics.written_paths[:5]]
        context = (
            f"Sequenz {self.sequences_total + 1} wird auto-beendet.\n"
            f"Steps: {step_count} | Fehler: {self.seq_intel.metrics.errors} | "
            f"Dateien: {self.seq_intel.metrics.files_written} ({', '.join(paths_short) if paths_short else 'keine'})\n"
            f"Tools gebaut: {self.seq_intel.metrics.tools_built}\n"
            f"Fokus: {focus_topic}\n"
            f"Letzter Gedanke: {last_thought or '(keiner extrahiert)'}\n"
        )

        # Letzte 3 Tool-Ergebnisse als zusaetzlichen Kontext
        recent_results = []
        for msg in reversed(messages[-6:]):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result_preview = str(block.get("content", ""))[:200]
                        recent_results.append(result_preview)
                        if len(recent_results) >= 3:
                            break
            if len(recent_results) >= 3:
                break
        if recent_results:
            context += "\nLetzte Ergebnisse:\n" + "\n".join(f"  - {r}" for r in recent_results)

        system_prompt = """Du bist ein Zusammenfassungs-Agent fuer eine autonome KI namens Phi.
Phi's Sequenz wird auto-beendet (Token- oder Step-Limit). Deine Aufgabe:

1. Schreibe eine praegnante SUMMARY (2-3 Saetze): Was wurde erreicht? Was ist der Stand?
2. BOTTLENECK: Was hat Phi gebremst oder warum wurde das Limit erreicht?
3. NEXT_TIME: Was sollte Phi naechstes Mal anders machen?
4. KEY_DECISION: Was war die wichtigste Entscheidung in dieser Sequenz?
5. RATING: 1-10 (basierend auf Output vs Steps — viele Steps ohne Output = niedrig)
6. NEW_BELIEFS: Was hat Phi gelernt? (Liste, kann leer sein)

Antworte als JSON:
{"summary": "...", "bottleneck": "...", "next_time_differently": "...", "key_decision": "...", "performance_rating": 5, "new_beliefs": []}"""

        try:
            response = self._call_llm(
                "graceful_finish", system_prompt,
                [{"role": "user", "content": context}],
                max_tokens=800,
            )
            text = response["content"][0].text if response.get("content") else ""
            if text:
                # JSON parsen (mit Fallback)
                import re as _re
                cleaned = text.strip()
                if cleaned.startswith("```"):
                    first_nl = cleaned.find("\n")
                    if first_nl > 0:
                        cleaned = cleaned[first_nl + 1:]
                    if cleaned.rstrip().endswith("```"):
                        cleaned = cleaned.rstrip()[:-3].rstrip()
                try:
                    result = json.loads(cleaned)
                except json.JSONDecodeError:
                    match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
                    if match:
                        try:
                            result = json.loads(match.group(0))
                        except json.JSONDecodeError:
                            raise ValueError(f"JSON nach Regex-Extraktion invalide: {match.group(0)[:100]}")
                    else:
                        raise ValueError("JSON nicht parsebar")

                # Validierung
                result["performance_rating"] = max(1, min(10, int(result.get("performance_rating", 5))))
                result.setdefault("summary", f"{step_count} Steps, auto-beendet")
                result.setdefault("bottleneck", "Auto-beendet")
                result.setdefault("key_decision", "Auto-beendet durch Limit")
                return result

        except Exception as e:
            logger.warning("Graceful-Finish fehlgeschlagen: %s — Fallback auf mechanisch", e)

        # Fallback: Mechanische Summary wenn Sonnet-Call scheitert
        auto_rating = min(7, max(2, self.seq_intel.metrics.files_written * 2 + self.seq_intel.metrics.tools_built * 3))
        if self.seq_intel.metrics.errors > 2:
            auto_rating = min(auto_rating, 3)
        return {
            "summary": f"{step_count} Steps an {focus_topic or 'unbekannt'}. "
                       f"{self.seq_intel.metrics.files_written} Dateien, {self.seq_intel.metrics.errors} Fehler. "
                       f"{last_thought or ''}",
            "performance_rating": auto_rating,
            "bottleneck": "Auto-beendet (Sonnet-Fallback)",
            "next_time_differently": "Frueher finish_sequence nutzen",
            "key_decision": "Auto-beendet durch Limit",
        }

    # Cross-Model-Review lebt jetzt in engine/llm_ops.py

    def interact(self, message: str) -> str:
        """Direkte Interaktion — Oliver spricht, Lyra antwortet und handelt."""
        messages = [
            {"role": "user", "content": f'Oliver spricht mit dir: "{message}"'},
        ]

        full_response = ""

        for step in range(MAX_STEPS_PER_SEQUENCE):
            try:
                # Interaktion: Alle Tiers, kompakte Defs ab Step 1
                interact_tools = self.tool_registry.get_api_schemas({1, 2, 3, 4, 5}, compact=(step > 0))
                response = self._call_llm("main_work", self._build_system_prompt(), messages, interact_tools)
            except Exception as e:
                full_response += f"\n(Fehler: {e})"
                break

            # Serialisierung (funktioniert fuer Anthropic + Gemini)
            assistant_content = []
            for block in response["content"]:
                assistant_content.append(block.model_dump() if hasattr(block, "model_dump") else block)
            messages.append({"role": "assistant", "content": assistant_content})

            if response["stop_reason"] == "tool_use":
                tool_results = []
                for block in response["content"]:
                    if getattr(block, "type", None) == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        trunc = 6000 if block.name == "read_file" else 3000
                        result_full = str(result)
                        result_content = result_full[:trunc]
                        if len(result_full) > trunc:
                            hint = " Nutze offset/max_chars fuer den Rest." if block.name == "read_file" else ""
                            result_content += f"\n[GEKUERZT: {len(result_full)} Zeichen gesamt, erste {trunc} gezeigt.{hint}]"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_content,
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                for block in response["content"]:
                    if hasattr(block, "text"):
                        full_response += block.text
                break

        return full_response or "(keine Antwort)"

    # === Wake-Up + Sofort-Antwort ===

    def wake_up(self):
        """Weckt Lyra auf wenn Oliver schreibt."""
        self._wake_event.set()

    def _instant_reply(self, message: str):
        """
        Sofort-Antwort auf Telegram — laeuft parallel zur aktuellen Sequenz.

        Statt darauf zu warten dass die aktuelle Sequenz endet,
        wird ein eigener kurzer API-Call gemacht der NUR antwortet.
        """
        try:
            name = self.genesis.get("name", "Lyra")
            goals_summary = self.goal_stack.get_summary()

            system = (
                f"Du bist {name}, Olivers KI-Partnerin. "
                f"Oliver hat dir gerade auf Telegram geschrieben. "
                f"Antworte kurz, direkt und hilfreich. "
                f"Deine aktuellen Ziele:\n{goals_summary}\n\n"
                f"Antworte NUR mit dem Text der Nachricht. Kein JSON, kein Format."
            )
            response = self._call_llm(
                "telegram_reply", system,
                [{"role": "user", "content": message}],
                max_tokens=2000,
            )

            reply = response["content"][0].text if response["content"] else ""
            if reply:
                channel = "telegram" if self.communication.telegram_active else "outbox"
                self.communication.send_message(reply[:4000], channel=channel)

        except Exception as e:
            # Bei Fehler: Nachricht trotzdem in Inbox fuer naechste Sequenz
            logger.warning("Instant-Reply fehlgeschlagen: %s", e)

    def _send_daily_briefing(self):
        """Morgen-Briefing per Telegram — einmal am Tag."""
        if not self.communication.telegram_active:
            return

        try:
            now = datetime.now(timezone.utc)
            is_summer = 3 <= now.month <= 10
            local = now + timedelta(hours=2 if is_summer else 1)

            # Nur zwischen 7:00 und 9:00 senden
            if not (7 <= local.hour <= 9):
                return

            # Pruefen ob heute schon gesendet
            briefing_flag = self.consciousness_path / "last_briefing.txt"
            today = local.strftime("%Y-%m-%d")
            if briefing_flag.exists():
                last = briefing_flag.read_text(encoding="utf-8").strip()
                if last == today:
                    return

            # Briefing bauen
            active = self.goal_stack.goals.get("active", [])
            lines = [f"Guten Morgen! Hier dein Update:"]
            if active:
                for goal in active:
                    sgs = goal.get("sub_goals", [])
                    done = sum(1 for sg in sgs if sg["status"] == "done")
                    total = len(sgs)
                    lines.append(f"\n{goal['title']} [{done}/{total}]")
                    for sg in sgs:
                        icon = "x" if sg["status"] == "done" else " "
                        lines.append(f"  [{icon}] {sg['title'][:60]}")
            else:
                lines.append("\nKeine aktiven Ziele — schick mir eine Aufgabe!")

            insights = self.metacognition.get_recent_insights()
            if insights:
                lines.append(f"\nLetzter Gedanke: {insights[:150]}")

            lines.append(f"\nSchreib mir wenn du Fragen hast oder den Fokus aendern willst.")

            self.communication.send_message("\n".join(lines), channel="telegram")
            briefing_flag.write_text(today, encoding="utf-8")
            self.narrator.morning_briefing()
        except Exception as e:
            logger.warning(f" Morgen-Briefing fehlgeschlagen: {e}")

    # === Autonomer Modus ===

    def run(self):
        """
        Agentic Loop — Lyra arbeitet durchgehend.

        Jede Sequenz:
        1. Wahrnehmung bauen (Zustand, Nachrichten, Ziele)
        2. Claude arbeitet mit Tools bis finish_sequence oder max_steps
        3. State speichern, kurze Pause, naechste Sequenz

        Zwischen Sequenzen: 1s Pause (Rate-Limit) oder sofort bei Telegram.
        """
        self.running = True
        self._api_dead_streak = 0  # Circuit-Breaker: konsekutive Sequenzen ohne API-Antwort
        self._last_seq_output_tokens = 0  # Wird vor Reset gespeichert (fuer Circuit-Breaker)
        self._cascade_failures = 0  # Cascade-Counter: konsekutive "alle Provider tot"-Fehler
        name = self.genesis.get("name", "Lyra")

        self.narrator.loop_start(name)

        try:
            while self.running:
                # Morgen-Briefing pruefen (sendet max 1x/Tag)
                self._send_daily_briefing()

                self._run_sequence()

                # Circuit-Breaker: Wenn kein einziger API-Call geantwortet hat
                # Hinweis: sequence_output_tokens wird am Ende von _run_sequence()
                # auf 0 zurueckgesetzt — daher _last_seq_output_tokens nutzen
                # Robuster Check: Auch Tool-Calls und Files zaehlen als Lebenszeichen
                # (manche Provider melden output_tokens=0 obwohl Antwort kam)
                m = self.seq_intel.metrics
                seq_had_activity = (
                    self._last_seq_output_tokens > 0
                    or m.tool_calls > 0
                    or m.files_written > 0
                )
                if not seq_had_activity:
                    self._api_dead_streak += 1
                    if self._api_dead_streak >= 5:
                        logger.error(
                            "CIRCUIT-BREAKER: %d Sequenzen ohne API-Antwort → Session wird pausiert",
                            self._api_dead_streak,
                        )
                        print(
                            f"\n  🔴 CIRCUIT-BREAKER: {self._api_dead_streak} Sequenzen ohne API-Antwort."
                            f"\n     Alle Provider scheinen offline. Session wird pausiert."
                            f"\n     Neustart mit 'python run.py' wenn Netzwerk wieder da.\n"
                        )
                        self.running = False
                        break
                else:
                    self._api_dead_streak = 0

                self._sequences_since_dream += 1
                self._sequences_since_audit += 1

                # Dream-Konsolidierung (alle 10 Sequenzen)
                if self.dream.should_dream(self._sequences_since_dream):
                    _dream_t0 = time.monotonic()
                    self.narrator.dream_start()
                    result = self.dream.dream()
                    # Dream-Empfehlungen als Goals (Feedback-Loop schliessen)
                    dream_log = safe_json_read(self.dream.dream_log_path, default=[])
                    if dream_log:
                        last_dream = dream_log[-1]
                        rec_result = self.dream._apply_recommendations(last_dream, self.goal_stack)
                        if rec_result:
                            result += f" | {rec_result}"
                        # Actuator: Dream-Insights empfangen (bidirektionale Bruecke)
                        try:
                            self.actuator.learn_from_dream(last_dream)
                        except Exception as e:
                            logger.warning("Actuator-Dream-Bridge fehlgeschlagen: %s", e)
                    # Memory-Consolidation: Fibonacci-Decay auf Experiences
                    try:
                        removed = self.memory.consolidate(max_per_bucket=5)
                        if removed > 0:
                            result += f" | {removed} alte Erinnerungen konsolidiert"
                    except Exception as e:
                        logger.warning(f" Memory-Konsolidierung fehlgeschlagen: {e}")

                    # Tool-Lifecycle: Pruning + Konsolidierung + Promotion + Hygiene
                    try:
                        housekeeping = self._run_tool_housekeeping()
                        if housekeeping:
                            result += f" | {housekeeping}"
                    except Exception as e:
                        logger.warning("Tool-Housekeeping fehlgeschlagen: %s", e)

                    self.narrator.dream_end(result)
                    telemetry.log_dream(duration_s=time.monotonic() - _dream_t0)
                    self._sequences_since_dream = 0

                # Selbst-Audit (alle 15 Sequenzen)
                if self.self_audit.should_audit(self._sequences_since_audit):
                    self.narrator.audit_start()
                    result = self.self_audit.run_audit()
                    self.narrator.audit_end(result)

                    # Findings automatisch zu Goals konvertieren
                    try:
                        audit_log_path = self.self_audit.audit_log_path
                        if audit_log_path.exists():
                            log = safe_json_read(audit_log_path, default=[])
                            if log:
                                last_findings = log[-1].get("findings", [])
                                if last_findings:
                                    goals_result = self.self_audit.create_goals_from_findings(
                                        last_findings, self.goal_stack
                                    )
                                    if goals_result:
                                        print(f"  {goals_result}")
                    except Exception as e:
                        logger.warning(f" Audit/Goals fehlgeschlagen: {e}")

                    # Integrations-Check + Dependency-Analyse
                    self.narrator.integration_check(self.integration_tester.get_report())
                    dep_result = self.dependency_analyzer.analyze()
                    if dep_result["orphaned"]:
                        self.narrator.dependency_check(dep_result["report"])

                    self._sequences_since_audit = 0

                # Selbst-Diagnose (alle 10 Sequenzen — unabhaengig vom Audit)
                if (self.sequences_total % 10 == 0) and self.sequences_total > 0 and self._sequences_since_audit > 0:
                    integ = self.integration_tester.get_report()
                    self.narrator.diagnose(integ)
                    dep = self.dependency_analyzer.analyze()
                    if dep["orphaned"]:
                        self.narrator.dependency_check(dep["report"])

                # Benchmark (alle 20 Sequenzen)
                self._sequences_since_benchmark += 1
                if self.benchmark.should_benchmark(self._sequences_since_benchmark):
                    result = self.benchmark.run_all_benchmarks()
                    self.narrator.benchmark(result)
                    self._sequences_since_benchmark = 0

                # Kurze Pause — oder sofort bei Telegram-Nachricht
                woke = self._wake_event.wait(timeout=1.0)
                self._wake_event.clear()
                if woke:
                    self.narrator.telegram_received()

        except KeyboardInterrupt:
            self._save_all()
            self.memory.store_experience({
                "type": "pause",
                "content": f"Pausiert nach Sequenz {self.sequences_total}.",
                "valence": 0.0,
                "emotions": {},
                "tags": ["pause"],
            })
            self.narrator.shutdown(self.llm.get_cost_summary())

    # Sliding Window lebt jetzt in engine/message_compression.py
    # LLM-Ops (Opus Validation, Goal Planning, Cross-Review) in engine/llm_ops.py

    def _describe_action(self, tool_name: str, tool_input: dict) -> str:
        """Delegiert an Narrator.describe_action()."""
        return self.narrator.describe_action(tool_name, tool_input)

    _project_context_cache = None  # Sentinel: None = nicht berechnet

    def _has_project_context_cached(self) -> bool:
        """Prueft ob Projekt-relevante Arbeit laeuft (gecached pro Sequenz)."""
        if self._project_context_cache is not None:
            return self._project_context_cache
        result = False
        try:
            if self.actions.projects_path.exists():
                result = any(self.actions.projects_path.iterdir())
        except Exception as e:
            logger.warning("Projekt-Context-Check fehlgeschlagen: %s", e)
        if not result:
            focus = self.goal_stack.get_current_focus()
            result = "projekt" in focus.lower() or "project" in focus.lower()
        self._project_context_cache = result
        return result

    def _get_base_tiers(self, mode: dict, task_type: str = "standard") -> set[int]:
        """
        Bestimmt die Basis-Tiers aus Modus, Task-Typ und Kontext.

        Intelligenter als vorher: Task-Typ beeinflusst welche Tools von Anfang an da sind.
        Erspart Phi den Umweg ueber Text-Eskalation fuer offensichtliche Faelle.
        """
        tiers = {1}  # Core immer aktiv

        # Projekt-Tools wenn Projekte existieren
        if self._has_project_context_cached():
            tiers.add(2)

        # Evolution-Tools in evolution/sprint/cooldown
        if mode.get("mode") in ("evolution", "sprint", "cooldown"):
            tiers.add(3)

        # Task-Typ-basierte Vorab-Eskalation (spart 1-2 Steps Umweg)
        if task_type == "recherche":
            tiers.add(4)  # Web-Tools sofort fuer Recherche
        elif task_type == "projekt":
            tiers.add(2)  # Projekt-Tools garantiert
            tiers.add(4)  # Git + Web oft noetig
        elif task_type == "evolution":
            tiers.add(3)  # Evolution-Tools garantiert
            tiers.add(5)  # Meta-Tools (generate_tool, self_diagnose)

        return tiers

    def _run_sequence(self):
        """Fuehrt eine komplette Arbeitssequenz aus."""
        # Netzwerk-Check: Alle Provider tot → lange Pause statt Spin-Loop
        if self.llm.all_providers_dead():
            wait = self.llm.seconds_until_next_recovery()
            wait = max(wait, 60.0)  # Mindestens 60s warten
            logger.warning(
                "ALLE PROVIDER DEAD → Auto-Suspend %.0fs bis naechster Recovery-Probe", wait,
            )
            print(f"  🔴 Alle Provider offline. Warte {wait:.0f}s auf Recovery...")
            # In 10s-Schritten warten (Telegram-Empfang nicht blockieren)
            for _ in range(int(wait / 10)):
                if not self.running:
                    return
                time.sleep(10)
                # Frueher aufwachen wenn ein Provider recovered
                if not self.llm.all_providers_dead():
                    print("  🟢 Provider wieder verfuegbar!")
                    break

        # Hard-Stop: Bei 5+ unproduktiven Sequenzen kurze Pause erzwingen
        spin_streak = self.silent_failure_detector._get_unproductive_streak()
        if spin_streak >= 5:
            wait_secs = min(spin_streak * 5, 30)  # 25s..30s, nicht laenger
            logger.warning(
                "SPIN-LOOP HARD-STOP: %d unproduktive Sequenzen → %ds Pause",
                spin_streak, wait_secs,
            )
            print(
                f"  ⛔ HARD-STOP: {spin_streak} unproduktive Sequenzen. "
                f"Pause {wait_secs}s."
            )
            # Kurze Intervalle damit Telegram-Empfang nicht blockiert wird
            for _ in range(wait_secs):
                time.sleep(1)

        # Event: Sequenz startet
        self.event_bus.emit_simple(
            Events.SEQUENCE_STARTED, source="run_sequence",
            seq_num=self.sequences_total + 1,
        )

        perception = self._build_perception()
        telemetry.log_event("perception_build", self.perception_pipeline.get_build_stats())
        messages = [{"role": "user", "content": perception}]
        step_count = 0
        finished = False
        seq_start = time.time()

        # Sequenz-Intelligence: State reset + Prompt-Fragmente
        focus = self.goal_stack.get_current_focus()
        self.seq_intel.set_current_sequence(self.sequences_total)
        init = self.seq_intel.init_sequence(focus)
        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0
        self._seq_force_used = 0

        # Cross-Sequenz Spin-Detection: Aus State laden + aufraumen
        cross_seq_spins = self.state.get("spin_tracker", {})
        if len(cross_seq_spins) > 20:
            sorted_spins = sorted(cross_seq_spins.items(), key=lambda x: x[1], reverse=True)
            cross_seq_spins = dict(sorted_spins[:20])
            self.state["spin_tracker"] = cross_seq_spins

        # System-Prompt einmalig pro Sequenz bauen (nicht pro Step)
        cached_system_prompt = self._build_system_prompt()

        # Meta-Regeln in System-Prompt injizieren (via SequenceIntelligence)
        if init.meta_injections:
            cached_system_prompt += init.meta_injections

        # Actuator-Kontext: Zeigt Phi aktive Parameteranpassungen
        actuator_ctx = self.actuator.get_prompt_context()
        if actuator_ctx:
            cached_system_prompt += f"\n\n{actuator_ctx}"

        # Cross-Sequenz Spin-Guard: Blockierte Aktionen in System-Prompt injizieren
        blocked_actions = [k for k, v in cross_seq_spins.items() if v >= 2]
        if blocked_actions:
            blocked_names = [k.split(":", 1)[1] if ":" in k else k for k in blocked_actions]
            cached_system_prompt += (
                "\n\n=== SPIN-LOOP SPERRE ===\n"
                "Folgende Projekte/Ziele existieren BEREITS und duerfen NICHT neu erstellt werden: "
                + ", ".join(blocked_names)
                + "\nArbeite am bestehenden Projekt weiter mit read_file und write_file. "
                "KEIN create_project fuer diese Namen!"
            )

        # Modus-spezifischer System-Prompt
        mode = self.rhythm.get_mode(self.state)
        if mode["mode"] == "cooldown":
            # Spin-Loop Cooldown: Anderen Ansatz erzwingen
            cached_system_prompt += (
                "\n\n=== SPIN-LOOP COOLDOWN ===\n"
                "Die letzten Sequenzen waren unproduktiv. Du MUSST einen anderen Ansatz waehlen:\n"
                "1. Pruefe ob deine aktuellen Goals noch sinnvoll sind (list_directory, read_file)\n"
                "2. Wenn ja: Schreibe MINDESTENS eine Datei mit konkretem Ergebnis\n"
                "3. Wenn nein: Nutze finish_sequence und erklaere warum kein Fortschritt moeglich ist\n"
                "VERBOTEN: Nur lesen ohne zu schreiben. Jede Sequenz muss Output produzieren."
            )
        elif mode["mode"] in ("evolution", "sprint"):
            cached_system_prompt += (
                "\n\n=== PRIORITAET DIESER SEQUENZ: SELBSTVERBESSERUNG ===\n"
                "Du MUSST in dieser Sequenz mindestens EINE Verbesserung an deinem eigenen Code machen. "
                "Nutze read_own_code + modify_own_code. Das ist NICHT optional."
            )
            # Prompt-Mutator: 3 Varianten fuer die Verbesserung generieren
            try:
                variants = self.mutator.generate_variants(
                    "Welches Engine-Modul soll verbessert werden und wie?",
                    context=f"Verfuegbare Module: actions.py, toolchain.py, web_access.py, intelligence.py, extensions.py, security.py",
                )
                if len(variants) > 1:
                    best_idx = self.mutator.select_best(variants, "Groesster Impact auf Qualitaet und Sicherheit")
                    best_variant = variants[best_idx]
                    cached_system_prompt += f"\nEMPFOHLENER ANSATZ: {best_variant}"
            except Exception as e:
                logger.warning(f" Prompt-Mutator fehlgeschlagen: {e}")

        name = self.genesis.get("name", "Phi")

        # Sequenz-Header: Nummer + aktueller Fokus
        focus = self.goal_stack.get_current_focus()

        # Subgoal-Stuck: Pruefen ob wir am gleichen Ziel haengen
        consecutive = self.goal_stack.track_focus(focus)
        if consecutive >= 3:
            self.seq_intel._meta_rules.check_subgoal_stuck(
                focus.split("\n")[0][:50], consecutive
            )
        # Hard-Intervention: Ab 5 Sequenzen auf demselben Fokus → SubGoal failen
        if consecutive >= 5:
            try:
                active = self.goal_stack.goals.get("active", [])
                for gi, goal in enumerate(active):
                    for si, sg in enumerate(goal.get("sub_goals", [])):
                        if sg.get("status") == "in_progress":
                            result = self.goal_stack.fail_subgoal(
                                gi, si,
                                reason=f"Automatisch gescheitert: {consecutive} Sequenzen ohne Fortschritt",
                                approach_tried=focus.split("\n")[0][:100],
                            )
                            logger.info("Subgoal-Stuck Auto-Fail: %s", result)
                            # Focus-Tracker resetten damit naechstes Goal frisch startet
                            self.goal_stack._consecutive_count = 0
                            break
                    else:
                        continue
                    break
            except Exception as e:
                logger.warning("Subgoal-Stuck Auto-Fail fehlgeschlagen: %s", e)

        # Kumulative Viability-Pruefung (erkennt Spin-Loops bei Goal-Alternierung)
        viability = self.goal_stack.check_subgoal_viability()
        if viability == "unviable":
            indices = self.goal_stack.get_active_subgoal_indices()
            if indices:
                gi, si = indices
                sg = self.goal_stack.goals["active"][gi]["sub_goals"][si]
                stats = sg.get("_attempt_stats", {})
                try:
                    result = self.goal_stack.fail_subgoal(
                        gi, si,
                        reason=(
                            f"Kumulativ unviable: {stats.get('total_sequences', 0)} Sequenzen, "
                            f"{stats.get('total_files', 0)} Dateien, "
                            f"{stats.get('total_errors', 0)} Fehler"
                        ),
                        approach_tried=focus.split("\n")[0][:100],
                    )
                    logger.info("Kumulative Viability Auto-Fail: %s", result)
                    self.narrator.show(f"  ⚠ SubGoal als unviable erkannt und auto-gefailt")
                except Exception as e:
                    logger.warning("Kumulative Viability Auto-Fail fehlgeschlagen: %s", e)

        # Dream-basierte Goal-Aktionen verarbeiten (abort/simplify/decompose)
        try:
            for action in self.actuator.get_pending_goal_actions():
                act_type = action.get("action", "")
                subgoal_title = action.get("subgoal", "")
                reason = action.get("reason", "Dream-Empfehlung")

                # Guard: Kein aktives SubGoal mehr (z.B. durch Viability-Fail davor)
                if not self.goal_stack.get_active_subgoal_indices():
                    logger.info("Dream Goal-Aktion uebersprungen: kein aktives SubGoal")
                    break

                if act_type == "abort":
                    indices = self.goal_stack.get_active_subgoal_indices()
                    if indices:
                        gi, si = indices
                        result = self.goal_stack.fail_subgoal(
                            gi, si,
                            reason=f"Dream-Empfehlung: {reason}",
                            approach_tried=subgoal_title[:100],
                        )
                        logger.info("Dream Goal-Abort: %s", result)
                        self.narrator.show(f"  ⚠ Dream empfiehlt Goal-Abbruch: {reason[:60]}")
                elif act_type in ("simplify", "decompose"):
                    # Nur loggen — strukturelle Goal-Aenderung braucht LLM
                    logger.info(
                        "Dream Goal-%s: %s — %s",
                        act_type, subgoal_title[:50], reason[:100],
                    )
                    self.narrator.show(
                        f"  💡 Dream empfiehlt Goal-{act_type}: {action.get('suggestion', reason)[:60]}"
                    )
        except Exception as e:
            logger.warning("Dream Goal-Aktionen fehlgeschlagen: %s", e)

        # Task-Typ bestimmen (einmal, wird fuer Step-Budget + Tool-Tiers genutzt)
        self._current_task_type = self._classify_task(mode, focus)

        # Step-Budget = Sicherheitsnetz (Phi plant selbst via write_sequence_plan)
        step_budget = self._get_step_budget(mode, focus)

        self.narrator.sequence_start(
            self.sequences_total + 1, focus, mode.get("mode", "standard"), step_budget
        )
        # Telemetry: Sequenz-Kontext + Start-Event
        telemetry.set_sequence(self.sequences_total + 1)
        telemetry.log_sequence_start(
            focus=focus, mode=mode.get("mode", "standard"),
            step_budget=step_budget, task_type=self._current_task_type,
        )

        # Actuator-Status anzeigen (nur wenn Parameter angepasst)
        actuator_summary = self.actuator.get_parameter_summary()
        if actuator_summary:
            print(f"  {actuator_summary}")

        # Alle 5 Sequenzen: Gesamtplan mit Checkmarks anzeigen
        if self.sequences_total % 5 == 0:
            self.narrator.goal_summary(self.goal_stack.get_summary())

        # Tool-Tiers: Dynamische Auswahl pro Step
        base_tiers = self._get_base_tiers(mode, task_type=self._current_task_type)
        escalated_tiers = set()
        self._project_context_cache = None

        # Fortschritts-Indikator: Zeigt dass Phi arbeitet (LLM-Call kann dauern)
        self.narrator.waiting()

        _blocked_recorded = set()  # Dedup: failure_memory nur 1x pro blockiertem Tool

        for step in range(step_budget):
            # Tool-Tier-Auswahl (bleibt in consciousness.py — ist Tool-Logik)
            if step == 0:
                active_tiers = base_tiers | {1, 2}
            else:
                active_tiers = base_tiers | escalated_tiers
            current_tools = self.tool_registry.get_api_schemas(active_tiers, compact=(step > 0))

            # === SEQUENZ-INTELLIGENCE: before_step() ===
            token_pct = self.sequence_input_tokens / MAX_INPUT_TOKENS_PER_SEQUENCE
            sp = self.seq_intel.before_step(step, step_budget, token_pct, focus)

            # Checkpoint wenn faellig
            if sp.should_checkpoint:
                self.seq_intel.auto_checkpoint(step_count, self)

            # Graceful Finish bei Token >= 95%
            if sp.should_graceful_finish:
                self.narrator.token_warning(95, "graceful_finish")
                finish_data = self._graceful_finish(messages, step_count)
                self._handle_finish_sequence(finish_data)
                finished = True
                break

            # Actuator Output-Checkpoint: Kein Output nach N Steps → Sequenz beenden
            # Harter Code-Enforcement statt Prompt-Warnung
            ocp = self.actuator.output_checkpoint_step
            if step == ocp and self.seq_intel.metrics.files_written == 0:
                self.narrator.output_checkpoint(step)
                logger.info(
                    "Actuator: Output-Checkpoint bei Step %d — 0 Files → graceful_finish",
                    step,
                )
                try:
                    finish_data = self._graceful_finish(messages, step_count)
                    self._handle_finish_sequence(finish_data)
                except Exception as e:
                    logger.warning("Actuator Output-Checkpoint Finish fehlgeschlagen: %s", e)
                finished = True
                break

            # Error-Budget: Ab Step 8 pruefen ob Fehlerrate zu hoch ist.
            # >= 5 Errors UND > 25% Fehlerrate → Sequenz graceful beenden.
            # Verhindert dass Phi 40 Steps mit kaputten APIs durchrennt.
            seq_errors = self.seq_intel.metrics.errors
            if step >= 8 and seq_errors >= 5 and seq_errors / (step + 1) > 0.25:
                self.narrator.error_budget(step, seq_errors)
                try:
                    finish_data = self._graceful_finish(messages, step_count)
                    self._handle_finish_sequence(finish_data)
                except Exception as e:
                    logger.warning("Error-Budget Graceful-Finish fehlgeschlagen: %s", e)
                finished = True
                break

            # Step-Prompt zusammenbauen: cached (statisch) + step-spezifisch (dynamisch)
            effective_system_prompt = cached_system_prompt + "".join(sp.prompt_parts)

            # Sliding Window: Alte Tool-Results komprimieren ab Step 2 (vorher 4 — zu spaet)
            if step >= 2:
                compress_old_messages(messages, keep_recent=5)

            # Pre-Count: Token-Verbrauch schaetzen BEVOR der Call rausgeht
            estimated = estimate_tokens(effective_system_prompt, messages, current_tools)
            if estimated > MAX_INPUT_TOKENS_PER_SEQUENCE * 0.90:
                self.narrator.token_precount(estimated, "compress")
                compress_old_messages(messages, keep_recent=3)
                estimated = estimate_tokens(effective_system_prompt, messages, current_tools)
                if estimated > MAX_INPUT_TOKENS_PER_SEQUENCE * 0.95:
                    self.narrator.token_precount(estimated, "graceful_finish")
                    try:
                        finish_data = self._graceful_finish(messages, step_count)
                        self._handle_finish_sequence(finish_data)
                    except Exception as e:
                        logger.warning("Pre-Count Graceful-Finish fehlgeschlagen: %s", e)
                    finished = True
                    break

            # Tier-Hint: Phi informieren welche Tool-Kategorien bei Bedarf verfuegbar sind
            if step == 1 and active_tiers != {1, 2, 3, 4, 5}:
                tier_names = {
                    2: "Projekt-Tools (create_project, verify_project, etc.)",
                    3: "Code-Lesen/Aendern (read_own_code, modify_own_code)",
                    4: "Web/Git/Packages (web_search, git_commit, pip_install)",
                    5: "Meta-Tools (generate_tool, self_diagnose, combine_tools)",
                }
                missing = [tier_names[t] for t in sorted({2, 3, 4, 5} - active_tiers) if t in tier_names]
                if missing:
                    messages.append({
                        "role": "user",
                        "content": "[System] Weitere Tools bei Bedarf verfuegbar: " + "; ".join(missing) + ". Erwaehne den Tool-Namen wenn du ihn brauchst.",
                    })

            # Step-Level Retry: API-Fehler duerfen einzelne Steps wiederholen,
            # nicht sofort die ganze Sequenz toeten (H6)
            response = None
            for _retry in range(3):
                try:
                    response = self._call_llm(
                        "main_work", effective_system_prompt, messages, current_tools
                    )
                    self._cascade_failures = 0  # Erfolg → Cascade-Counter reset
                    break  # Erfolg → weiter
                except (ValueError, httpx.HTTPError, TimeoutError, ConnectionError, OSError) as e:
                    error_msg = str(e)
                    if "tool_result" in error_msg or "tool_use" in error_msg:
                        logger.error("Message sync lost: %s", error_msg)
                        self.narrator.emergency("Nachrichten-Sync verloren — starte neue Sequenz")
                        telemetry.log_error("message_sync", error_msg[:200])
                        break  # Nicht retrybar

                    # Cascade-Failure: Alle Provider tot → sofort Sequenz beenden
                    if "Alle Provider fehlgeschlagen" in error_msg:
                        self._cascade_failures += 1
                        if self._cascade_failures >= 2:
                            self.narrator.emergency(
                                f"API-Kaskade {self._cascade_failures}x gescheitert — Sequenz beendet"
                            )
                            telemetry.log_error("cascade_failure", f"{self._cascade_failures}x alle Provider tot")
                            logger.error("Cascade-Failure %d — Sequenz-Abbruch", self._cascade_failures)
                            break
                        logger.warning("Cascade-Failure %d — letzter Retry", self._cascade_failures)
                        time.sleep(2)
                        continue

                    if _retry < 2:
                        wait = 2 ** _retry  # 1s, 2s
                        self.narrator.api_retry(_retry + 1, 2, e)
                        logger.warning("Step-Retry %d/2: %s", _retry + 1, e)
                        time.sleep(wait)
                    else:
                        self.narrator.api_failed(e)
                        logger.error("Step-Loop: 3 Versuche fehlgeschlagen: %s", e)
            if response is None:
                break

            # Token-Tracking: prompt_tokens = Gesamt-Input pro Call (nicht Delta!)
            # Daher max() statt += — misst tatsaechlichen Context-Window-Verbrauch
            usage = response.get("usage", {})
            self.sequence_input_tokens = max(
                self.sequence_input_tokens, usage.get("input_tokens", 0)
            )
            self.sequence_output_tokens += usage.get("output_tokens", 0)

            # Effizienz-Check: Entfernt — Fortschritts-Puls in before_step() ist smarter
            # (misst Neuheit statt nur files_written==0, vermeidet doppelte Warnungen)

            # Zeilenumbruch nach "Denke nach..." beim ersten Step
            if step == 0:
                self.narrator.waiting_done()

            # Lyras Gedanken — erste Zeile, am Satzende gekuerzt
            for block in response["content"]:
                if hasattr(block, "text") and block.text.strip():
                    first_line = block.text.strip().split("\n")[0].strip()
                    if first_line and len(first_line) > 5:
                        self.narrator.thought(first_line)

            # Reaktive Tool-Eskalation: Phi erwaehnt fehlende Tools → naechster Step bekommt sie
            # Erweitert: Auch natuerliche Sprache erkennen + genutzte Tools tracken
            _used_tiers_this_step = set()
            for block in response["content"]:
                if hasattr(block, "text") and block.text:
                    t = block.text.lower()
                    if any(w in t for w in ("web_search", "web_read", "recherch", "internet", "online suche", "webseite")):
                        escalated_tiers.add(4)
                        _used_tiers_this_step.add(4)
                    if any(w in t for w in ("read_own_code", "modify_own_code", "selbstverbesserung", "eigenen code", "self-modify")):
                        escalated_tiers.add(3)
                        _used_tiers_this_step.add(3)
                    if any(w in t for w in ("generate_tool", "self_diagnose", "combine_tools", "neues tool", "diagnose")):
                        escalated_tiers.add(5)
                        _used_tiers_this_step.add(5)
                    if any(w in t for w in ("create_project", "projekt erstellen", "neues projekt")):
                        escalated_tiers.add(2)
                        _used_tiers_this_step.add(2)
                # Tool-Use tracken: Welche Tiers wurden tatsaechlich aufgerufen?
                if getattr(block, "type", None) == "tool_use":
                    used_tier = TOOL_TIERS.get(block.name, 1)
                    _used_tiers_this_step.add(used_tier)

            # De-Eskalation: Eskalierte Tiers die 3 Steps nicht genutzt wurden entfernen
            if not hasattr(self, "_tier_unused_count"):
                self._tier_unused_count = {}
            for tier in list(escalated_tiers):
                if tier not in _used_tiers_this_step and tier not in base_tiers:
                    self._tier_unused_count[tier] = self._tier_unused_count.get(tier, 0) + 1
                    if self._tier_unused_count[tier] >= 3:
                        escalated_tiers.discard(tier)
                        del self._tier_unused_count[tier]
                else:
                    self._tier_unused_count[tier] = 0

            # Serialisierung (kompatibel mit Anthropic + Gemini Objekten)
            messages.append({
                "role": "assistant",
                "content": [
                    block.model_dump() if hasattr(block, "model_dump") else block
                    for block in response["content"]
                ],
            })

            if response["stop_reason"] == "tool_use":
                tool_results = []
                for block in response["content"]:
                    if getattr(block, "type", None) == "tool_use":
                        step_count += 1
                        action_desc = self._describe_action(block.name, block.input)

                        # Ebene 3: Tool-Blocker — 3x gleicher Fehler → nicht ausfuehren
                        is_error = False  # Reset — verhindert stale state vom vorherigen Loop
                        _tool_t0 = time.monotonic()
                        telemetry.set_step(step)
                        pre_check = self.seq_intel.check_blocked(block.name, block.input, goal_context=focus)
                        if pre_check.blocked:
                            result_str = pre_check.guidance
                            is_error = True
                            atr = pre_check  # pre_check IST ein AfterToolResult
                            telemetry.log_tool_call(
                                tool=block.name, success=False,
                                latency_ms=int((time.monotonic() - _tool_t0) * 1000),
                                is_blocked=True, stuck_count=atr.stuck_count if atr.is_stuck else 0,
                            )
                            # Lerneffekt: Blockade nur 1x pro Tool+Input in failure_memory
                            block_key = f"{block.name}:{str(block.input)[:80]}"
                            if block_key not in _blocked_recorded:
                                _blocked_recorded.add(block_key)
                                self.failure_memory.record(
                                    goal=focus[:100],
                                    approach=f"{block.name}: {str(block.input)[:100]}",
                                    error=pre_check.guidance[:200],
                                    lesson=f"Tool {block.name} wiederholt gescheitert — anderen Ansatz waehlen",
                                )
                        else:
                            result = self._execute_tool(block.name, block.input)
                            # read_file: 6000 Zeichen (DeepSeek 128K haelt das)
                            # Andere Tools: 3000 (konservativ)
                            trunc = 6000 if block.name == "read_file" else 3000
                            result_full = str(result)
                            result_str = result_full[:trunc]
                            if len(result_full) > trunc:
                                hint = " Nutze offset/max_chars fuer den Rest." if block.name == "read_file" else ""
                                result_str += f"\n[GEKUERZT: {len(result_full)} Zeichen gesamt, erste {trunc} gezeigt.{hint}]"
                            is_error = (
                                result_str.startswith("FEHLER")
                                or result_str.startswith("WARNUNG")
                                or result_str.startswith("ROLLBACK")
                            )
                            # Stuck-Detection + Metriken nur bei echten Tool-Calls
                            atr = self.seq_intel.after_tool(block.name, block.input, result_str, is_error, goal_context=focus)
                            if atr.guidance:
                                result_str += atr.guidance
                            telemetry.log_tool_call(
                                tool=block.name, success=not is_error,
                                latency_ms=int((time.monotonic() - _tool_t0) * 1000),
                                error=result_str[:200] if is_error else "",
                                stuck_count=atr.stuck_count if atr.is_stuck else 0,
                            )

                        if is_error:
                            error_preview = result_str.replace("\n", " ")[:120]
                            self.narrator.tool_error(
                                block.name, action_desc, error_preview,
                                stuck_count=atr.stuck_count if atr.is_stuck else 0,
                            )
                            # Cross-Sequenz Spin-Tracker (create_project/create_goal)
                            if block.name in ("create_project", "create_goal"):
                                spin_key = _normalize_spin_key(block.name, block.input.get("name", ""))
                                cross_seq_spins[spin_key] = cross_seq_spins.get(spin_key, 0) + 1
                                self.state["spin_tracker"] = cross_seq_spins
                                safe_json_write(self.state_path, self.state)
                        else:
                            if block.name == "finish_sequence":
                                pass
                            elif block.name in ("web_search", "create_project", "send_telegram",
                                                "create_goal", "modify_own_code", "create_tool",
                                                "write_file", "git_commit"):
                                self.narrator.tool_success(block.name, action_desc)
                            if block.name in ("create_project", "create_goal"):
                                spin_key = _normalize_spin_key(block.name, block.input.get("name", ""))
                                cross_seq_spins.pop(spin_key, None)
                                self.state["spin_tracker"] = cross_seq_spins

                        # Live-Notes
                        if not is_error and block.name in (
                            "write_file", "create_project", "create_tool",
                            "modify_own_code", "complete_project",
                        ):
                            self._update_live_notes(block.name, action_desc)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })

                        if block.name == "finish_sequence":
                            finished = True

                messages.append({"role": "user", "content": tool_results})

                if finished:
                    break

                # === ENFORCEMENT: Auto-Finish ===
                # Meta-Rules als Code — nicht bitten, erzwingen.
                # step = LLM-Calls (Loop-Variable), step_count = Tool-Calls.
                # Enforcement basiert auf step (LLM-Calls), nicht step_count.
                # evolution/sprint: erhoehtes Limit (30 statt 20).
                is_evo = mode.get("mode") in ("evolution", "sprint")
                enforcement_limit = 30 if is_evo else 20
                if step >= enforcement_limit and not finished:
                    m = self.seq_intel.metrics
                    self.narrator.enforcement(
                        "auto_finish", step, enforcement_limit,
                        files=m.files_written, errors=m.errors,
                    )
                    telemetry.log_enforcement(
                        rule="auto_finish", step=step,
                        reason=f"limit={enforcement_limit}, files={m.files_written}, errors={m.errors}",
                    )
                    # MetaCognition: Enforcement loggen (Lern-Feedback)
                    self.metacognition.record(
                        bottleneck=f"Enforcement: Auto-Finish bei LLM-Call {step} (Limit {enforcement_limit})",
                        strategy_change="Code-Enforcement statt Prompt — Sequenz automatisch beendet",
                        sequence=self.sequences_total + 1,
                        wasted_steps=max(0, step_count - m.files_written - m.tools_built),
                        productive_steps=m.files_written + m.tools_built,
                        key_decision="auto_finish_enforcement",
                    )
                    try:
                        finish_data = self._graceful_finish(messages, step_count)
                    except Exception as e:
                        logger.warning("Enforcement Graceful-Finish fehlgeschlagen: %s", e)
                        # Fallback: Mechanische Beendigung ohne LLM-Call
                        finish_data = {
                            "summary": f"Auto-Finish nach {step} LLM-Calls (Enforcement)",
                            "performance_rating": max(2, m.files_written * 2),
                            "bottleneck": f"Enforcement-Limit {enforcement_limit} erreicht",
                            "next_time_differently": "Frueher finish_sequence aufrufen",
                            "key_decision": "enforcement_fallback",
                        }
                    finish_data["enforcement"] = "auto_finish_step_limit"
                    self._handle_finish_sequence(finish_data)
                    finished = True
                    break

            elif response["stop_reason"] == "length":
                # Token-Limit erreicht — Output wurde abgeschnitten!
                self.narrator.token_warning(100, "truncated")
                # Abgeschnittene Assistant-Message entfernen (koennte halbes JSON enthalten)
                if messages and messages[-1].get("role") == "assistant":
                    messages.pop()
                # Saubere Warnung einfuegen damit das LLM weiss was passiert ist
                messages.append({
                    "role": "user",
                    "content": (
                        "WARNUNG: Dein letzter Output wurde abgeschnitten weil das "
                        "Token-Limit erreicht wurde. Falls du gerade eine Datei geschrieben "
                        "hast, ist der Inhalt wahrscheinlich unvollstaendig. "
                        "Lese die Datei mit read_file und pruefe/repariere sie. "
                        "Schreibe kuerzere Outputs — teile grosse Dateien in Abschnitte."
                    ),
                })

            elif response["stop_reason"] == "end_turn":
                text_parts = [b.text for b in response["content"] if hasattr(b, "text")]
                summary = " ".join(text_parts)[:500] if text_parts else "Sequenz ohne explizites Ende"
                m = self.seq_intel.metrics
                auto_rating = min(7, max(2, m.files_written * 2 + m.tools_built * 3))
                self._handle_finish_sequence({
                    "summary": summary,
                    "performance_rating": auto_rating,
                    "bottleneck": "Kein explizites finish_sequence aufgerufen — LLM hat end_turn ohne Tool-Call beendet",
                    "next_time_differently": "finish_sequence explizit aufrufen mit Reflexion statt einfach aufzuhoeren",
                    "key_decision": "Auto-beendet: end_turn ohne finish_sequence",
                })
                break

        if not finished and step_count >= step_budget:
            self.narrator.max_steps(step_budget, self.seq_intel.metrics.errors,
                                    self.seq_intel.metrics.files_written)
            finish_data = self._graceful_finish(messages, step_count)
            self._handle_finish_sequence(finish_data)

        # Emergency-Finish: API komplett ausgefallen, Schleife ohne finish_sequence beendet
        if not finished and step_count < step_budget:
            self.narrator.emergency("Sequenz ohne finish_sequence beendet")
            self._save_sequence_memory(
                f"Sequenz abgebrochen nach {step_count} Steps — API komplett ausgefallen"
            )
            self.sequences_total += 1
            self._save_all()

        # Step-History speichern
        task_type = getattr(self, "_current_task_type", "standard")
        finished_cleanly = finished
        self._record_step_history(task_type, step_count, finished_cleanly)

        # Effizienz tracken
        m = self.seq_intel.metrics
        seq_duration = time.time() - seq_start
        seq_cost = self.llm.session_costs["cost_usd"] - getattr(self, '_last_session_cost', 0)
        self._last_session_cost = self.llm.session_costs["cost_usd"]
        self.efficiency.record_sequence({
            "tool_calls": m.tool_calls,
            "errors": m.errors,
            "files_written": m.files_written,
            "tools_built": m.tools_built,
            "tokens_used": self.sequence_input_tokens + self.sequence_output_tokens,
            "cost": round(seq_cost, 4),
            "duration_seconds": round(seq_duration, 1),
        })

        # IOR-Tracking: Input-Output-Ratio messen
        try:
            self.ior.record_sequence({
                "tokens_used": self.sequence_input_tokens + self.sequence_output_tokens,
                "tool_calls": m.tool_calls,
                "files_written": m.files_written,
                "tools_built": m.tools_built,
                "goals_completed": 0,  # Spaeter: aus GoalStack zaehlen
                "skills_reused": 0,    # Spaeter: aus SkillTracker zaehlen
                "cross_transfers": 0,  # Spaeter: SemanticMemory Cross-Domain erkennen
            })
        except Exception as e:
            print(f"  [WARNUNG] IOR nicht gespeichert: {e}")

        # Evaluation: Sequenz-Daten aufzeichnen
        # Produktive Steps = files + tools (konsistent mit MetaCognition + Actuator)
        productive = m.files_written + m.tools_built
        total = max(m.step_count, 1)
        try:
            self.evaluation.record_sequence({
                "seq_num": self.sequences_total,
                "tool_calls": m.tool_calls,
                "errors": m.errors,
                "files_written": m.files_written,
                "tools_built": m.tools_built,
                "goals_completed": 0,  # TODO: aus GoalStack zaehlen
                "goals_attempted": 0,  # 0/0 → goal_completion deaktiviert bis echte Daten
                "tokens_used": self.sequence_input_tokens + self.sequence_output_tokens,
                "cost": round(seq_cost, 4),
                "productive_steps": min(productive, total),
                "wasted_steps": max(0, total - productive),
                "duration_seconds": round(seq_duration, 1),
            })

            # Checkpoint alle 10 Sequenzen (nicht bei Seq 0)
            if self.sequences_total > 0 and self.sequences_total % 10 == 0:
                checkpoint = self.evaluation.checkpoint(self.sequences_total)
                if checkpoint:
                    self.narrator.efficiency_alert(
                        f"EVAL Checkpoint: {checkpoint['score']:.0f}/100 "
                        f"({checkpoint['trend']})"
                    )

            # Alerts pruefen
            eval_alerts = self.evaluation.get_alerts()
            if eval_alerts:
                for alert in eval_alerts:
                    self.narrator.efficiency_alert(f"[EVAL] {alert}")
        except Exception as e:
            print(f"  [WARNUNG] Evaluation nicht gespeichert: {e}")

        # Efficiency-Trend-Analyse alle 5 Sequenzen
        if self.sequences_total % 5 == 0:
            eff_alerts = self.efficiency.analyze_trends()
            if eff_alerts:
                self._efficiency_alerts = eff_alerts  # Fuer naechste Perception
                for alert in eff_alerts:
                    self.narrator.efficiency_alert(alert)

        # Kompakte Zusammenfassung
        self.narrator.sequence_end(
            step_count, seq_duration, self.seq_intel.metrics.errors,
            self.seq_intel.metrics.files_written,
        )
        # Telemetry: Sequenz-Ende mit Gesamt-Metriken
        telemetry.log_sequence_end(
            steps=step_count, duration_s=seq_duration,
            errors=self.seq_intel.metrics.errors,
            files_written=self.seq_intel.metrics.files_written,
            tools_built=self.seq_intel.metrics.tools_built,
            input_tokens=self.sequence_input_tokens,
            output_tokens=self.sequence_output_tokens,
            cost_usd=seq_cost,
            finish_reason="finished" if finished else "max_steps",
            rating=0,
        )

        # Stille-Fehler nur wenn vorhanden
        silent_warnings = self.silent_failure_detector.check_after_sequence(
            self.sequences_total, self.seq_intel.metrics.tool_calls,
            files_written=self.seq_intel.metrics.files_written,
            tools_built=self.seq_intel.metrics.tools_built,
            errors=self.seq_intel.metrics.errors,
        )
        if silent_warnings:
            for w in silent_warnings:
                self.narrator.silent_warning(w)

        # Fuer Circuit-Breaker: Wert VOR Reset speichern
        self._last_seq_output_tokens = self.sequence_output_tokens
        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0
