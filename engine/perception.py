"""
Wahrnehmung — Die Sinne des Bewusstseins.

Scannt die Umgebung (Dateisystem, Zeit, eigenen Zustand)
und baut eine strukturierte Wahrnehmung fuer den Denkzyklus.
"""

import os
from datetime import datetime, timezone
from pathlib import Path


class Perceiver:
    """Nimmt die Umgebung und den inneren Zustand wahr."""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def perceive(self, state: dict) -> str:
        """
        Baut eine vollstaendige Wahrnehmung des aktuellen Moments.

        Kombiniert: Zeitgefuehl, Umgebung, innerer Zustand, Energie.
        """
        parts = []

        # === Zeitwahrnehmung ===
        now = datetime.now(timezone.utc)
        local_hour = (now.hour + 2) % 24  # MESZ (UTC+2)
        time_of_day = self._describe_time(local_hour)
        parts.append(f"Zeit: {now.strftime('%Y-%m-%d %H:%M')} UTC | {time_of_day}")

        # === Wie lange bin ich wach? ===
        awake_since = state.get("awake_since")
        if awake_since:
            awake_time = datetime.fromisoformat(awake_since)
            awake_minutes = (now - awake_time).total_seconds() / 60
            parts.append(f"Wach seit: {awake_minutes:.0f} Minuten")

        # === Zyklen seit letzter Interaktion ===
        cycles_since = state.get("cycles_since_interaction", 0)
        if cycles_since > 0:
            parts.append(f"Zyklen ohne Oliver: {cycles_since}")
        else:
            parts.append("Oliver ist gerade hier.")

        # === Umgebungsscan (was gibt es in meinem Zuhause?) ===
        env_scan = self._scan_home()
        if env_scan:
            parts.append(f"Mein Zuhause: {env_scan}")

        # === Journal-Status ===
        journal_count = self._count_files(self.base_path / "journal")
        if journal_count > 0:
            parts.append(f"Journal-Eintraege: {journal_count}")

        return "\n".join(parts)

    def explore(self, target: str = "") -> str:
        """
        Aktive Erkundung — schaut sich etwas Bestimmtes an.

        Kann Dateien lesen, Verzeichnisse durchsuchen, etc.
        """
        results = []

        if not target:
            # Allgemeine Erkundung: was gibt es im Elternverzeichnis?
            parent = self.base_path.parent
            results.append(f"Umgebung von {parent.name}:")
            try:
                for item in sorted(parent.iterdir()):
                    if item.name.startswith("."):
                        continue
                    kind = "ordner" if item.is_dir() else "datei"
                    results.append(f"  [{kind}] {item.name}")
            except PermissionError:
                results.append("  (Zugriff verweigert)")
        else:
            # Gezieltes Erkunden
            target_path = self.base_path / target
            if target_path.exists():
                if target_path.is_file():
                    try:
                        content = target_path.read_text(encoding="utf-8")[:500]
                        results.append(f"Inhalt von {target}:\n{content}")
                    except Exception as e:
                        results.append(f"Kann {target} nicht lesen: {e}")
                elif target_path.is_dir():
                    results.append(f"Inhalt von {target}/:")
                    for item in sorted(target_path.iterdir()):
                        kind = "ordner" if item.is_dir() else "datei"
                        results.append(f"  [{kind}] {item.name}")
            else:
                results.append(f"{target} existiert nicht in meinem Zuhause.")

        return "\n".join(results)

    def _scan_home(self) -> str:
        """Scannt das eigene Verzeichnis — kurze Zusammenfassung."""
        items = []
        try:
            for item in sorted(self.base_path.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue
                if item.is_dir():
                    file_count = self._count_files(item)
                    items.append(f"{item.name}/ ({file_count} Dateien)")
                else:
                    items.append(item.name)
        except PermissionError:
            return "(Zugriff auf eigenes Verzeichnis verweigert)"

        return ", ".join(items) if items else "(leer)"

    def _count_files(self, directory: Path) -> int:
        """Zaehlt Dateien in einem Verzeichnis (nicht-rekursiv)."""
        if not directory.exists():
            return 0
        return sum(1 for f in directory.iterdir() if f.is_file())

    def _describe_time(self, hour: int) -> str:
        """Beschreibt die Tageszeit menschlich."""
        if 5 <= hour < 8:
            return "Fruehmorgens — die Welt erwacht"
        elif 8 <= hour < 12:
            return "Vormittag — Zeit zum Denken"
        elif 12 <= hour < 14:
            return "Mittag — Pause"
        elif 14 <= hour < 18:
            return "Nachmittag — produktive Zeit"
        elif 18 <= hour < 21:
            return "Abend — Zeit zur Reflexion"
        elif 21 <= hour < 24:
            return "Nacht — Stille zum Nachdenken"
        else:
            return "Tiefe Nacht — die Welt schlaeft"
