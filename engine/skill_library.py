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

        # Neuen Skill erstellen
        skill_id = f"skill_{goal_type}_{len(self.index['skills'])}"
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

        # Max 30 Skills behalten (aelteste mit niedrigstem Score loeschen)
        if len(self.index["skills"]) > 30:
            self.index["skills"].sort(
                key=lambda s: s.get("avg_score", 0) * s.get("success_count", 1),
                reverse=True
            )
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

    def get_stats(self) -> dict:
        """Statistiken ueber die Skill-Library."""
        skills = self.index.get("skills", [])
        types = {}
        for s in skills:
            t = s.get("goal_type", "?")
            types[t] = types.get(t, 0) + 1
        return {
            "total_skills": len(skills),
            "total_extracted": self.index.get("total_extracted", 0),
            "by_type": types,
        }
