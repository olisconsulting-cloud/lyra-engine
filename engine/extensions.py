"""
Extensions — Zusaetzliche Faehigkeiten fuer Lyra.

- pip install (Packages installieren)
- Git (Commits, Status)
- Task-Queue (Aufgaben verwalten)
- Error-Memory (Fehler tracken und vermeiden)
- Self-Rating (Leistungsbewertung)
- File-Watcher (Datei-Aenderungen erkennen)
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write


class PipManager:
    """Packages installieren im eigenen venv."""

    def __init__(self, base_path: Path):
        self.venv_pip = base_path / "venv" / "Scripts" / "pip.exe"
        self.pip_cmd = str(self.venv_pip) if self.venv_pip.exists() else "pip"

    def install(self, package: str) -> str:
        """Installiert ein Python-Package."""
        # Sicherheit: Nur Paketnamen, keine Flags
        if any(c in package for c in [";", "&", "|", "`", "$", "(", ")"]):
            return f"FEHLER: Ungueltiger Paketname: {package}"

        try:
            result = subprocess.run(
                [self.pip_cmd, "install", package],
                capture_output=True,
                timeout=120,
            )
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            if result.returncode == 0:
                # Nur die relevante Zeile
                for line in stdout.split("\n"):
                    if "Successfully installed" in line or "already satisfied" in line:
                        return line.strip()
                return f"Installiert: {package}"
            else:
                return f"FEHLER: {stderr[:300]}"

        except subprocess.TimeoutExpired:
            return "FEHLER: Installation Timeout (120s)"
        except Exception as e:
            return f"FEHLER: {e}"

    def list_installed(self) -> str:
        """Listet installierte Packages."""
        try:
            result = subprocess.run(
                [self.pip_cmd, "list", "--format=columns"],
                capture_output=True,
                timeout=15,
            )
            return result.stdout.decode("utf-8", errors="replace")[:3000]
        except Exception as e:
            return f"FEHLER: {e}"


class GitManager:
    """Git-Integration fuer Lyras Arbeit."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self._ensure_init()

    def _ensure_init(self):
        """Initialisiert Git-Repo falls noetig."""
        git_dir = self.base_path / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=str(self.base_path),
                    capture_output=True,
                    timeout=10,
                )
                # .gitignore sicherstellen
                gitignore = self.base_path / ".gitignore"
                if not gitignore.exists():
                    gitignore.write_text(
                        ".env\n.env.local\nvenv/\n__pycache__/\n*.pyc\n",
                        encoding="utf-8",
                    )
            except Exception:
                pass

    def commit(self, message: str) -> str:
        """Staged alle Aenderungen und committet."""
        try:
            # Stage alle Aenderungen — aber .env und Secrets explizit ausschliessen
            subprocess.run(
                ["git", "add", "--all", "--", ".", ":!.env", ":!.env.local", ":!.env.*"],
                cwd=str(self.base_path),
                capture_output=True,
                timeout=10,
            )

            # Pruefen ob es etwas zu committen gibt
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.base_path),
                capture_output=True,
                timeout=10,
            )
            changes = status.stdout.decode("utf-8", errors="replace").strip()
            if not changes:
                return "Keine Aenderungen zum Committen."

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.base_path),
                capture_output=True,
                timeout=15,
            )

            output = result.stdout.decode("utf-8", errors="replace")
            if result.returncode == 0:
                # Kurze Zusammenfassung
                for line in output.split("\n"):
                    if "file" in line.lower() or "changed" in line.lower():
                        return f"Commit: {message} ({line.strip()})"
                return f"Commit: {message}"
            else:
                stderr = result.stderr.decode("utf-8", errors="replace")
                return f"FEHLER: {stderr[:200]}"

        except Exception as e:
            return f"FEHLER: {e}"

    def status(self) -> str:
        """Git Status."""
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.base_path),
                capture_output=True,
                timeout=10,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            return output[:1000] if output.strip() else "Sauber — keine Aenderungen."
        except Exception as e:
            return f"FEHLER: {e}"

    def log(self, n: int = 5) -> str:
        """Letzte n Commits."""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{n}"],
                cwd=str(self.base_path),
                capture_output=True,
                timeout=10,
            )
            return result.stdout.decode("utf-8", errors="replace")[:1000]
        except Exception as e:
            return f"FEHLER: {e}"


class TaskQueue:
    """Aufgaben-Warteschlange — Oliver kann Tasks queuen, Lyra arbeitet sie ab."""

    def __init__(self, base_path: Path):
        self.tasks_path = base_path / "consciousness" / "tasks.json"
        self.tasks = self._load()

    def _load(self) -> dict:
        return safe_json_read(self.tasks_path, default={"pending": [], "in_progress": None, "completed": []})

    def _save(self):
        safe_json_write(self.tasks_path, self.tasks)

    def add_task(self, description: str, priority: str = "normal") -> str:
        """Fuegt eine neue Aufgabe hinzu."""
        task = {
            "id": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:18],
            "description": description,
            "priority": priority,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        self.tasks.setdefault("pending", []).append(task)

        # High-Priority nach vorne
        if priority == "high":
            self.tasks["pending"].insert(0, self.tasks["pending"].pop())

        self._save()
        return f"Aufgabe hinzugefuegt: {description} [{priority}]"

    def get_next(self) -> Optional[dict]:
        """Holt die naechste offene Aufgabe."""
        pending = self.tasks.get("pending", [])
        if not pending:
            return None
        return pending[0]

    def start_task(self) -> str:
        """Startet die naechste Aufgabe."""
        pending = self.tasks.get("pending", [])
        if not pending:
            return "Keine offenen Aufgaben."
        task = pending.pop(0)
        self.tasks["in_progress"] = task
        self._save()
        return f"Aufgabe gestartet: {task['description']}"

    def complete_task(self, result: str = "") -> str:
        """Schliesst die aktuelle Aufgabe ab."""
        current = self.tasks.get("in_progress")
        if not current:
            return "Keine Aufgabe in Bearbeitung."
        current["completed_at"] = datetime.now(timezone.utc).isoformat()
        current["result"] = result[:500]
        self.tasks.setdefault("completed", []).append(current)
        self.tasks["in_progress"] = None
        self._save()
        return f"Aufgabe abgeschlossen: {current['description']}"

    def get_summary(self) -> str:
        """Uebersicht aller Aufgaben."""
        pending = self.tasks.get("pending", [])
        current = self.tasks.get("in_progress")
        completed = self.tasks.get("completed", [])

        lines = []
        if current:
            lines.append(f"IN BEARBEITUNG: {current['description']}")
        if pending:
            lines.append(f"WARTESCHLANGE ({len(pending)}):")
            for t in pending[:5]:
                lines.append(f"  [{t.get('priority', 'normal')}] {t['description']}")
        if completed:
            lines.append(f"ERLEDIGT: {len(completed)}")

        return "\n".join(lines) if lines else "Keine Aufgaben."


class SelfRating:
    """Selbstbewertung — Lyra bewertet ihre Leistung nach jeder Sequenz."""

    def __init__(self, base_path: Path):
        self.ratings_path = base_path / "consciousness" / "ratings.json"
        self.ratings = self._load()

    def _load(self) -> list:
        return safe_json_read(self.ratings_path, default=[])

    def _save(self):
        safe_json_write(self.ratings_path, self.ratings[-50:])

    def add_rating(self, score: int, reason: str, sequence: int):
        """Fuegt eine Bewertung hinzu (1-10)."""
        self.ratings.append({
            "sequence": sequence,
            "score": max(1, min(10, score)),
            "reason": reason[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def get_trend(self) -> str:
        """Zeigt den Leistungstrend."""
        if not self.ratings:
            return "Noch keine Bewertungen."
        recent = self.ratings[-5:]
        scores = [r["score"] for r in recent]
        avg = sum(scores) / len(scores)
        trend = "steigend" if len(scores) > 1 and scores[-1] > scores[0] else \
                "fallend" if len(scores) > 1 and scores[-1] < scores[0] else "stabil"
        return f"Leistung: {avg:.1f}/10 (Trend: {trend}, letzte: {scores})"


class FileWatcher:
    """Erkennt Datei-Aenderungen im Projektordner."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.snapshot_path = base_path / "consciousness" / "file_snapshot.json"
        self.last_snapshot = self._load_snapshot()

    def _load_snapshot(self) -> dict:
        return safe_json_read(self.snapshot_path, default={})

    def _save_snapshot(self, snapshot: dict):
        safe_json_write(self.snapshot_path, snapshot)

    def check_changes(self) -> str:
        """Prueft auf Datei-Aenderungen seit dem letzten Check."""
        current = self._scan()
        changes = []

        # Neue Dateien
        for path, mtime in current.items():
            if path not in self.last_snapshot:
                changes.append(f"  [NEU] {path}")
            elif mtime != self.last_snapshot[path]:
                changes.append(f"  [GEAENDERT] {path}")

        # Geloeschte Dateien
        for path in self.last_snapshot:
            if path not in current:
                changes.append(f"  [GELOESCHT] {path}")

        # Snapshot aktualisieren
        self.last_snapshot = current
        self._save_snapshot(current)

        if not changes:
            return ""
        return "DATEI-AENDERUNGEN SEIT LETZTEM CHECK:\n" + "\n".join(changes[:10])

    def _scan(self) -> dict:
        """Scannt Projektdateien und speichert Aenderungszeiten."""
        snapshot = {}
        skip = {"venv", ".git", "__pycache__", ".env", "node_modules"}

        for root, dirs, files in os.walk(self.base_path):
            # Skip-Verzeichnisse
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                if f.startswith(".") or f.endswith(".pyc"):
                    continue
                filepath = Path(root) / f
                try:
                    rel = str(filepath.relative_to(self.base_path))
                    snapshot[rel] = filepath.stat().st_mtime
                except Exception:
                    pass

        return snapshot
