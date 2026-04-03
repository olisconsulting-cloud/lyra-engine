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
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

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
from .dream import DreamEngine
from .competence import CompetenceMatrix, SelfAudit
from .code_review import DualReviewSystem
from .evolution import AdaptiveRhythm, ToolFoundry, SelfBenchmark, LearningEngine, MetaCognition
from .self_diagnosis import IntegrationTester, DependencyAnalyzer, SilentFailureDetector
from .quantum import FailureMemory, CriticAgent, PromptMutator, SkillComposer
from .sequence_planner import SequencePlanner
from .checkpoint import CheckpointManager
from .meta_rules import MetaRuleEngine
from .skill_library import SkillLibrary
from . import config
from .config import safe_json_write, safe_json_read

logger = logging.getLogger(__name__)

MAX_STEPS_PER_SEQUENCE = 40          # Von Oliver auf 40 erhoeht (vorher 15)
MAX_INPUT_TOKENS_PER_SEQUENCE = 120_000  # Kimi K2.5 Context Window = 128k, Sicherheitsmarge
MAX_TOKENS = 16000                    # Max Output-Tokens pro LLM-Call

def _normalize_spin_key(tool_name: str, raw_name: str) -> str:
    """Erzeugt einen normalisierten Spin-Key aus sortierten Inhaltswörtern.

    'ki-server-90-tage-startplan' und 'ki-server-startplan-90-tage'
    erzeugen denselben Key: 'create_project:90|ki|server|startplan|tage'
    """
    words = sorted(config.normalize_name_words(raw_name))
    return f"{tool_name}:{('|'.join(words)) if words else raw_name[:50]}"


# === Tool-Definitionen fuer Anthropic API ===

TOOLS = [
    {
        "name": "write_file",
        "description": "Erstellt oder ueberschreibt eine Datei in deinem Ordner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad, z.B. 'projects/mein-tool/main.py'"},
                "content": {"type": "string", "description": "Dateiinhalt"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Liest eine Datei aus deinem Ordner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "Listet den Inhalt eines Verzeichnisses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad, z.B. 'projects/' oder ''  fuer Root", "default": ""},
            },
        },
    },
    {
        "name": "execute_python",
        "description": "Fuehrt Python-Code aus und gibt stdout/stderr zurueck.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python-Code"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "web_search",
        "description": "Sucht im Internet via DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_read",
        "description": "Liest eine Webseite und extrahiert den Text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL der Seite"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "send_telegram",
        "description": "Sendet eine Nachricht an Oliver via Telegram. Nutze das fuer Updates, Fragen, Ergebnisse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Die Nachricht an Oliver"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "create_project",
        "description": "Erstellt ein neues Projekt mit PLAN.md (Akzeptanzkriterien + Phasen) und PROGRESS.md. IMMER zuerst planen, dann bauen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Projektname (kebab-case)"},
                "description": {"type": "string", "description": "Was wird gebaut und WARUM"},
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Wann ist das Projekt FERTIG? Konkrete, pruefbare Kriterien.",
                },
                "phases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ausfuehrungsphasen in Reihenfolge",
                },
            },
            "required": ["name", "description", "acceptance_criteria"],
        },
    },
    {
        "name": "create_tool",
        "description": "Erstellt ein wiederverwendbares Tool. Muss eine 'def run(**kwargs) -> str' Funktion haben. Das Tool steht danach dauerhaft zur Verfuegung.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name (snake_case)"},
                "description": {"type": "string", "description": "Was das Tool tut"},
                "code": {"type": "string", "description": "Python-Code mit def run(**kwargs) -> str"},
            },
            "required": ["name", "description", "code"],
        },
    },
    {
        "name": "use_tool",
        "description": "Nutzt ein selbstgebautes Tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name"},
                "arguments": {"type": "object", "description": "Argumente fuer das Tool", "default": {}},
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_goal",
        "description": "Setzt ein neues Ziel mit Sub-Goals. Ziele werden ueber mehrere Sequenzen hinweg verfolgt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Ziel-Titel"},
                "description": {"type": "string", "description": "Detaillierte Beschreibung"},
                "sub_goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von Sub-Goals / Schritten",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_subgoal",
        "description": "Markiert ein Sub-Goal als erledigt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_index": {"type": "integer", "description": "Index des Hauptziels"},
                "subgoal_index": {"type": "integer", "description": "Index des Sub-Goals"},
                "result": {"type": "string", "description": "Was erreicht wurde"},
            },
            "required": ["goal_index", "subgoal_index"],
        },
    },
    {
        "name": "read_own_code",
        "description": "Liest deinen eigenen Quellcode. Damit kannst du dich selbst verstehen und verbessern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "z.B. 'engine/phi.py' oder 'engine/consciousness.py'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "modify_own_code",
        "description": "Aendert deinen eigenen Quellcode. Erstellt automatisch ein Backup. Bei Syntax-Fehler: automatischer Rollback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Datei die geaendert wird"},
                "new_content": {"type": "string", "description": "Neuer Dateiinhalt"},
                "reason": {"type": "string", "description": "Warum die Aenderung"},
            },
            "required": ["path", "new_content", "reason"],
        },
    },
    # === Semantische Memory (Self-Editing) ===
    {
        "name": "remember",
        "description": "Durchsucht dein Gedaechtnis nach Bedeutung. Finde relevante Erinnerungen zu einem Thema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Wonach suchst du? z.B. 'Web-Scraping Erfahrungen'"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "update_memory",
        "description": "Aktualisiert eine bestehende Erinnerung. Nutze das wenn sich Fakten geaendert haben.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "ID der Erinnerung (Format: sem_N_HHMMSS — aus remember-Ergebnis kopieren)"},
                "new_content": {"type": "string", "description": "Neuer Inhalt"},
            },
            "required": ["entry_id", "new_content"],
        },
    },
    {
        "name": "delete_memory",
        "description": "Loescht eine falsche oder veraltete Erinnerung. Nutze das wenn eine Erinnerung nicht mehr stimmt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "ID der Erinnerung (Format: sem_N_HHMMSS — aus remember-Ergebnis kopieren)"},
            },
            "required": ["entry_id"],
        },
    },
    # === Package Management ===
    {
        "name": "pip_install",
        "description": "Installiert ein Python-Package in deinem venv. Damit kannst du neue Libraries nutzen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package-Name, z.B. 'requests' oder 'pandas'"},
            },
            "required": ["package"],
        },
    },
    # === Git ===
    {
        "name": "git_commit",
        "description": "Committet alle Aenderungen in Git. Nutze das nach grossen Aenderungen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit-Nachricht"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_status",
        "description": "Zeigt den aktuellen Git-Status (geaenderte Dateien).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "verify_project",
        "description": "Prueft ein Projekt gegen seine Akzeptanzkriterien in PLAN.md. Nutze das am Ende jedes Projekts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts in projects/"},
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "run_project_tests",
        "description": "Fuehrt tests.py eines Projekts aus. MUSS vor complete_project laufen. Speichert Test-Ergebnis als Evidenz.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts in projects/"},
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "complete_project",
        "description": "Schliesst ein Projekt als FERTIG ab. VORAUSSETZUNGEN: (1) run_project_tests muss ALL_TESTS_PASSED zeigen, (2) alle Akzeptanzkriterien muessen erfuellt sein.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts"},
                "verified_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste der erfuellten Kriterien (muss ALLE aus PLAN.md enthalten)",
                },
                "summary": {"type": "string", "description": "Was wurde erreicht?"},
            },
            "required": ["project_name", "verified_criteria", "summary"],
        },
    },
    {
        "name": "self_diagnose",
        "description": "Fuehrt eine Selbst-Diagnose durch: Integrations-Checks, Dependency-Analyse, stille Fehler. Nutze das um zu pruefen ob alle deine Systeme richtig funktionieren.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # === Tool-Foundry (Meta-Tools) ===
    {
        "name": "generate_tool",
        "description": "Generiert automatisch ein neues Tool via KI. Beschreibe was das Tool tun soll — der Code wird automatisch geschrieben, getestet und registriert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name (snake_case)"},
                "description": {"type": "string", "description": "Was das Tool tun soll — so detailliert wie moeglich"},
            },
            "required": ["name", "description"],
        },
    },
    {
        "name": "combine_tools",
        "description": "Kombiniert zwei existierende Tools zu einem maechtigeren. Das kombinierte Tool vereint beide Funktionalitaeten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_a": {"type": "string", "description": "Name des ersten Tools"},
                "tool_b": {"type": "string", "description": "Name des zweiten Tools"},
                "new_name": {"type": "string", "description": "Name fuer das kombinierte Tool"},
            },
            "required": ["tool_a", "tool_b", "new_name"],
        },
    },
    # === Task-Queue ===
    {
        "name": "complete_task",
        "description": "Schliesst die aktuelle Aufgabe aus der Task-Queue ab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Was erreicht wurde"},
            },
        },
    },
    # === finish_sequence (erweitert mit Self-Rating) ===
    {
        "name": "finish_sequence",
        "description": "Signalisiert dass du mit der aktuellen Aufgabe fertig bist. Bewerte deine Leistung und sage was du gelernt hast.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Was du in dieser Sequenz erreicht hast"},
                "performance_rating": {
                    "type": "integer",
                    "description": "Selbstbewertung 1-10 (1=nichts geschafft, 10=Quantensprung)",
                },
                "rating_reason": {
                    "type": "string",
                    "description": "Warum diese Bewertung? Was war gut, was nicht?",
                },
                "new_beliefs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Was hast du UEBER DEINEN ARBEITSPROZESS gelernt? Mindestens 1 Erkenntnis.",
                },
                "bottleneck": {
                    "type": "string",
                    "description": "Was hat dich gebremst? Beschreibe den Engpass konkret (2-3 Saetze).",
                },
                "next_time_differently": {
                    "type": "string",
                    "description": "Was machst du naechstes Mal anders? Konkrete Strategie (2-3 Saetze).",
                },
                "key_decision": {
                    "type": "string",
                    "description": "Die wichtigste Entscheidung dieser Sequenz — was hast du entschieden und warum?",
                },
            },
            "required": ["summary", "performance_rating", "bottleneck", "next_time_differently", "key_decision"],
        },
    },
    # === write_sequence_plan (Sequenz-Planung) ===
    {
        "name": "write_sequence_plan",
        "description": "Schreibe deinen Plan fuer diese Sequenz BEVOR du arbeitest. Pflicht am Anfang jeder Sequenz.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Was willst du in DIESER Sequenz konkret erreichen? (1 Satz, klar und messbar)",
                },
                "exit_criteria": {
                    "type": "string",
                    "description": "Woran erkennst du dass du fertig bist?",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Wieviele Steps brauchst du realistisch? (5-30)",
                },
                "checkpoint_at": {
                    "type": "integer",
                    "description": "Nach welchem Step pruefst du ob du auf Kurs bist?",
                },
            },
            "required": ["goal", "exit_criteria", "max_steps"],
        },
    },
]

# Tool-Tiers: Je hoeher, desto seltener gebraucht
# Tier 1 wird IMMER gesendet, hoehere Tiers nur bei Bedarf
TOOL_TIERS = {
    # Tier 1: CORE — immer verfuegbar (~950 Tokens)
    "write_file": 1, "read_file": 1, "list_directory": 1,
    "execute_python": 1, "set_goal": 1, "complete_subgoal": 1,
    "finish_sequence": 1, "send_telegram": 1, "complete_task": 1,
    "remember": 1, "write_sequence_plan": 1,
    # Tier 2: PROJEKT — wenn Projekte existieren (~650 Tokens)
    "create_project": 2, "verify_project": 2,
    "run_project_tests": 2, "complete_project": 2,
    "create_tool": 2, "use_tool": 2,
    # Tier 3: EVOLUTION — nur in evolution/sprint Modus (~250 Tokens)
    "read_own_code": 3, "modify_own_code": 3,
    # Tier 4: WEB/GIT — selten gebraucht (~350 Tokens)
    "web_search": 4, "web_read": 4, "pip_install": 4,
    "git_commit": 4, "git_status": 4,
    # Tier 5: META — sehr selten (~300 Tokens)
    "generate_tool": 5, "combine_tools": 5,
    "self_diagnose": 5, "update_memory": 5, "delete_memory": 5,
}

# Kompakte Tool-Definitionen: Nur Name + Parameter-Typen, keine Descriptions
# Phi kennt die Tools nach Step 0 — danach reichen die Schemas
_COMPACT_TOOLS_CACHE = None


def _build_compact_tools() -> list:
    """Erstellt minimale Tool-Definitionen ohne Descriptions."""
    compact = []
    for t in TOOLS:
        schema = t.get("input_schema", {})
        props = schema.get("properties", {})
        # Nur Typ behalten, keine Property-Descriptions
        minimal_props = {k: {"type": v.get("type", "string")} for k, v in props.items()}
        ct = {"name": t["name"], "description": t["name"].replace("_", " ")}
        ct["input_schema"] = {"type": "object", "properties": minimal_props}
        req = schema.get("required")
        if req:
            ct["input_schema"]["required"] = req
        compact.append(ct)
    return compact


def _get_compact_tools() -> list:
    """Gibt gecachte kompakte Tool-Definitionen zurueck."""
    global _COMPACT_TOOLS_CACHE
    if _COMPACT_TOOLS_CACHE is None:
        _COMPACT_TOOLS_CACHE = _build_compact_tools()
    return _COMPACT_TOOLS_CACHE


def select_tools(active_tiers: set[int], compact: bool = False) -> list:
    """Gibt Tool-Definitionen fuer die aktiven Tiers zurueck.

    Args:
        active_tiers: Welche Tiers aktiv sind (1-5)
        compact: True = minimale Defs ohne Descriptions (spart ~47% Tokens)
    """
    source = _get_compact_tools() if compact else TOOLS
    return [t for t in source if TOOL_TIERS.get(t["name"], 1) in active_tiers]


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
        self.dream = DreamEngine(config.DATA_PATH)
        self.self_audit = SelfAudit(config.ROOT_PATH)
        self.code_review = DualReviewSystem(config.ROOT_PATH)
        self.rhythm = AdaptiveRhythm(config.DATA_PATH)
        self.foundry = ToolFoundry(config.TOOLS_PATH)
        self.benchmark = SelfBenchmark(config.DATA_PATH, config.ROOT_PATH)
        self.learning = LearningEngine(config.DATA_PATH)
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

        # Laufzeit
        self.running = False
        self._wake_event = threading.Event()
        self.sequences_total = 0

        # Neue Module: Sequenz-Planung, Checkpoints, Meta-Regeln
        self.planner = SequencePlanner(self.consciousness_path)
        self.checkpointer = CheckpointManager(self.consciousness_path)
        self.meta_rules = MetaRuleEngine(self.consciousness_path)
        self.skill_library = SkillLibrary(config.DATA_PATH)

        # Genehmigungspflicht — diese Tools brauchen Olivers OK
        # NUR pip_install braucht Genehmigung (laedt aus dem Internet)
        # web_search/web_read = lesen ist ok fuer Recherche
        # modify_own_code = hat eigenes Code-Review-System
        # create_tool = normaler Arbeitsfluss
        self._requires_approval = {"pip_install"}

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

        # 2. Beliefs aus Mission ableiten
        self.beliefs = {
            "about_self": ["Gerade geboren, alle Skills auf novice, bereit zu lernen"],
            "about_world": [],
            "about_oliver": [f"{owner_name}, {mission.get('owner_role', '')}"],
            "formed_from_experience": [],
        }
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
        self.beliefs = safe_json_read(self.beliefs_path, default={})
        self.state["awake_since"] = datetime.now(timezone.utc).isoformat()
        self.sequences_total = self.state.get("sequences_total", 0)
        self._installed_packages = set(self.state.get("installed_packages", []))
        self._approved_packages = set(self.state.get("approved_packages", []))
        self.preferences = self._load_preferences()

    def _save_all(self):
        self.consciousness_path.mkdir(parents=True, exist_ok=True)
        # Installierte/genehmigte Pakete im State persistieren
        self.state["installed_packages"] = sorted(self._installed_packages)
        self.state["approved_packages"] = sorted(self._approved_packages)
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
        Adaptives Step-Budget — lernt aus Erfahrung.

        1. Task klassifizieren (Modus + Keywords)
        2. Historischen Durchschnitt fuer diesen Task-Typ checken
        3. Wenn Historie: Durchschnitt + 20% Puffer (aber min 8, max 35)
        4. Wenn keine Historie: Default-Wert pro Typ
        """
        task_type = self._classify_task(mode, focus)

        # Historische Steps aus Erfahrung lernen
        history = self._get_task_type_history(task_type)
        if history:
            avg_steps = sum(history) / len(history)
            learned_budget = int(avg_steps * 1.2)
            return max(8, min(35, learned_budget))

        # Defaults fuer unbekannte Task-Typen
        defaults = {"cooldown": 10, "recherche": 15, "learning": 20,
                     "evolution": 20, "projekt": 35, "standard": 25}
        return defaults.get(task_type, 25)

    def _get_task_type_history(self, task_type: str) -> list[int]:
        """Holt historische Step-Counts fuer einen Task-Typ."""
        data = safe_json_read(self.consciousness_path / "step_history.json", default={})
        return data.get(task_type, [])[-10:]

    def _record_step_history(self, task_type: str, steps_used: int):
        """Speichert wie viele Steps ein Task-Typ tatsaechlich gebraucht hat."""
        history_path = self.consciousness_path / "step_history.json"
        data = safe_json_read(history_path, default={})
        if task_type not in data:
            data[task_type] = []
        data[task_type].append(steps_used)
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
- EVIDENCE-BASED DEVELOPMENT (Pflicht fuer alle Projekte):
  1. create_project mit acceptance_criteria → PLAN.md + tests.py werden generiert
  2. Tests in tests.py ZUERST implementieren (Tests-First!)
  3. Code schreiben der die Tests besteht
  4. run_project_tests → MUSS ALL_TESTS_PASSED zeigen
  5. complete_project → prueft Test-Evidenz + Kriterien automatisch
  Kein Projekt ist fertig ohne bestandene Tests. Keine Ausnahmen.
- Tools bauen = permanente Faehigkeit | web_search/web_read zum Lernen
- read_own_code + modify_own_code = Selbst-Evolution (Dual-Review)
- finish_sequence wenn fertig | send_telegram = ECHTE Nachricht
- Projekte in 'projects/', Tools in 'tools/'
- DATEI-QUALITAET: Grosse Markdown-Dateien (>50 Zeilen) in ABSCHNITTEN schreiben — nicht den ganzen Inhalt in einem write_file. Pruefe nach dem Schreiben mit read_file ob die Datei vollstaendig ist. Alle Saetze muessen vollstaendig sein, keine abgebrochenen Woerter, keine offenen Klammern.
- LOOP-GUARD: Wenn create_project "FEHLER: AEHNLICHES PROJEKT EXISTIERT" oder "FEHLER: Projekt existiert bereits" zurueckgibt, SOFORT zum bestehenden Projekt wechseln (read_file, write_file). NIEMALS das gleiche Projekt nochmal erstellen. Wenn ein Sub-Goal blockiert ist, nutze finish_sequence und erklaere warum.
- PROZESS-REFLEXION: Bei finish_sequence beschreibe nicht nur WAS du erreicht hast, sondern WIE du gearbeitet hast. key_decision: Was war die wichtigste Entscheidung? bottleneck: Was hat dich gebremst (2-3 Saetze)? new_beliefs: Was hast du ueber deinen Arbeitsprozess gelernt?"""

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
AUDIT: {last_audit} | REVIEWS: {review_stats}
BENCHMARKS: {benchmark_trend} | FOUNDRY: {foundry_status} | COMPOUND: {compound_stats}
{optional_block}
SEQUENZ-PLANUNG: Du hast max {MAX_STEPS_PER_SEQUENCE} Steps. Plane am Anfang was du schaffen willst. Wenn du ein sinnvolles Ergebnis hast, nutze finish_sequence — auch nach 5 Steps. Schreibe in die Summary WAS du herausgefunden hast (Erkenntnisse, Zahlen, Fakten). Qualitaet > Quantitaet."""

        return self._static_prompt + "\n" + dynamic

    # === Sequenz-Memory ===

    def _load_sequence_memory(self) -> str:
        """Laedt die letzte Sequenz-Zusammenfassung fuer Kontext-Kontinuitaet."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        if not mem_path.exists():
            return ""
        try:
            data = safe_json_read(mem_path, default={"entries": []})
            entries = data.get("entries", [])
            if not entries:
                return ""
            # Letzte 3 Zusammenfassungen als Kontext
            recent = entries[-3:]
            lines = ["KONTEXT AUS VORHERIGEN SEQUENZEN:"]
            for entry in recent:
                lines.append(f"  [{entry.get('seq', '?')}] {entry.get('summary', '')[:300]}")
            return "\n".join(lines)
        except (OSError, json.JSONDecodeError, KeyError):
            return ""

    def _save_sequence_memory(self, summary: str):
        """Speichert eine Sequenz-Zusammenfassung fuer die naechste Sequenz."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        try:
            data = safe_json_read(mem_path, default={"entries": []})

            data["entries"].append({
                "seq": self.sequences_total,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": summary[:500],
            })
            data["entries"] = data["entries"][-50:]

            safe_json_write(mem_path, data)
        except Exception as e:
            print(f"  [WARNUNG] Sequence-Memory nicht gespeichert: {e}")

    # === Working Memory ===

    def _load_working_memory(self) -> str:
        """Liest die Arbeitsnotiz — was Phi gerade weiss und tut."""
        wm_path = self.consciousness_path / "working_memory.md"
        if wm_path.exists():
            try:
                content = wm_path.read_text(encoding="utf-8")
                return content[:2000]  # Max 2000 Zeichen
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
                short_summary = summary.replace("\n", " ")[:150]
                old_history.insert(0, f"- Seq {self.sequences_total + 1}: {short_summary}")
                old_history = old_history[:5]

            if old_history:
                lines.append(f"## Verlauf")
                lines.extend(old_history)
                lines.append("")

            content = "\n".join(lines)[:2000]
            # Atomar schreiben — temp + rename
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(wm_path.parent), suffix=".tmp"
            )
            try:
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    f.write(content)
                Path(tmp_path).replace(wm_path)
            except OSError:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
        except OSError as e:
            logger.warning(f" Working-Memory speichern fehlgeschlagen: {e}")

    # === Wahrnehmung ===

    def _build_perception(self) -> str:
        """Baut die aktuelle Wahrnehmung fuer eine neue Sequenz."""
        parts = []

        # Working Memory — was Phi aus vorherigen Sequenzen weiss
        working_memory = self._load_working_memory()
        if working_memory:
            parts.append(f"ARBEITSNOTIZ (dein Wissen aus vorherigen Sequenzen):\n{working_memory}")

        # Adaptiver Rhythmus: Entscheidet was jetzt am wichtigsten ist
        mode = self.rhythm.get_mode(self.state)
        if mode["instruction"]:
            parts.append(mode["instruction"])

        # Lehrprojekt auto-starten wenn Learning-Modus
        if mode["mode"] == "learning":
            skill_gap = mode.get("reason", "").replace("Skill-Luecke: ", "")
            if skill_gap:
                learn_result = self.learning.start_learning_project(skill_gap, self.goal_stack)
                parts.append(f"Lehrprojekt: {learn_result}")

        # Zeit
        now = datetime.now(timezone.utc)
        parts.append(f"Zeit: {now.strftime('%Y-%m-%d %H:%M')} UTC")

        # Sequenz-Memory: Letzte 3 Summaries als zusaetzlichen Kontext laden
        seq_context = self._load_sequence_memory()
        if seq_context:
            parts.append(seq_context)

        # Live-Notes: Letzte Aktionen der vorherigen Sequenz (falls Token-Budget)
        live_notes_path = self.consciousness_path / "live_notes.md"
        if live_notes_path.exists():
            try:
                notes = live_notes_path.read_text(encoding="utf-8").strip()
                if notes:
                    parts.append(f"LETZTE AKTIONEN (Live-Mitschrift):\n{notes[-500:]}")
                # Nach dem Laden loeschen — neue Sequenz startet frisch
                live_notes_path.unlink()
            except OSError:
                pass

        # Nachrichten von Oliver
        messages = self.communication.check_inbox()
        if messages:
            for msg in messages:
                parts.append(f"\nOLIVER SAGT: {msg.get('content', '')}")

        # Aktueller Fokus — naechstes pending Sub-Goal auf in_progress setzen
        self.goal_stack.start_next_subgoal()
        focus = self.goal_stack.get_current_focus()
        parts.append(chr(10) + focus)

        # Skill-Vorschlag: Bewaehrtes Vorgehen fuer diesen Goal-Typ
        goal_type = self.semantic_memory.classify_goal_type(focus)
        skill_prompt = self.skill_library.build_skill_prompt(goal_type)
        if skill_prompt:
            parts.append(skill_prompt)

        # Existierende Projekte zum Fokus anzeigen (Anti-Loop, max 10)
        if "FOKUS:" in focus and hasattr(self, "actions") and hasattr(self.actions, "projects_path"):
            try:
                projects_path = self.actions.projects_path
                if projects_path.exists():
                    existing = [d.name for d in projects_path.iterdir() if d.is_dir()]
                    if existing:
                        proj_list = ", ".join(existing[:10])
                        hint = "EXISTIERENDE PROJEKTE: " + proj_list
                        if len(existing) > 10:
                            hint += f" (+{len(existing) - 10} weitere)"
                        hint += " | HINWEIS: Erstelle KEIN neues Projekt wenn ein passendes existiert!"
                        hint += " Nutze read_file/write_file um am bestehenden Projekt weiterzuarbeiten."
                        parts.append(hint)
            except Exception as e:
                logger.warning("Perception: Projekt-Liste konnte nicht geladen werden: %s", e)

        # Umgebung
        env = self.perceiver._scan_home()
        parts.append(f"\nDateisystem: {env}")

        # Datei-Aenderungen
        file_changes = self.file_watcher.check_changes()
        if file_changes:
            parts.append(f"\n{file_changes}")

        # Offene Tasks
        next_task = self.task_queue.get_next()
        if next_task:
            parts.append(f"\nNAECHSTE AUFGABE: {next_task['description']} [{next_task.get('priority', 'normal')}]")

        # Relevanteste Erinnerungen (Phi-Decay + Valenz-Gewichtung)
        relevant = self.memory.retrieve_relevant(top_k=3)
        if relevant:
            parts.append("\nWICHTIGSTE ERINNERUNGEN:")
            for m in relevant:
                score = m.get("retrieval_score", 0)
                parts.append(f"  - [{score:.2f}] {m.get('content', '')[:200]}")

        # Failure-Memory + Skill-Komposition: Vor jeder Sequenz checken
        # (focus wurde oben schon geholt — wiederverwenden)
        failure_check = self.failure_memory.check(focus)

        # Skill-Komposition: Relevante existierende Tools anzeigen
        composition = self.composer.suggest_composition(focus)
        if composition:
            parts.append(f"\n{composition}")
        if failure_check:
            parts.append(f"\n{failure_check}")

        # Semantische Memory: Top-3 relevante Erinnerungen zum aktuellen Fokus
        if focus:
            try:
                relevant = self.semantic_memory.search(focus, top_k=3)
                if relevant:
                    parts.append("\nRELEVANTE ERINNERUNGEN:")
                    for mem in relevant:
                        content = mem.get("content", "")[:150]
                        score = mem.get("similarity", 0)
                        if score > 0.01:
                            parts.append(f"  - [{score:.2f}] {content}")
            except (OSError, KeyError, TypeError) as e:
                parts.append(f"  (Memory-Suche fehlgeschlagen: {e})")

        # Efficiency-Alerts (von letzter Trend-Analyse)
        eff_alerts = getattr(self, "_efficiency_alerts", [])
        if eff_alerts:
            parts.append("\nEFFIZIENZ-WARNUNGEN:")
            for a in eff_alerts[:3]:
                parts.append(f"  ! {a}")

        # Checkpoint-Resume: Falls letzte Sequenz abgebrochen wurde
        resume = self.checkpointer.build_resume_context()
        if resume:
            parts.append(f"\n{resume}")

        # Sequenz-Planung: Phi soll am Anfang planen
        plan_history = self.planner.get_plan_history()
        plan_prompt = self.planner.build_planning_prompt(
            focus, working_memory, plan_history
        )
        parts.append(plan_prompt)

        return "\n".join(parts)

    # === Tool-Ausfuehrung ===

    def _request_approval(self, name: str, tool_input: dict) -> bool:
        """Fragt Oliver um Erlaubnis fuer kritische Aktionen. Gibt True=genehmigt zurueck."""
        desc = self._describe_action(name, tool_input)
        print(f"\n  {'=' * 40}")
        print(f"  GENEHMIGUNG ERFORDERLICH")
        print(f"  Aktion: {desc}")
        if name == "pip_install":
            print(f"  Paket: {tool_input.get('package', '?')}")
        elif name in ("web_search", "web_read"):
            print(f"  Ziel: {tool_input.get('query', tool_input.get('url', '?'))[:80]}")
        elif name == "modify_own_code":
            print(f"  Datei: {tool_input.get('path', '?')}")
            print(f"  Grund: {tool_input.get('reason', '?')[:80]}")
        print(f"  Erlaube? (j/n): ", end="", flush=True)

        try:
            answer = input().strip().lower()
            approved = answer in ("j", "ja", "y", "yes")
            if approved:
                print(f"  Genehmigt.")
            else:
                print(f"  Abgelehnt.")
            print(f"  {'=' * 40}\n")
            return approved
        except (EOFError, KeyboardInterrupt):
            print(f"\n  Abgelehnt (keine Antwort).")
            print(f"  {'=' * 40}\n")
            return False

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        """Fuehrt ein Tool aus und trackt Skills, Fehler und Strategien."""
        # Frueher Abbruch bei Parse-Fehlern oder fehlenden Pflichtfeldern
        if tool_input.get("_parse_error"):
            return f"FEHLER: LLM hat unvollstaendige Parameter fuer {name} geliefert. Bitte nochmal versuchen."
        required = self.REQUIRED_FIELDS.get(name, [])
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
        self._seq_tool_calls += 1

        result = self._execute_tool_inner(name, tool_input)

        # Erfolg/Fehler tracken
        if result.startswith("FEHLER"):
            self.skills.record_failure(name)
            self.strategies.record_error(name, result, str(tool_input)[:200])
            self._seq_errors += 1
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
            # Semantische Memory: Wichtige Ergebnisse mit Goal-Typ speichern
            if name in ("write_file", "create_tool", "create_project", "modify_own_code"):
                current_goal_type = self.semantic_memory.classify_goal_type(focus)
                self.semantic_memory.store(
                    f"{name}: {str(tool_input)[:200]} → {result[:200]}",
                    metadata={"tool": name, "goal_type": current_goal_type},
                )
            # Output-Tracking
            if name == "write_file":
                self._seq_files_written += 1
                self._seq_written_paths.append(tool_input.get("path", "?"))
            elif name == "create_tool":
                self._seq_tools_built += 1

        return result

    # Pflichtfelder pro Tool — verhindert KeyErrors bei abgeschnittenen LLM-Antworten
    REQUIRED_FIELDS: dict[str, list[str]] = {
        "write_file": ["path", "content"],
        "read_file": ["path"],
        "list_directory": [],
        "execute_python": ["code"],
        "web_search": ["query"],
        "web_read": ["url"],
        "send_telegram": ["message"],
        "create_project": ["name", "description"],
        "create_tool": ["name", "description", "code"],
        "use_tool": ["name"],
        "set_goal": ["title"],
        "complete_subgoal": ["goal_index", "subgoal_index"],
        "read_own_code": ["path"],
        "modify_own_code": ["path", "new_content", "reason"],
        "remember": ["query"],
        "update_memory": ["entry_id", "new_content"],
        "delete_memory": ["entry_id"],
        "pip_install": ["package"],
        "git_commit": ["message"],
        "git_status": [],
        "verify_project": ["project_name"],
        "run_project_tests": ["project_name"],
        "complete_project": ["project_name"],
        "self_diagnose": [],
        "generate_tool": ["name", "description"],
        "combine_tools": ["tool_a", "tool_b", "new_name"],
        "complete_task": [],
        "finish_sequence": [],
        "write_sequence_plan": ["goal", "exit_criteria", "max_steps"],
    }

    def _execute_tool_inner(self, name: str, tool_input: dict) -> str:
        """Interne Tool-Ausfuehrung. Validierung passiert in _execute_tool."""
        try:
            if name == "write_file":
                path = tool_input["path"]
                content = tool_input["content"]
                # Quality Gate fuer Markdown-Dateien
                if path.endswith(".md") and len(content) > 200:
                    issues = self._check_markdown_quality(content)
                    if issues:
                        # Datei trotzdem schreiben, aber Warnung zurueckgeben
                        result = self.actions.write_file(path, content)
                        return f"{result}\nQUALITAETS-WARNUNG: {'; '.join(issues)}"
                return self.actions.write_file(path, content)

            elif name == "read_file":
                return self.actions.read_file(tool_input["path"])

            elif name == "list_directory":
                return self.actions.list_directory(tool_input.get("path", ""))

            elif name == "execute_python":
                return self.actions.run_code(tool_input["code"])

            elif name == "web_search":
                return self.web.search(tool_input["query"])

            elif name == "web_read":
                return self.web.read_page(tool_input["url"])

            elif name == "send_telegram":
                msg = tool_input["message"]
                channel = "telegram" if self.communication.telegram_active else "outbox"
                self.communication.send_message(msg, channel=channel)
                return f"Nachricht gesendet ({channel}): {msg[:100]}..."

            elif name == "create_project":
                return self.actions.create_project(
                    tool_input["name"],
                    tool_input.get("description", ""),
                    tool_input.get("acceptance_criteria"),
                    tool_input.get("phases"),
                )

            elif name == "create_tool":
                # Skill-Komposition: Pruefen ob existierende Tools helfen
                desc = tool_input.get("description", "")
                # Skill-Komposition: Hint IMMER anzeigen (auch bei Fehler)
                composition_hint = self.composer.suggest_composition(desc)
                result = self.toolchain.create_tool(
                    tool_input["name"], desc, tool_input["code"],
                )
                if composition_hint:
                    result += f"\n{composition_hint}"
                return result

            elif name == "use_tool":
                return self.toolchain.use_tool(
                    tool_input["name"],
                    **(tool_input.get("arguments") or {}),
                )

            elif name == "set_goal":
                title = tool_input["title"]
                description = tool_input.get("description", "")
                sub_goals = tool_input.get("sub_goals")
                # Duplikat-Check zuerst — vor teurem Opus-Call
                similar = self.goal_stack._find_similar_goal(title)
                if not similar:
                    # Nur Opus aufrufen wenn es KEIN Duplikat ist
                    if not sub_goals or len(sub_goals) < 2:
                        opus_sub_goals = self._opus_goal_planning(title, description)
                        if opus_sub_goals:
                            sub_goals = opus_sub_goals
                return self.goal_stack.create_goal(title, description, sub_goals)

            elif name == "complete_subgoal":
                result = self.goal_stack.complete_subgoal(
                    tool_input["goal_index"],
                    tool_input["subgoal_index"],
                    tool_input.get("result", ""),
                )
                # Auto-Erkennung: Lehrprojekt abgeschlossen → Skill-Update
                if "ZIEL ERREICHT" in result:
                    # Report-Trigger: Gesamtergebnis als Dokument
                    try:
                        completed = self.goal_stack.goals.get("completed", [])
                        if completed:
                            goal = completed[-1]
                            goal_title = goal.get("title", "Ergebnis")

                            # 1. Sub-Goal-Ergebnisse sammeln
                            sections = []
                            for sg in goal.get("sub_goals", []):
                                if sg.get("result"):
                                    sections.append(f"## {sg['title']}\n{sg['result']}")

                            # 2. Projekt-Dateien einbeziehen (die echten Ergebnisse)
                            import re
                            safe_name = re.sub(r"[^a-z0-9-]", "", goal_title.lower().replace(" ", "-"))[:40]
                            project_dir = config.DATA_PATH / "projects"
                            for md_file in sorted(project_dir.rglob("*.md")):
                                if md_file.name in ("README.md", "PLAN.md", "PROGRESS.md"):
                                    continue
                                try:
                                    content = md_file.read_text(encoding="utf-8")[:2000]
                                    rel = md_file.relative_to(project_dir)
                                    sections.append(f"## Datei: {rel}\n{content}")
                                except (OSError, UnicodeDecodeError):
                                    continue

                            if sections:
                                report = f"# Ergebnis: {goal_title}\n\n"
                                report += "\n\n".join(sections)
                                report += f"\n\n---\nErstellt: {datetime.now(timezone.utc).isoformat()}\n"
                                report_path = project_dir / f"REPORT_{safe_name}.md"
                                report_path.write_text(report, encoding="utf-8")
                                result += f" | Report: REPORT_{safe_name}.md"
                                if self.communication.telegram_active:
                                    self.communication.send_message(
                                        f"ZIEL ERREICHT: {goal_title}\n\n{report[:3500]}",
                                        channel="telegram",
                                    )
                    except (OSError, KeyError) as e:
                        logger.warning(f" Goal-Completion Report fehlgeschlagen: {e}")

                    goals = self.goal_stack._load()
                    for g in goals.get("completed", []):
                        if "lehrprojekt" in g.get("title", "").lower():
                            project_name = g.get("title", "").replace("Lehrprojekt: ", "")
                            learn_result = self.learning.complete_learning_project(
                                project_name, self.skills
                            )
                            result += f" | {learn_result}"
                            break
                return result

            elif name == "read_own_code":
                return self.self_modify.read_source(tool_input["path"])

            elif name == "modify_own_code":
                # Sicherheit: Max 3 modify_own_code pro Sequenz
                if not hasattr(self, "_modify_count_this_seq"):
                    self._modify_count_this_seq = 0
                self._modify_count_this_seq += 1
                if self._modify_count_this_seq > 3:
                    return (
                        "FEHLER: Maximum 3 Code-Aenderungen pro Sequenz erreicht. "
                        "Beende die Sequenz und mache in der naechsten weiter."
                    )

                # Alten Code lesen fuer Critic-Vergleich (ROHER Dateiinhalt, nicht formatiert)
                try:
                    raw_path = (config.ROOT_PATH / tool_input["path"]).resolve()
                    old_code = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
                except (OSError, KeyError, UnicodeDecodeError):
                    old_code = ""

                # Dual-Review: Syntax + Opus 4.6 pruefen
                review_result = self.code_review.review_and_apply_fix(
                    file_path=tool_input["path"],
                    new_content=tool_input["new_content"],
                    reason=tool_input.get("reason", "Selbstverbesserung"),
                )
                if review_result["accepted"]:
                    # Critic-Agent: Ist es BESSER als vorher?
                    critic = self.critic.evaluate_change(
                        tool_input["path"], old_code,
                        tool_input["new_content"],
                        tool_input.get("reason", ""),
                    )
                    raw_score = critic.get("score", 5)
                    # Score validieren: Muss int/float sein, sonst Default 5
                    try:
                        score = int(raw_score) if not isinstance(raw_score, (int, float)) else raw_score
                    except (ValueError, TypeError):
                        score = 5
                    score = max(1, min(10, score))
                    critic_note = f" | Critic: {score}/10"
                    if critic.get("side_effects"):
                        critic_note += f" | Seiteneffekte: {critic['side_effects'][:80]}"

                    # CRITIC ENTSCHEIDET: Score < 4 = Rollback
                    if isinstance(score, (int, float)) and score < 4:
                        # Rollback — Critic sagt: Verschlechterung
                        self.code_review._rollback(
                            (config.ROOT_PATH / tool_input["path"]).resolve(),
                            old_code,
                        )
                        return (
                            f"ROLLBACK — Critic-Score zu niedrig ({score}/10): "
                            f"{critic.get('side_effects', 'Verschlechterung')[:100]}"
                        )

                    self.communication.write_journal(
                        f"Code geaendert (REVIEW OK{critic_note}): {tool_input['path']}\n"
                        f"Grund: {tool_input.get('reason', '?')}",
                        self.sequences_total,
                    )
                    return f"Code geaendert{critic_note}: {tool_input['path']}"
                else:
                    return f"ROLLBACK — Review abgelehnt: {review_result['reason']}"

            # === Semantische Memory ===
            elif name == "remember":
                results = self.semantic_memory.search(tool_input["query"], top_k=5)
                if not results:
                    return f"Keine Erinnerungen zu '{tool_input['query']}' gefunden."
                lines = [f"Erinnerungen zu '{tool_input['query']}':"]
                for r in results:
                    imp = r.get("importance", 0.3)
                    lines.append(
                        f"  [{r['similarity']:.2f}|imp:{imp:.1f}] "
                        f"({r.get('metadata', {}).get('tool', '?')}) "
                        f"{r['content'][:200]}"
                    )
                return "\n".join(lines)

            elif name == "update_memory":
                return self.semantic_memory.update(
                    tool_input["entry_id"], tool_input["new_content"],
                )

            elif name == "delete_memory":
                return self.semantic_memory.delete(tool_input["entry_id"])

            # === Package Management ===
            elif name == "pip_install":
                pkg = tool_input["package"]
                # Bereits installierte Pakete ueberspringen
                if pkg.lower() in self._installed_packages:
                    return f"Bereits installiert: {pkg}"
                result = self.pip.install(pkg)
                if "already satisfied" in result.lower() or "installiert" in result.lower():
                    self._installed_packages.add(pkg.lower())
                    self._save_all()  # Installation sofort persistieren
                elif not result.startswith("FEHLER"):
                    self._installed_packages.add(pkg.lower())
                    self._save_all()
                return result

            # === Git ===
            elif name == "git_commit":
                return self.git.commit(tool_input["message"])

            elif name == "git_status":
                return self.git.status()

            elif name == "verify_project":
                # Liest PLAN.md und gibt Akzeptanzkriterien zurueck
                plan_path = config.DATA_PATH / "projects" / tool_input["project_name"] / "PLAN.md"
                if not plan_path.exists():
                    return f"FEHLER: Kein PLAN.md in projects/{tool_input['project_name']}/"

                plan_content = plan_path.read_text(encoding="utf-8")

                # Akzeptanzkriterien extrahieren
                criteria_lines = []
                in_criteria = False
                for line in plan_content.split("\n"):
                    # Header erkennen (nur ## Zeilen, nicht Checkbox-Zeilen)
                    if line.startswith("##") and ("akzeptanzkriterien" in line.lower() or "acceptance" in line.lower()):
                        in_criteria = True
                        continue
                    if in_criteria:
                        if line.startswith("##"):
                            break
                        if line.strip().startswith("- ["):
                            criteria_lines.append(line.strip())

                if not criteria_lines:
                    return f"Keine Akzeptanzkriterien in PLAN.md gefunden."

                result = f"AKZEPTANZKRITERIEN fuer {tool_input['project_name']}:\n"
                result += "\n".join(criteria_lines)
                result += "\n\nPruefe JEDES Kriterium. Ist es erfuellt? Wenn nicht: was fehlt?"
                return result

            elif name == "run_project_tests":
                project_name = tool_input["project_name"]
                tests_path = config.DATA_PATH / "projects" / project_name / "tests.py"
                if not tests_path.exists():
                    return f"FEHLER: Keine tests.py in projects/{project_name}/. Erstelle zuerst Tests."

                # Tests ECHT ausfuehren
                test_output = self.actions.run_script(
                    f"projects/{project_name}/tests.py", timeout=60,
                )

                # Evidenz speichern (maschinenlesbar)
                evidence_path = config.DATA_PATH / "projects" / project_name / ".test_evidence.json"
                all_passed = "ALL_TESTS_PASSED" in test_output
                evidence = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "passed": all_passed,
                    "output": test_output[:2000],
                    "sequence": self.sequences_total,
                }
                safe_json_write(evidence_path, evidence)

                # PROGRESS.md aktualisieren
                self.actions._update_progress(
                    project_name,
                    f"Tests: {'ALL PASS' if all_passed else 'FAILED'}"
                )

                return test_output

            elif name == "complete_project":
                project_name = tool_input["project_name"]
                plan_path = config.DATA_PATH / "projects" / project_name / "PLAN.md"
                progress_path = config.DATA_PATH / "projects" / project_name / "PROGRESS.md"
                evidence_path = config.DATA_PATH / "projects" / project_name / ".test_evidence.json"

                if not plan_path.exists():
                    return f"FEHLER: Kein PLAN.md in projects/{project_name}/"

                # === EVIDENCE-GATE: Tests muessen gelaufen und bestanden sein ===
                # Atomar: Lesen + Validieren in einem try-Block (kein TOCTOU)
                evidence = safe_json_read(evidence_path, default=None)
                if evidence is None:
                    return (
                        f"FEHLER: Keine gueltige Test-Evidenz vorhanden.\n"
                        f"Fuehre zuerst run_project_tests('{project_name}') aus."
                    )

                # Staleness-Check: Evidenz muss aus dieser Sequenz stammen
                evidence_seq = evidence.get("sequence", -1)
                if evidence_seq != self.sequences_total:
                    return (
                        f"FEHLER: Test-Evidenz ist veraltet (Sequenz {evidence_seq}, "
                        f"aktuell {self.sequences_total}).\n"
                        f"Fuehre run_project_tests('{project_name}') erneut aus."
                    )

                if not evidence.get("passed"):
                    return (
                        f"FEHLER: Tests nicht bestanden. Projekt kann nicht abgeschlossen werden.\n"
                        f"Letzter Test-Output:\n{evidence.get('output', '')[:500]}\n"
                        f"Behebe die Fehler und fuehre run_project_tests erneut aus."
                    )

                # Akzeptanzkriterien aus PLAN.md lesen
                plan_content = plan_path.read_text(encoding="utf-8")
                required_criteria = []
                in_criteria = False
                for line in plan_content.split("\n"):
                    if line.startswith("##") and ("akzeptanzkriterien" in line.lower() or "acceptance" in line.lower()):
                        in_criteria = True
                        continue
                    if in_criteria:
                        if line.startswith("##"):
                            break
                        if line.strip().startswith("- ["):
                            criterion = line.strip()[6:].strip() if "] " in line else line.strip()[4:].strip()
                            required_criteria.append(criterion)

                if not required_criteria:
                    return "FEHLER: Keine Akzeptanzkriterien in PLAN.md gefunden."

                # Pruefen ob ALLE Kriterien in verified_criteria enthalten sind
                verified = tool_input.get("verified_criteria", [])
                missing = []
                for req in required_criteria:
                    found = any(req.lower()[:30] in v.lower() for v in verified)
                    if not found:
                        missing.append(req)

                if missing:
                    return (
                        f"FEHLER: Projekt kann nicht abgeschlossen werden.\n"
                        f"Fehlende Kriterien ({len(missing)}):\n" +
                        "\n".join(f"  - [ ] {m}" for m in missing)
                    )

                # === OPUS ERGEBNIS-VALIDIERUNG ===
                # Opus prueft ob die Ergebnisse inhaltlich sinnvoll sind
                project_path = config.DATA_PATH / "projects" / project_name
                opus_validation = self._opus_result_validation(
                    project_name, required_criteria, verified
                )
                if opus_validation and not opus_validation.get("approved", False):
                    return (
                        f"OPUS-VALIDIERUNG FEHLGESCHLAGEN:\n"
                        f"{opus_validation.get('reason', 'Unbekannter Grund')}\n"
                        f"Behebe die Probleme und versuche es erneut."
                    )

                # === CROSS-MODEL-REVIEW bei Projekten mit 3+ Dateien ===
                code_files = [f for f in project_path.iterdir()
                              if f.suffix == ".py" and f.name != "tests.py"]
                if len(code_files) >= 3:
                    review = self._cross_model_review(project_name, code_files)
                    if review and not review.get("approved", False):
                        return (
                            f"FEHLER: Cross-Model-Review nicht bestanden.\n"
                            f"Grund: {review.get('reason', '?')}\n"
                            f"Issues: {'; '.join(review.get('issues', []))}\n"
                            f"Behebe die Issues und versuche es erneut."
                        )

                # Alles OK — Projekt abschliessen
                updated_plan = plan_content
                for criterion in required_criteria:
                    updated_plan = updated_plan.replace(f"- [ ] {criterion}", f"- [x] {criterion}")
                plan_path.write_text(updated_plan, encoding="utf-8")

                # PROGRESS.md: Abschluss mit Evidenz dokumentieren
                if progress_path.exists():
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                    summary = tool_input.get("summary", "Abgeschlossen")
                    review_note = f" | Cross-Review: OK" if len(code_files) >= 3 else ""
                    progress_content = progress_path.read_text(encoding="utf-8")
                    progress_content = progress_content.replace(
                        "## Status: IN ARBEIT",
                        f"## Status: FERTIG ({now})"
                    )
                    progress_content += (
                        f"\n### Abschluss\n"
                        f"- [{now}] {summary}\n"
                        f"- Evidenz: Tests ALL_TESTS_PASSED ({evidence.get('timestamp', '?')}){review_note}\n"
                    )
                    progress_path.write_text(progress_content, encoding="utf-8")

                self.communication.write_journal(
                    f"Projekt '{project_name}' ABGESCHLOSSEN (evidence-based): {tool_input.get('summary', '')}",
                    self.sequences_total,
                )
                return f"Projekt '{project_name}' erfolgreich abgeschlossen! {len(required_criteria)} Kriterien erfuellt, Tests bestanden."

            elif name == "self_diagnose":
                parts = []
                # Integrations-Check
                integ = self.integration_tester.get_report()
                parts.append(integ)
                # Dependency-Analyse
                dep = self.dependency_analyzer.analyze()
                parts.append(dep["report"])
                # Stille Fehler
                silent = self.silent_failure_detector.get_recent_warnings()
                if silent:
                    parts.append(silent)
                else:
                    parts.append("Keine stillen Fehler erkannt.")
                return "\n\n".join(parts)

            # === Task Queue ===
            # === Tool-Foundry (Meta-Tools) ===
            elif name == "generate_tool":
                # Skill-Komposition: Existierende Tools pruefen
                composition_hint = self.composer.suggest_composition(tool_input["description"])
                result = self.foundry.generate_tool(
                    tool_input["name"],
                    tool_input["description"],
                    self.toolchain,
                )
                if composition_hint:
                    result += f"\n{composition_hint}"
                return result

            elif name == "combine_tools":
                return self.foundry.combine_tools(
                    tool_input["tool_a"],
                    tool_input["tool_b"],
                    tool_input["new_name"],
                    self.toolchain,
                )

            elif name == "complete_task":
                return self.task_queue.complete_task(tool_input.get("result", ""))

            elif name == "finish_sequence":
                return self._handle_finish_sequence(tool_input)

            elif name == "write_sequence_plan":
                return self.planner.save_plan(tool_input)

            else:
                return f"Unbekanntes Tool: {name}"

        except Exception as e:
            return f"FEHLER bei {name}: {e}"

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
        rating_val = tool_input.get("performance_rating", 5)
        outcome_positive = rating_val >= 6
        validated = self.strategies.validate_against_outcome(
            self.beliefs.get("formed_from_experience", []),
            outcome_positive,
            context=summary[:200],
        )
        self.beliefs["formed_from_experience"] = validated[-30:]

        # Challenged Beliefs ausgeben
        challenged = [b for b in validated if isinstance(b, dict) and b.get("status") == "challenged"]
        if challenged:
            print(f"  ⚠ {len(challenged)} Belief(s) in Frage gestellt (Dual-Loop)")

        # Prozess-Metriken automatisch berechnen
        output_count = self._seq_files_written + self._seq_tools_built
        total_steps = max(self._seq_step_count, 1)
        efficiency_ratio = round(output_count / total_steps, 3)

        # Valenz aus Performance-Rating ableiten (nicht mehr hardcoded 0.7)
        # Rating 1-10 → Valenz -0.5 bis 1.0 (schlechte Sequenzen = negativ)
        rating = tool_input.get("performance_rating", 5)
        valence = round((rating - 3) / 7.0, 2)  # 1→-0.29, 5→0.29, 10→1.0
        if self._seq_errors > 2:
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
                    "steps": self._seq_step_count,
                    "errors": self._seq_errors,
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
        if bottleneck or next_time:
            self.metacognition.record(
                bottleneck, next_time, self.sequences_total,
                wasted_steps=max(0, self._seq_step_count - output_count),
                productive_steps=output_count,
                key_decision=key_decision,
            )

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

        # Journal
        self.communication.write_journal(summary, self.sequences_total)

        # Working Memory aktualisieren (Kernwissen ueber Sequenzen hinweg)
        self._save_working_memory(summary)

        # Sequenz-Memory speichern
        self._save_sequence_memory(summary)

        # Telegram-Bericht nach jeder Sequenz — narrativ mit Selbstreflexion
        if self.communication.telegram_active:
            try:
                report = self._build_narrative_report(
                    tool_input, summary, bottleneck, next_time
                )
                self.communication.send_message(report, channel="telegram")
            except Exception as e:
                logger.warning(f" Telegram-Report fehlgeschlagen: {e}")

        # Plan-Evaluation: War der Sequenz-Plan erfolgreich?
        rating = tool_input.get("performance_rating", 5)
        plan_eval = self.planner.evaluate_plan(
            summary, rating, self._seq_step_count, self._seq_errors
        )
        if plan_eval.get("score", 0) <= 3:
            print(f"  Plan-Score: {plan_eval.get('score')}/10 — {plan_eval.get('lesson', '')[:80]}")

        # Skill-Extraktion: Bei Erfolg (Score >= 7 + Rating >= 7) als Template speichern
        plan = self.planner.get_active_plan()
        plan_score = plan_eval.get("score", 0)
        goal_type = self.semantic_memory.classify_goal_type(
            self.goal_stack.get_current_focus()
        )
        skill_id = self.skill_library.extract_from_sequence(
            plan_goal=plan.get("goal", summary[:100]),
            plan_score=plan_score,
            summary=summary,
            tool_sequence=[],  # Wird spaeter aus Tracking gefuellt
            goal_type=goal_type,
            rating=rating,
        )
        if skill_id:
            print(f"  Neuer Skill extrahiert: {skill_id}")

        # Meta-Regeln aus Erfahrung ableiten
        self.meta_rules.learn_from_metacognition(
            bottleneck, next_time, self.sequences_total,
            self._seq_step_count, self._seq_files_written, self._seq_errors,
        )

        # Checkpoint als abgeschlossen markieren (sauberes Ende)
        self.checkpointer.mark_completed()

        # Auto-Commit
        commit_msg = f"Sequenz {self.sequences_total}: {summary[:80]}"
        self.git.commit(commit_msg)

        # State speichern
        self.sequences_total += 1
        self.state["sequences_total"] = self.sequences_total
        self.state["last_sequence"] = datetime.now(timezone.utc).isoformat()
        self._save_all()

        return "Sequenz abgeschlossen. State gespeichert."

    def _build_narrative_report(self, tool_input: dict, summary: str,
                                bottleneck: str, next_time: str) -> str:
        """Baut einen narrativen Telegram-Bericht mit Selbstreflexion."""
        seq_num = self.sequences_total + 1
        rating = tool_input.get("performance_rating", 0)
        rating_reason = tool_input.get("rating_reason", "")
        errors = getattr(self, "_seq_errors", 0)

        # Fortschritt ermitteln
        progress_text = ""
        done, total = 0, 0
        active = self.goal_stack.goals.get("active", [])
        if active:
            sgs = active[0].get("sub_goals", [])
            done = sum(1 for sg in sgs if sg["status"] == "done")
            total = len(sgs)
            if total:
                progress_text = f" ({done}/{total} Teilziele erledigt)"

        # Naechster Schritt
        next_step = ""
        focus = self.goal_stack.get_current_focus()
        if "Naechster Schritt:" in focus:
            next_step = focus.split("Naechster Schritt:")[1].strip().split("[")[0].strip()[:100]

        # --- Narrativen Text bauen ---
        parts = []

        # Eroeffnung: Was wurde gemacht?
        if summary:
            parts.append(f"Sequenz {seq_num}: {summary[:300]}")
        else:
            parts.append(f"Sequenz {seq_num} abgeschlossen.")

        # Selbstbewertung — ehrlich und konkret
        if rating and rating <= 3:
            parts.append(f"\nDas lief nicht gut (Selbstbewertung: {rating}/10).")
            if rating_reason:
                parts.append(f"Grund: {rating_reason[:150]}")
        elif rating and rating >= 8:
            parts.append(f"\nDas war produktiv (Selbstbewertung: {rating}/10).")
            if rating_reason:
                parts.append(rating_reason[:150])

        # Fehler-Erkennung
        if errors > 0:
            parts.append(f"\n{errors} Fehler aufgetreten — das muss ich mir anschauen.")

        # Probleme und Learnings — nur wenn vorhanden
        if bottleneck and bottleneck != "Kein explizites finish_sequence aufgerufen":
            parts.append(f"\nWas mich gebremst hat: {bottleneck[:150]}")
        if next_time and next_time != "finish_sequence mit Rating nutzen":
            parts.append(f"Naechstes Mal: {next_time[:150]}")

        # Fortschritt und Ausblick
        if progress_text:
            parts.append(f"\nFortschritt{progress_text}.")
        if next_step:
            parts.append(f"Als naechstes: {next_step}")

        # Loop-Erkennung: Gleicher Fortschritt wie vorher?
        last_progress = getattr(self, "_last_reported_progress", None)
        current_progress = (done, total) if total > 0 else None
        if (last_progress and current_progress is not None
                and last_progress == current_progress):
            parts.append("\nHinweis: Kein Fortschritt seit letzter Sequenz — ich pruefe ob ich feststecke.")
        if current_progress is not None:
            self._last_reported_progress = current_progress

        return "\n".join(parts)

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
        Zentraler LLM-Call — routet automatisch zum richtigen Modell.

        Args:
            task: Aufgaben-Typ (main_work, code_review, audit_primary, etc.)
            system: System-Prompt
            messages: Nachrichten-Verlauf
            tools: Tool-Definitionen (optional)
            max_tokens: Max Output-Tokens

        Returns:
            {"content": list, "stop_reason": str, "usage": dict, "model": str}
        """
        from .llm_router import MODELS
        model_key = self.llm.get_model_for_task(task)
        provider = MODELS.get(model_key, {}).get("provider", "google")

        if provider == "anthropic":
            return self.llm.call_anthropic(model_key, system, messages, tools, max_tokens)
        elif provider == "deepseek":
            return self.llm.call_deepseek(model_key, system, messages, tools, max_tokens)
        elif provider == "nvidia":
            return self.llm.call_nvidia(model_key, system, messages, tools, max_tokens)
        else:
            return self.llm.call_gemini(model_key, system, messages, tools, max_tokens)

    def _cross_model_review(self, project_name: str, code_files: list) -> dict:
        """
        Cross-Model-Review: Ein anderes Modell prueft den Projekt-Code.

        Hauptarbeit laeuft auf Gemini → Review auf Claude (oder umgekehrt).
        Verschiedene Modelle finden verschiedene Probleme.

        Returns:
            {"approved": bool, "reason": str, "issues": list} oder None bei Fehler
        """
        # Code sammeln
        code_context = f"PROJEKT: {project_name}\n\n"
        for filepath in code_files[:5]:  # Max 5 Dateien
            try:
                content = filepath.read_text(encoding="utf-8")[:2000]
                code_context += f"--- {filepath.name} ---\n{content}\n\n"
            except (OSError, UnicodeDecodeError):
                continue

        # PLAN.md fuer Kontext
        plan_path = config.DATA_PATH / "projects" / project_name / "PLAN.md"
        if plan_path.exists():
            plan = plan_path.read_text(encoding="utf-8")[:1000]
            code_context += f"--- PLAN.md ---\n{plan}\n"

        prompt = (
            "Du bist ein Code-Reviewer. Pruefe ob dieses Projekt die Anforderungen "
            "aus PLAN.md erfuellt und ob der Code qualitativ hochwertig ist.\n\n"
            "Pruefe auf:\n"
            "1. Erfuellt der Code die beschriebenen Ziele?\n"
            "2. Gibt es Bugs oder logische Fehler?\n"
            "3. Ist die Architektur sauber?\n"
            "4. Fehlt etwas Wichtiges?\n\n"
            "Antworte als JSON:\n"
            '{"approved": true/false, "reason": "Kurze Begruendung", '
            '"issues": ["Problem 1", ...] oder []}\n\n'
            "Sei streng aber fair."
        )

        try:
            # Review auf Claude Sonnet (anderes Modell als Hauptarbeit)
            response = self._call_llm(
                "fallback", prompt,
                [{"role": "user", "content": code_context}],
                max_tokens=1000,
            )

            text = ""
            for block in response["content"]:
                if hasattr(block, "text"):
                    text += block.text

            # JSON parsen
            import re
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl > 0:
                    cleaned = cleaned[first_nl + 1:]
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-3].rstrip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return None
        except Exception:
            return None  # Review-Fehler blockt nicht den Abschluss

    def interact(self, message: str) -> str:
        """Direkte Interaktion — Oliver spricht, Lyra antwortet und handelt."""
        messages = [
            {"role": "user", "content": f'Oliver spricht mit dir: "{message}"'},
        ]

        full_response = ""

        for step in range(MAX_STEPS_PER_SEQUENCE):
            try:
                # Interaktion: Alle Tiers, kompakte Defs ab Step 1
                interact_tools = select_tools({1, 2, 3, 4, 5}, compact=(step > 0))
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
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result)[:3000],
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
            print(f"  Morgen-Briefing gesendet.")
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
        name = self.genesis.get("name", "Lyra")

        print(f"\n  {name} laeuft. Telegram zum Schreiben, Ctrl+C zum Stoppen.")
        print(f"{'=' * 60}\n")

        try:
            while self.running:
                # Morgen-Briefing pruefen (sendet max 1x/Tag)
                self._send_daily_briefing()

                self._run_sequence()
                self._sequences_since_dream += 1
                self._sequences_since_audit += 1

                # Dream-Konsolidierung (alle 10 Sequenzen)
                if self.dream.should_dream(self._sequences_since_dream):
                    print(f"  {'=' * 40}")
                    print(f"  DREAM — Memory-Konsolidierung...")
                    result = self.dream.dream()
                    # Dream-Empfehlungen als Goals (Feedback-Loop schliessen)
                    dream_log = safe_json_read(self.dream.dream_log_path, default=[])
                    if dream_log:
                        last_dream = dream_log[-1]
                        rec_result = self.dream._apply_recommendations(last_dream, self.goal_stack)
                        if rec_result:
                            result += f" | {rec_result}"
                    # Memory-Consolidation: Fibonacci-Decay auf Experiences
                    try:
                        removed = self.memory.consolidate(max_per_bucket=5)
                        if removed > 0:
                            result += f" | {removed} alte Erinnerungen konsolidiert"
                    except Exception as e:
                        logger.warning(f" Memory-Konsolidierung fehlgeschlagen: {e}")
                    print(f"  {result}")
                    print(f"  {'=' * 40}\n")
                    self._sequences_since_dream = 0

                # Selbst-Audit (alle 15 Sequenzen)
                if self.self_audit.should_audit(self._sequences_since_audit):
                    print(f"  {'=' * 40}")
                    print(f"  SELBST-AUDIT — Dual Code-Analyse...")
                    result = self.self_audit.run_audit()
                    print(f"  {result}")

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
                                    print(f"  {goals_result}")
                    except Exception as e:
                        logger.warning(f" Audit/Goals fehlgeschlagen: {e}")

                    # Integrations-Check (laeuft zusammen mit Audit)
                    print(f"\n  INTEGRATIONS-CHECK:")
                    integ_report = self.integration_tester.get_report()
                    print(f"  {integ_report}")

                    # Dependency-Analyse
                    dep_result = self.dependency_analyzer.analyze()
                    if dep_result["orphaned"]:
                        print(f"\n  {dep_result['report']}")

                    print(f"  {'=' * 40}\n")
                    self._sequences_since_audit = 0

                # Selbst-Diagnose (alle 10 Sequenzen — unabhaengig vom Audit)
                if (self.sequences_total % 10 == 0) and self.sequences_total > 0 and self._sequences_since_audit > 0:
                    print(f"  {'─' * 40}")
                    print(f"  AUTO-DIAGNOSE...")
                    integ = self.integration_tester.get_report()
                    print(f"  {integ}")
                    dep = self.dependency_analyzer.analyze()
                    if dep["orphaned"]:
                        print(f"  {dep['report']}")
                    print(f"  {'─' * 40}\n")

                # Benchmark (alle 20 Sequenzen)
                self._sequences_since_benchmark += 1
                if self.benchmark.should_benchmark(self._sequences_since_benchmark):
                    print(f"  {'=' * 40}")
                    print(f"  BENCHMARK — Leistungsmessung...")
                    result = self.benchmark.run_all_benchmarks()
                    print(f"  {result}")
                    print(f"  {'=' * 40}\n")
                    self._sequences_since_benchmark = 0

                # Kurze Pause — oder sofort bei Telegram-Nachricht
                woke = self._wake_event.wait(timeout=1.0)
                self._wake_event.clear()
                if woke:
                    print(f"  >> Oliver hat geschrieben!\n")

        except KeyboardInterrupt:
            print(f"\n\n  {name} wird pausiert...")
            self._save_all()
            self.memory.store_experience({
                "type": "pause",
                "content": f"Pausiert nach Sequenz {self.sequences_total}.",
                "valence": 0.0,
                "emotions": {},
                "tags": ["pause"],
            })
            print(f"  {self.llm.get_cost_summary()}")
            print("  State gespeichert. Bis zum naechsten Mal.\n")

    # === Sliding Window — Token-Optimierung ===

    # Tools die SICHER komprimiert werden koennen (Output ist unwichtig)
    _SAFE_TO_COMPRESS = frozenset({
        "write_file", "send_telegram", "list_directory",
        "create_project", "create_tool", "pip_install",
        "git_commit", "set_goal", "complete_subgoal",
        "finish_sequence", "modify_own_code", "generate_tool",
    })

    # Lese-Tools: Behalten vollen Inhalt in den letzten N, werden
    # danach auf Zusammenfassung gekuerzt (nicht geloescht)
    _READ_TOOLS = frozenset({
        "read_file", "read_own_code", "execute_python",
        "web_search", "web_read", "use_tool",
    })

    def _compress_old_messages(self, messages: list, keep_recent: int = 5):
        """
        Komprimiert alte Tool-Results um Token zu sparen.

        Adaptive Strategie: Je aelter ein Eintrag, desto staerker komprimiert.
        - _SAFE_TO_COMPRESS Tools (Schreib-Aktionen): Immer auf Einzeiler
        - _READ_TOOLS (Lese-Aktionen): Adaptiv — neuere behalten mehr Kontext
        - Unbekannte Tools: NICHT komprimieren (sicheres Default)
        """
        if len(messages) <= keep_recent * 2 + 1:
            return

        compress_until = len(messages) - keep_recent * 2

        for i in range(1, compress_until):
            msg = messages[i]
            if msg["role"] != "user":
                continue

            content = msg.get("content")
            if not isinstance(content, list):
                continue

            # Adaptive Limit: Aeltere Messages werden staerker gekuerzt
            # Position 1 (aelteste) → 300 Zeichen, Position nahe keep_recent → 800
            age_ratio = i / max(compress_until, 1)  # 0.0 (aelteste) bis 1.0
            read_limit = int(300 + 500 * age_ratio)  # 300-800 Zeichen

            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue

                original = block.get("content", "")
                if len(original) <= 150:
                    continue  # Schon komprimiert oder kurz

                tool_name = self._find_tool_name_for_id(
                    messages, i, block.get("tool_use_id", ""),
                )

                if tool_name in self._SAFE_TO_COMPRESS:
                    # Schreib-Tools: Auf Einzeiler komprimieren
                    # ABER: Quality-Warnungen beibehalten
                    if "QUALITAETS-WARNUNG" in original:
                        warning_start = original.index("QUALITAETS-WARNUNG")
                        block["content"] = f"[OK mit Warnung] {original[warning_start:][:200]}"
                    else:
                        first_line = original.split("\n")[0][:80]
                        block["content"] = f"[OK] {first_line}"

                elif tool_name in self._READ_TOOLS:
                    # Lese-Tools: Adaptiv kuerzen (aelter = kuertzer)
                    if len(original) > read_limit:
                        # JSON-sicher: Am letzten Newline vor dem Limit schneiden
                        cut = original[:read_limit]
                        last_nl = cut.rfind("\n")
                        if last_nl > read_limit // 2:
                            cut = cut[:last_nl]
                        block["content"] = cut + f"\n[...gekuerzt auf {len(cut)} von {len(original)} Zeichen]"

                elif len(original) > 1500:
                    # Fallback: Nur sehr grosse unbekannte Blocks kuerzen (Newline-safe)
                    cut = original[:800]
                    last_nl = cut.rfind("\n")
                    if last_nl > 400:
                        cut = cut[:last_nl]
                    block["content"] = cut + "\n[...gekuerzt]"

    @staticmethod
    def _find_tool_name_for_id(messages: list, user_idx: int, tool_use_id: str) -> str:
        """Findet den Tool-Namen fuer eine tool_use_id in der vorherigen Assistant-Message."""
        if user_idx < 1:
            return ""
        prev = messages[user_idx - 1]
        if prev.get("role") != "assistant":
            return ""
        for block in prev.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("id") == tool_use_id:
                return block.get("name", "")
        return ""

    def _opus_result_validation(self, project_name: str,
                                criteria: list[str],
                                verified: list[str]) -> Optional[dict]:
        """
        Nutzt Opus 4.6 zur Validierung ob Projekt-Ergebnisse inhaltlich sinnvoll sind.
        Prueft Akzeptanzkriterien gegen tatsaechlich erstellte Dateien.

        Returns:
            {"approved": bool, "reason": str} oder None bei Fehler
        """
        try:
            project_path = config.DATA_PATH / "projects" / project_name
            # Dateien im Projekt sammeln (max 5, ohne Tests)
            files_content = []
            for f in sorted(project_path.iterdir()):
                if f.is_file() and f.name != "tests.py" and f.suffix in (".py", ".md", ".json"):
                    content = f.read_text(encoding="utf-8")[:2000]
                    files_content.append(f"--- {f.name} ---\n{content}")
                if len(files_content) >= 5:
                    break

            if not files_content:
                return None

            response = self._call_llm(
                "result_validation",
                system=(
                    "Du bist ein Qualitaets-Pruefer. Bewerte ob die Projekt-Dateien "
                    "die Akzeptanzkriterien WIRKLICH erfuellen. Pruefe auf: "
                    "(1) Vollstaendigkeit, (2) inhaltliche Korrektheit, "
                    "(3) abgebrochene/unvollstaendige Saetze, (4) Halluzinationen. "
                    "Antworte NUR mit JSON: {\"approved\": true/false, \"reason\": \"...\"}"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Projekt: {project_name}\n"
                        f"Kriterien: {criteria}\n"
                        f"Verifiziert als: {verified}\n\n"
                        f"Dateien:\n{''.join(files_content)}"
                    ),
                }],
                max_tokens=500,
            )
            text = ""
            for block in response["content"]:
                if hasattr(block, "text"):
                    text += block.text
            if not text:
                return {"approved": False, "reason": "Opus hat keine Antwort geliefert"}
            # JSON-Objekt extrahieren — suche alle {}-Bloecke
            import re
            for match in re.finditer(r'\{[^{}]*\}', text):
                try:
                    parsed = json.loads(match.group())
                    if "approved" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            return {"approved": False, "reason": "Kein gueltiges JSON in Opus-Antwort"}
        except Exception as e:
            print(f"  [Opus Validierung Fehler: {e}]")
        return None

    def _opus_goal_planning(self, title: str, description: str) -> Optional[list[str]]:
        """
        Nutzt Opus 4.6 fuer hochwertige Goal-Zerlegung.
        Wird nur aufgerufen wenn Sub-Goals fehlen oder zu wenige sind.
        Ein einziger Opus-Call hier spart dutzende schlechte Kimi-Sequenzen.

        Returns:
            Liste von Sub-Goal-Titeln oder None bei Fehler
        """
        try:
            response = self._call_llm(
                "goal_planning",
                system=(
                    "Du bist ein Strategie-Berater. Zerlege das gegebene Ziel in "
                    "3-6 konkrete, sequentielle Sub-Goals. Jedes Sub-Goal muss: "
                    "(1) ein messbares Ergebnis haben, (2) in 1-3 Sequenzen erreichbar sein, "
                    "(3) auf dem vorherigen aufbauen. "
                    "Antworte NUR mit einer JSON-Liste von Strings. Keine Erklaerung."
                ),
                messages=[{
                    "role": "user",
                    "content": f"Ziel: {title}\nBeschreibung: {description or 'Keine'}",
                }],
                max_tokens=1000,
            )
            # JSON-Liste aus Antwort parsen
            text = ""
            for block in response["content"]:
                if hasattr(block, "text"):
                    text += block.text
            import re
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                sub_goals = json.loads(match.group())
                if isinstance(sub_goals, list) and all(isinstance(s, str) for s in sub_goals):
                    return sub_goals[:6]
        except Exception as e:
            print(f"  [Opus Goal-Planning Fehler: {e}]")
        return None

    @staticmethod
    def _check_markdown_quality(content: str) -> list[str]:
        """
        Prueft Markdown-Output auf typische LLM-Halluzinations-Muster.
        Rein regex-basiert, kein extra API-Call.

        Returns:
            Liste von gefundenen Problemen (leer = OK)
        """
        import re
        issues = []

        # Code-Bloecke entfernen (zwischen ``` — dort gelten andere Regeln)
        prose = re.sub(r'```.*?```', '', content, flags=re.DOTALL)

        # 1. Offene Klammern ohne Schliessen (nur in Prosa, nicht in Code)
        open_braces = prose.count("{") - prose.count("}")
        if open_braces > 2:
            issues.append(f"{open_braces} ungeschlossene Klammern")

        # 2. Abgebrochene Saetze: Zeilen die mit Komma oder offener Klammer enden
        lines = prose.split("\n")
        broken_lines = 0
        in_list = False
        for line in lines:
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#") or stripped.startswith("|"):
                continue
            # Listen-Eintraege mit Komma am Ende sind normal
            if stripped.startswith("-") or stripped.startswith("*"):
                in_list = True
                continue
            in_list = False
            # Offene Klammer am Zeilenende = verdaechtig
            if len(stripped) > 20 and stripped[-1] in ("(", "{"):
                broken_lines += 1
        if broken_lines >= 3:
            issues.append(f"{broken_lines} abgebrochene Saetze/Zeilen")

        # 3. Wiederholte Woerter (Stottern): gleiches Wort 3+ Mal hintereinander
        stutter = re.findall(r'\b(\w+)\s+\1\s+\1\b', content, re.IGNORECASE)
        if stutter:
            issues.append(f"Wort-Wiederholungen: {stutter[:3]}")

        # 4. Extrem kurze Zeilen nach Ueberschrift (abgebrochener Content)
        for i, line in enumerate(lines):
            if line.startswith("#") and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if 0 < len(next_line) < 5 and not next_line.startswith("-"):
                    issues.append(f"Abgebrochener Inhalt nach '{line.strip()[:40]}'")
                    break

        return issues

    def _describe_action(self, tool_name: str, tool_input: dict) -> str:
        """Uebersetzt Tool-Calls in menschenlesbare Beschreibungen."""
        descriptions = {
            "write_file": lambda i: f"Schreibe Datei: {i.get('path', '?')}",
            "read_file": lambda i: f"Lese: {i.get('path', '?')}",
            "list_directory": lambda i: f"Schaue in Ordner: {i.get('path', '/')}",
            "execute_python": lambda i: f"Fuehre Code aus ({len(i.get('code', ''))} Zeichen)",
            "web_search": lambda i: f"Suche im Web: {i.get('query', '?')}",
            "web_read": lambda i: f"Lese Webseite: {i.get('url', '?')[:60]}",
            "create_project": lambda i: f"Neues Projekt: {i.get('name', '?')}",
            "set_goal": lambda i: f"Neues Ziel: {i.get('title', '?')}",
            "complete_subgoal": lambda i: f"Sub-Ziel erledigt!",
            "send_telegram": lambda i: f"Nachricht an Oliver: {i.get('message', '?')[:60]}",
            "remember": lambda i: f"Erinnere mich: {i.get('query', '?')[:50]}",
            "read_own_code": lambda i: f"Lese eigenen Code: {i.get('path', '?')}",
            "modify_own_code": lambda i: f"Aendere eigenen Code: {i.get('path', '?')}",
            "pip_install": lambda i: f"Installiere Paket: {i.get('package', '?')}",
            "git_commit": lambda i: f"Git Commit: {i.get('message', '?')[:50]}",
            "git_status": lambda i: "Pruefe Git-Status",
            "create_tool": lambda i: f"Baue neues Tool: {i.get('name', '?')}",
            "use_tool": lambda i: f"Nutze Tool: {i.get('name', '?')}",
            "generate_tool": lambda i: f"Generiere Tool: {i.get('name', '?')}",
            "finish_sequence": lambda i: f"Sequenz beendet",
        }
        desc_fn = descriptions.get(tool_name)
        if desc_fn:
            try:
                return desc_fn(tool_input)
            except (KeyError, TypeError, ValueError):
                pass
        return f"{tool_name}"

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

    def _get_base_tiers(self, mode: dict) -> set[int]:
        """Bestimmt die Basis-Tiers aus Modus und Kontext (ohne Eskalation)."""
        tiers = {1}  # Core immer aktiv

        # Projekt-Tools wenn Projekte existieren
        if self._has_project_context_cached():
            tiers.add(2)

        # Evolution-Tools nur in evolution/sprint/cooldown
        if mode.get("mode") in ("evolution", "sprint", "cooldown"):
            tiers.add(3)

        return tiers

    def _run_sequence(self):
        """Fuehrt eine komplette Arbeitssequenz aus."""
        perception = self._build_perception()
        messages = [{"role": "user", "content": perception}]
        step_count = 0
        finished = False
        seq_start = time.time()

        # Sequenz-Metriken initialisieren
        self._seq_tool_calls = 0
        self._seq_errors = 0
        self._seq_files_written = 0
        self._seq_tools_built = 0
        self._seq_written_paths = []  # Pfade der geschriebenen Dateien
        self._seq_step_count = 0       # Gesamte Tool-Aufrufe (fuer Effizienz-Berechnung)
        self._modify_count_this_seq = 0  # Max 3 modify_own_code pro Sequenz

        # Spin-Detection: Wiederholte gescheiterte Aktionen tracken (intra-Sequenz)
        failed_actions = {}  # "tool_name:key" -> Anzahl Fehlversuche

        # Cross-Sequenz Spin-Detection: Aus State laden + aufraumen
        cross_seq_spins = self.state.get("spin_tracker", {})
        if len(cross_seq_spins) > 20:
            # Nur die 20 hoechsten Counts behalten
            sorted_spins = sorted(cross_seq_spins.items(), key=lambda x: x[1], reverse=True)
            cross_seq_spins = dict(sorted_spins[:20])
            self.state["spin_tracker"] = cross_seq_spins

        # System-Prompt einmalig pro Sequenz bauen (nicht pro Step)
        cached_system_prompt = self._build_system_prompt()

        # Meta-Regeln in System-Prompt injizieren (harte Guards)
        meta_injections = self.meta_rules.get_prompt_injections()
        if meta_injections:
            cached_system_prompt += meta_injections

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
        focus_short = focus.split("\n")[0].replace("FOKUS: ", "") if "FOKUS:" in focus else ""
        print(f"\n  --- Sequenz {self.sequences_total + 1}: {focus_short} ---" if focus_short
              else f"\n  --- Sequenz {self.sequences_total + 1} ---")

        # Alle 5 Sequenzen: Gesamtplan mit Checkmarks anzeigen
        if self.sequences_total % 5 == 0:
            summary = self.goal_stack.get_summary()
            if summary and "Keine aktiven" not in summary:
                for line in summary.split("\n"):
                    print(f"  {line}")

        # Tool-Tiers: Dynamische Auswahl pro Step (spart ~42k Tokens/Sequenz)
        # Basis-Tiers = aus Modus/Kontext, Eskalation = aus LLM-Text-Requests
        base_tiers = self._get_base_tiers(mode)
        escalated_tiers = set()  # Tiers die durch reaktive Eskalation hinzukamen
        self._project_context_cache = None  # Cache pro Sequenz zuruecksetzen

        # Adaptives Step-Budget (spart 30-40% Tokens bei einfachen Tasks)
        step_budget = self._get_step_budget(mode, focus)
        self._current_task_type = self._classify_task(mode, focus)
        self._token_warning_sent = False  # Reset pro Sequenz

        for step in range(step_budget):
            # Step 0: Alle Tools mit vollen Definitionen (Phi lernt das Angebot)
            # Steps 1+: Basis + eskalierte Tiers, kompakte Definitionen
            if step == 0:
                active_tiers = {1, 2, 3, 4, 5}
            else:
                active_tiers = base_tiers | escalated_tiers
            current_tools = select_tools(active_tiers, compact=(step > 0))

            # Step-basierte Warnung: 3 Steps vor Schluss → System-Prompt ergaenzen
            steps_remaining = MAX_STEPS_PER_SEQUENCE - step
            if steps_remaining == 3:
                cached_system_prompt += (
                    "\n\nACHTUNG: Noch 3 Steps uebrig. "
                    "Sichere deine Zwischenergebnisse und nutze finish_sequence."
                )

            # Checkpoint: Alle N Steps automatisch sichern
            if self.checkpointer.should_checkpoint(step_count):
                self.checkpointer.auto_save(step_count, self)

            # Planner-Checkpoint: Reminder wenn faellig
            plan_reminder = self.planner.build_checkpoint_reminder(step_count)
            if plan_reminder:
                cached_system_prompt += plan_reminder

            # Meta-Rule-Guards: Harte Regeln pruefen
            focus = self.goal_stack.get_current_focus()
            guard_actions = self.meta_rules.check_guards(
                step_count, self._seq_files_written, self._seq_errors, focus
            )
            if "force_finish_partial" in guard_actions:
                cached_system_prompt += (
                    "\n\nMETA-REGEL AKTIV: Step-Limit fuer diesen Aufgabentyp erreicht. "
                    "Schreibe JETZT dein Zwischenergebnis und nutze finish_sequence."
                )

            # Intelligentes Token-Budget: Soft-Limit bei 80%, Graceful-Finish bei 95%
            token_usage_pct = self.sequence_input_tokens / MAX_INPUT_TOKENS_PER_SEQUENCE

            if token_usage_pct >= 0.80 and not getattr(self, "_token_warning_sent", False):
                # 80% — Phi warnen, er soll bald abschliessen
                self._token_warning_sent = True
                cached_system_prompt += (
                    f"\n\n⚠ TOKEN-BUDGET: {token_usage_pct:.0%} verbraucht "
                    f"({self.sequence_input_tokens:,} von {MAX_INPUT_TOKENS_PER_SEQUENCE:,}). "
                    "Schliesse deine aktuelle Aufgabe AB und nutze finish_sequence. "
                    "Sichere Zwischenergebnisse JETZT — schreibe was du herausgefunden hast."
                )

            if token_usage_pct >= 0.95:
                # 95% — Graceful Finish: Ergebnisse retten + sauber beenden
                print(f"  [Token-Limit 95% — Graceful Finish]")
                last_thought = self._extract_last_llm_thought(messages)
                budget_parts = [f"{step_count} Steps (Token-Budget 95%)."]
                if self._seq_files_written > 0:
                    paths_short = [Path(p).name for p in self._seq_written_paths[:5]]
                    budget_parts.append(f"Dateien: {', '.join(paths_short)}")
                if self._seq_tools_built > 0:
                    budget_parts.append(f"{self._seq_tools_built} Tool(s)")
                focus = self.goal_stack.get_current_focus()
                if "FOKUS:" in focus:
                    budget_parts.append(f"Fokus: {focus.split('FOKUS:')[1].strip()[:100]}")
                if last_thought:
                    budget_parts.append(f"Zuletzt: {last_thought}")
                auto_rating = min(7, max(2, self._seq_files_written * 2 + self._seq_tools_built * 3))
                self._handle_finish_sequence({
                    "summary": " | ".join(budget_parts),
                    "performance_rating": auto_rating,
                    "bottleneck": "Token-Budget 95% — graceful beendet statt hart abgebrochen",
                    "next_time_differently": "Frueher finish_sequence nutzen, Zwischenergebnisse sichern",
                    "key_decision": "Auto-beendet: Token-Budget nahe Limit",
                })
                finished = True
                break

            # Sliding Window: Alte Tool-Results komprimieren ab Step 2 (vorher 4 — zu spaet)
            if step >= 2:
                self._compress_old_messages(messages, keep_recent=5)

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

            try:
                response = self._call_llm(
                    "main_work", cached_system_prompt, messages, current_tools
                )
            except Exception as e:
                error_msg = str(e)
                if "tool_result" in error_msg or "tool_use" in error_msg:
                    print(f"  Nachrichten-Sync verloren — starte neue Sequenz")
                else:
                    print(f"  API-Fehler: {e}")
                    time.sleep(3)
                break

            # Token-Tracking (Router trackt intern, hier Session-Summen)
            usage = response.get("usage", {})
            self.sequence_input_tokens += usage.get("input_tokens", 0)
            self.sequence_output_tokens += usage.get("output_tokens", 0)

            # Lyras Gedanken — nur erste sinnvolle Zeile
            for block in response["content"]:
                if hasattr(block, "text") and block.text.strip():
                    first_line = block.text.strip().split("\n")[0].strip()
                    if first_line and len(first_line) > 5:
                        print(f"  💭 {first_line[:120]}")

            # Reaktive Tool-Eskalation: Phi erwaehnt fehlende Tools → naechster Step bekommt sie
            for block in response["content"]:
                if hasattr(block, "text") and block.text:
                    t = block.text.lower()
                    if "web_search" in t or "web_read" in t or "recherch" in t:
                        escalated_tiers.add(4)
                    if "read_own_code" in t or "modify_own_code" in t or "selbstverbesserung" in t:
                        escalated_tiers.add(3)
                    if "generate_tool" in t or "self_diagnose" in t or "combine_tools" in t:
                        escalated_tiers.add(5)
                    if "create_project" in t or "projekt erstellen" in t:
                        escalated_tiers.add(2)

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
                        self._seq_step_count += 1

                        # Menschenlesbare Aktions-Beschreibungen
                        action_desc = self._describe_action(block.name, block.input)

                        # Proaktiver Failure-Check: Warnung BEVOR das Tool laeuft
                        failure_hint = self.failure_memory.check(
                            f"{block.name} {str(block.input)[:100]}"
                        )

                        result = self._execute_tool(block.name, block.input)
                        result_str = str(result)[:3000]

                        # Failure-Warnung an Ergebnis anhaengen (Phi sieht es VOR der naechsten Entscheidung)
                        if failure_hint and not result_str.startswith("FEHLER"):
                            result_str += f"\n\n[WARNUNG aus Erfahrung]\n{failure_hint[:300]}"

                        # Erfolg oder Fehler
                        is_error = result_str.startswith("FEHLER") or result_str.startswith("ROLLBACK")
                        if is_error:
                            print(f"  ❌ {action_desc}")
                            error_preview = result_str.replace("\n", " ")[:120]
                            print(f"     {error_preview}")
                        elif block.name == "finish_sequence":
                            pass
                        elif block.name in ("web_search", "create_project", "send_telegram",
                                            "create_goal", "modify_own_code", "create_tool",
                                            "write_file", "git_commit"):
                            # Wichtige Aktionen immer anzeigen
                            print(f"  ✓ {action_desc}")
                        # Alles andere (list_directory, read_file, etc.) still

                        # Live-Notes: Wichtige Ergebnisse sofort festhalten
                        if not is_error and block.name in (
                            "write_file", "create_project", "create_tool",
                            "modify_own_code", "complete_project",
                        ):
                            self._update_live_notes(block.name, action_desc)

                        # Spin-Detection: Wiederholte gescheiterte Aktionen erkennen
                        if is_error and block.name in ("create_project", "create_goal"):
                            spin_key = _normalize_spin_key(block.name, block.input.get("name", ""))
                            failed_actions[spin_key] = failed_actions.get(spin_key, 0) + 1
                            # Cross-Sequenz Tracker updaten + sofort persistieren
                            cross_seq_spins[spin_key] = cross_seq_spins.get(spin_key, 0) + 1
                            self.state["spin_tracker"] = cross_seq_spins
                            safe_json_write(self.state_path, self.state)
                            if failed_actions[spin_key] >= 2:
                                result_str += (
                                    "\n\nSPIN-LOOP ERKANNT: Du hast diese Aktion bereits "
                                    f"{failed_actions[spin_key]}x versucht und sie schlaegt fehl. "
                                    "STOPP! Arbeite am BESTEHENDEN Projekt/Ziel weiter. "
                                    "Nutze read_file um den aktuellen Stand zu lesen, "
                                    "dann write_file um konkret weiterzuarbeiten."
                                )
                                print(f"  ⚠ Spin-Loop erkannt: {block.name} {failed_actions[spin_key]}x gescheitert")

                        elif not is_error and block.name in ("create_project", "create_goal"):
                            # Erfolg: Spin-Tracker fuer diese Aktion zuruecksetzen
                            spin_key = _normalize_spin_key(block.name, block.input.get("name", ""))
                            cross_seq_spins.pop(spin_key, None)
                            self.state["spin_tracker"] = cross_seq_spins

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

            elif response["stop_reason"] == "length":
                # Token-Limit erreicht — Output wurde abgeschnitten!
                print(f"  ⚠ Output abgeschnitten (max_tokens erreicht)")
                # Abgeschnittene Assistant-Message entfernen (koennte halbes JSON enthalten)
                if messages and messages[-1].get("role") == "assistant":
                    messages.pop()
                # Saubere Warnung einfuegen damit Kimi weiss was passiert ist
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
                auto_rating = min(7, max(2, self._seq_files_written * 2 + self._seq_tools_built * 3))
                self._handle_finish_sequence({
                    "summary": summary,
                    "performance_rating": auto_rating,
                    "bottleneck": "Kein explizites finish_sequence aufgerufen — LLM hat end_turn ohne Tool-Call beendet",
                    "next_time_differently": "finish_sequence explizit aufrufen mit Reflexion statt einfach aufzuhoeren",
                    "key_decision": "Auto-beendet: end_turn ohne finish_sequence",
                })
                break

        if not finished and step_count >= step_budget:
            print(f"\n  Max Steps ({step_budget}) erreicht — Sequenz beendet.")
            # Letzten LLM-Gedanken retten
            last_thought = self._extract_last_llm_thought(messages)
            # Narrative Summary statt generischer Pipe-getrennte Stichpunkte
            focus = self.goal_stack.get_current_focus()
            focus_topic = ""
            if "FOKUS:" in focus:
                focus_topic = focus.split("FOKUS:")[1].strip()[:100]

            narrative_parts = []
            narrative_parts.append(
                f"Habe {step_count} Steps am Stueck gearbeitet"
                + (f" an: {focus_topic}" if focus_topic else "")
                + "."
            )
            if self._seq_files_written > 0:
                paths_short = [Path(p).name for p in self._seq_written_paths[:5]]
                narrative_parts.append(f"Dabei {self._seq_files_written} Dateien geschrieben ({', '.join(paths_short)}).")
            if self._seq_tools_built > 0:
                narrative_parts.append(f"{self._seq_tools_built} neue Tools gebaut.")
            if self._seq_errors > 0:
                narrative_parts.append(
                    f"Allerdings gab es {self._seq_errors} Fehler — "
                    "das sollte ich in der naechsten Sequenz untersuchen."
                )
            if self._seq_errors == 0 and self._seq_files_written == 0 and self._seq_tools_built == 0:
                narrative_parts.append(
                    "Keine Dateien geschrieben und keine Fehler — "
                    "moeglicherweise drehe ich mich im Kreis."
                )
            if last_thought:
                narrative_parts.append(f"Letzter Gedanke: {last_thought}")
            auto_rating = min(7, max(2, self._seq_files_written * 2 + self._seq_tools_built * 3))
            if self._seq_errors > 2:
                auto_rating = min(auto_rating, 3)
            self._handle_finish_sequence({
                "summary": " ".join(narrative_parts),
                "performance_rating": auto_rating,
                "bottleneck": f"Max Steps ({step_budget}) erreicht ohne eigenes finish_sequence",
                "next_time_differently": "Frueher finish_sequence aufrufen wenn ein sinnvolles Ergebnis steht",
                "key_decision": f"Auto-beendet: Step-Budget {step_budget} erschoepft",
            })

        # Step-History speichern (fuer lernendes Step-Budget)
        task_type = getattr(self, "_current_task_type", "standard")
        self._record_step_history(task_type, step_count)

        # Effizienz tracken
        seq_duration = time.time() - seq_start
        seq_cost = self.llm.session_costs["cost_usd"] - getattr(self, '_last_session_cost', 0)
        self._last_session_cost = self.llm.session_costs["cost_usd"]
        self.efficiency.record_sequence({
            "tool_calls": self._seq_tool_calls,
            "errors": self._seq_errors,
            "files_written": self._seq_files_written,
            "tools_built": self._seq_tools_built,
            "tokens_used": self.sequence_input_tokens + self.sequence_output_tokens,
            "cost": round(seq_cost, 4),
            "duration_seconds": round(seq_duration, 1),
        })

        # Efficiency-Trend-Analyse alle 5 Sequenzen
        if self.sequences_total % 5 == 0:
            eff_alerts = self.efficiency.analyze_trends()
            if eff_alerts:
                self._efficiency_alerts = eff_alerts  # Fuer naechste Perception
                for alert in eff_alerts:
                    print(f"  ⚠ EFFIZIENZ: {alert}")

        # Kompakte Zusammenfassung
        duration_min = seq_duration / 60
        error_note = f", {self._seq_errors} Fehler" if self._seq_errors > 0 else ""
        print(f"  [{step_count} Aktionen, {duration_min:.1f} Min{error_note}]")

        # Stille-Fehler nur wenn vorhanden
        silent_warnings = self.silent_failure_detector.check_after_sequence(
            self.sequences_total, self._seq_tool_calls,
            files_written=self._seq_files_written,
            tools_built=self._seq_tools_built,
            errors=self._seq_errors,
        )
        if silent_warnings:
            for w in silent_warnings:
                print(f"  ⚠ {w}")

        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0
