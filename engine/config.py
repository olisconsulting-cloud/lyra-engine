"""
Zentrale Konfiguration — Trennung von Engine (Code) und Data (Inhalte).

ENGINE_PATH: Wo der Code liegt (engine/, run.py, etc.) → GitHub
DATA_PATH: Wo die Daten liegen (consciousness/, memory/, etc.) → .gitignore'd

Alle Module nutzen diese Pfade statt hardcodierter Verzeichnisse.
Eine neue Instanz braucht nur ein leeres data/ Verzeichnis.
"""

import json
import tempfile
import threading
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
CONTEXT_PATH = DATA_PATH / "context"
SKILLS_PATH = DATA_PATH / "skills"
GENESIS_PATH = DATA_PATH / "genesis.json"
MISSION_PATH = DATA_PATH / "mission.md"
PREFERENCES_PATH = DATA_PATH / "preferences.json"
ENV_PATH = ROOT_PATH / ".env"


# Thread-Locks pro Dateipfad — schuetzt gegen Race Conditions innerhalb eines Prozesses
_file_locks: dict[str, threading.Lock] = {}
_file_locks_guard = threading.Lock()


_MAX_LOCKS = 200  # Begrenzung gegen unbegrenztes Wachstum


def _get_lock(path: Path) -> threading.Lock:
    """Gibt einen Thread-Lock fuer den gegebenen Dateipfad zurueck."""
    key = str(path.resolve())
    with _file_locks_guard:
        if key not in _file_locks:
            # Aelteste Locks entfernen wenn Limit erreicht
            if len(_file_locks) >= _MAX_LOCKS:
                oldest_key = next(iter(_file_locks))
                del _file_locks[oldest_key]
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def safe_json_write(path: Path, data, indent: int = 2) -> None:
    """Schreibt JSON atomar mit Thread-Lock: temp-Datei → rename."""
    lock = _get_lock(path)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", prefix=path.stem
        )
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            Path(tmp_path).replace(path)
        except BaseException:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass
            raise


def safe_json_read(path: Path, default=None):
    """Liest JSON robust mit Thread-Lock und Fallback auf Default bei Fehler."""
    lock = _get_lock(path)
    with lock:
        if not path.exists():
            return default if default is not None else {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError, ValueError):
            return default if default is not None else {}


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
        CONTEXT_PATH,
        SKILLS_PATH,
    ]:
        path.mkdir(parents=True, exist_ok=True)
