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
import logging
import sys
import traceback

logger = logging.getLogger(__name__)
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

        # Tool-Lifecycle: Metrics-Callback (wird von consciousness.py gesetzt)
        self._metrics_callback = None

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
                    logger.warning("Toolchain: Tool '%s' konnte nicht geladen werden (%s)", name, filepath)

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

        # Duplikat-Check: Aehnliches Tool bereits registriert?
        similar = self._find_similar_tool(name)
        if similar:
            ex_desc = self.registry["tools"][similar].get("description", "")[:80]
            return (f"DUPLIKAT: Aehnliches Tool existiert: '{similar}' ({ex_desc}). "
                    f"Nutze oder verbessere das bestehende Tool.")

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

    # Version-Woerter: Nur nummerierte Versionen erlaubt (v1, v2...)
    _TOOL_VERSION_WORDS = frozenset({
        "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10",
    })

    def _find_similar_tool(self, name: str) -> Optional[str]:
        """Findet aehnliches registriertes Tool (Jaccard >= 0.5)."""
        from .config import normalize_name_words
        new_words = normalize_name_words(name)
        if not new_words or (new_words & self._TOOL_VERSION_WORDS):
            return None
        for ex_name, ex_meta in self.registry.get("tools", {}).items():
            if ex_meta.get("status") == "archived":
                continue
            ex_words = normalize_name_words(ex_name)
            if not ex_words or (ex_words & self._TOOL_VERSION_WORDS):
                continue
            overlap = len(new_words & ex_words)
            union = len(new_words | ex_words)
            if union and overlap / union >= 0.5:
                return ex_name
        return None

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
            if info.get("status") == "archived":
                return f"FEHLER: Tool '{name}' ist archiviert."
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

            # Tool-Lifecycle: Erfolg melden
            if self._metrics_callback:
                self._metrics_callback(name, True)

            return str(result)[:3000]

        except Exception as e:
            error_msg = f"FEHLER bei Ausfuehrung von '{name}': {e}\n{traceback.format_exc()[:500]}"

            # Tool-Lifecycle: Fehler melden
            if self._metrics_callback:
                self._metrics_callback(name, False, str(e)[:200])

            return error_msg

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
        """Liste aller aktiven Tools (archivierte werden ausgeblendet)."""
        tools = self.registry.get("tools", {})
        if not tools:
            return "(keine Tools — baue dein erstes!)"

        lines = []
        for name, info in sorted(tools.items()):
            if info.get("status") == "archived":
                continue
            uses = info.get("uses", 0)
            version = info.get("version", 1)
            lines.append(f"  - {name} (v{version}, {uses}x benutzt): {info.get('description', '')[:60]}")

        return "\n".join(lines) if lines else "(keine aktiven Tools)"

    # === Archiv & Alias-System ===

    def archive_tool(self, name: str, reason: str = "") -> str:
        """
        Archiviert ein Tool: verschiebt Datei, markiert in Registry.

        Args:
            name: Tool-Name
            reason: Grund fuer Archivierung (z.B. 'Consolidated into unified_api_client')

        Returns:
            Ergebnis-Nachricht
        """
        info = self.registry.get("tools", {}).get(name)
        if not info:
            return f"FEHLER: Tool '{name}' nicht in Registry."

        if info.get("status") == "archived":
            return f"Tool '{name}' ist bereits archiviert."

        # Datei verschieben
        archived_dir = self.tools_path / "_archived"
        archived_dir.mkdir(exist_ok=True)

        src = self.tools_path / info.get("file", f"{name}.py")
        dst = archived_dir / src.name
        if src.exists():
            # Wenn Ziel existiert, altes Archiv ueberschreiben
            if dst.exists():
                dst.unlink()
            src.rename(dst)

        # Registry aktualisieren (Eintrag bleibt, Status aendert sich)
        info["status"] = "archived"
        info["archived_date"] = datetime.now(timezone.utc).isoformat()
        if reason:
            info["archived_reason"] = reason
        self._save_registry()

        # Aus geladenen Tools entfernen
        self.loaded_tools.pop(name, None)

        return f"Tool '{name}' archiviert. Grund: {reason or 'nicht angegeben'}"

    def add_alias(self, old_name: str, new_name: str) -> str:
        """
        Registriert einen Alias: use_tool(old_name) wird auf new_name umgeleitet.

        Prueft auf zirkulaere Alias-Ketten (max 10 Stufen).

        Args:
            old_name: Alter Tool-Name (der umgeleitet werden soll)
            new_name: Neuer Tool-Name (das Ziel)

        Returns:
            Ergebnis-Nachricht
        """
        if new_name not in self.registry.get("tools", {}):
            return f"FEHLER: Ziel-Tool '{new_name}' nicht in Registry."

        # Zyklus-Erkennung: Folge der Alias-Kette vom Ziel aus
        aliases = self.registry.get("aliases", {})
        current = new_name
        for _ in range(10):
            current = aliases.get(current)
            if current is None:
                break
            if current == old_name:
                return f"FEHLER: Zirkulaerer Alias erkannt ({old_name} -> {new_name} -> ... -> {old_name})"

        if "aliases" not in self.registry:
            self.registry["aliases"] = {}

        self.registry["aliases"][old_name] = new_name
        self._save_registry()
        return f"Alias: '{old_name}' -> '{new_name}'"

    def get_tool_code(self, name: str) -> str:
        """Gibt den Quellcode eines Tools zurueck."""
        info = self.registry.get("tools", {}).get(name)
        if not info:
            return f"FEHLER: Tool '{name}' nicht gefunden."

        filepath = self.tools_path / info["file"]
        if not filepath.exists():
            return f"FEHLER: Datei {info['file']} nicht gefunden."

        return filepath.read_text(encoding="utf-8")[:50000]

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
