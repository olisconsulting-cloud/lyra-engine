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

from .config import safe_json_read, safe_json_write
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
        return safe_json_read(self.failures_path, default=[])

    def _save(self):
        safe_json_write(self.failures_path, self.failures[-100:])

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
        model_key = TASK_MODEL_MAP["code_review"]
        model_config = MODELS[model_key]
        self.provider = model_config["provider"]
        self.model = model_config["model_id"]
        # API-Key je nach Provider
        if self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        else:
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.api_url = "https://api.deepseek.com/chat/completions"

    def _call_api(self, prompt: str, max_tokens: int = 500) -> str:
        """Ruft die konfigurierte API auf und gibt den Text zurueck."""
        with httpx.Client(timeout=30.0) as client:
            if self.provider == "google":
                resp = client.post(
                    self.api_url,
                    params={"key": self.api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": max_tokens}},
                )
                if resp.status_code != 200:
                    return ""
                return resp.json()["candidates"][0]["content"]["parts"][-1]["text"]
            else:
                resp = client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model,
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens},
                )
                if resp.status_code != 200:
                    return ""
                return resp.json()["choices"][0]["message"]["content"]

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
        if not self.api_key:
            return {"score": 5, "is_improvement": None, "side_effects": "Kein Critic verfuegbar — Bewertung nicht moeglich", "suggestion": ""}

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
            text = self._call_api(prompt, max_tokens=500)
            if not text:
                return {"score": 5, "is_improvement": None, "side_effects": "API-Fehler — Bewertung nicht moeglich", "suggestion": ""}

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
                return {"score": 5, "is_improvement": None, "side_effects": "Antwort nicht parsebar — Bewertung nicht moeglich", "suggestion": ""}

        except Exception as e:
            return {"score": 5, "is_improvement": None, "side_effects": f"Critic-Fehler: {str(e)[:100]}", "suggestion": ""}


# ============================================================
# 3. PROMPT-MUTATOR (AlphaEvolve-Prinzip)
# ============================================================

class PromptMutator:
    """
    Generiert mehrere Loesungsvarianten und waehlt die beste.

    Statt: Ein Ansatz → ausfuehren
    Neu: 3 Ansaetze → bewerten → besten ausfuehren

    Nutzt das konfigurierte Haupt-Modell fuer die Varianten.
    """

    def __init__(self):
        model_key = TASK_MODEL_MAP["main_work"]
        model_config = MODELS[model_key]
        self.provider = model_config["provider"]
        self.model = model_config["model_id"]
        if self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        else:
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.api_url = "https://api.deepseek.com/chat/completions"

    def _call_api(self, prompt: str, max_tokens: int = 500) -> str:
        """Ruft die konfigurierte API auf und gibt den Text zurueck."""
        with httpx.Client(timeout=30.0) as client:
            if self.provider == "google":
                resp = client.post(
                    self.api_url,
                    params={"key": self.api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"maxOutputTokens": max_tokens}},
                )
                if resp.status_code != 200:
                    return ""
                return resp.json()["candidates"][0]["content"]["parts"][-1]["text"]
            else:
                resp = client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model,
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": max_tokens},
                )
                if resp.status_code != 200:
                    return ""
                return resp.json()["choices"][0]["message"]["content"]

    def generate_variants(self, task: str, context: str = "",
                          n_variants: int = 3) -> list[str]:
        """
        Generiert n Loesungsvarianten fuer eine Aufgabe.

        Returns:
            Liste von Ansaetzen (Strings)
        """
        if not self.api_key:
            return [task]  # Ohne API: Original zurueckgeben

        prompt = f"""Generiere {n_variants} VERSCHIEDENE Ansaetze fuer diese Aufgabe:

AUFGABE: {task}
{f'KONTEXT: {context}' if context else ''}

Gib genau {n_variants} Ansaetze als JSON-Array zurueck:
["Ansatz 1: ...", "Ansatz 2: ...", "Ansatz 3: ..."]

Die Ansaetze muessen WIRKLICH verschieden sein — verschiedene Strategien, nicht Variationen."""

        try:
            text = self._call_api(prompt, max_tokens=1000)
            if not text:
                return [task]

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

        if not self.api_key:
            return 0

        prompt = f"""Welcher Ansatz ist der BESTE? Antworte NUR mit der Nummer (1, 2, oder 3).

{chr(10).join(f'{i+1}. {v}' for i, v in enumerate(variants))}

{f'Kriterium: {criteria}' if criteria else 'Kriterium: Effektivitaet, Einfachheit, Zuverlaessigkeit'}"""

        try:
            text = self._call_api(prompt, max_tokens=10)
            if not text:
                return 0
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
            log = safe_json_read(self.composition_log_path, default=[])
            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "new_tool": new_tool,
                "composed_from": used_tools,
                "task": task[:200],
            })
            safe_json_write(self.composition_log_path, log[-50:])
        except Exception:
            pass

    def get_compound_stats(self) -> str:
        """Zeigt den Compound-Effekt."""
        registry = self._load_registry()
        total_tools = len(registry)
        total_uses = sum(t.get("uses", 0) for t in registry.values())

        log = safe_json_read(self.composition_log_path, default=[])

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
