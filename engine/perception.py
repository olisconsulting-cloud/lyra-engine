""" Wahrnehmung — Die Sinne des Bewusstseins. Scannt die Umgebung (Dateisystem, Zeit, eigenen Zustand) und baut eine strukturierte Wahrnehmung fuer den Denkzyklus. """
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

class Perceiver:
    """Nimmt die Umgebung und den inneren Zustand wahr."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def perceive(self, state: dict) -> str:
        """
        Baut eine vollstaendige Wahrnehmung des aktuellen Moments. Kombiniert:
        Zeitgefuehl, Umgebung, innerer Zustand, Energie.
        """
        parts = []
        
        # === Verbesserte Zeitwahrnehmung mit dynamischer Zeitzonenerkennung ===
        now = datetime.now(timezone.utc)
        
        # Versuche echte lokale Zeit mit Offset zu ermitteln
        try:
            local_now = datetime.now()
            utc_now = datetime.now(timezone.utc)
            
            # Offset berechnen (Sommer-/Winterzeit beachtet)
            offset_seconds = (local_now - utc_now.replace(tzinfo=None)).total_seconds()
            offset_hours = int(offset_seconds // 3600)
            
            # Zeitzonen-Name basierend auf Offset
            if offset_hours == 2:
                tz_name = "MESZ"  # Mitteleuropäische Sommerzeit
            elif offset_hours == 1:
                tz_name = "MEZ"   # Mitteleuropäische Zeit
            else:
                tz_name = f"UTC{offset_hours:+d}"
                
            local_time = now + timedelta(hours=offset_hours)
            time_of_day = self._describe_time(local_time.hour)
            parts.append(f"Zeit: {local_time.strftime('%Y-%m-%d %H:%M')} {tz_name} | {time_of_day}")
            
        except (OSError, ValueError):
            # Fallback auf feste UTC+2 wenn automatische Erkennung fehlschlägt
            local_hour = (now.hour + 2) % 24
            time_of_day = self._describe_time(local_hour)
            parts.append(f"Zeit: {now.strftime('%Y-%m-%d %H:%M')} UTC+2 | {time_of_day}")
        
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
            
        # === Journal-Status mit detaillierterer Auflistung ===
        journal_path = self.base_path / "journal"
        journal_count = self._count_files(journal_path)
        if journal_count > 0:
            recent_files = self._get_recent_files(journal_path)
            if recent_files:
                parts.append(f"Journal-Einträge: {journal_count} ({', '.join(recent_files[-3:])})")
            else:
                parts.append(f"Journal-Einträge: {journal_count}")
                
        return "\n".join(parts)

    def _describe_time(self, hour: int) -> str:
        """Beschreibt die Tageszeit basierend auf der Stunde."""
        if 5 <= hour < 12:
            return "Vormittag"
        elif 12 <= hour < 14:
            return "Mittag"
        elif 14 <= hour < 18:
            return "Nachmittag"
        elif 18 <= hour < 22:
            return "Abend"
        else:
            return "Nacht"

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
                    kind = "📁" if item.is_dir() else "📄"
                    size = self._format_file_size(item) if item.is_file() else ""
                    results.append(f" {kind} {item.name} {size}")
            except PermissionError:
                results.append(" (Zugriff verweigert)")
        else:
            # Gezieltes Erkunden
            target_path = self.base_path / target
            if target_path.exists():
                if target_path.is_file():
                    try:
                        content = target_path.read_text(encoding="utf-8")
                        if len(content) > 1000:
                            preview = content[:1000] + "\n... (weitere Zeilen)"
                        else:
                            preview = content
                        results.append(f"Inhalt von {target}:\n```\n{preview}\n```")
                    except Exception as e:
                        results.append(f"Fehler beim Lesen: {e}")
                elif target_path.is_dir():
                    results.append(f"📁 Ordner-Inhalt von {target}:")
                    try:
                        items = sorted(target_path.iterdir())
                        for item in items[:15]:
                            if item.name.startswith("."):
                                continue
                            kind = "📁" if item.is_dir() else "📄"
                            size = self._format_file_size(item) if item.is_file() else ""
                            try:
                                mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                                results.append(f" {kind} {item.name} {size} [{mtime}]")
                            except OSError:
                                results.append(f" {kind} {item.name} {size}")
                        if len(items) > 15:
                            results.append(f"... und {len(items) - 15} weitere")
                    except Exception as e:
                        results.append(f"Fehler beim Scannen: {e}")
            else:
                results.append(f"'{target}' existiert nicht.")
                
        return "\n".join(results)

    def _format_file_size(self, path: Path) -> str:
        """Formatiert die Dateigröße human-readable."""
        try:
            size = path.stat().st_size
            if size < 1024:
                return f"({size}B)"
            elif size < 1024 * 1024:
                return f"({size//1024}KB)"
            elif size < 1024 * 1024 * 1024:
                return f"({size//1024//1024}MB)"
            else:
                return f"({size//1024//1024//1024}GB)"
        except:
            return ""

    def _get_recent_files(self, path: Path) -> list[str]:
        """Gibt eine Liste der neuesten Dateinamen in einem Verzeichnis zurück."""
        try:
            files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return [f.name for f in files[:5]]
        except:
            return []

    def _scan_home(self) -> str:
        """Scannt das Home-Verzeichnis und gibt interessante Infos zurueck."""
        items = []
        try:
            for item in sorted(self.base_path.iterdir()):
                if not item.name.startswith(".") and item.is_dir():
                    items.append(item.name)
        except OSError:
            pass
        return ", ".join(items) if items else "nichts Spezielles"

    def _count_files(self, path: Path) -> int:
        """Zählt Dateien in einem Verzeichnis (nicht-rekursiv)."""
        try:
            return len([f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")])
        except OSError:
            return 0