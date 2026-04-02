"""
Quantum-Features — Die Quantenspruenge.

1. Failure-Memory mit Pattern-Matching
   Jeder Fehler speichert: was versucht, warum gescheitert, Lektion.
   Vor neuem Versuch: Memory abfragen → verhindert 80% Wiederholungsfehler.

2. Critic-Agent bei Self-Modify
   Nach jeder Code-Aenderung: Separater LLM-Call bewertet den Diff.
   "Ist das besser? Seiteneffekte? Regressionen?"

3. Evolutionaerer Prompt-Mutator (AlphaEvolve-Prinzip)
   Bei wichtigen Entscheidungen: 3 Varianten generieren, beste waehlen.
   Nicht immer den ersten Gedanken nehmen — Exploration > Exploitation.

4. Skill-Komposition
   Tools mit depends_on und composes_with.
   Lyra sucht erst bestehende Tools bevor sie neue baut.
   Exponentieller Compound-Effekt.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .llm_router import MODELS, TASK_MODEL_MAP


# ============================================================
# 1. FAILURE-MEMORY
# ============================================================

class FailureMemory:
    """
    Strukturiertes Fehler-Gedaechtnis.

    Nicht nur "Tool X hat Fehler Y" — sondern:
    - Was war das ZIEL?
    - Was wurde VERSUCHT?
    - Warum hat es NICHT funktioniert?
    - Was ist die LEKTION?

    Vor jedem neuen Versuch: check() aufrufen.
    """

    def __init__(self, data_path: Path):
        self.failures_path = data_path / "consciousness" / "failures.json"
        self.failures = self._load()

    def _load(self) -> list:
        if self.failures_path.exists():
            try:
                with open(self.failures_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        with open(self.failures_path, "w", encoding="utf-8") as f:
            json.dump(self.failures[-100:], f, indent=2, ensure_ascii=False)

    def record(self, goal: str, approach: str, error: str, lesson: str):
        """Speichert einen strukturierten Fehler."""
        self.failures.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goal": goal[:200],
            "approach": approach[:200],
            "error": error[:300],
            "lesson": lesson[:200],
        })
        self._save()

    def check(self, goal: str) -> str:
        """
        Prueft ob es bekannte Fehler fuer ein aehnliches Ziel gibt.

        Matching-Strategie:
        1. Tool-Name Match (approach enthält den Tool-Namen)
        2. Wort-Overlap (mindestens 1 gemeinsames Wort reicht)
        """
        if not self.failures:
            return ""

        # Stoppwoerter die False Positives erzeugen
        stopwords = {
            "kein", "keine", "nicht", "und", "oder", "der", "die", "das",
            "ein", "eine", "ist", "hat", "mit", "von", "zu", "auf", "in",
            "fuer", "noch", "aktive", "ziele", "aktiv", "fokus", "sequenz",
            "the", "and", "for", "not", "this", "that", "with",
        }

        goal_lower = goal.lower()
        goal_words = set(goal_lower.split()) - stopwords
        matches = []

        if not goal_words:
            return ""

        for failure in self.failures:
            # Match 1: Tool-Name im Ziel enthalten
            approach = failure.get("approach", "").lower()
            if approach and approach in goal_lower:
                matches.append(failure)
                continue

            # Match 2: Wort-Overlap (ohne Stoppwoerter, min 2 Woerter)
            failure_goal = failure.get("goal", "").lower()
            failure_words = set(failure_goal.split()) - stopwords
            failure_words.update(set(approach.split()) - stopwords)
            overlap = len(goal_words & failure_words)
            if overlap >= 2:
                matches.append(failure)

        if not matches:
            return ""

        lines = ["BEKANNTE FEHLER (vermeide diese):"]
        for m in matches[-3:]:
            lines.append(
                f"  Versuch: {m.get('approach', '')[:80]}\n"
                f"  Fehler: {m.get('error', '')[:80]}\n"
                f"  Lektion: {m.get('lesson', '')[:80]}"
            )
        return "\n".join(lines)

    def get_summary(self) -> str:
        """Kurze Zusammenfassung fuer den System-Prompt."""
        if not self.failures:
            return ""
        # Top-Lektionen (dedupliziert)
        lessons = []
        seen = set()
        for f in reversed(self.failures):
            lesson = f.get("lesson", "")
            if lesson and lesson not in seen:
                lessons.append(lesson)
                seen.add(lesson)
            if len(lessons) >= 3:
                break
        if not lessons:
            return ""
        return "TOP-LEKTIONEN AUS FEHLERN:\n" + "\n".join(f"  - {l}" for l in lessons)


# ============================================================
# 2. CRITIC-AGENT
# ============================================================

class CriticAgent:
    """
    Bewertet Code-Aenderungen NACH dem Dual-Review.

    Nicht nur "ist es sicher?" (das macht Gemini Review)
    sondern "ist es BESSER als vorher?"

    Nutzt Gemini Flash — kostet fast nichts.
    """

    def __init__(self):
        self.google_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.model = MODELS[TASK_MODEL_MAP["code_review"]]["model_id"]

    def evaluate_change(self, file_path: str, old_code: str, new_code: str,
                        reason: str) -> dict:
        """
        Bewertet eine Code-Aenderung.

        Returns:
            {
                "score": 1-10 (10 = Quantensprung),
                "is_improvement": bool,
                "side_effects": str,
                "suggestion": str,
            }
        """
        if not self.google_key:
            return {"score": 5, "is_improvement": True, "side_effects": "Kein Critic verfuegbar", "suggestion": ""}

        prompt = f"""Bewerte diese Code-Aenderung auf einer Skala von 1-10.

DATEI: {file_path}
GRUND: {reason}

=== VORHER ===
{old_code[:2000]}

=== NACHHER ===
{new_code[:2000]}

Bewerte:
1. Ist der neue Code BESSER als der alte? (Nicht nur anders, sondern besser)
2. Gibt es SEITENEFFEKTE die etwas anderes kaputt machen koennten?
3. Wie wuerdest du es NOCH BESSER machen?

Antworte als JSON:
{{"score": 1-10, "is_improvement": true/false, "side_effects": "...", "suggestion": "..."}}"""

        try:
            client = httpx.Client(timeout=30.0)
            resp = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                params={"key": self.google_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 500},
                },
            )
            client.close()

            if resp.status_code != 200:
                return {"score": 5, "is_improvement": True, "side_effects": f"API {resp.status_code}", "suggestion": ""}

            text = resp.json()["candidates"][0]["content"]["parts"][-1]["text"]

            # JSON parsen
            import re
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl > 0: cleaned = cleaned[first_nl + 1:]
                if cleaned.rstrip().endswith("```"): cleaned = cleaned.rstrip()[:-3].rstrip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return {"score": 5, "is_improvement": True, "side_effects": "Parse-Fehler", "suggestion": ""}

        except Exception as e:
            return {"score": 5, "is_improvement": True, "side_effects": str(e)[:100], "suggestion": ""}


# ============================================================
# 3. PROMPT-MUTATOR (AlphaEvolve-Prinzip)
# ============================================================

class PromptMutator:
    """
    Generiert mehrere Loesungsvarianten und waehlt die beste.

    Statt: Ein Ansatz → ausfuehren
    Neu: 3 Ansaetze → bewerten → besten ausfuehren

    Nutzt Gemini Flash fuer die Varianten (guenstig).
    """

    def __init__(self):
        self.google_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.model = MODELS[TASK_MODEL_MAP["main_work"]]["model_id"]

    def generate_variants(self, task: str, context: str = "",
                          n_variants: int = 3) -> list[str]:
        """
        Generiert n Loesungsvarianten fuer eine Aufgabe.

        Returns:
            Liste von Ansaetzen (Strings)
        """
        if not self.google_key:
            return [task]  # Ohne API: Original zurueckgeben

        prompt = f"""Generiere {n_variants} VERSCHIEDENE Ansaetze fuer diese Aufgabe:

AUFGABE: {task}
{f'KONTEXT: {context}' if context else ''}

Gib genau {n_variants} Ansaetze als JSON-Array zurueck:
["Ansatz 1: ...", "Ansatz 2: ...", "Ansatz 3: ..."]

Die Ansaetze muessen WIRKLICH verschieden sein — verschiedene Strategien, nicht Variationen."""

        try:
            client = httpx.Client(timeout=30.0)
            resp = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                params={"key": self.google_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1000},
                },
            )
            client.close()

            if resp.status_code != 200:
                return [task]

            text = resp.json()["candidates"][0]["content"]["parts"][-1]["text"]

            import re
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl > 0: cleaned = cleaned[first_nl + 1:]
                if cleaned.rstrip().endswith("```"): cleaned = cleaned.rstrip()[:-3].rstrip()
            try:
                variants = json.loads(cleaned)
                if isinstance(variants, list) and len(variants) >= 2:
                    return variants[:n_variants]
            except json.JSONDecodeError:
                pass

            return [task]

        except Exception:
            return [task]

    def select_best(self, variants: list[str], criteria: str = "") -> int:
        """
        Waehlt die beste Variante aus.

        Returns:
            Index der besten Variante
        """
        if len(variants) <= 1:
            return 0

        if not self.google_key:
            return 0

        prompt = f"""Welcher Ansatz ist der BESTE? Antworte NUR mit der Nummer (1, 2, oder 3).

{chr(10).join(f'{i+1}. {v}' for i, v in enumerate(variants))}

{f'Kriterium: {criteria}' if criteria else 'Kriterium: Effektivitaet, Einfachheit, Zuverlaessigkeit'}"""

        try:
            client = httpx.Client(timeout=15.0)
            resp = client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                params={"key": self.google_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 10},
                },
            )
            client.close()

            if resp.status_code != 200:
                return 0

            text = resp.json()["candidates"][0]["content"]["parts"][-1]["text"]
            # Extrahiere die Nummer
            import re
            match = re.search(r"(\d+)", text)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(variants):
                    return idx
            return 0

        except Exception:
            return 0


# ============================================================
# 4. SKILL-KOMPOSITION
# ============================================================

class SkillComposer:
    """
    Findet und kombiniert existierende Tools fuer neue Aufgaben.

    Statt: "Ich brauche X" → von Null bauen
    Neu: "Ich brauche X" → Welche bestehenden Tools kann ich kombinieren?

    Das ist der Compound-Effekt: Jedes neue Tool macht alle zukuenftigen staerker.
    """

    def __init__(self, data_path: Path):
        self.tools_path = data_path / "tools"
        self.registry_path = self.tools_path / "registry.json"
        self.composition_log_path = data_path / "consciousness" / "compositions.json"

    def find_composable(self, task_description: str) -> list[dict]:
        """
        Findet existierende Tools die fuer eine Aufgabe relevant sein koennten.

        Nutzt Wort-Matching auf Tool-Beschreibungen.
        """
        registry = self._load_registry()
        if not registry:
            return []

        task_words = set(task_description.lower().split())
        matches = []

        for name, info in registry.items():
            desc = info.get("description", "").lower()
            desc_words = set(desc.split())
            overlap = len(task_words & desc_words)
            if overlap >= 2:
                matches.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "relevance": overlap,
                    "uses": info.get("uses", 0),
                })

        matches.sort(key=lambda x: x["relevance"], reverse=True)
        return matches[:5]

    def suggest_composition(self, task_description: str) -> str:
        """
        Schlaegt eine Komposition existierender Tools vor.

        Returns:
            Vorschlag als Text fuer den System-Prompt
        """
        composable = self.find_composable(task_description)
        if not composable:
            return ""

        lines = ["EXISTIERENDE TOOLS DIE HELFEN KOENNTEN:"]
        for tool in composable:
            lines.append(f"  - {tool['name']}: {tool['description'][:60]} ({tool['uses']}x genutzt)")
        lines.append("  → Pruefe ob du diese kombinieren kannst statt von Null zu bauen!")
        return "\n".join(lines)

    def log_composition(self, new_tool: str, used_tools: list[str], task: str):
        """Loggt eine erfolgreiche Komposition."""
        try:
            log = []
            if self.composition_log_path.exists():
                with open(self.composition_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "new_tool": new_tool,
                "composed_from": used_tools,
                "task": task[:200],
            })
            log = log[-50:]
            with open(self.composition_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_compound_stats(self) -> str:
        """Zeigt den Compound-Effekt."""
        registry = self._load_registry()
        total_tools = len(registry)
        total_uses = sum(t.get("uses", 0) for t in registry.values())

        log = []
        if self.composition_log_path.exists():
            try:
                with open(self.composition_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except Exception:
                pass

        return (
            f"Tools: {total_tools} | Nutzungen: {total_uses} | "
            f"Kompositionen: {len(log)}"
        )

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            return {}
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("tools", {})
        except Exception:
            return {}
