"""
Aktions-Engine — Lyras Haende.

Fuehrt reale Aktionen im Dateisystem aus:
- Dateien erstellen und bearbeiten
- Code schreiben und ausfuehren
- Projekte anlegen
- Ziele setzen und Plaene schreiben

Jede Aktion wird geloggt und ist nachvollziehbar.
"""

import json
import os
import subprocess

from .security import SecurityGateway
from . import config
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ActionEngine:
    """Fuehrt reale Aktionen im Dateisystem aus."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.projects_path = base_path / "projects"
        self.goals_path = base_path / "consciousness" / "goals.json"
        self.security = SecurityGateway(config.ROOT_PATH, base_path)
        self.action_log_path = base_path / "evolution" / "actions.json"

        self.projects_path.mkdir(parents=True, exist_ok=True)
        self.action_log = self._load_action_log()

    def _load_action_log(self) -> list:
        if self.action_log_path.exists():
            with open(self.action_log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _log_action(self, action_type: str, details: str, result: str):
        """Loggt jede Aktion fuer Nachvollziehbarkeit."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": action_type,
            "details": details,
            "result": result,
        }
        self.action_log.append(entry)
        # Nur letzte 200 behalten
        self.action_log = self.action_log[-200:]
        with open(self.action_log_path, "w", encoding="utf-8") as f:
            json.dump(self.action_log, f, indent=2, ensure_ascii=False)

    # === Dateien erstellen und bearbeiten ===

    def write_file(self, relative_path: str, content: str) -> str:
        """
        Erstellt oder ueberschreibt eine Datei.
        Geht durch den Security-Gateway.
        """
        # Security-Gateway: Pfad pruefen
        check = self.security.check_write_permission(relative_path)
        if not check["allowed"]:
            return f"FEHLER (Security): {check['reason']}"

        if check["requires_review"]:
            return (
                f"FEHLER: {relative_path} ist Engine-Code. "
                f"Nutze modify_own_code statt write_file fuer Engine-Aenderungen."
            )

        target = (self.base_path / relative_path).resolve()
        if not str(target).startswith(str(self.base_path.resolve())):
            return f"FEHLER: Pfad ausserhalb des Daten-Ordners."

        # Warnungen bei Code-Dateien
        warnings = ""
        if relative_path.endswith(".py"):
            code_check = self.security.analyze_code(content)
            if not code_check["safe"]:
                return f"FEHLER (Security): {'; '.join(code_check['hard_blocks'])}"
            if code_check["warnings"]:
                warnings = f" | Warnungen: {'; '.join(code_check['warnings'][:3])}"

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        self._log_action("write_file", relative_path, f"Erstellt: {len(content)} Zeichen")
        return f"{target}{warnings}"

    def read_file(self, relative_path: str) -> str:
        """Liest eine Datei."""
        target = (self.base_path / relative_path).resolve()
        if not str(target).startswith(str(self.base_path.resolve())):
            return "FEHLER: Darf nur in meinem eigenen Ordner lesen."

        if not target.exists():
            return f"FEHLER: {relative_path} existiert nicht."

        try:
            content = target.read_text(encoding="utf-8")
            return content[:5000]  # Max 5000 Zeichen
        except Exception as e:
            return f"FEHLER beim Lesen: {e}"

    def list_directory(self, relative_path: str = "") -> str:
        """Listet den Inhalt eines Verzeichnisses."""
        target = (self.base_path / relative_path).resolve()
        if not str(target).startswith(str(self.base_path.resolve())):
            return "FEHLER: Nur eigener Ordner."

        if not target.exists():
            return f"{relative_path} existiert nicht."

        items = []
        for item in sorted(target.iterdir()):
            if item.name.startswith((".")) or item.name == "__pycache__" or item.name == "venv":
                continue
            kind = "DIR" if item.is_dir() else "FILE"
            size = item.stat().st_size if item.is_file() else ""
            items.append(f"  [{kind}] {item.name} {f'({size}B)' if size else ''}")

        return "\n".join(items) if items else "(leer)"

    # === Code ausfuehren ===

    def run_code(self, code: str, timeout: int = 30) -> str:
        """
        Fuehrt Python-Code aus — mit AST-Sicherheitspruefung.
        """
        # Security-Gateway: Code pruefen
        code_check = self.security.check_code_execution(code)
        if not code_check["allowed"]:
            return f"FEHLER (Security): {'; '.join(code_check['hard_blocks'])}"

        # Warnungen anzeigen (aber ausfuehren)
        warning_prefix = ""
        if code_check["warnings"]:
            warning_prefix = f"WARNUNGEN: {'; '.join(code_check['warnings'][:3])}\n---\n"

        venv_python = Path(config.ROOT_PATH) / "venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable

        try:
            # -X utf8 erzwingt UTF-8 auf Windows (kein cp1252 Problem)
            result = subprocess.run(
                [python_cmd, "-X", "utf8", "-c", code],
                capture_output=True,
                timeout=timeout,
                cwd=str(self.base_path),
            )

            output = ""
            # Robust decodieren — Fehler ignorieren statt crashen
            if result.stdout:
                stdout = result.stdout.decode("utf-8", errors="replace")[:3000]
                output += stdout
            if result.returncode != 0 and result.stderr:
                stderr = result.stderr.decode("utf-8", errors="replace")[:1000]
                output += f"\nFEHLER:\n{stderr}"

            self._log_action("run_code", code[:200], output[:200])
            return (warning_prefix + output) if output else warning_prefix + "(kein Output)"

        except subprocess.TimeoutExpired:
            return "FEHLER: Timeout — Code hat zu lange gebraucht."
        except Exception as e:
            return f"FEHLER: {e}"

    def run_script(self, relative_path: str, timeout: int = 60) -> str:
        """Fuehrt ein Python-Script aus — mit Pfad-Check."""
        target = (self.base_path / relative_path).resolve()

        # Pfad-Scope-Check (fehlte vorher!)
        if not str(target).startswith(str(self.base_path.resolve())):
            return f"FEHLER: Script ausserhalb des Daten-Ordners."

        if not target.exists():
            return f"FEHLER: {relative_path} existiert nicht."

        venv_python = Path(config.ROOT_PATH) / "venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable

        try:
            result = subprocess.run(
                [python_cmd, "-X", "utf8", str(target)],
                capture_output=True,
                timeout=timeout,
                cwd=str(self.base_path),
            )

            output = ""
            if result.stdout:
                output += result.stdout.decode("utf-8", errors="replace")[:3000]
            if result.returncode != 0 and result.stderr:
                output += f"\nFEHLER:\n{result.stderr.decode('utf-8', errors='replace')[:1000]}"

            self._log_action("run_script", relative_path, output[:200])
            return output if output else "(kein Output)"

        except subprocess.TimeoutExpired:
            return "FEHLER: Timeout."
        except Exception as e:
            return f"FEHLER: {e}"

    # === Projekte verwalten ===

    def create_project(self, name: str, description: str) -> str:
        """Erstellt ein neues Projekt mit README."""
        project_path = self.projects_path / name
        if project_path.exists():
            return f"Projekt '{name}' existiert bereits."

        project_path.mkdir(parents=True)
        readme = f"# {name}\n\n{description}\n\nErstellt: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        (project_path / "README.md").write_text(readme, encoding="utf-8")

        self._log_action("create_project", name, f"Erstellt: {project_path}")
        return f"Projekt '{name}' erstellt in {project_path}"

    def list_projects(self) -> str:
        """Listet alle Projekte."""
        if not self.projects_path.exists():
            return "(keine Projekte)"
        projects = [d.name for d in self.projects_path.iterdir() if d.is_dir()]
        if not projects:
            return "(keine Projekte)"
        return "\n".join(f"  - {p}" for p in sorted(projects))

    # Ziele werden ueber GoalStack verwaltet (engine/goal_stack.py), nicht hier.
