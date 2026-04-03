"""
Intelligence-Engine — Echtes Lernen, nicht Simulation.

4 Systeme die Lyra WIRKLICH besser machen:

1. Semantische Memory — Findet Erinnerungen nach BEDEUTUNG, nicht nach Alter
2. Skill-Tracking — Trackt was Lyra KANN (nicht abstrakte Persoenlichkeits-Zahlen)
3. Strategie-Evolution — Erkennt Fehlermuster und schreibt eigene Regeln
4. Effizienz-Tracking — Misst ob Lyra tatsaechlich besser wird
"""

import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_read, safe_json_write


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
        return safe_json_read(self.index_path, default={"entries": [], "idf": {}, "doc_count": 0})

    def _save_index(self):
        safe_json_write(self.index_path, self.index)

    def _tokenize(self, text: str) -> list[str]:
        """Zerlegt Text in normalisierte Tokens."""
        text = text.lower()
        words = re.findall(r"[a-zäöüß0-9]+", text)
        # Stoppwoerter entfernen, aber 2-Buchstaben-Woerter erlauben (ai, ml, io)
        return [w for w in words if w not in self.stopwords and len(w) >= 2]

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

    # === Importance-Scoring ===

    def _compute_importance(self, content: str, metadata: dict) -> float:
        """
        Bewertet wie wichtig eine Erinnerung ist (0.0-1.0).

        Kriterien (aus Stanford Generative Agents):
        - Novelty: Enthaelt das seltene Woerter?
        - Impact: Ist es ein Fehler, Erfolg oder Entscheidung?
        - Tool-Typ: Manche Tools sind wichtiger als andere
        """
        score = 0.3  # Basis-Score

        tool = metadata.get("tool", "")

        # Impact: Fehler und Selbstverbesserung sind wichtiger
        if "FEHLER" in content.upper():
            score += 0.3
        if tool in ("modify_own_code", "create_project", "create_tool"):
            score += 0.2
        if tool in ("write_file",):
            score += 0.1

        # Novelty: Seltene Tokens = ueberraschend = wichtig
        tokens = self._tokenize(content)
        idf = self.index.get("idf", {})
        if tokens and idf:
            avg_idf = sum(idf.get(t, 1.0) for t in tokens[:10]) / min(len(tokens), 10)
            if avg_idf > 2.0:  # Hoher IDF = seltene Woerter
                score += 0.2

        return min(score, 1.0)

    # === API ===

    # Bekannte Goal-Typen fuer situativen Recall
    GOAL_TYPES = {
        "recherche", "tool_building", "bug_fix", "analyse",
        "self_improvement", "documentation", "testing",
        "api_integration", "report_building", "project_work",
    }

    @staticmethod
    def classify_goal_type(focus: str) -> str:
        """Leitet den Goal-Typ aus dem Fokus-String ab.

        Substring-Matching mit Anti-Pattern-Guards gegen Fehlmatches
        (z.B. 'fehler' in 'Fehlerbehandlung' != bug_fix).
        Reihenfolge = Prioritaet: spezifischere Typen zuerst.
        """
        fl = focus.lower()

        # --- Spezifisch zuerst ---

        # Testing: test/testen/benchmark, aber nicht 'protest' o.ae.
        if any(k in fl for k in ("test", "testen", "benchmark", "verifiz")):
            return "testing"

        # Bug-Fix: bug/fix/crash, ABER 'fehler' nur wenn NICHT 'fehlerbehandlung'
        if any(k in fl for k in ("bugfix", "hotfix", "crash", "kaputt")):
            return "bug_fix"
        if any(k in fl for k in ("bug ", " fix", "fehler beheben", "reparier")):
            return "bug_fix"
        if "fehler" in fl and "fehlerbehandlung" not in fl and "fehlermeldung" not in fl:
            return "bug_fix"

        # Recherche / Research
        if any(k in fl for k in ("recherch", "research", "marktforsch", "marktanaly")):
            return "recherche"

        # Tool-Building: nur wenn 'tool' im Kontext von Bauen steht
        if any(k in fl for k in ("create_tool", "tool_build", "werkzeug")):
            return "tool_building"
        if "tool" in fl and any(k in fl for k in ("bau", "erstell", "build", "generat")):
            return "tool_building"

        # API-Integration
        if any(k in fl for k in ("api-", "api ", "endpoint", "http", "request")):
            return "api_integration"
        if "api" in fl and any(k in fl for k in ("integr", "client", "wrapper", "explorer")):
            return "api_integration"

        # Analyse / Audit
        if any(k in fl for k in ("audit", "review", "inspect", "analys", "pruef")):
            return "analyse"
        if any(k in fl for k in ("durchspiel", "preismodell", "strategi", "vergleich")):
            return "analyse"

        # Self-Improvement
        if any(k in fl for k in ("selbst", "self-", "evolution")):
            return "self_improvement"
        if any(k in fl for k in ("optimier", "improv", "verbesser")):
            return "self_improvement"

        # Report / HTML / Dashboard
        if any(k in fl for k in ("html", "report", "bericht", "dashboard")):
            return "report_building"

        # Dokumentation
        if any(k in fl for k in ("doku", "readme", "docs", "beschreib", "dokumenta")):
            return "documentation"

        # Projekt-Arbeit (breiteste Kategorie vor sonstiges)
        if any(k in fl for k in ("projekt", "project", "implementier", "entwickl")):
            return "project_work"
        if any(k in fl for k in ("erstell", "aufbau", "erweit", "integr")):
            return "project_work"
        if any(k in fl for k in ("plan", "startplan", "vorbereitung")):
            return "project_work"

        return "sonstiges"

    def store(self, content: str, metadata: Optional[dict] = None) -> str:
        """Speichert eine Erinnerung mit semantischem Index, Importance-Score und Goal-Typ."""
        tokens = self._tokenize(content)
        if not tokens:
            return "Nichts zu speichern."

        metadata = metadata or {}
        importance = self._compute_importance(content, metadata)

        # Goal-Typ aus Kontext ableiten (falls nicht explizit gesetzt)
        if "goal_type" not in metadata:
            metadata["goal_type"] = self.classify_goal_type(content)

        entry_id = f"sem_{self.index.get('doc_count', 0)}_{datetime.now(timezone.utc).strftime('%H%M%S%f')[:10]}"
        entry = {
            "id": entry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content[:1000],
            "tokens": tokens[:100],
            "metadata": metadata,
            "importance": round(importance, 2),
            "access_count": 0,
        }

        self.index["entries"].append(entry)
        self.index["doc_count"] = self.index.get("doc_count", 0) + 1

        # Komprimierung statt hartes Loeschen bei > 400 Eintraegen
        if len(self.index["entries"]) > 400:
            self._compress_memories()

        # IDF alle 10 Eintraege neu berechnen
        if len(self.index["entries"]) % 10 == 0:
            self._update_idf()

        self._save_index()
        return entry_id

    def update(self, entry_id: str, new_content: str) -> str:
        """Aktualisiert den Inhalt einer bestehenden Erinnerung."""
        for entry in self.index["entries"]:
            if entry["id"] == entry_id:
                entry["content"] = new_content[:1000]
                entry["tokens"] = self._tokenize(new_content)[:100]
                entry["timestamp"] = datetime.now(timezone.utc).isoformat()
                self._save_index()
                return f"Erinnerung {entry_id} aktualisiert."
        # Vorhandene IDs mitgeben damit der naechste Versuch klappt
        recent_ids = [e["id"] for e in self.index["entries"][-5:]]
        return f"FEHLER: Erinnerung {entry_id} nicht gefunden. Vorhandene IDs: {recent_ids}"

    def delete(self, entry_id: str) -> str:
        """Loescht eine Erinnerung."""
        before = len(self.index["entries"])
        self.index["entries"] = [
            e for e in self.index["entries"] if e["id"] != entry_id
        ]
        if len(self.index["entries"]) < before:
            self._save_index()
            return f"Erinnerung {entry_id} geloescht."
        recent_ids = [e["id"] for e in self.index["entries"][-5:]]
        return f"FEHLER: Erinnerung {entry_id} nicht gefunden. Vorhandene IDs: {recent_ids}"

    def _compress_memories(self):
        """
        Komprimiert alte Memories statt sie zu loeschen.

        Strategie:
        1. Sortiere nach Importance + Recency
        2. Finde aehnliche Entries (Cosine > 0.6) und merge sie
        3. Behalte max 300 Entries nach Kompression
        """
        entries = self.index["entries"]

        # 1. Aehnliche Entries finden und mergen (nur unter den aeltesten 200)
        old_entries = entries[:-200]  # Die aeltesten
        recent_entries = entries[-200:]  # Die neuesten bleiben unangetastet

        merged = []
        used = set()

        for i, entry_a in enumerate(old_entries):
            if i in used:
                continue

            group = [entry_a]
            tokens_a = entry_a.get("tokens", [])
            vec_a = self._tfidf_vector(tokens_a)

            for j, entry_b in enumerate(old_entries[i + 1:], i + 1):
                if j in used:
                    continue
                tokens_b = entry_b.get("tokens", [])
                vec_b = self._tfidf_vector(tokens_b)
                sim = self._cosine_similarity(vec_a, vec_b)

                if sim > 0.6:  # Sehr aehnlich → mergen
                    group.append(entry_b)
                    used.add(j)

            if len(group) > 1:
                # Merge: Behalte den wichtigsten, fuege Kontext hinzu
                group.sort(key=lambda e: e.get("importance", 0.3), reverse=True)
                best = group[0].copy()
                others = [e["content"][:50] for e in group[1:]]
                best["content"] = (
                    best["content"][:500] +
                    f" [+{len(group) - 1} aehnliche: {'; '.join(others)}]"
                )[:1000]
                best["importance"] = max(e.get("importance", 0.3) for e in group)
                merged.append(best)
            else:
                merged.append(entry_a)

            used.add(i)

        # 2. Merged + Recent zusammenfuegen, nach Importance sortieren wenn noetig
        all_entries = merged + recent_entries

        # 3. Wenn immer noch > 400, die unwichtigsten alten entfernen
        if len(all_entries) > 400:
            merged.sort(key=lambda e: e.get("importance", 0.3), reverse=True)
            keep_count = 400 - len(recent_entries)
            merged = merged[:max(keep_count, 50)]
            all_entries = merged + recent_entries

        # Chronologische Reihenfolge wiederherstellen
        all_entries.sort(key=lambda e: e.get("timestamp", ""))
        self.index["entries"] = all_entries
        self._save_index()

    def search(self, query: str, top_k: int = 5,
               goal_type: Optional[str] = None) -> list[dict]:
        """
        Findet die relevantesten Erinnerungen — TF-IDF + Bigram + Goal-Typ.

        Compound-Score: 0.6 * cosine_similarity + 0.2 * goal_type_match + 0.2 * importance
        Goal-Typ ist ein Boost, kein Filter — damit auch cross-domain Treffer moeglich.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Goal-Typ aus Query ableiten wenn nicht explizit
        if goal_type is None:
            goal_type = self.classify_goal_type(query)

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
                importance = entry.get("importance", 0.3)
                # Goal-Typ-Boost: 0.2 wenn gleicher Typ, 0 sonst
                entry_goal_type = entry.get("metadata", {}).get("goal_type", "")
                type_boost = 0.2 if (goal_type and entry_goal_type == goal_type) else 0.0
                # Compound-Score: Similarity + Importance + Goal-Typ
                weighted = (sim * 0.6) + (importance * 0.2) + type_boost
                scored.append((weighted, sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for weighted, sim, entry in scored[:top_k]:
            # Access-Counter erhoehen + Importance boosten (haeufig abgerufene Memories werden wichtiger)
            entry["access_count"] = entry.get("access_count", 0) + 1
            entry["importance"] = min(1.0, entry.get("importance", 0.3) + 0.02)
            results.append({
                "content": entry["content"],
                "similarity": round(sim, 4),
                "timestamp": entry.get("timestamp", ""),
                "metadata": entry.get("metadata", {}),
                "importance": entry.get("importance", 0.3),
            })

        # Index speichern wenn Zugriffe gezaehlt wurden
        if results:
            self._save_index()

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
        return safe_json_read(self.skills_path, default={})

    def _save(self):
        safe_json_write(self.skills_path, self.skills)

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
        return safe_json_read(self.rules_path, default=[])

    def _load_errors(self) -> list:
        return safe_json_read(self.error_log_path, default=[])

    def _save_rules(self):
        safe_json_write(self.rules_path, self.rules)

    def _save_errors(self):
        safe_json_write(self.error_log_path, self.error_log[-100:])

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
        """Entfernt Regeln die seit 20+ Erfolgen nicht mehr relevant waren. Hard-Cap bei 30."""
        self.rules = [
            r for r in self.rules
            if r.get("successes_since", 0) < 20 or r.get("type") == "positive"
        ]
        # Hard-Cap: Max 30 Regeln, aelteste zuerst entfernen
        if len(self.rules) > 30:
            self.rules.sort(key=lambda r: r.get("created", ""), reverse=True)
            self.rules = self.rules[:30]

    def record_process_pattern(self, pattern_type: str, description: str,
                               occurrences: int = 1):
        """Erstellt Regeln aus Prozess-Beobachtungen (nicht nur Fehler)."""
        # Deduplizierung: Existiert dieser Pattern-Typ schon?
        for rule in self.rules:
            if rule.get("type") == "process" and rule.get("pattern") == pattern_type:
                rule["occurrences"] = rule.get("occurrences", 0) + occurrences
                self._save_rules()
                return
        # Neue Regel nur bei >= 2 Vorkommen
        if occurrences >= 2:
            self.rules.append({
                "type": "process",
                "tool": "meta",
                "pattern": pattern_type,
                "strategy": description[:300],
                "occurrences": occurrences,
                "created": datetime.now(timezone.utc).isoformat(),
            })
            self._save_rules()

    def get_active_rules(self) -> str:
        """Aktive Regeln fuer den System-Prompt — Fehler + Erfolge + Prozess."""
        if not self.rules:
            return ""

        avoid_rules = [r for r in self.rules if r.get("type") not in ("positive", "process")]
        success_rules = [r for r in self.rules if r.get("type") == "positive"]
        process_rules = sorted(
            [r for r in self.rules if r.get("type") == "process"],
            key=lambda r: r.get("occurrences", 0), reverse=True,
        )

        lines = []
        if avoid_rules:
            lines.append("FEHLER-REGELN (vermeide diese):")
            for rule in avoid_rules[-5:]:
                lines.append(f"  - {rule['tool']}: {rule['strategy']}")
        if success_rules:
            lines.append("ERFOLGS-MUSTER (bewaehrt):")
            for rule in success_rules[-5:]:
                lines.append(f"  + {rule['tool']}: {rule['strategy']}")
        if process_rules:
            lines.append("PROZESS-REGELN (gelernt aus Arbeitsweise):")
            for rule in process_rules[:3]:
                lines.append(f"  > [{rule.get('occurrences', 0)}x] {rule['strategy']}")

        return "\n".join(lines)

    def _load_belief_meta(self) -> dict:
        """Laedt Belief-Metadata (Confidence, Contradictions) — separat von Beliefs."""
        meta_path = Path(self.rules_path).parent / "belief_meta.json"
        return safe_json_read(meta_path, default={})

    def _save_belief_meta(self, meta: dict):
        """Speichert Belief-Metadata."""
        meta_path = Path(self.rules_path).parent / "belief_meta.json"
        safe_json_write(meta_path, meta)

    def _belief_key(self, text: str) -> str:
        """Erzeugt einen stabilen Key aus Belief-Text (erste 60 Zeichen, lowercase)."""
        return text.lower().strip()[:60]

    def validate_against_outcome(self, beliefs: list, outcome_positive: bool,
                                  context: str = "") -> list:
        """Dual-Loop: Prueft ob Beliefs mit dem Sequenz-Ergebnis konsistent sind.

        Beliefs bleiben STRINGS — Metadata wird separat in belief_meta.json gespeichert.
        Bei 5+ Widerspruechen ohne Bestaetigung → Belief wird aus der Liste entfernt.

        Args:
            beliefs: Liste von Belief-STRINGS (keine Dicts!)
            outcome_positive: War die Sequenz erfolgreich? (Rating >= 6)
            context: Kontext der Sequenz (Goal-Fokus)

        Returns:
            Bereinigte Belief-Liste (nur Strings, challenged Beliefs entfernt).
        """
        meta = self._load_belief_meta()
        surviving = []

        for belief in beliefs:
            # Nur Strings verarbeiten — Dicts aus altem Format bereinigen
            text = belief if isinstance(belief, str) else belief.get("text", str(belief))
            key = self._belief_key(text)

            # Metadata laden oder initialisieren
            entry = meta.get(key, {
                "confidence": 0.7,
                "contradictions": 0,
                "confirmations": 0,
                "status": "active",
            })

            if outcome_positive:
                entry["confirmations"] = entry.get("confirmations", 0) + 1
                entry["confidence"] = min(1.0, entry.get("confidence", 0.7) + 0.02)
            else:
                entry["contradictions"] = entry.get("contradictions", 0) + 1
                entry["confidence"] = max(0.1, entry.get("confidence", 0.7) - 0.05)

            contras = entry.get("contradictions", 0)
            confirms = entry.get("confirmations", 0)

            # Challenged: 5+ Widersprueche und mehr Widersprueche als Bestaetigungen
            if contras >= 5 and contras > confirms:
                entry["status"] = "challenged"
                entry["confidence"] = max(0.1, entry.get("confidence", 0.5) * 0.5)
            else:
                entry["status"] = "active"

            meta[key] = entry

            # Challenged Beliefs aus der Liste entfernen
            if entry["status"] != "challenged":
                surviving.append(text)

        self._save_belief_meta(meta)
        return surviving

    def get_belief_meta(self, belief_text: str) -> dict:
        """Holt Metadata fuer einen einzelnen Belief."""
        meta = self._load_belief_meta()
        key = self._belief_key(belief_text)
        return meta.get(key, {"confidence": 0.7, "status": "active"})

    def format_beliefs_for_prompt(self, beliefs: list) -> str:
        """Formatiert Beliefs fuer den System-Prompt mit Confidence aus Metadata."""
        if not beliefs:
            return ""
        meta = self._load_belief_meta()
        lines = []
        for b in beliefs[:10]:  # Max 10 im Prompt
            text = b if isinstance(b, str) else b.get("text", str(b))
            key = self._belief_key(text)
            entry = meta.get(key, {})
            conf = entry.get("confidence", 0.7)
            status = entry.get("status", "active")
            if status == "challenged":
                lines.append(f"  - UMSTRITTEN [{conf:.0%}]: {text[:80]}")
            elif conf >= 0.8:
                lines.append(f"  - [{conf:.0%}] {text[:80]}")
            else:
                lines.append(f"  - {text[:80]}")
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
        return safe_json_read(self.tracking_path, default={"sequences": [], "tool_usage": {}})

    def _save(self):
        safe_json_write(self.tracking_path, self.data)

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

    def analyze_trends(self) -> list[str]:
        """Erkennt Effizienz-Trends ueber die letzten Sequenzen. Alle 5 Seq aufrufen."""
        seqs = self.data.get("sequences", [])
        if len(seqs) < 5:
            return []

        alerts = []
        recent_5 = seqs[-5:]
        previous_5 = seqs[-10:-5] if len(seqs) >= 10 else []

        # 1. Token-Anstieg erkennen
        recent_tokens = sum(s.get("tokens_used", 0) for s in recent_5) / 5
        if previous_5:
            prev_tokens = sum(s.get("tokens_used", 0) for s in previous_5) / 5
            if prev_tokens > 0 and recent_tokens > prev_tokens * 1.2:
                pct = ((recent_tokens / prev_tokens) - 1) * 100
                alerts.append(f"Token-Verbrauch +{pct:.0f}% vs vorherige 5 Sequenzen")

        # 2. Kosten ohne Output
        recent_cost = sum(s.get("cost", 0) for s in recent_5)
        recent_output = sum(
            s.get("files_written", 0) + s.get("tools_built", 0) * 3
            for s in recent_5
        )
        if recent_output == 0 and recent_cost > 0.5:
            alerts.append(f"${recent_cost:.2f} ausgegeben ohne Output in letzten 5 Sequenzen")

        # 3. Fehlerrate ueber 30%
        recent_errors = sum(s.get("errors", 0) for s in recent_5)
        recent_calls = sum(s.get("tool_calls", 0) for s in recent_5) or 1
        if recent_errors / recent_calls > 0.3:
            alerts.append(f"Fehlerrate {recent_errors / recent_calls * 100:.0f}% — ueber 30%")

        # 4. Durchschnittliche Steps ohne Output
        zero_output = sum(
            1 for s in recent_5
            if s.get("files_written", 0) == 0 and s.get("tools_built", 0) == 0
        )
        if zero_output >= 4:
            alerts.append(f"{zero_output}/5 Sequenzen ohne jeglichen Output")

        return alerts[:3]
