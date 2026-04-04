"""
Skill-Library — Prozedurale Memory fuer Phi.

Extrahiert wiederverwendbare Arbeits-Templates aus erfolgreichen Sequenzen.
Inspiriert von: Anthropic SKILL.md-Format + MemP (prozedurale Memory) + Voyager.

Nicht "Phi kann web_search" (das trackt SkillTracker),
sondern "Fuer Marktanalyse: 1. Scope definieren, 2. Quellen suchen, 3. Synthese."

Zwei Abstraktionsstufen (MemP-Pattern):
- Fine-grained: Konkrete Tool-Sequenz (write_file → read_file → execute_python)
- Script-level: Abstrakte Strategie ("Recherche: definieren → sammeln → synthetisieren")
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write

logger = logging.getLogger(__name__)


class SkillLibrary:
    """Speichert und findet prozedurale Skills — gelernt aus Erfahrung."""

    def __init__(self, data_path: Path):
        self.skills_path = data_path / "skill_library"
        self.skills_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.skills_path / "index.json"
        self.index = self._load_index()
        self._migrate_v2()
        self._migrate_v3()

    def _load_index(self) -> dict:
        return safe_json_read(self.index_path, default={
            "skills": [],
            "total_extracted": 0,
        })

    def _save_index(self):
        safe_json_write(self.index_path, self.index)

    def _migrate_v2(self):
        """Einmalige Reklassifizierung: sonstiges-Skills korrekt zuordnen."""
        if self.index.get("schema_version", 0) >= 2:
            return

        _REMAP = {
            "skill_sonstiges_28": "process_management",
            "skill_sonstiges_30": "process_management",
            "skill_sonstiges_29": "process_management",
            "skill_sonstiges_25": "process_management",
            "skill_sonstiges_27": "process_management",
            "skill_sonstiges_26": "process_management",
            "skill_sonstiges_8": "api_integration",
            "skill_sonstiges_16": "api_integration",
            "skill_sonstiges_9": "api_integration",
            "skill_sonstiges_15": "api_integration",
            "skill_sonstiges_18": "api_integration",
            "skill_sonstiges_6": "api_integration",
            "skill_sonstiges_20": "project_work",
            "skill_sonstiges_14": "project_work",
            "skill_sonstiges_10": "project_work",
            "skill_sonstiges_17": "project_work",
            "skill_sonstiges_19": "project_work",
            "skill_sonstiges_11": "testing",
            "skill_sonstiges_23": "testing",
            "skill_sonstiges_3": "report_building",
        }

        migrated = 0
        for skill in self.index.get("skills", []):
            new_type = _REMAP.get(skill.get("id"))
            if new_type:
                skill["goal_type"] = new_type
                migrated += 1

        self.index["schema_version"] = 2
        if migrated > 0:
            self._save_index()
            logger.info("Skill-Migration v2: %d Skills reklassifiziert", migrated)

    def _migrate_v3(self):
        """Einmalig: Duplikat-IDs bereinigen (Counter-Bug Fix).

        Problem: skill_id nutzte len(skills) statt globalen Counter,
        daher entstanden bei Limit 30 immer IDs mit Suffix _30.
        """
        if self.index.get("schema_version", 0) >= 3:
            return

        skills = self.index.get("skills", [])
        id_counts = Counter(s["id"] for s in skills)
        dupes = {k for k, v in id_counts.items() if v > 1}

        removed = 0
        if dupes:
            # Pro Duplikat-Gruppe: besten behalten, Rest entfernen
            to_remove: list[int] = []
            for dup_id in dupes:
                group = [(i, s) for i, s in enumerate(skills)
                         if s["id"] == dup_id]
                group.sort(
                    key=lambda x: (x[1].get("avg_score", 0)
                                   * x[1].get("success_count", 1)),
                    reverse=True,
                )
                for idx, _ in group[1:]:
                    to_remove.append(idx)

            for idx in sorted(to_remove, reverse=True):
                skills.pop(idx)
            removed = len(to_remove)

            # Verbliebene Skills mit _30-Suffix umbenennen
            counter = self.index.get("total_extracted", len(skills))
            for skill in skills:
                if skill["id"].endswith("_30"):
                    skill["id"] = f"skill_{skill['goal_type']}_{counter}"
                    counter += 1
            self.index["total_extracted"] = counter

        self.index["schema_version"] = 3
        self._save_index()
        if removed:
            logger.info("Skill-Migration v3: %d Duplikate entfernt", removed)

    # === Skill-Extraktion ===

    def extract_from_sequence(self, plan_goal: str, plan_score: int,
                               summary: str, tool_sequence: list,
                               goal_type: str, rating: int) -> Optional[str]:
        """Extrahiert einen Skill aus einer erfolgreichen Sequenz.

        Nur bei Plan-Score >= 7 UND Rating >= 7 (Qualitaets-Gate).

        Args:
            plan_goal: Was war das Ziel?
            plan_score: Wie gut war der Plan? (1-10)
            summary: Was wurde erreicht?
            tool_sequence: Welche Tools in welcher Reihenfolge?
            goal_type: Typ des Goals (recherche, tool_building, etc.)
            rating: Phi's Selbstbewertung (1-10)

        Returns:
            Skill-ID oder None wenn Qualitaets-Gate nicht bestanden.
        """
        # Qualitaets-Gate: Gute Sequenzen extrahieren (nicht nur perfekte)
        if plan_score < 5 or rating < 5:
            logger.info(
                "Skill nicht extrahiert: score=%d, rating=%d (min 5/5) — %s",
                plan_score, rating, plan_goal[:60],
            )
            return None

        # Tool-Sequenz zu abstraktem Pattern verdichten
        tool_names = [t.get("name", "") for t in tool_sequence if t.get("name")]
        if len(tool_names) < 2:
            logger.info("Skill nicht extrahiert: nur %d Tools (min 2) — %s",
                        len(tool_names), plan_goal[:60])
            return None  # Zu wenig Schritte fuer ein Muster

        # Duplikat-Check: Aehnlicher Skill schon vorhanden?
        existing = self.find_by_goal_type(goal_type)
        for skill in existing:
            if self._is_similar(skill.get("plan_goal", ""), plan_goal):
                logger.info("Skill-Update statt Neu: %s (aehnlich zu %s)",
                            plan_goal[:50], skill.get("plan_goal", "")[:50])
                return self._update_skill(skill["id"], plan_score, rating)

        # Neuen Skill erstellen (total_extracted als globaler Counter — nie Duplikate)
        skill_id = f"skill_{goal_type}_{self.index.get('total_extracted', 0)}"
        skill = {
            "id": skill_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "goal_type": goal_type,
            "plan_goal": plan_goal[:200],
            "summary": summary[:300],
            # Fine-grained: Konkrete Tool-Sequenz
            "tool_sequence": tool_names[:15],
            # Script-level: Abstrakte Schritte (aus Tool-Gruppen)
            "abstract_steps": self._abstract_steps(tool_names),
            "success_count": 1,
            "avg_score": plan_score,
            "avg_rating": rating,
            "last_used": datetime.now(timezone.utc).isoformat(),
        }

        self.index["skills"].append(skill)
        self.index["total_extracted"] = self.index.get("total_extracted", 0) + 1

        # Max 30 Skills behalten (schwache archivieren statt loeschen)
        if len(self.index["skills"]) > 30:
            self.index["skills"].sort(
                key=lambda s: s.get("avg_score", 0) * s.get("success_count", 1),
                reverse=True
            )
            removed = self.index["skills"][30:]
            self._archive_skills(removed)
            self.index["skills"] = self.index["skills"][:30]

        self._save_index()
        logger.info(f" Neuer Skill extrahiert: {skill_id} ({goal_type})")
        return skill_id

    def _update_skill(self, skill_id: str, score: int, rating: int) -> str:
        """Aktualisiert einen bestehenden Skill mit neuem Erfolg."""
        for skill in self.index["skills"]:
            if skill["id"] == skill_id:
                n = skill.get("success_count", 1)
                skill["success_count"] = n + 1
                # Gleitender Durchschnitt
                skill["avg_score"] = round(
                    (skill.get("avg_score", 5) * n + score) / (n + 1), 1
                )
                skill["avg_rating"] = round(
                    (skill.get("avg_rating", 5) * n + rating) / (n + 1), 1
                )
                skill["last_used"] = datetime.now(timezone.utc).isoformat()
                self._save_index()
                return skill_id
        return skill_id

    def _archive_skills(self, skills: list):
        """Archiviert entfernte Skills fuer spaetere Analyse."""
        archive_path = self.skills_path / "archive.json"
        archive = safe_json_read(
            archive_path, default={"archived": [], "total_archived": 0},
        )
        now = datetime.now(timezone.utc).isoformat()
        for skill in skills:
            skill["archived_at"] = now
            archive["archived"].append(skill)
        # Max 100 archivierte Skills
        if len(archive["archived"]) > 100:
            archive["archived"] = archive["archived"][-100:]
        archive["total_archived"] = len(archive["archived"])
        safe_json_write(archive_path, archive)
        logger.info("Skill-Archiv: %d Skills archiviert", len(skills))

    @staticmethod
    def _abstract_steps(tool_names: list) -> list:
        """Verdichtet eine Tool-Sequenz zu abstrakten Schritten.

        z.B. [read_file, read_file, web_search, write_file, read_file]
        → ["Kontext lesen", "Recherche", "Ergebnis schreiben", "Verifizieren"]
        """
        # Tool-Gruppen zu abstrakten Phasen
        phases = {
            "lesen": {"read_file", "list_directory", "read_own_code"},
            "recherche": {"web_search", "web_read"},
            "schreiben": {"write_file", "create_project"},
            "code": {"execute_python", "modify_own_code"},
            "tools": {"create_tool", "generate_tool", "use_tool"},
            "testen": {"run_project_tests", "verify_project"},
            "planen": {"set_goal", "complete_subgoal", "write_sequence_plan"},
            "kommunizieren": {"send_telegram"},
        }

        # Tool-Namen auf Phasen mappen (Reihenfolge beibehalten, Duplikate entfernen)
        steps = []
        last_phase = None
        for tool in tool_names:
            for phase_name, tools in phases.items():
                if tool in tools and phase_name != last_phase:
                    steps.append(phase_name)
                    last_phase = phase_name
                    break

        return steps or ["unbekannt"]

    @staticmethod
    def _is_similar(text_a: str, text_b: str) -> bool:
        """Wort-Overlap-Check (>= 60% Jaccard-Similarity)."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return False
        overlap = len(words_a & words_b)
        union = len(words_a | words_b)
        return union > 0 and overlap / union >= 0.6

    # === Skill-Abruf ===

    def find_by_goal_type(self, goal_type: str) -> list:
        """Findet Skills passend zum Goal-Typ."""
        return [
            s for s in self.index["skills"]
            if s.get("goal_type") == goal_type
        ]

    def get_best_skill(self, goal_type: str) -> Optional[dict]:
        """Findet den besten Skill fuer einen Goal-Typ (nach Score * Nutzung)."""
        matching = self.find_by_goal_type(goal_type)
        if not matching:
            return None
        return max(
            matching,
            key=lambda s: s.get("avg_score", 0) * min(s.get("success_count", 1), 5)
        )

    def build_skill_prompt(self, goal_type: str) -> str:
        """Baut einen Prompt-Abschnitt mit dem besten Skill fuer den Goal-Typ.

        Returns:
            Prompt-Text oder leerer String.
        """
        skill = self.get_best_skill(goal_type)
        if not skill:
            return ""

        steps = skill.get("abstract_steps", [])
        steps_text = " → ".join(steps) if steps else "keine Schritte"

        return (
            f"\nBEWAEHRTES VORGEHEN (aus {skill.get('success_count', 1)} Erfolgen):\n"
            f"  Ziel-Typ: {goal_type}\n"
            f"  Muster: {steps_text}\n"
            f"  Beispiel: {skill.get('plan_goal', '')[:100]}\n"
            f"  Score: {skill.get('avg_score', '?')}/10\n"
            f"  Dies ist ein VORSCHLAG — passe ihn an die aktuelle Aufgabe an."
        )

    # === Skill → Tool Bridge ===

    def find_promotion_candidates(self, min_successes: int = 7) -> list[dict]:
        """Findet reife Skills die als Tool generiert werden sollten.

        Kriterien:
        - success_count >= min_successes
        - avg_score >= 8.0
        - Noch nicht promoted (kein 'promoted_to_tool' Flag)

        Returns:
            Liste von Skill-Dicts die reif fuer Tool-Generierung sind.
        """
        candidates = []
        for skill in self.index.get("skills", []):
            if skill.get("promoted_to_tool"):
                continue
            if (skill.get("success_count", 0) >= min_successes
                    and skill.get("avg_score", 0) >= 8.0):
                candidates.append(skill)
        return sorted(
            candidates,
            key=lambda s: s.get("avg_score", 0) * s.get("success_count", 1),
            reverse=True,
        )

    def build_tool_spec(self, skill: dict) -> dict:
        """Baut eine Tool-Spezifikation aus einem reifen Skill.

        Returns:
            {"name": str, "description": str, "steps": list}
        """
        goal_type = skill.get("goal_type", "general")
        steps = skill.get("abstract_steps", [])
        tools = skill.get("tool_sequence", [])

        name = f"auto_{goal_type}_{skill['id'].rsplit('_', 1)[-1]}"
        description = (
            f"Automatisiert: {skill.get('plan_goal', '')[:120]}. "
            f"Bewaehrtes Muster aus {skill.get('success_count', 0)} Erfolgen "
            f"(Score: {skill.get('avg_score', 0)}/10)."
        )
        return {
            "name": name,
            "description": description,
            "abstract_steps": steps,
            "tool_sequence": tools,
            "source_skill_id": skill["id"],
        }

    def mark_as_promoted(self, skill_id: str, tool_name: str) -> bool:
        """Markiert einen Skill als zu Tool promoted.

        Returns:
            True bei Erfolg, False wenn Skill nicht gefunden.
        """
        for skill in self.index.get("skills", []):
            if skill["id"] == skill_id:
                skill["promoted_to_tool"] = tool_name
                skill["promoted_at"] = datetime.now(timezone.utc).isoformat()
                self._save_index()
                return True
        logger.warning("mark_as_promoted: Skill %s nicht gefunden", skill_id)
        return False

    def get_stats(self) -> dict:
        """Statistiken ueber die Skill-Library."""
        skills = self.index.get("skills", [])
        types = {}
        promoted = 0
        for s in skills:
            t = s.get("goal_type", "?")
            types[t] = types.get(t, 0) + 1
            if s.get("promoted_to_tool"):
                promoted += 1
        return {
            "total_skills": len(skills),
            "total_extracted": self.index.get("total_extracted", 0),
            "promoted_to_tools": promoted,
            "by_type": types,
        }
