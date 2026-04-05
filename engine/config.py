"""
Zentrale Konfiguration — Trennung von Engine (Code) und Data (Inhalte).

ENGINE_PATH: Wo der Code liegt (engine/, run.py, etc.) → GitHub
DATA_PATH: Wo die Daten liegen (consciousness/, memory/, etc.) → .gitignore'd

Alle Module nutzen diese Pfade statt hardcodierter Verzeichnisse.
Eine neue Instanz braucht nur ein leeres data/ Verzeichnis.
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path

# Stoppwoerter fuer Namens-Normalisierung (Projekte, Goals, Spin-Keys)
STOP_WORDS = frozenset({
    "und", "oder", "fuer", "mit", "der", "die", "das", "ein", "eine",
    "zu", "von", "in", "auf", "an", "bei", "nach", "aus", "um",
    "ueber", "unter", "durch", "gegen", "ohne", "seit",
})


def normalize_name_words(name: str) -> set[str]:
    """Extrahiert normalisierte Inhaltswoerter aus einem Namen (Projekt, Goal, etc.)."""
    return {w for w in re.split(r"[\s\-_:.()\/]+", name.lower()) if len(w) >= 2} - STOP_WORDS


# Keywords die auf Meta-Reflexion statt echte Arbeit hindeuten.
# Zentral definiert — wird von dream.py, goal_stack.py, self_diagnosis.py importiert.
META_GOAL_KEYWORDS = frozenset((
    "finish_sequence", "konsisten", "fruehzeitig", "steps aufrufen",
    "tracking-system", "alert-mechanis", "uebungssequenz", "skill erweit",
    "self-diagnose", "speichermanagement", "reflexion", "routine",
))


def is_meta_goal(title: str) -> bool:
    """Erkennt ob ein Goal-Titel Meta-Reflexion statt echte Arbeit beschreibt."""
    tl = title.lower()
    return any(kw in tl for kw in META_GOAL_KEYWORDS)


# Root = Verzeichnis das run.py enthaelt
ROOT_PATH = Path(__file__).parent.parent

# Engine = Der Code (GitHub-faehig)
ENGINE_PATH = ROOT_PATH / "engine"

# Bootstrap = Universelles Wissen fuer neue Instanzen (Git-tracked)
BOOTSTRAP_PATH = ENGINE_PATH / "bootstrap"

# Data = Die Inhalte (persoenlich, austauschbar)
# PHI_DATA_PATH Env-Variable erlaubt Metatron-Multi-Instanz-Betrieb
_data_override = os.environ.get("PHI_DATA_PATH")
DATA_PATH = Path(_data_override) if _data_override else ROOT_PATH / "data"

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
# .env neben data/ wenn PHI_DATA_PATH gesetzt, sonst Root
ENV_PATH = DATA_PATH.parent / ".env" if _data_override else ROOT_PATH / ".env"


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
