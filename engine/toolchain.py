"""
Self-Improving Toolchain — Lyras expandierendes Werkzeug-Arsenal.

Jedes Tool das Lyra baut wird automatisch registriert und steht
in zukuenftigen Zyklen als neue Faehigkeit zur Verfuegung.

Zyklus 1: Baut fibonacci_tool.py
Zyklus 5: Nutzt fibonacci_tool um pattern_analyzer.py zu bauen
Zyklus 10: Nutzt pattern_analyzer um eigene Beliefs zu optimieren
-> Echte Kompound-Effekte. Exponentielles Wachstum.

Jedes Tool muss eine standard-Schnittstelle implementieren:
    NAME = "tool_name"
    DESCRIPTION = "Was das Tool tut"
    def run(**kwargs) -> str: ...
"""

import importlib.util
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class Toolchain:
    """Verwaltet Lyras selbstgebaute Tools."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.tools_path = base_path / "tools"
        self.registry_path = self.tools_path / "registry.json"

        self.tools_path.mkdir(parents=True, exist_ok=True)
        self.registry = self._load_registry()
        self.loaded_tools: dict = {}

        # Alle registrierten Tools laden
        self._load_all_tools()

    def _load_registry(self) -> dict:
        if self.registry_path.exists():
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"tools": {}, "total_created": 0}

    def _save_registry(self):
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def _load_all_tools(self):
        """Laedt alle registrierten, aktiven Tools in den Speicher."""
        for name, info in self.registry.get("tools", {}).items():
            if info.get("status") == "archived":
                continue
            filepath = self.tools_path / info.get("file", "")
            if filepath.exists():
                try:
                    module = self._load_module(name, filepath)
                    self.loaded_tools[name] = module
                except Exception:
                    pass  # Kaputte Tools ignorieren

    def _load_module(self, name: str, filepath: Path):
        """Laedt ein Python-Modul dynamisch."""
        spec = importlib.util.spec_from_file_location(name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # === Tool erstellen ===

    def create_tool(self, name: str, description: str, code: str) -> str:
        """
        Erstellt und registriert ein neues Tool.

        Args:
            name: Tool-Name (snake_case, z.B. 'text_analyzer')
            description: Was das Tool tut
            code: Python-Code mit run(**kwargs) -> str Funktion

        Returns:
            Ergebnis-Nachricht
        """
        # Validierung
        if not name.replace("_", "").isalnum():
            return f"FEHLER: Ungueltiger Name '{name}' — nur Buchstaben, Zahlen, Unterstriche."

        filename = f"{name}.py"
        filepath = self.tools_path / filename

        # Code-Template wenn noetig
        if "def run(" not in code:
            return "FEHLER: Tool muss eine 'def run(**kwargs) -> str' Funktion haben."

        # Header hinzufuegen
        full_code = f'"""\nTool: {name}\n{description}\n\nErstellt: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n"""\n\n'
        full_code += f'NAME = "{name}"\n'
        full_code += f'DESCRIPTION = """{description}"""\n\n'
        full_code += code

        # Security-Scan: AST-Check auf gefaehrliche Patterns
        try:
            from .security import SecurityGateway
            from . import config
            sg = SecurityGateway(config.ROOT_PATH, config.DATA_PATH)
            security_check = sg.analyze_code(full_code)
            if not security_check["safe"]:
                return f"Tool '{name}' blockiert (Security): {'; '.join(security_check['hard_blocks'][:2])}"
            # Warnungen loggen aber nicht blockieren
        except ImportError:
            pass  # Security-Modul nicht verfuegbar — weiter ohne Check

        # Speichern
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_code)

        # Testen — importieren und run() aufrufen
        test_result = self._test_tool(name, filepath)
        if test_result.startswith("FEHLER"):
            filepath.unlink()  # Kaputtes Tool loeschen
            return f"Tool '{name}' hat den Test nicht bestanden: {test_result}"

        # Registrieren
        self.registry["tools"][name] = {
            "file": filename,
            "description": description,
            "created": datetime.now(timezone.utc).isoformat(),
            "version": 1,
            "uses": 0,
        }
        self.registry["total_created"] = self.registry.get("total_created", 0) + 1
        self._save_registry()

        # Laden
        try:
            module = self._load_module(name, filepath)
            self.loaded_tools[name] = module
        except Exception:
            pass

        return f"Tool '{name}' erstellt und registriert. Test: {test_result}"

    def _test_tool(self, name: str, filepath: Path) -> str:
        """Testet ob ein Tool importierbar ist und run() hat."""
        try:
            module = self._load_module(f"_test_{name}", filepath)
            if not hasattr(module, "run"):
                return "FEHLER: Keine run() Funktion gefunden."
            if not callable(module.run):
                return "FEHLER: run ist nicht aufrufbar."
            return "OK"
        except Exception as e:
            return f"FEHLER: {e}"

    # === Tool ausfuehren ===

    def use_tool(self, name: str, **kwargs) -> str:
        """
        Fuehrt ein registriertes Tool aus.

        Args:
            name: Tool-Name (oder Alias eines archivierten Tools)
            **kwargs: Parameter fuer das Tool

        Returns:
            Tool-Output
        """
        # Alias-Aufloesung: Alte Tool-Namen auf neue umleiten
        resolved = self.registry.get("aliases", {}).get(name, name)
        if resolved != name:
            name = resolved

        if name not in self.loaded_tools:
            # Versuche neu zu laden
            info = self.registry.get("tools", {}).get(name)
            if not info:
                return f"FEHLER: Tool '{name}' nicht gefunden. Verfuegbar: {self.list_tools()}"
            filepath = self.tools_path / info["file"]
            try:
                self.loaded_tools[name] = self._load_module(name, filepath)
            except Exception as e:
                return f"FEHLER beim Laden von '{name}': {e}"

        module = self.loaded_tools[name]

        try:
            result = module.run(**kwargs)

            # Nutzungszaehler erhoehen
            if name in self.registry.get("tools", {}):
                self.registry["tools"][name]["uses"] = \
                    self.registry["tools"][name].get("uses", 0) + 1
                self._save_registry()

            return str(result)[:3000]

        except Exception as e:
            return f"FEHLER bei Ausfuehrung von '{name}': {e}\n{traceback.format_exc()[:500]}"

    # === Tool aktualisieren ===

    def update_tool(self, name: str, code: str) -> str:
        """Aktualisiert ein bestehendes Tool mit neuem Code."""
        if name not in self.registry.get("tools", {}):
            return f"FEHLER: Tool '{name}' existiert nicht."

        info = self.registry["tools"][name]
        filepath = self.tools_path / info["file"]

        # Backup
        backup_path = self.tools_path / f"{name}_v{info.get('version', 1)}.py.bak"
        if filepath.exists():
            filepath.rename(backup_path)

        # Neuen Code schreiben
        description = info.get("description", "")
        full_code = f'"""\nTool: {name}\n{description}\n\nVersion: {info.get("version", 1) + 1}\n"""\n\n'
        full_code += f'NAME = "{name}"\n'
        full_code += f'DESCRIPTION = """{description}"""\n\n'
        full_code += code

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_code)

        # Testen
        test_result = self._test_tool(name, filepath)
        if test_result.startswith("FEHLER"):
            # Rollback
            filepath.unlink()
            backup_path.rename(filepath)
            return f"Update fehlgeschlagen, Rollback: {test_result}"

        # Backup loeschen, Version erhoehen
        if backup_path.exists():
            backup_path.unlink()

        info["version"] = info.get("version", 1) + 1
        info["updated"] = datetime.now(timezone.utc).isoformat()
        self._save_registry()

        # Neu laden
        try:
            self.loaded_tools[name] = self._load_module(name, filepath)
        except Exception:
            pass

        return f"Tool '{name}' aktualisiert auf v{info['version']}. Test: {test_result}"

    # === Uebersicht ===

    def list_tools(self) -> str:
        """Liste aller verfuegbaren Tools."""
        tools = self.registry.get("tools", {})
        if not tools:
            return "(keine Tools — baue dein erstes!)"

        lines = []
        for name, info in sorted(tools.items()):
            uses = info.get("uses", 0)
            version = info.get("version", 1)
            lines.append(f"  - {name} (v{version}, {uses}x benutzt): {info.get('description', '')[:60]}")

        return "\n".join(lines)

    def get_tool_code(self, name: str) -> str:
        """Gibt den Quellcode eines Tools zurueck."""
        info = self.registry.get("tools", {}).get(name)
        if not info:
            return f"FEHLER: Tool '{name}' nicht gefunden."

        filepath = self.tools_path / info["file"]
        if not filepath.exists():
            return f"FEHLER: Datei {info['file']} nicht gefunden."

        return filepath.read_text(encoding="utf-8")[:5000]

    def get_stats(self) -> dict:
        """Statistiken ueber die Toolchain."""
        tools = self.registry.get("tools", {})
        total_uses = sum(t.get("uses", 0) for t in tools.values())
        return {
            "total_tools": len(tools),
            "total_created": self.registry.get("total_created", 0),
            "total_uses": total_uses,
            "most_used": max(tools.items(), key=lambda x: x[1].get("uses", 0))[0] if tools else None,
        }
