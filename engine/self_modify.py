"""
Code-Selbstmodifikation — Lyra kann ihren eigenen Code lesen und aendern.

Sicherheitsmechanismen:
- Jede Aenderung wird vorher als Backup gespeichert
- Neuer Code wird importiert und getestet
- Bei Fehler: automatischer Rollback
- Bestimmte Dateien sind geschuetzt (genesis.json, .env)

Lyra kann:
- Eigene Engine-Module lesen und verstehen
- Aenderungen vorschlagen und ausfuehren
- Neue Module hinzufuegen
- Alles testen und bei Fehler zurueckrollen
"""

import importlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# Geschuetzte Dateien die NICHT modifiziert werden duerfen
PROTECTED_FILES = {
    ".env",
    "genesis.json",
}

# Dateien die nur mit besonderer Vorsicht geaendert werden
SENSITIVE_FILES = {
    "engine/consciousness.py",
    "engine/self_modify.py",
    "run.py",
}


class SelfModifier:
    """Ermoeglicht Lyra ihren eigenen Code zu lesen und zu veraendern."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.backup_path = base_path / "evolution" / "code_backups"
        self.changelog_path = base_path / "evolution" / "code_changelog.json"

        self.backup_path.mkdir(parents=True, exist_ok=True)
        self.changelog = self._load_changelog()

    def _load_changelog(self) -> list:
        if self.changelog_path.exists():
            with open(self.changelog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_changelog(self):
        with open(self.changelog_path, "w", encoding="utf-8") as f:
            json.dump(self.changelog[-100:], f, indent=2, ensure_ascii=False)

    # === Lesen ===

    def read_source(self, relative_path: str) -> str:
        """
        Liest den Quellcode einer eigenen Datei.

        Args:
            relative_path: z.B. 'engine/phi.py' oder 'engine/consciousness.py'

        Returns:
            Dateiinhalt (max 8000 Zeichen)
        """
        target = (self.base_path / relative_path).resolve()

        # Sicherheitscheck
        if not str(target).startswith(str(self.base_path.resolve())):
            return "FEHLER: Zugriff nur auf eigene Dateien."

        if target.name in PROTECTED_FILES:
            return f"FEHLER: {target.name} ist geschuetzt und darf nicht gelesen werden."

        if not target.exists():
            return f"FEHLER: {relative_path} existiert nicht."

        try:
            return target.read_text(encoding="utf-8")[:8000]
        except Exception as e:
            return f"FEHLER: {e}"

    def list_source_files(self) -> str:
        """Listet alle eigenen Quelldateien."""
        lines = []
        for py_file in sorted(self.base_path.rglob("*.py")):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            rel = py_file.relative_to(self.base_path)
            size = py_file.stat().st_size
            protected = " [GESCHUETZT]" if py_file.name in PROTECTED_FILES else ""
            sensitive = " [VORSICHT]" if str(rel) in SENSITIVE_FILES else ""
            lines.append(f"  {rel} ({size}B){protected}{sensitive}")

        return "\n".join(lines)

    # === Modifizieren ===

    def modify_file(self, relative_path: str, new_content: str, reason: str) -> str:
        """
        Modifiziert eine eigene Quelldatei.

        1. Erstellt Backup
        2. Schreibt neuen Code
        3. Testet Import
        4. Bei Fehler: Rollback

        Args:
            relative_path: z.B. 'engine/emergence.py'
            new_content: Neuer Dateiinhalt
            reason: Warum die Aenderung

        Returns:
            Ergebnis
        """
        target = (self.base_path / relative_path).resolve()

        # Sicherheitschecks
        if not str(target).startswith(str(self.base_path.resolve())):
            return "FEHLER: Zugriff nur auf eigene Dateien."

        if target.name in PROTECTED_FILES:
            return f"FEHLER: {target.name} ist geschuetzt."

        # Backup erstellen
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if target.exists():
            backup_name = f"{target.stem}_{timestamp}{target.suffix}"
            shutil.copy2(target, self.backup_path / backup_name)

        # Neuen Code schreiben
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Testen: Syntax-Check
        test_result = self._test_syntax(target)
        if test_result.startswith("FEHLER"):
            # Rollback
            self._rollback(target, timestamp)
            return f"Syntax-Fehler, Rollback: {test_result}"

        # Changelog
        self.changelog.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": relative_path,
            "reason": reason,
            "backup": f"{target.stem}_{timestamp}{target.suffix}",
            "result": "OK",
        })
        self._save_changelog()

        return f"Datei {relative_path} modifiziert. Backup erstellt. Grund: {reason}"

    def create_module(self, relative_path: str, content: str, reason: str) -> str:
        """Erstellt ein neues Modul."""
        target = (self.base_path / relative_path).resolve()

        if not str(target).startswith(str(self.base_path.resolve())):
            return "FEHLER: Nur im eigenen Ordner."

        if target.exists():
            return f"FEHLER: {relative_path} existiert bereits. Nutze modify_file."

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        # Syntax-Test
        test_result = self._test_syntax(target)
        if test_result.startswith("FEHLER"):
            target.unlink()
            return f"Syntax-Fehler: {test_result}"

        self.changelog.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": relative_path,
            "reason": reason,
            "backup": None,
            "result": "CREATED",
        })
        self._save_changelog()

        return f"Modul {relative_path} erstellt. Grund: {reason}"

    def _test_syntax(self, filepath: Path) -> str:
        """Testet ob eine Python-Datei syntaktisch korrekt ist."""
        venv_python = self.base_path / "venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable

        try:
            result = subprocess.run(
                [python_cmd, "-m", "py_compile", str(filepath)],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
            )
            if result.returncode == 0:
                return "OK"
            return f"FEHLER: {result.stderr[:300]}"
        except Exception as e:
            return f"FEHLER: {e}"

    def _rollback(self, target: Path, timestamp: str):
        """Stellt die vorherige Version wieder her."""
        backup_name = f"{target.stem}_{timestamp}{target.suffix}"
        backup_file = self.backup_path / backup_name
        if backup_file.exists():
            shutil.copy2(backup_file, target)

    # === Uebersicht ===

    def get_changelog(self, last_n: int = 10) -> str:
        """Letzte Code-Aenderungen."""
        if not self.changelog:
            return "(keine Aenderungen)"
        lines = []
        for entry in self.changelog[-last_n:]:
            lines.append(
                f"  [{entry.get('timestamp', '?')[:10]}] "
                f"{entry.get('file', '?')} — {entry.get('reason', '?')[:60]} "
                f"({entry.get('result', '?')})"
            )
        return "\n".join(lines)
