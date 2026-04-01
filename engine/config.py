"""
Zentrale Konfiguration — Trennung von Engine (Code) und Data (Inhalte).

ENGINE_PATH: Wo der Code liegt (engine/, run.py, etc.) → GitHub
DATA_PATH: Wo die Daten liegen (consciousness/, memory/, etc.) → .gitignore'd

Alle Module nutzen diese Pfade statt hardcodierter Verzeichnisse.
Eine neue Instanz braucht nur ein leeres data/ Verzeichnis.
"""

from pathlib import Path

# Root = Verzeichnis das run.py enthaelt
ROOT_PATH = Path(__file__).parent.parent

# Engine = Der Code (GitHub-faehig)
ENGINE_PATH = ROOT_PATH / "engine"

# Data = Die Inhalte (persoenlich, austauschbar)
DATA_PATH = ROOT_PATH / "data"

# Sub-Pfade innerhalb von data/
CONSCIOUSNESS_PATH = DATA_PATH / "consciousness"
MEMORY_PATH = DATA_PATH / "memory"
JOURNAL_PATH = DATA_PATH / "journal"
MESSAGES_PATH = DATA_PATH / "messages"
EVOLUTION_PATH = DATA_PATH / "evolution"
PROJECTS_PATH = DATA_PATH / "projects"
TOOLS_PATH = DATA_PATH / "tools"
GENESIS_PATH = DATA_PATH / "genesis.json"
ENV_PATH = ROOT_PATH / ".env"


def ensure_data_dirs():
    """Erstellt alle notwendigen Daten-Verzeichnisse."""
    for path in [
        CONSCIOUSNESS_PATH,
        MEMORY_PATH / "experiences",
        MEMORY_PATH / "reflections",
        MEMORY_PATH / "semantic",
        JOURNAL_PATH,
        MESSAGES_PATH / "inbox",
        MESSAGES_PATH / "outbox",
        EVOLUTION_PATH / "rollback",
        EVOLUTION_PATH / "code_backups",
        PROJECTS_PATH,
        TOOLS_PATH,
    ]:
        path.mkdir(parents=True, exist_ok=True)
