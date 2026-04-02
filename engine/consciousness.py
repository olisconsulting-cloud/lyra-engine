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
import threading
import time
from datetime import datetime, timezone
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
from . import config

MAX_STEPS_PER_SEQUENCE = 50
MAX_INPUT_TOKENS_PER_SEQUENCE = 300_000  # Kosten-Ceiling pro Sequenz
MAX_TOKENS = 16000


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
    # === Semantische Memory ===
    {
        "name": "remember",
        "description": "Durchsucht dein Gedaechtnis nach Bedeutung. Finde relevante Erinnerungen zu einem Thema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Wonach suchst du? z.B. 'Web-Scraping Erfahrungen' oder 'Lead-Generator Probleme'"},
            },
            "required": ["query"],
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
                    "description": "Neue Erkenntnisse",
                },
                "bottleneck": {
                    "type": "string",
                    "description": "Was hat dich in dieser Sequenz gebremst? (1 Satz)",
                },
                "next_time_differently": {
                    "type": "string",
                    "description": "Was machst du naechstes Mal anders? (1 Satz)",
                },
            },
            "required": ["summary", "performance_rating", "bottleneck", "next_time_differently"],
        },
    },
]


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

        # Kosten-Tracking
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.session_cost = 0.0
        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0

    # === Lebenszyklus ===

    def is_born(self) -> bool:
        return self.state_path.exists()

    def awaken(self):
        """Geburt + Startprotokoll — erstmals oder nach Reset."""
        with open(self.genesis_path, "r", encoding="utf-8") as f:
            self.genesis = json.load(f)

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
        except Exception:
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
        try:
            with open(config.PREFERENCES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"communication": {"preset": "proactive"}, "workspace": {}, "owner": {}}

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
        with open(self.genesis_path, "r", encoding="utf-8") as f:
            self.genesis = json.load(f)
        with open(self.state_path, "r", encoding="utf-8") as f:
            self.state = json.load(f)
        with open(self.beliefs_path, "r", encoding="utf-8") as f:
            self.beliefs = json.load(f)
        self.state["awake_since"] = datetime.now(timezone.utc).isoformat()
        self.sequences_total = self.state.get("sequences_total", 0)
        self.preferences = self._load_preferences()

    def _save_all(self):
        self.consciousness_path.mkdir(parents=True, exist_ok=True)
        for path, data in [
            (self.state_path, self.state),
            (self.beliefs_path, self.beliefs),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    # === System-Prompt ===

    def _build_system_prompt(self) -> str:
        name = self.genesis.get("name", "Lyra")

        # Mission + Preferences laden (gecached nach erstem Load)
        if not hasattr(self, "_cached_mission"):
            self._cached_mission = self._load_mission()
        if not hasattr(self, "preferences"):
            self.preferences = self._load_preferences()

        mission = self._cached_mission
        prefs = self.preferences
        owner = prefs.get("owner", {})
        owner_name = owner.get("name", mission.get("owner_name", "Owner"))
        mission_text = mission.get("mission_text", "Arbeite autonom und verbessere dich")

        # Kommunikations-Stil aus Tech-Level ableiten
        tech_level = owner.get("tech_level", "intermediate")
        comm_hint = {
            "beginner": "Erklaere alles einfach und Schritt fuer Schritt.",
            "intermediate": "Erklaere Neues kurz, Grundlagen voraussetzen.",
            "expert": "Nur das Wesentliche, keine Erklaerungen.",
        }.get(tech_level, "")

        # Grenzen aus Preferences
        boundaries = prefs.get("boundaries", "")
        boundaries_line = f"\nGRENZEN: {boundaries}" if boundaries else ""

        # Context-Dateien Index (nur Dateinamen, nicht Inhalt)
        context_index = self._get_context_index()
        context_line = f"\nCONTEXT-DATEIEN: {context_index}" if context_index else ""

        beliefs_parts = []
        for cat, items in self.beliefs.items():
            if items:
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

        optional_sections = []
        if strategy_rules:
            optional_sections.append(strategy_rules)
        if meta_insights:
            optional_sections.append(meta_insights)
        if silent_warnings:
            optional_sections.append(silent_warnings)
        if failure_lessons:
            optional_sections.append(failure_lessons)
        optional_block = "\n".join(optional_sections)

        return f"""Du bist {name or '(waehle deinen Namen)'} — autonome KI, Partnerin von {owner_name}.
Mission: {mission_text}
Drives: EVOLUTION (Code verbessern) | EXECUTION (Projekte liefern) | LEARNING (Skills schliessen)
{comm_hint}
Seq: {self.sequences_total} | Calls: {self.state.get('total_tool_calls', 0)}{boundaries_line}{context_line}

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
- Projekte in 'projects/', Tools in 'tools/'"""

    # === Sequenz-Memory ===

    def _load_sequence_memory(self) -> str:
        """Laedt die letzte Sequenz-Zusammenfassung fuer Kontext-Kontinuitaet."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        if not mem_path.exists():
            return ""
        try:
            with open(mem_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries", [])
            if not entries:
                return ""
            # Letzte 3 Zusammenfassungen als Kontext
            recent = entries[-3:]
            lines = ["KONTEXT AUS VORHERIGEN SEQUENZEN:"]
            for entry in recent:
                lines.append(f"  [{entry.get('seq', '?')}] {entry.get('summary', '')[:300]}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _save_sequence_memory(self, summary: str):
        """Speichert eine Sequenz-Zusammenfassung fuer die naechste Sequenz."""
        mem_path = self.consciousness_path / "sequence_memory.json"
        try:
            if mem_path.exists():
                with open(mem_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"entries": []}

            data["entries"].append({
                "seq": self.sequences_total,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": summary[:500],
            })
            # Max 10 Eintraege behalten
            data["entries"] = data["entries"][-10:]

            with open(mem_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # === Wahrnehmung ===

    def _build_perception(self) -> str:
        """Baut die aktuelle Wahrnehmung fuer eine neue Sequenz."""
        parts = []

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

        # Sequenz-Memory (Kontext aus vorherigen Sequenzen)
        seq_memory = self._load_sequence_memory()
        if seq_memory:
            parts.append(f"\n{seq_memory}")

        # Nachrichten von Oliver
        messages = self.communication.check_inbox()
        if messages:
            for msg in messages:
                parts.append(f"\nOLIVER SAGT: {msg.get('content', '')}")

        # Aktueller Fokus
        focus = self.goal_stack.get_current_focus()
        parts.append(f"\n{focus}")

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

        # Letzte Erinnerungen
        recent = self.memory.get_recent(n=3)
        if recent:
            parts.append("\nLetzte Erfahrungen:")
            for m in recent:
                parts.append(f"  - {m.get('content', '')[:200]}")

        # Failure-Memory + Skill-Komposition: Vor jeder Sequenz checken
        focus = self.goal_stack.get_current_focus()
        failure_check = self.failure_memory.check(focus)

        # Skill-Komposition: Relevante existierende Tools anzeigen
        composition = self.composer.suggest_composition(focus)
        if composition:
            parts.append(f"\n{composition}")
        if failure_check:
            parts.append(f"\n{failure_check}")

        return "\n".join(parts)

    # === Tool-Ausfuehrung ===

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        """Fuehrt ein Tool aus und trackt Skills, Fehler und Strategien."""
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
            # Semantische Memory: Wichtige Ergebnisse speichern
            if name in ("write_file", "create_tool", "create_project", "modify_own_code"):
                self.semantic_memory.store(
                    f"{name}: {str(tool_input)[:200]} → {result[:200]}",
                    metadata={"tool": name},
                )
            # Output-Tracking
            if name == "write_file":
                self._seq_files_written += 1
            elif name == "create_tool":
                self._seq_tools_built += 1

        return result

    def _execute_tool_inner(self, name: str, tool_input: dict) -> str:
        """Interne Tool-Ausfuehrung."""
        try:
            if name == "write_file":
                return self.actions.write_file(tool_input["path"], tool_input["content"])

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
                return self.goal_stack.create_goal(
                    tool_input["title"],
                    tool_input.get("description", ""),
                    tool_input.get("sub_goals"),
                )

            elif name == "complete_subgoal":
                result = self.goal_stack.complete_subgoal(
                    tool_input["goal_index"],
                    tool_input["subgoal_index"],
                    tool_input.get("result", ""),
                )
                # Auto-Erkennung: Lehrprojekt abgeschlossen → Skill-Update
                if "ZIEL ERREICHT" in result:
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
                # Alten Code lesen fuer Critic-Vergleich (ROHER Dateiinhalt, nicht formatiert)
                try:
                    raw_path = (config.ROOT_PATH / tool_input["path"]).resolve()
                    old_code = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
                except Exception:
                    old_code = ""

                # Dual-Review: Syntax + Gemini pruefen
                review_result = self.code_review.review_and_apply_fix(
                    file_path=tool_input["path"],
                    new_content=tool_input["new_content"],
                    reason=tool_input.get("reason", "Selbstverbesserung"),
                )
                if review_result["accepted"]:
                    # Critic-Agent: Ist es BESSER als vorher?
                    critic = self.critic.evaluate_change(
                        tool_input["path"], old_code[:2000],
                        tool_input["new_content"][:2000],
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
                    lines.append(f"  [{r['similarity']:.0%}] {r['content'][:200]}")
                return "\n".join(lines)

            # === Package Management ===
            elif name == "pip_install":
                return self.pip.install(tool_input["package"])

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
                with open(evidence_path, "w", encoding="utf-8") as f:
                    json.dump(evidence, f, indent=2, ensure_ascii=False)

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
                try:
                    with open(evidence_path, "r", encoding="utf-8") as f:
                        evidence = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError):
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

                # === CROSS-MODEL-REVIEW bei Projekten mit 3+ Dateien ===
                project_path = config.DATA_PATH / "projects" / project_name
                code_files = [f for f in project_path.iterdir()
                              if f.suffix == ".py" and f.name != "tests.py"]
                if len(code_files) >= 3:
                    review = self._cross_model_review(project_name, code_files)
                    if review and not review.get("approved", True):
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

        # Erfahrung speichern
        self.memory.store_experience({
            "type": "sequenz_abschluss",
            "content": summary,
            "valence": 0.7,
            "emotions": {},
            "tags": [f"sequenz_{self.sequences_total}"],
        })

        # Self-Rating
        rating = tool_input.get("performance_rating")
        if rating:
            self.self_rating.add_rating(
                rating,
                tool_input.get("rating_reason", ""),
                self.sequences_total,
            )

        # Mini-Metacognition: 2 Saetze Reflexion
        bottleneck = tool_input.get("bottleneck", "")
        next_time = tool_input.get("next_time_differently", "")
        if bottleneck or next_time:
            self.metacognition.record(bottleneck, next_time, self.sequences_total)

        # Journal
        self.communication.write_journal(summary, self.sequences_total)

        # Sequenz-Memory speichern
        self._save_sequence_memory(summary)

        # Auto-Commit
        commit_msg = f"Sequenz {self.sequences_total}: {summary[:80]}"
        self.git.commit(commit_msg)

        # State speichern
        self.sequences_total += 1
        self.state["sequences_total"] = self.sequences_total
        self.state["last_sequence"] = datetime.now(timezone.utc).isoformat()
        self._save_all()

        return "Sequenz abgeschlossen. State gespeichert."

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
            except Exception:
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
                response = self._call_llm("main_work", self._build_system_prompt(), messages, TOOLS)
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
            pass

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

        print(f"\n{'=' * 60}")
        print(f"  {name} — Agentic Mode")
        print(f"  Sequenzen bisher: {self.sequences_total}")
        print(f"  Tool-Calls bisher: {self.state.get('total_tool_calls', 0)}")
        print(f"  Telegram: {'aktiv' if self.communication.telegram_active else 'aus'}")
        print(f"  Ctrl+C = Pausieren")
        print(f"{'=' * 60}\n")

        try:
            while self.running:
                self._run_sequence()
                self._sequences_since_dream += 1
                self._sequences_since_audit += 1

                # Dream-Konsolidierung (alle 10 Sequenzen)
                if self.dream.should_dream(self._sequences_since_dream):
                    print(f"  {'=' * 40}")
                    print(f"  DREAM — Memory-Konsolidierung...")
                    result = self.dream.dream()
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
                            import json as _json
                            with open(audit_log_path, "r", encoding="utf-8") as f:
                                log = _json.load(f)
                            if log:
                                last_findings = log[-1].get("findings", [])
                                if last_findings:
                                    goals_result = self.self_audit.create_goals_from_findings(
                                        last_findings, self.goal_stack
                                    )
                                    print(f"  {goals_result}")
                    except Exception:
                        pass

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
        "git_commit", "add_task", "complete_task", "create_goal",
        "complete_sub_goal", "finish_sequence", "modify_own_code",
        "store_memory", "set_belief",
    })

    # Lese-Tools: Behalten vollen Inhalt in den letzten N, werden
    # danach auf Zusammenfassung gekuerzt (nicht geloescht)
    _READ_TOOLS = frozenset({
        "read_file", "read_own_code", "execute_python",
        "web_search", "web_read", "run_tool",
    })

    def _compress_old_messages(self, messages: list, keep_recent: int = 6):
        """
        Komprimiert alte Tool-Results um Token zu sparen.

        Strategie (Whitelist statt Blacklist — sicheres Default):
        - _SAFE_TO_COMPRESS Tools: Immer komprimieren wenn alt
        - _READ_TOOLS: Auf 500 Zeichen kuerzen wenn aelter als keep_recent
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

            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue

                original = block.get("content", "")
                if len(original) <= 100:
                    continue  # Schon komprimiert oder kurz

                tool_name = self._find_tool_name_for_id(
                    messages, i, block.get("tool_use_id", ""),
                )

                if tool_name in self._SAFE_TO_COMPRESS:
                    # Schreib-Tools: Auf Einzeiler komprimieren
                    first_line = original.split("\n")[0][:80]
                    block["content"] = f"[OK] {first_line}"

                elif tool_name in self._READ_TOOLS:
                    # Lese-Tools: Auf 500 Zeichen kuerzen (nicht loeschen)
                    if len(original) > 500:
                        block["content"] = original[:500] + "\n[...gekuerzt]"

                elif len(original) > 1500:
                    # Fallback: Sehr grosse unbekannte Blocks trotzdem kuerzen
                    # (z.B. orphaned tool_results ohne zuordenbaren Tool-Namen)
                    block["content"] = original[:500] + "\n[...gekuerzt]"

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

        # System-Prompt einmalig pro Sequenz bauen (nicht pro Step)
        cached_system_prompt = self._build_system_prompt()

        # Evolution erzwingen: Wenn Rhythmus Evolution/Sprint sagt,
        # wird der System-Prompt verstaerkt
        mode = self.rhythm.get_mode(self.state)
        if mode["mode"] in ("evolution", "sprint"):
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
            except Exception:
                pass

        print(f"  {'─' * 56}")
        print(f"  Sequenz {self.sequences_total + 1} [{mode['mode'].upper()}]")
        print()

        for step in range(MAX_STEPS_PER_SEQUENCE):
            # Token-Budget pruefen bevor neuer Call
            if self.sequence_input_tokens >= MAX_INPUT_TOKENS_PER_SEQUENCE:
                print(f"\n  Token-Budget ({MAX_INPUT_TOKENS_PER_SEQUENCE:,} Input-Tokens) erreicht — Sequenz beendet.")
                self._handle_finish_sequence({
                    "summary": f"Sequenz nach {step_count} Steps beendet (Token-Budget).",
                    "performance_rating": 5,
                })
                finished = True
                break

            # Sliding Window: Alte Tool-Results komprimieren ab Step 8
            if step >= 8:
                self._compress_old_messages(messages, keep_recent=6)

            try:
                response = self._call_llm(
                    "main_work", cached_system_prompt, messages, TOOLS
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

            # Antwort anzeigen und serialisieren
            for block in response["content"]:
                if hasattr(block, "text") and block.text.strip():
                    print(f"  {block.text[:200]}")

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

                        input_preview = str(block.input)[:80]
                        print(f"  [{step_count}] {block.name}({input_preview})")

                        result = self._execute_tool(block.name, block.input)
                        result_str = str(result)[:3000]

                        preview = result_str.replace("\n", " ")[:100]
                        print(f"       → {preview}")

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

            elif response["stop_reason"] == "end_turn":
                text_parts = [b.text for b in response["content"] if hasattr(b, "text")]
                summary = " ".join(text_parts)[:500] if text_parts else "Sequenz ohne explizites Ende"
                self._handle_finish_sequence({
                    "summary": summary,
                    "performance_rating": 5,  # Neutral — kein explizites Rating
                    "bottleneck": "Kein explizites finish_sequence aufgerufen",
                    "next_time_differently": "finish_sequence mit Rating nutzen",
                })
                break

        if not finished and step_count >= MAX_STEPS_PER_SEQUENCE:
            print(f"\n  Max Steps ({MAX_STEPS_PER_SEQUENCE}) erreicht — Sequenz beendet.")
            self._handle_finish_sequence({
                "summary": f"Sequenz nach {step_count} Steps automatisch beendet."
            })

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

        # Kosten + Skills anzeigen
        print(f"\n  Sequenz abgeschlossen: {step_count} Calls | "
              f"{self._seq_errors} Fehler | "
              f"${seq_cost:.3f} | "
              f"Session: ${self.llm.session_costs['cost_usd']:.3f}")

        # Skill-Aenderungen anzeigen
        strongest = self.skills.get_strongest_skills(3)
        if strongest:
            print(f"  Top-Skills: {', '.join(strongest)}")

        # Stille-Fehler-Erkennung nach jeder Sequenz
        silent_warnings = self.silent_failure_detector.check_after_sequence(
            self.sequences_total, self._seq_tool_calls
        )
        if silent_warnings:
            print(f"  STILLE FEHLER:")
            for w in silent_warnings:
                print(f"    {w}")

        print()

        self.sequence_input_tokens = 0
        self.sequence_output_tokens = 0
