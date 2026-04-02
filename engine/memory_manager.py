"""
Fibonacci-Gedaechtnis — Erinnerungen mit phi-gewichtetem Decay.

Organisiert in Fibonacci-Buckets: Neueste Erinnerungen in feiner Aufloesung,
aeltere Erinnerungen konsolidiert — wie menschliches Gedaechtnis.

Frisches verblasst schnell, aber was ueberlebt, bleibt lange.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .phi import phi_decay, fibonacci_bucket, PHI


class MemoryManager:
    """Verwaltet das Gedaechtnis des Bewusstseins."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.experiences_path = base_path / "experiences"
        self.reflections_path = base_path / "reflections"
        self.index_path = base_path / "index.json"

        # Verzeichnisse sicherstellen
        self.experiences_path.mkdir(parents=True, exist_ok=True)
        self.reflections_path.mkdir(parents=True, exist_ok=True)

        self.index = self._load_index()

    def _load_index(self) -> dict:
        default = {
            "experiences": [],
            "reflections": [],
            "total_experiences": 0,
            "total_reflections": 0,
        }
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError):
                return default
        return default

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)

    # === Erfahrungen ===

    def store_experience(self, experience: dict) -> str:
        """
        Speichert eine neue Erfahrung.

        Args:
            experience: Dict mit 'type', 'content', 'valence', 'emotions', 'tags'

        Returns:
            ID der gespeicherten Erfahrung
        """
        exp_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "id": exp_id,
            "timestamp": timestamp,
            "type": experience.get("type", "unknown"),
            "content": experience.get("content", ""),
            "valence": experience.get("valence", 0.0),
            "emotions": experience.get("emotions", {}),
            "tags": experience.get("tags", []),
        }

        # Als Datei speichern
        filename = f"{timestamp[:10]}_{exp_id}.json"
        filepath = self.experiences_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        # Index aktualisieren
        self.index["experiences"].append({
            "id": exp_id,
            "timestamp": timestamp,
            "type": entry["type"],
            "file": filename,
            "valence": entry["valence"],
        })
        self.index["total_experiences"] += 1
        self._save_index()

        return exp_id

    def store_reflection(self, reflection: dict) -> str:
        """Speichert eine Selbstreflexion."""
        ref_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = {
            "id": ref_id,
            "timestamp": timestamp,
            "content": reflection.get("content", ""),
            "insights": reflection.get("insights", []),
            "cycle": reflection.get("cycle", 0),
            "triggered_by": reflection.get("triggered_by", "routine"),
        }

        filename = f"{timestamp[:10]}_{ref_id}.json"
        filepath = self.reflections_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        self.index["reflections"].append({
            "id": ref_id,
            "timestamp": timestamp,
            "file": filename,
        })
        self.index["total_reflections"] += 1
        self._save_index()

        return ref_id

    # === Abruf ===

    def retrieve_relevant(self, top_k: int = 5) -> list[dict]:
        """
        Holt die relevantesten Erinnerungen basierend auf phi-Decay.

        Neuere Erinnerungen wiegen staerker, aber alte bleiben erhalten.
        Starke Emotionen (hohe Valenz) bekommen einen Boost — wie beim Menschen.
        """
        now = datetime.now(timezone.utc)
        scored = []

        for entry in self.index.get("experiences", []):
            exp_time = datetime.fromisoformat(entry["timestamp"])
            age_minutes = (now - exp_time).total_seconds() / 60.0
            bucket = fibonacci_bucket(age_minutes)

            # Phi-Decay Score
            score = phi_decay(bucket, base_relevance=1.0)

            # Valenz-Boost: Starke Emotionen bleiben laenger relevant
            valence_boost = abs(entry.get("valence", 0)) * 0.3
            score += valence_boost

            scored.append((score, entry))

        # Nach Score sortieren, Top-K zurueckgeben
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, entry in scored[:top_k]:
            filepath = self.experiences_path / entry["file"]
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        full = json.load(f)
                        full["retrieval_score"] = round(score, 4)
                        results.append(full)
                except (json.JSONDecodeError, ValueError):
                    continue

        return results

    def get_recent(self, n: int = 3) -> list[dict]:
        """Holt die n neuesten Erfahrungen."""
        recent_entries = self.index.get("experiences", [])[-n:]
        results = []
        for entry in reversed(recent_entries):
            filepath = self.experiences_path / entry["file"]
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, ValueError):
                    continue
        return results

    def get_recent_reflections(self, n: int = 3) -> list[dict]:
        """Holt die n neuesten Reflexionen."""
        recent = self.index.get("reflections", [])[-n:]
        results = []
        for entry in reversed(recent):
            filepath = self.reflections_path / entry["file"]
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        results.append(json.load(f))
                except (json.JSONDecodeError, ValueError):
                    continue
        return results

    def get_stats(self) -> dict:
        """Statistiken ueber das Gedaechtnis."""
        exps = self.index.get("experiences", [])
        return {
            "total_experiences": self.index.get("total_experiences", 0),
            "total_reflections": self.index.get("total_reflections", 0),
            "oldest_memory": exps[0]["timestamp"] if exps else None,
            "newest_memory": exps[-1]["timestamp"] if exps else None,
        }

    # === Konsolidierung ===

    def consolidate(self, max_per_bucket: int = 5) -> int:
        """
        Fibonacci-Konsolidierung: Behalte nur die relevantesten
        Erinnerungen pro Bucket. Aeltere Buckets behalten weniger.

        Bucket 0-2: max_per_bucket Eintraege
        Bucket 3-5: max_per_bucket / phi Eintraege
        Bucket 6+:  max_per_bucket / phi^2 Eintraege

        Returns:
            Anzahl entfernter Erinnerungen
        """
        now = datetime.now(timezone.utc)
        buckets: dict[int, list] = {}

        for entry in self.index.get("experiences", []):
            exp_time = datetime.fromisoformat(entry["timestamp"])
            age_minutes = (now - exp_time).total_seconds() / 60.0
            bucket = fibonacci_bucket(age_minutes)
            buckets.setdefault(bucket, []).append(entry)

        kept = []
        removed_files = []

        for bucket_level, entries in sorted(buckets.items()):
            if bucket_level <= 2:
                limit = max_per_bucket
            elif bucket_level <= 5:
                limit = max(1, int(max_per_bucket / PHI))
            else:
                limit = max(1, int(max_per_bucket / (PHI ** 2)))

            # Sortiere nach Valenz — staerkere Emotionen behalten
            entries.sort(key=lambda e: abs(e.get("valence", 0)), reverse=True)

            kept.extend(entries[:limit])
            for entry in entries[limit:]:
                removed_files.append(entry["file"])

        # Entferne konsolidierte Dateien
        for filename in removed_files:
            filepath = self.experiences_path / filename
            if filepath.exists():
                filepath.unlink()

        # Index aktualisieren
        self.index["experiences"] = sorted(kept, key=lambda e: e["timestamp"])
        self.index["total_experiences"] = len(kept)
        self._save_index()

        return len(removed_files)
