"""
ToolContext — Dependency-Container fuer Tool-Handler.

Jeder Handler bekommt einen ToolContext statt 25 self.*-Attribute.
Der Context wird einmal in consciousness.py erstellt und an alle Handler weitergegeben.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Alle Dependencies die Tool-Handler brauchen, gebündelt in einem Objekt.

    Typen sind Any um zirkulaere Imports zu vermeiden —
    die echten Typen leben in ihren jeweiligen Modulen.
    """

    # Kern-Systeme
    actions: Any = None              # ActionEngine
    toolchain: Any = None            # Toolchain
    goal_stack: Any = None           # GoalStack
    seq_intel: Any = None            # SequenceIntelligence
    communication: Any = None        # CommunicationEngine
    semantic_memory: Any = None      # SemanticMemory
    web: Any = None                  # WebAccess
    proactive_learner: Any = None    # ProactiveLearner

    # Code-Qualitaet
    self_modify: Any = None          # SelfModifier
    code_review: Any = None          # DualReviewSystem
    critic: Any = None               # CriticAgent
    composer: Any = None             # SkillComposer
    foundry: Any = None              # ToolFoundry
    learning: Any = None             # LearningEngine
    skills: Any = None               # SkillTracker

    # Infrastruktur
    pip: Any = None                  # PipManager
    git: Any = None                  # GitManager
    task_queue: Any = None           # TaskQueue

    # Diagnose
    integration_tester: Any = None   # IntegrationTester
    dependency_analyzer: Any = None  # DependencyAnalyzer
    silent_failure_detector: Any = None  # SilentFailureDetector

    # Laufzeit-State (mutable — wird pro Sequenz zurueckgesetzt)
    sequences_total: int = 0
    _installed_packages: set = field(default_factory=set)
    _seq_force_used: int = 0

    # Callbacks in consciousness.py (fuer Dinge die nicht extrahiert werden koennen)
    opus_goal_planning: Any = None       # Callable: (title, desc) -> list[str]|None
    opus_result_validation: Any = None   # Callable: (name, criteria, verified) -> dict|None
    cross_model_review: Any = None       # Callable: (name, files) -> dict|None
    check_markdown_quality: Any = None   # Callable: (content) -> list[str]
    save_all: Any = None                 # Callable: () -> None
    handle_finish_sequence: Any = None   # Callable: (tool_input) -> str
