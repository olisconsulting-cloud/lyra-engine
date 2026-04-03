"""
Dream-System — Memory-Konsolidierung wie Claude Code AutoDream.

Periodisch (nach N Sequenzen oder manuell) laueft ein Konsolidierungs-Agent
der alle Erinnerungen, Beliefs, Strategien und Skills durchgeht und:

1. ORIENT — Inventarisiert den aktuellen Memory-Stand
2. GATHER — Extrahiert Muster aus letzten Erfahrungen
3. CONSOLIDATE — Merged, dedupliziert, aktualisiert
4. PRUNE — Entfernt Veraltetes, haelt Index kompakt

Basiert auf dem oeffentlichen Claude Code Dream System-Prompt.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .llm_ops import _extract_response_text

logger = logging.getLogger(__name__)


class DreamEngine:
    """Konsolidiert Lyras Gedaechtnis im Hintergrund."""

    def __init__(self, base_path: Path, call_llm: Callable = None,
                 tool_dream_bridge=None):
        self.base_path = base_path
        self.consciousness_path = base_path / "consciousness"
        self.dream_log_path = self.consciousness_path / "dream_log.json"
        self.call_llm = call_llm
        self.tool_dream_bridge = tool_dream_bridge

    @staticmethod
    def _is_belief_duplicate(new_belief: str, existing_beliefs: list,
                             threshold: float = 0.5) -> bool:
        """Prueft ob ein Belief als Duplikat eines bestehenden gilt.

        Nutzt Wort-Overlap (Jaccard-Similarity) statt exaktem String-Match.
        Threshold 0.5 = 50% Wort-Ueberlappung = wahrscheinlich dasselbe.
        """
        new_text = new_belief if isinstance(new_belief, str) else str(new_belief)
        new_words = set(new_text.lower().split())
        if len(new_words) < 3:
            return False  # Zu kurz fuer sinnvollen Vergleich

        for existing in existing_beliefs:
            ex_text = existing if isinstance(existing, str) else str(existing)
            ex_words = set(ex_text.lower().split())
            if len(ex_words) < 3:
                continue
            overlap = len(new_words & ex_words)
            union = len(new_words | ex_words)
            if union > 0 and overlap / union >= threshold:
                return True
        return False

    def should_dream(self, sequences_since_last: int) -> bool:
        """Prueft ob eine Konsolidierung faellig ist."""
        return sequences_since_last >= 10

    def dream(self) -> str:
        """
        Fuehrt eine komplette Memory-Konsolidierung durch.

        Liest alle Memory-Dateien, laesst Claude Muster erkennen,
        konsolidiert und pruned.
        """
        # === 1. ORIENT — Alles lesen ===
        context = self._gather_all_memory()

        # === 2-4. Claude konsolidiert ===
        system_prompt = """Du bist ein Memory-Konsolidierungs-Agent.
Deine Aufgabe: Das Gedaechtnis eines autonomen KI-Agenten namens Lyra aufraumen und optimieren.

Du bekommst den aktuellen Stand aller Memory-Dateien. Deine Aufgabe:

1. ANALYSE: Was sind die wichtigsten Erkenntnisse? Was wiederholt sich? Was ist veraltet?
2. BELIEFS: Konsolidiere auf max 15 einzigartige, wertvolle Ueberzeugungen. Loesche Redundanz.
3. STRATEGIEN: Welche Regeln sind noch relevant? Welche koennen geloescht werden?
4. SKILLS: Stimmen die Levels? Gibt es Meta-Skills die fehlen?
5. ZUSAMMENFASSUNG: Was hat Lyra in letzter Zeit gelernt? Ein Absatz.
6. PROZESS-ANALYSE: Analysiere die Metacognition-Eintraege. Welche Engpaesse wiederholen sich? Welche Sequenzen hatten hohe Effizienz (viel Output pro Step) und was war anders? Welche Arbeitsgewohnheiten sind gut, welche schlecht?
7. META-SKILLS: Wie arbeitet Lyra? Beschreibe den Arbeitsstil — plant sie gut? Fuehrt sie effizient aus? Springt sie zwischen Aufgaben? Nutzt sie finish_sequence rechtzeitig?
8. RECOMMENDATIONS: Max 2 Empfehlungen, JEDE mit 2-3 konkreten Sub-Goals. Jedes Sub-Goal muss ein messbarer, ausfuehrbarer Schritt sein — keine Absichtserklaerungen.

Antworte als JSON:
{
  "consolidated_beliefs": ["Liste der 10-15 wichtigsten Ueberzeugungen"],
  "obsolete_beliefs": ["Beliefs die geloescht werden sollen"],
  "strategy_updates": [{"rule": "...", "action": "keep|delete|update", "reason": "..."}],
  "skill_notes": "Freitext-Analyse der Skills",
  "memory_summary": "Was Lyra in letzter Zeit gelernt hat — 2-3 Saetze",
  "recommendations": [{"title": "Kurzer Titel (max 80 Zeichen)", "sub_goals": ["Konkreter Schritt 1", "Konkreter Schritt 2", "Messbares Erfolgskriterium"]}],
  "process_insights": "Was Lyra ueber ihren ARBEITSSTIL gelernt hat — nicht Aufgaben, sondern WIE sie arbeitet",
  "efficiency_patterns": ["Konkrete Beobachtungen ueber Produktivitaet und Effizienz"]
}"""

        try:
            if not self.call_llm:
                return "Dream-Fehler: call_llm nicht konfiguriert"

            response = self.call_llm(
                "dream", system_prompt,
                [{"role": "user", "content": context}],
                max_tokens=4000,
            )
            result_text = _extract_response_text(response)

            if not result_text:
                return "Dream-Fehler: Leere Antwort vom LLM"

            # JSON parsen (mit Markdown-Fence-Bereinigung und Regex-Fallback)
            cleaned = result_text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl > 0:
                    cleaned = cleaned[first_nl + 1:]
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-3].rstrip()

            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                else:
                    return "Dream fehlgeschlagen: Konnte Antwort nicht parsen"

            # === Ergebnisse anwenden ===
            applied = self._apply_results(result)

            # Dream loggen
            self._log_dream(result, applied)

            return f"Dream abgeschlossen: {applied}"

        except Exception as e:
            return f"Dream-Fehler: {e}"

    def _safe_load_json(self, path: Path) -> dict | list | None:
        """Laedt JSON robust — gibt None bei Fehler zurueck."""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return None

    def _gather_all_memory(self) -> str:
        """Sammelt alle Memory-Dateien fuer die Konsolidierung."""
        parts = []

        # Beliefs
        beliefs = self._safe_load_json(self.consciousness_path / "beliefs.json")
        if beliefs:
            parts.append(f"=== BELIEFS ===\n{json.dumps(beliefs, indent=2, ensure_ascii=False)}")

        # Strategies
        strategies = self._safe_load_json(self.consciousness_path / "strategies.json")
        if strategies:
            parts.append(f"\n=== STRATEGIEN ===\n{json.dumps(strategies, indent=2, ensure_ascii=False)}")

        # Skills
        skills = self._safe_load_json(self.consciousness_path / "skills.json")
        if skills:
            parts.append(f"\n=== SKILLS ===\n{json.dumps(skills, indent=2, ensure_ascii=False)}")

        # Sequence Memory
        seq_mem = self._safe_load_json(self.consciousness_path / "sequence_memory.json")
        if seq_mem:
            parts.append(f"\n=== LETZTE SEQUENZEN ===\n{json.dumps(seq_mem, indent=2, ensure_ascii=False)}")

        # Effizienz
        eff = self._safe_load_json(self.consciousness_path / "efficiency.json")
        if eff:
            parts.append(f"\n=== EFFIZIENZ ===\n{json.dumps(eff, indent=2, ensure_ascii=False)}")

        # Ratings
        ratings = self._safe_load_json(self.consciousness_path / "ratings.json")
        if ratings:
            last_10 = ratings[-10:] if isinstance(ratings, list) else ratings
            parts.append(f"\n=== SELBSTBEWERTUNGEN ===\n{json.dumps(last_10, indent=2, ensure_ascii=False)}")

        # Goals
        goals = self._safe_load_json(self.consciousness_path / "goals.json")
        if goals:
            parts.append(f"\n=== ZIELE ===\n{json.dumps(goals, indent=2, ensure_ascii=False)}")

        # Failures/Lessons
        failures = self._safe_load_json(self.consciousness_path / "failures.json")
        if failures:
            parts.append(f"\n=== FEHLER-LEKTIONEN ===\n{json.dumps(failures[-10:], indent=2, ensure_ascii=False)}")

        # Metacognition (Selbstreflexionen mit Prozess-Metriken)
        metacog = self._safe_load_json(self.consciousness_path / "metacognition.json")
        if metacog:
            parts.append(f"\n=== METACOGNITION (letzte 15 Reflexionen) ===\n{json.dumps(metacog[-15:], ensure_ascii=False)}")

        # Semantic Memory (letzte 20 Eintraege — nicht alle)
        sem_index = self._safe_load_json(self.base_path / "memory" / "semantic" / "index.json")
        if sem_index and sem_index.get("entries"):
            recent_sem = sem_index["entries"][-20:]
            summaries = [e.get("content", "")[:100] for e in recent_sem]
            parts.append(f"\n=== SEMANTISCHE ERINNERUNGEN (letzte 20) ===\n" +
                         "\n".join(f"  - {s}" for s in summaries))

        return "\n".join(parts)

    def _apply_results(self, result: dict) -> str:
        """Wendet die Dream-Ergebnisse an."""
        applied = []

        # Beliefs konsolidieren (Guard: nie leere Liste uebernehmen + Schema-Validierung)
        new_beliefs = result.get("consolidated_beliefs", [])
        if new_beliefs and len(new_beliefs) >= 3:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                # Schema-Validierung: Nur Strings akzeptieren, max 30
                validated = [b for b in new_beliefs if isinstance(b, str) and len(b) > 5][:30]
                if len(validated) >= 3:
                    # Bekannte Kategorie-Keys erhalten, nur formed_from_experience updaten
                    _KNOWN_KEYS = {"about_self", "about_world", "about_oliver", "formed_from_experience"}
                    for key in _KNOWN_KEYS:
                        if key not in beliefs:
                            beliefs[key] = []
                    # Deduplikation: Nur Beliefs aufnehmen die nicht schon existieren
                    existing = beliefs.get("formed_from_experience", [])
                    deduplicated = []
                    for b in validated:
                        if not self._is_belief_duplicate(b, deduplicated + existing):
                            deduplicated.append(b)
                    beliefs["formed_from_experience"] = deduplicated
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(f"Beliefs: {len(validated)} konsolidiert")
                else:
                    applied.append(f"Beliefs: Validierung fehlgeschlagen ({len(validated)} von {len(new_beliefs)} gueltig)")
            except (OSError, json.JSONDecodeError) as e:
                applied.append(f"Beliefs-Update fehlgeschlagen: {e}")

        # Obsolete Beliefs entfernen (Dual-Loop — war bisher toter Code)
        obsolete = result.get("obsolete_beliefs", [])
        if obsolete:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                formed = beliefs.get("formed_from_experience", [])
                before_count = len(formed)
                # Entferne Beliefs die als obsolet markiert wurden
                obsolete_lower = {o.lower().strip() for o in obsolete if isinstance(o, str)}
                formed = [
                    b for b in formed
                    if (b if isinstance(b, str) else b.get("text", "")).lower().strip()
                    not in obsolete_lower
                ]
                removed = before_count - len(formed)
                if removed > 0:
                    beliefs["formed_from_experience"] = formed
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(f"Obsolete Beliefs: {removed} entfernt")
            except (OSError, json.JSONDecodeError):
                pass

        # Strategien updaten
        strategy_updates = result.get("strategy_updates", [])
        if strategy_updates:
            strategies_path = self.consciousness_path / "strategies.json"
            strategies = self._safe_load_json(strategies_path)
            if isinstance(strategies, list):

                # Regeln die geloescht werden sollen entfernen
                delete_rules = [
                    u.get("rule", "") for u in strategy_updates
                    if u.get("action") == "delete"
                ]
                if delete_rules:
                    strategies = [
                        s for s in strategies
                        if s.get("pattern", "") not in delete_rules
                    ]
                    with open(strategies_path, "w", encoding="utf-8") as f:
                        json.dump(strategies, f, indent=2, ensure_ascii=False)
                    applied.append(f"Strategien: {len(delete_rules)} entfernt")

        # Memory-Summary als Sequenz-Memory speichern
        summary = result.get("memory_summary", "")
        if summary:
            seq_mem_path = self.consciousness_path / "sequence_memory.json"
            try:
                if seq_mem_path.exists():
                    with open(seq_mem_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {"entries": []}
                data["entries"].append({
                    "seq": "dream",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": f"[DREAM] {summary}",
                })
                data["entries"] = data["entries"][-50:]
                with open(seq_mem_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                applied.append("Summary gespeichert")
            except (OSError, json.JSONDecodeError) as e:
                applied.append(f"Summary-Speicherung fehlgeschlagen: {e}")

        # Prozess-Insights speichern (in metacognition.json als Dream-Eintrag)
        process_insights = result.get("process_insights", "")
        if process_insights:
            metacog_path = self.consciousness_path / "metacognition.json"
            try:
                metacog = self._safe_load_json(metacog_path) or []
                metacog.append({
                    "sequence": "dream",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "bottleneck": "",
                    "strategy_change": process_insights[:500],
                    "source": "dream_consolidation",
                })
                with open(metacog_path, "w", encoding="utf-8") as f:
                    json.dump(metacog[-30:], f, indent=2, ensure_ascii=False)
                applied.append("Prozess-Insights gespeichert")
            except (OSError, json.JSONDecodeError):
                pass

        # Effizienz-Muster als neue Beliefs speichern
        eff_patterns = result.get("efficiency_patterns", [])
        if eff_patterns:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                formed = beliefs.get("formed_from_experience", [])
                for pattern in eff_patterns[:3]:
                    if pattern and not self._is_belief_duplicate(pattern, formed):
                        formed.append(pattern)
                beliefs["formed_from_experience"] = formed[-30:]
                with open(beliefs_path, "w", encoding="utf-8") as f:
                    json.dump(beliefs, f, indent=2, ensure_ascii=False)
                applied.append(f"{len(eff_patterns)} Effizienz-Muster gespeichert")
            except (OSError, json.JSONDecodeError):
                pass

        return ", ".join(applied) if applied else "Keine Aenderungen"

    def _apply_recommendations(self, result: dict, goal_stack=None) -> str:
        """Wandelt Dream-Empfehlungen in Goals um (max 2 pro Dream)."""
        recommendations = result.get("recommendations", [])
        if not recommendations or goal_stack is None:
            return ""

        try:
            summary = goal_stack.get_summary()
            # Nicht mehr als 5 aktive Goals
            active_count = summary.count("[ ]") + summary.count("[→]") if summary else 0
            if active_count >= 5:
                return ""

            created = 0
            for rec in recommendations[:2]:
                # Neues Format: dict mit title + sub_goals
                if isinstance(rec, dict):
                    title = rec.get("title", "")[:100]
                    sub_goals = rec.get("sub_goals", [])
                    if not title or len(title) < 10:
                        continue
                elif isinstance(rec, str) and len(rec) >= 10:
                    # Legacy-Fallback: String-Empfehlungen
                    title = rec[:100]
                    sub_goals = None
                else:
                    continue
                # Duplikat-Check: Nicht erstellen wenn aehnlich existiert
                if title[:30].lower() in summary.lower():
                    continue
                goal_stack.create_goal(
                    title=title,
                    description=f"[Dream-Empfehlung] {title}",
                    priority="medium",
                    sub_goals=sub_goals,
                )
                created += 1
                if active_count + created >= 5:
                    break

            if created:
                return f"{created} Dream-Empfehlungen als Goals erstellt"
        except Exception as e:
            logger.warning("Dream-Empfehlungen zu Goals fehlgeschlagen: %s", e)
        return ""

    def _log_dream(self, result: dict, applied: str):
        """Loggt den Dream-Vorgang."""
        try:
            log = []
            if self.dream_log_path.exists():
                with open(self.dream_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)

            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "applied": applied,
                "recommendations": result.get("recommendations", []),
                "skill_notes": result.get("skill_notes", ""),
                "process_insights": result.get("process_insights", ""),
                "efficiency_patterns": result.get("efficiency_patterns", []),
            })
            log = log[-20:]

            with open(self.dream_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Dream-Log konnte nicht geschrieben werden: %s", e)
