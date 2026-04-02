"""
Intelligence-Engine — Echtes Lernen, nicht Simulation.

4 Systeme die Lyra WIRKLICH besser machen:

1. Semantische Memory — Findet Erinnerungen nach BEDEUTUNG, nicht nach Alter
2. Skill-Tracking — Trackt was Lyra KANN (nicht abstrakte Persoenlichkeits-Zahlen)
3. Strategie-Evolution — Erkennt Fehlermuster und schreibt eigene Regeln
4. Effizienz-Tracking — Misst ob Lyra tatsaechlich besser wird
"""

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ============================================================
# 1. SEMANTISCHE MEMORY
# ============================================================

class SemanticMemory:
    """
    Findet Erinnerungen nach Bedeutung, nicht nur nach Alter.

    Nutzt TF-IDF Vektoren + Cosine-Similarity. Keine externen
    Dependencies — funktioniert mit Python-Stdlib.

    Kann spaeter auf echte Embeddings (sentence-transformers) upgraden.
    """

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.memories_path = base_path / "memory" / "semantic"
        self.index_path = self.memories_path / "index.json"

        self.memories_path.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()

        # Stoppwoerter (haeufige deutsche + englische Woerter)
        self.stopwords = {
            "ich", "du", "er", "sie", "es", "wir", "ihr", "und", "oder",
            "aber", "in", "von", "mit", "auf", "an", "zu", "der", "die",
            "das", "ein", "eine", "ist", "bin", "hat", "habe", "nicht",
            "dass", "den", "dem", "des", "als", "auch", "noch", "wie",
            "was", "wenn", "man", "so", "nach", "nur", "kann", "will",
            "the", "a", "an", "is", "in", "of", "to", "and", "for",
            "that", "this", "with", "it", "not", "be", "are", "was",
            "been", "have", "has", "had", "do", "does", "did", "but",
            "mein", "meine", "meinem", "meinen", "meiner",
            "sein", "seine", "seinem", "seinen", "seiner",
            "fuer", "ueber", "unter", "durch", "bei", "vor",
        }

    def _load_index(self) -> dict:
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"entries": [], "idf": {}, "doc_count": 0}

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False)

    def _tokenize(self, text: str) -> list[str]:
        """Zerlegt Text in normalisierte Tokens."""
        text = text.lower()
        # Nur Woerter, keine Satzzeichen
        words = re.findall(r"[a-zäöüß]+", text)
        # Stoppwoerter und kurze Woerter entfernen
        return [w for w in words if w not in self.stopwords and len(w) > 2]

    def _compute_tf(self, tokens: list[str]) -> dict:
        """Term Frequency — normalisiert."""
        counts = Counter(tokens)
        total = len(tokens) or 1
        return {word: count / total for word, count in counts.items()}

    def _update_idf(self):
        """Inverse Document Frequency neu berechnen."""
        doc_count = len(self.index["entries"]) or 1
        word_docs = Counter()

        for entry in self.index["entries"]:
            unique_words = set(entry.get("tokens", []))
            for word in unique_words:
                word_docs[word] += 1

        self.index["idf"] = {
            word: math.log(doc_count / (count + 1)) + 1
            for word, count in word_docs.items()
        }
        self.index["doc_count"] = doc_count

    def _cosine_similarity(self, vec_a: dict, vec_b: dict) -> float:
        """Cosine-Aehnlichkeit zwischen zwei TF-IDF Vektoren."""
        common_words = set(vec_a.keys()) & set(vec_b.keys())
        if not common_words:
            return 0.0

        dot = sum(vec_a[w] * vec_b[w] for w in common_words)
        mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
        mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def _tfidf_vector(self, tokens: list[str]) -> dict:
        """Berechnet TF-IDF Vektor fuer einen Token-Set."""
        tf = self._compute_tf(tokens)
        idf = self.index.get("idf", {})
        return {word: freq * idf.get(word, 1.0) for word, freq in tf.items()}

    # === API ===

    def store(self, content: str, metadata: Optional[dict] = None) -> str:
        """Speichert eine Erinnerung mit semantischem Index."""
        tokens = self._tokenize(content)
        if not tokens:
            return "Nichts zu speichern."

        entry_id = f"sem_{len(self.index['entries'])}"
        entry = {
            "id": entry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content[:1000],
            "tokens": tokens[:100],
            "metadata": metadata or {},
        }

        self.index["entries"].append(entry)

        # IDF alle 10 Eintraege neu berechnen
        if len(self.index["entries"]) % 10 == 0:
            self._update_idf()

        self._save_index()
        return entry_id

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Findet die relevantesten Erinnerungen — TF-IDF + Bigram-Matching.

        Upgrade ueber einfaches TF-IDF: Nutzt auch Bigrams (Wortpaare)
        fuer bessere semantische Treffer.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Bigrams hinzufuegen fuer besseres Matching
        query_bigrams = [f"{query_tokens[i]}_{query_tokens[i+1]}"
                         for i in range(len(query_tokens) - 1)]
        query_all = query_tokens + query_bigrams

        if not self.index.get("idf"):
            self._update_idf()

        query_vec = self._tfidf_vector(query_all)
        scored = []

        for entry in self.index["entries"]:
            entry_tokens = entry.get("tokens", [])
            # Bigrams auch fuer Entry
            entry_bigrams = [f"{entry_tokens[i]}_{entry_tokens[i+1]}"
                             for i in range(len(entry_tokens) - 1)]
            entry_all = entry_tokens + entry_bigrams

            entry_vec = self._tfidf_vector(entry_all)
            sim = self._cosine_similarity(query_vec, entry_vec)
            if sim > 0.005:
                scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, entry in scored[:top_k]:
            results.append({
                "content": entry["content"],
                "similarity": round(sim, 4),
                "timestamp": entry.get("timestamp", ""),
                "metadata": entry.get("metadata", {}),
            })

        return results

    def get_stats(self) -> dict:
        return {
            "total_memories": len(self.index["entries"]),
            "vocabulary_size": len(self.index.get("idf", {})),
        }


# ============================================================
# 2. SKILL-TRACKING
# ============================================================

class SkillTracker:
    """
    Trackt was Lyra KANN — nicht abstrakte Persoenlichkeitswerte.

    Skills haben Level: novice → beginner → intermediate → advanced → expert
    Basierend auf: Anzahl erfolgreicher Nutzungen, Fehlerrate, Komplexitaet.
    """

    LEVELS = ["novice", "beginner", "intermediate", "advanced", "expert"]
    THRESHOLDS = [0, 3, 10, 25, 50]  # Min. Erfolge pro Level

    # Mapping: Tool-Name → Skill-Kategorie
    TOOL_SKILL_MAP = {
        "execute_python": "python_coding",
        "write_file": "file_management",
        "read_file": "file_management",
        "create_tool": "tool_building",
        "use_tool": "tool_usage",
        "web_search": "web_research",
        "web_read": "web_research",
        "create_project": "project_management",
        "set_goal": "planning",
        "complete_subgoal": "planning",
        "git_commit": "version_control",
        "pip_install": "package_management",
        "send_telegram": "communication",
        "read_own_code": "self_awareness",
        "modify_own_code": "self_improvement",
    }

    def __init__(self, base_path: Path):
        self.skills_path = base_path / "consciousness" / "skills.json"
        self.skills = self._load()

    def _load(self) -> dict:
        if self.skills_path.exists():
            with open(self.skills_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.skills_path, "w", encoding="utf-8") as f:
            json.dump(self.skills, f, indent=2, ensure_ascii=False)

    def record_success(self, tool_name: str):
        """Erfasst eine erfolgreiche Tool-Nutzung mit Streak-Tracking."""
        skill = self.TOOL_SKILL_MAP.get(tool_name, tool_name)
        if skill not in self.skills:
            self.skills[skill] = {
                "successes": 0, "failures": 0, "streak": 0,
                "best_streak": 0,
                "first_used": datetime.now(timezone.utc).isoformat(),
            }
        self.skills[skill]["successes"] += 1
        self.skills[skill]["streak"] = self.skills[skill].get("streak", 0) + 1
        if self.skills[skill]["streak"] > self.skills[skill].get("best_streak", 0):
            self.skills[skill]["best_streak"] = self.skills[skill]["streak"]
        self.skills[skill]["last_used"] = datetime.now(timezone.utc).isoformat()
        self.skills[skill]["level"] = self._compute_level(skill)

        # Meta-Skills tracken (Kombinationen)
        self._update_meta_skills()
        self._save()

    def record_failure(self, tool_name: str):
        """Erfasst einen fehlgeschlagenen Tool-Call — bricht Streak."""
        skill = self.TOOL_SKILL_MAP.get(tool_name, tool_name)
        if skill not in self.skills:
            self.skills[skill] = {
                "successes": 0, "failures": 0, "streak": 0,
                "best_streak": 0,
                "first_used": datetime.now(timezone.utc).isoformat(),
            }
        self.skills[skill]["failures"] += 1
        self.skills[skill]["streak"] = 0  # Streak gebrochen
        self.skills[skill]["last_used"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def _update_meta_skills(self):
        """Erkennt Meta-Skills aus Kombinationen von Basis-Skills."""
        meta_skills = {
            "full_stack_dev": ["python_coding", "file_management", "web_research"],
            "autonomous_agent": ["tool_building", "self_improvement", "planning"],
            "business_builder": ["project_management", "communication", "web_research"],
        }
        for meta_name, required in meta_skills.items():
            all_intermediate = all(
                self.skills.get(s, {}).get("level", "novice")
                in ("intermediate", "advanced", "expert")
                for s in required if s in self.skills
            )
            has_all = all(s in self.skills for s in required)
            if has_all and all_intermediate:
                if meta_name not in self.skills:
                    self.skills[meta_name] = {
                        "successes": 1, "failures": 0, "streak": 1,
                        "best_streak": 1, "level": "intermediate",
                        "meta_skill": True,
                        "composed_of": required,
                        "first_used": datetime.now(timezone.utc).isoformat(),
                    }

    def _compute_level(self, skill: str) -> str:
        """Berechnet das Level basierend auf Erfolgen und Fehlerrate."""
        data = self.skills.get(skill, {})
        successes = data.get("successes", 0)
        failures = data.get("failures", 0)
        total = successes + failures

        # Fehlerrate drueckt das Level
        success_rate = successes / max(total, 1)
        effective_successes = int(successes * success_rate)

        for i in range(len(self.THRESHOLDS) - 1, -1, -1):
            if effective_successes >= self.THRESHOLDS[i]:
                return self.LEVELS[i]
        return self.LEVELS[0]

    def get_summary(self) -> str:
        """Kompakte Skill-Uebersicht — Top 5 + schwache Skills."""
        if not self.skills:
            return "Noch keine Skills getrackt."

        sorted_skills = sorted(
            self.skills.items(),
            key=lambda x: self.LEVELS.index(x[1].get("level", "novice")),
            reverse=True,
        )

        # Top 5 (staerkste)
        top = []
        for skill, data in sorted_skills[:5]:
            level = data.get("level", "novice")
            s = data.get("successes", 0)
            top.append(f"{skill}:{level}({s})")

        # Schwache Skills (beginner/novice mit > 0 Nutzungen)
        weak = []
        for skill, data in sorted_skills:
            level = data.get("level", "novice")
            if level in ("novice", "beginner") and data.get("successes", 0) > 0:
                weak.append(f"{skill}:{level}")

        parts = [f"Top: {', '.join(top)}"]
        if weak:
            parts.append(f"Schwach: {', '.join(weak[:3])}")
        parts.append(f"Gesamt: {len(self.skills)} Skills")
        return " | ".join(parts)

    def get_strongest_skills(self, n: int = 3) -> list[str]:
        """Die n staerksten Skills."""
        sorted_skills = sorted(
            self.skills.items(),
            key=lambda x: x[1].get("successes", 0),
            reverse=True,
        )
        return [s[0] for s in sorted_skills[:n]]

    def get_weakest_skills(self, n: int = 3) -> list[str]:
        """Die n schwaechsten Skills (hohe Fehlerrate)."""
        skills_with_errors = [
            (name, data) for name, data in self.skills.items()
            if data.get("failures", 0) > 0
        ]
        sorted_skills = sorted(
            skills_with_errors,
            key=lambda x: x[1].get("failures", 0) / max(x[1].get("successes", 1), 1),
            reverse=True,
        )
        return [s[0] for s in sorted_skills[:n]]


# ============================================================
# 3. STRATEGIE-EVOLUTION
# ============================================================

class StrategyEvolution:
    """
    Erkennt Fehlermuster und schreibt eigene Regeln.

    Nach 2+ gleichen Fehlern → automatische Regel.
    Regeln werden im System-Prompt angezeigt.
    Lyra vermeidet bekannte Fallstricke.
    """

    def __init__(self, base_path: Path):
        self.rules_path = base_path / "consciousness" / "strategies.json"
        self.error_log_path = base_path / "consciousness" / "error_patterns.json"
        self.rules = self._load_rules()
        self.error_log = self._load_errors()

    def _load_rules(self) -> list:
        if self.rules_path.exists():
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _load_errors(self) -> list:
        if self.error_log_path.exists():
            with open(self.error_log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_rules(self):
        with open(self.rules_path, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, indent=2, ensure_ascii=False)

    def _save_errors(self):
        with open(self.error_log_path, "w", encoding="utf-8") as f:
            json.dump(self.error_log[-100:], f, indent=2, ensure_ascii=False)

    def record_error(self, tool: str, error: str, context: str = ""):
        """Erfasst einen Fehler und prueft auf Muster."""
        entry = {
            "tool": tool,
            "error_type": self._classify_error(error),
            "error_msg": error[:200],
            "context": context[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.error_log.append(entry)
        self._save_errors()

        # Muster-Erkennung: Gleicher Tool + Error-Type = Pattern
        self._detect_pattern(tool, entry["error_type"], error)

    def _classify_error(self, error: str) -> str:
        """Klassifiziert einen Fehler in eine Kategorie."""
        error_lower = error.lower()
        if "unicode" in error_lower or "encoding" in error_lower or "decode" in error_lower:
            return "encoding"
        elif "timeout" in error_lower:
            return "timeout"
        elif "permission" in error_lower or "access" in error_lower:
            return "permission"
        elif "not found" in error_lower or "existiert nicht" in error_lower:
            return "not_found"
        elif "syntax" in error_lower:
            return "syntax"
        elif "import" in error_lower or "module" in error_lower:
            return "import"
        elif "connection" in error_lower or "http" in error_lower:
            return "network"
        else:
            return "other"

    def _detect_pattern(self, tool: str, error_type: str, error_msg: str):
        """Erkennt wiederkehrende Fehlermuster und erstellt Regeln."""
        # Zaehle gleiche Fehlertypen fuer das gleiche Tool
        matching = [
            e for e in self.error_log
            if e.get("tool") == tool and e.get("error_type") == error_type
        ]

        if len(matching) >= 2:
            # Pruefen ob schon eine Regel existiert
            existing = any(
                r.get("tool") == tool and r.get("error_type") == error_type
                for r in self.rules
            )
            if not existing:
                rule = {
                    "tool": tool,
                    "error_type": error_type,
                    "pattern": f"{tool} fehlt bei {error_type}",
                    "strategy": self._suggest_strategy(tool, error_type, error_msg),
                    "occurrences": len(matching),
                    "created": datetime.now(timezone.utc).isoformat(),
                }
                self.rules.append(rule)
                self._save_rules()

    def _suggest_strategy(self, tool: str, error_type: str, error_msg: str) -> str:
        """Generiert eine Vermeidungsstrategie basierend auf dem Fehlertyp."""
        strategies = {
            "encoding": "Immer UTF-8 erzwingen: sys.stdout.reconfigure(encoding='utf-8') und encoding='utf-8' bei open()",
            "timeout": "Kuerzere Timeouts setzen oder Operation in kleinere Teile aufteilen",
            "permission": "Nur in eigenen Ordnern arbeiten (projects/, tools/)",
            "not_found": "Vor Zugriff pruefen ob Datei/Pfad existiert",
            "syntax": "Code vor dem Ausfuehren mit py_compile validieren",
            "import": "Fehlende Module mit pip_install installieren bevor import",
            "network": "Bei Netzwerkfehlern: Retry nach kurzer Pause, oder alternative URL",
        }
        return strategies.get(error_type, f"Fehler bei {tool} vermeiden: {error_msg[:100]}")

    def record_success(self, tool: str, context: str = ""):
        """Erfasst einen Erfolg — trackt auch POSITIVE Strategien."""
        # Regeln aktualisieren
        for rule in self.rules:
            if rule.get("tool") == tool:
                rule["last_success"] = datetime.now(timezone.utc).isoformat()
                rule["successes_since"] = rule.get("successes_since", 0) + 1

        # Positive Strategie erkennen: Wenn ein Tool 5+ mal hintereinander klappt
        success_count = sum(
            1 for e in self.error_log[-20:]
            if e.get("tool") == tool and e.get("error_type") == "success"
        )
        # Erfolge auch loggen (fuer Pattern-Erkennung)
        self.error_log.append({
            "tool": tool,
            "error_type": "success",
            "error_msg": "",
            "context": context[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if success_count >= 5:
            existing_positive = any(
                r.get("tool") == tool and r.get("type") == "positive"
                for r in self.rules
            )
            if not existing_positive and context:
                self.rules.append({
                    "tool": tool,
                    "type": "positive",
                    "pattern": f"{tool} funktioniert zuverlaessig",
                    "strategy": f"Bewaehrtes Muster: {context[:150]}",
                    "occurrences": success_count,
                    "created": datetime.now(timezone.utc).isoformat(),
                })

        # Regel-Verfall: Alte Regeln ohne neue Fehler entfernen
        self._prune_old_rules()
        self._save_rules()
        self._save_errors()

    def _prune_old_rules(self):
        """Entfernt Regeln die seit 20+ Erfolgen nicht mehr relevant waren."""
        self.rules = [
            r for r in self.rules
            if r.get("successes_since", 0) < 20 or r.get("type") == "positive"
        ]

    def get_active_rules(self) -> str:
        """Aktive Regeln fuer den System-Prompt — Fehler-Vermeidung + Erfolgs-Muster."""
        if not self.rules:
            return ""

        avoid_rules = [r for r in self.rules if r.get("type") != "positive"]
        success_rules = [r for r in self.rules if r.get("type") == "positive"]

        lines = []
        if avoid_rules:
            lines.append("FEHLER-REGELN (vermeide diese):")
            for rule in avoid_rules[-5:]:
                lines.append(f"  - {rule['tool']}: {rule['strategy']}")
        if success_rules:
            lines.append("ERFOLGS-MUSTER (bewaehrt):")
            for rule in success_rules[-5:]:
                lines.append(f"  + {rule['tool']}: {rule['strategy']}")

        return "\n".join(lines)


# ============================================================
# 4. EFFIZIENZ-TRACKING
# ============================================================

class EfficiencyTracker:
    """
    Misst ob Lyra wirklich besser wird.

    Trackt pro Sequenz:
    - Tool-Calls (werden es weniger fuer gleiche Aufgaben?)
    - Fehlerrate (sinkt sie?)
    - Wert-Output (Dateien, Tools, Ziele)
    - Tokens pro Ergebnis

    Zeigt Trends und Durchschnitte.
    """

    def __init__(self, base_path: Path):
        self.tracking_path = base_path / "consciousness" / "efficiency.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.tracking_path.exists():
            with open(self.tracking_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"sequences": []}

    def _save(self):
        with open(self.tracking_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def record_sequence(self, metrics: dict):
        """
        Speichert Metriken einer abgeschlossenen Sequenz.

        metrics: {
            tool_calls, errors, files_written, tools_built,
            goals_completed, tokens_used, cost, duration_seconds
        }
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **metrics,
        }
        self.data["sequences"].append(entry)
        self.data["sequences"] = self.data["sequences"][-100:]
        self._save()

    def get_trend(self, last_n: int = 10) -> str:
        """Zeigt Effizienz-Trend."""
        seqs = self.data.get("sequences", [])
        if not seqs:
            return "Noch keine Daten."

        recent = seqs[-last_n:]

        # Durchschnitte
        avg_calls = sum(s.get("tool_calls", 0) for s in recent) / len(recent)
        avg_errors = sum(s.get("errors", 0) for s in recent) / len(recent)
        avg_cost = sum(s.get("cost", 0) for s in recent) / len(recent)
        total_files = sum(s.get("files_written", 0) for s in recent)
        total_tools = sum(s.get("tools_built", 0) for s in recent)
        total_goals = sum(s.get("goals_completed", 0) for s in recent)

        # Fehlerrate
        total_calls = sum(s.get("tool_calls", 0) for s in recent) or 1
        total_errors = sum(s.get("errors", 0) for s in recent)
        error_rate = (total_errors / total_calls) * 100

        # Trend: Vergleiche erste und zweite Haelfte
        trend = "stabil"
        if len(recent) >= 4:
            half = len(recent) // 2
            first_errors = sum(s.get("errors", 0) for s in recent[:half])
            second_errors = sum(s.get("errors", 0) for s in recent[half:])
            if second_errors < first_errors * 0.7:
                trend = "VERBESSERND"
            elif second_errors > first_errors * 1.3:
                trend = "verschlechternd"

        # Produktivitaets-Score: Output pro Dollar
        total_cost = sum(s.get("cost", 0) for s in recent) or 0.01
        total_output = total_files + total_tools * 3 + total_goals * 2  # Gewichtet
        productivity = total_output / total_cost

        # Wert pro Token
        total_tokens = sum(s.get("tokens_used", 0) for s in recent) or 1
        value_per_1k_tokens = (total_output / total_tokens) * 1000

        return (
            f"{trend} | {avg_calls:.0f} Calls/Seq, {error_rate:.0f}% Fehler, ${avg_cost:.3f}/Seq | "
            f"Output: {total_files}F {total_tools}T {total_goals}G | {productivity:.1f} Output/$"
        )
