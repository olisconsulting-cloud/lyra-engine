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
        entries = safe_json_read(self.failures_path, default=[])
        # Legacy-Migration: Alte Eintraege ohne type-Feld korrigieren
        for entry in entries:
            if "type" not in entry:
                entry["type"] = "failure"
        return entries

    def _save(self):
        safe_json_write(self.failures_path, self.failures[-100:])

    @staticmethod
    def _compute_fingerprint(error: str, approach: str = "") -> str:
        """Berechnet einen Error-Fingerprint fuer Cross-Kontext-Matching.

        Der Fingerprint extrahiert die technischen Kernwoerter aus dem Fehler,
        sodass dasselbe Problem erkannt wird — egal wie das Goal formuliert ist.
        z.B. 'exec() + __file__ + NameError' → gleicher Fingerprint ob bei
        data-insights oder time-series-analysis.
        """
        text = f"{error} {approach}".lower()
        # Technische Schluesselwoerter extrahieren
        tech_words = set()
        # Bekannte Error-Marker
        markers = [
            "__file__", "__name__", "exec(", "encoding", "utf-8", "charmap",
            "shutil.rmtree", "os.rmdir", "relative import", "modulenotfound",
            "importerror", "nameerror", "typeerror", "valueerror", "keyerror",
            "filenotfound", "permissionerror", "syntaxerror", "indentationerror",
            "blockiert", "security", "timeout", "connection", "429", "503",
            "json.decode", "unicodedecodeerror", "unicodeencodeerror",
        ]
        for marker in markers:
            if marker in text:
                tech_words.add(marker)

        # Tool-Namen extrahieren (read_file, write_file, execute_python, etc.)
        for word in text.split():
            if "_" in word and len(word) > 4 and word.replace("_", "").isalpha():
                tech_words.add(word)

        if not tech_words:
            return ""
        # Sortiert fuer deterministische Fingerprints
        return "|".join(sorted(tech_words))

    def record(self, goal: str, approach: str, error: str, lesson: str):
        """Speichert einen strukturierten Fehler mit Error-Fingerprint."""
        fingerprint = self._compute_fingerprint(error, approach)
        self.failures.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "failure",
            "goal": goal[:200],
            "approach": approach[:200],
            "error": error[:300],
            "lesson": lesson[:200],
            "fingerprint": fingerprint,
        })
        self._save()

    def record_success(self, tool: str, goal: str, approach: str):
        """Speichert einen bewaehrten Ansatz (positives Reinforcement)."""
        self.failures.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "success",
            "goal": goal[:200],
            "approach": approach[:200],
            "tool": tool,
        })
        self._save()

    def check(self, goal: str, error_context: str = "") -> str:
        """
        Prueft ob es bekannte Fehler fuer ein aehnliches Ziel gibt.

        Matching-Strategie (3 Ebenen):
        1. Fingerprint-Match — erkennt dasselbe technische Problem ueber
           verschiedene Goals hinweg (z.B. __file__ in exec())
        2. Tool-Name Match (approach enthaelt den Tool-Namen)
        3. Wort-Overlap (mindestens 2 gemeinsame Woerter)
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
        seen_fingerprints: set[str] = set()

        # Fingerprint fuer aktuellen Kontext berechnen (wenn vorhanden)
        current_fp = self._compute_fingerprint(error_context, goal) if error_context else ""

        for failure in self.failures:
            if failure.get("type") == "success":
                continue

            # Match 1: Fingerprint-Match (staerkster Match — Cross-Kontext)
            fp = failure.get("fingerprint", "")
            if fp and current_fp:
                # Overlap der Fingerprint-Teile pruefen (min 2 fuer Praezision)
                fp_parts = set(fp.split("|"))
                current_parts = set(current_fp.split("|"))
                if len(fp_parts & current_parts) >= 2:
                    if fp not in seen_fingerprints:
                        matches.append(failure)
                        seen_fingerprints.add(fp)
                    continue

            # Match 2: Tool-Name im Ziel enthalten
            approach = failure.get("approach", "").lower()
            if approach and approach in goal_lower:
                matches.append(failure)
                continue

            # Match 3: Wort-Overlap (ohne Stoppwoerter, min 2 Woerter)
            if not goal_words:
                continue
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
        """Kurze Zusammenfassung fuer den System-Prompt (Fehler + Erfolge)."""
        if not self.failures:
            return ""

        # Top-Lektionen aus Fehlern (dedupliziert)
        lessons = []
        seen = set()
        for f in reversed(self.failures):
            if f.get("type") == "success":
                continue
            lesson = f.get("lesson", "")
            if lesson and lesson not in seen:
                lessons.append(lesson)
                seen.add(lesson)
            if len(lessons) >= 3:
                break

        # Top bewaehrte Ansaetze (dedupliziert)
        successes = []
        seen_s = set()
        for f in reversed(self.failures):
            if f.get("type") != "success":
                continue
            approach = f.get("approach", "")
            if approach and approach not in seen_s:
                successes.append(approach)
                seen_s.add(approach)
            if len(successes) >= 2:
                break

        parts = []
        if lessons:
            parts.append("TOP-LEKTIONEN AUS FEHLERN:\n" + "\n".join(f"  - {l}" for l in lessons))
        if successes:
            parts.append("BEWAEHRTE ANSAETZE:\n" + "\n".join(f"  + {s[:100]}" for s in successes))
        return "\n".join(parts)

    def get_security_lessons(self) -> str:
        """Kompakte Security-Block-Lektionen (max ~50 Tokens)."""
        blocked_patterns: set[str] = set()
        for f in reversed(self.failures):
            if f.get("type") != "failure":
                continue
            error = f.get("error", "")
            if "BLOCKIERT" not in error:
                continue
            approach = f.get("approach", "")
            if approach:
                blocked_patterns.add(approach)
            if len(blocked_patterns) >= 5:
                break

        if not blocked_patterns:
            return ""

        return (
            "BEKANNTE SECURITY-BLOCKS (nicht erneut versuchen!):\n"
            "  Nutze Mock-Daten oder web_search/web_read statt direkter HTTP-Calls."
        )


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
        # API-Key und URL je nach Provider — explizite Cases, kein impliziter Fallback
        if self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        elif self.provider == "deepseek":
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.api_url = "https://api.deepseek.com/chat/completions"
        elif self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
            self.api_url = "https://api.openai.com/v1/chat/completions"
        else:
            raise ValueError(f"CriticAgent: Unbekannter Provider '{self.provider}' fuer Modell '{self.model}'")

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
            return {"score": 0, "is_improvement": False, "side_effects": "Kein Critic verfuegbar — manuelles Review noetig", "suggestion": "API-Key setzen fuer automatische Bewertung"}

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
                return {"score": 0, "is_improvement": False, "side_effects": "API-Fehler — manuelles Review noetig", "suggestion": ""}

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
                return {"score": 0, "is_improvement": False, "side_effects": "Antwort nicht parsebar — manuelles Review noetig", "suggestion": ""}

        except Exception as e:
            return {"score": 0, "is_improvement": False, "side_effects": f"Critic-Fehler: {str(e)[:100]} — manuelles Review noetig", "suggestion": ""}


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
        # API-Key und URL je nach Provider — explizite Cases, kein impliziter Fallback
        if self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
            self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        elif self.provider == "deepseek":
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.api_url = "https://api.deepseek.com/chat/completions"
        elif self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
            self.api_url = "https://api.openai.com/v1/chat/completions"
        else:
            raise ValueError(f"PromptMutator: Unbekannter Provider '{self.provider}' fuer Modell '{self.model}'")

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
