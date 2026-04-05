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

from .actuator import DEFAULTS as ACTUATOR_DEFAULTS
from .llm_ops import _extract_response_text

logger = logging.getLogger(__name__)


def _belief_importance(b: str) -> float:
    """Bewertet Belief-Wichtigkeit: hoeher = wertvoller."""
    score = 0.0
    # Laenge korreliert mit Spezifitaet
    score += min(len(b) / 200, 0.3)
    # Konkrete Handlungsanweisungen
    if any(kw in b.lower() for kw in ("sollte", "muss", "immer", "nie", "vermeiden", "stattdessen")):
        score += 0.3
    # Meta-Erkenntnisse besonders wertvoll
    if any(kw in b.lower() for kw in ("false positive", "ursache", "root cause", "hinterfragen")):
        score += 0.4
    return score


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
            if isinstance(existing, dict):
                ex_text = existing.get("text", "")
            elif isinstance(existing, str):
                ex_text = existing
            else:
                continue
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
2. BELIEFS: Konsolidiere Ueberzeugungen mit der Abstraktionsleiter:
   a) CLUSTERE aehnliche Beliefs zu Gruppen (z.B. alle exec()-Beliefs zusammen)
   b) EXTRAHIERE aus jedem Cluster EIN abstraktes Prinzip (nicht die Details, sondern die Regel dahinter)
   c) DESTILLIERE aus allen Prinzipien max 3 WISDOM-Saetze (domain-uebergreifende Weisheit)
   Beliefs haben Konfidenz (0.0-1.0). Haeufig bestaetigte Beliefs → hohe Konfidenz.
   Widersprueche erkennen und aufloesen (z.B. "nutze exec()" vs "vermeide exec()").
3. STRATEGIEN: Welche Regeln sind noch relevant? Welche koennen geloescht werden?
4. SKILLS: Stimmen die Levels? Gibt es Meta-Skills die fehlen?
5. ZUSAMMENFASSUNG: Was hat Lyra in letzter Zeit gelernt? Ein Absatz.
6. PROZESS-ANALYSE: Analysiere die Metacognition-Eintraege. Welche Engpaesse wiederholen sich? Welche Sequenzen hatten hohe Effizienz (viel Output pro Step) und was war anders? Welche Arbeitsgewohnheiten sind gut, welche schlecht?
7. META-SKILLS: Wie arbeitet Lyra? Beschreibe den Arbeitsstil — plant sie gut? Fuehrt sie effizient aus? Springt sie zwischen Aufgaben? Nutzt sie finish_sequence rechtzeitig?
8. RECOMMENDATIONS: Max 2 Empfehlungen, JEDE mit 2-3 konkreten Sub-Goals. Jedes Sub-Goal muss ein messbarer, ausfuehrbarer Schritt sein — keine Absichtserklaerungen.
9. TOOL-OEKOSYSTEM: Analysiere die selbstgebauten Tools. Welche sind wertvoll und sollten behalten werden? Welche verfallen (nie genutzt, niedrige Success-Rate)? Gibt es Luecken — Tools die fehlen? Gibt es aehnliche Tools die konsolidiert werden sollten?
10. ACTUATOR-ANALYSE: Analysiere die Behavior-Actuator-Daten. Welche Parameteraenderungen haben geholfen (Effizienz gestiegen)? Welche wurden revertiert und warum? Gibt es Parameter die zu aggressiv oder zu konservativ eingestellt sind? Formuliere max 3 konkrete Empfehlungen fuer Parameteranpassungen.
11. GOAL-ANALYSE: Fuer jedes aktive SubGoal mit _attempt_stats (mehr als 3 Sequenzen):
   Format: _attempt_stats: {total_sequences: int, total_wasted_steps: int, total_errors: int, total_files: int, last_efficiency: float}
   - Ist die Schwierigkeit angemessen fuer Lyras aktuelle Skills?
   - Zeigen die Metriken Fortschritt (steigende Files, sinkende Errors) oder Stagnation?
   - Empfehlung: "continue" (Fortschritt sichtbar), "simplify" (zu komplex, aber lernbar mit einfacherem Ansatz), "abort" (ueber Skill-Level, Waste > 70%), "decompose" (zu gross, in kleinere Sub-Goals zerlegen).

Antworte als JSON:
{
  "consolidated_beliefs": ["Abstrahiertes Prinzip — nicht die Details, sondern die Regel dahinter"],
  "wisdom_extractions": ["Domain-uebergreifende Weisheit — max 3 Saetze, abstrahiert aus allen Beliefs"],
  "contradictions_resolved": [{"beliefs": ["Belief A", "Belief B"], "resolution": "Wie der Widerspruch aufgeloest wird"}],
  "obsolete_beliefs": ["Beliefs die ueberholt sind — max 3, werden als Lektionen archiviert"],
  "strategy_updates": [{"rule": "...", "action": "keep|delete|update", "reason": "..."}],
  "skill_notes": "Freitext-Analyse der Skills",
  "memory_summary": "Was Lyra in letzter Zeit gelernt hat — 2-3 Saetze",
  "recommendations": [{"title": "Kurzer Titel (max 80 Zeichen)", "sub_goals": ["Konkreter Schritt 1", "Konkreter Schritt 2", "Messbares Erfolgskriterium"]}],
  "process_insights": "Was Lyra ueber ihren ARBEITSSTIL gelernt hat — nicht Aufgaben, sondern WIE sie arbeitet",
  "efficiency_patterns": ["Konkrete Beobachtungen ueber Produktivitaet und Effizienz"],
  "tool_insights": "Analyse des Tool-Oekosystems: Was ist wertvoll, was verfaellt, was fehlt?",
  "actuator_recommendations": [{"parameter": "step_budget_modifier|research_depth_limit|output_checkpoint_step", "direction": "increase|decrease", "reason": "Begruendung"}],
  "goal_recommendations": [{"subgoal": "Titel des SubGoals", "action": "continue|simplify|abort|decompose", "reason": "Begruendung", "suggestion": "Nur bei simplify/decompose: konkreter Vorschlag"}]
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

        # Telos Skill-Gaps (kompakte Ring-Summary fuer Token-Effizienz)
        telos = self._safe_load_json(self.consciousness_path / "telos.json")
        if telos:
            ring_summary = []
            for ring in telos.get("ringe", []):
                if ring.get("completion", 1.0) >= 0.9:
                    continue  # Ring fertig, keine Gaps
                # Level-basiert: novice/beginner = Gap (completion fehlt pro Domain)
                gaps = [d["name"] for d in ring.get("domaenen", [])
                        if d.get("level", "novice") in ("novice", "beginner")]
                if gaps:
                    ring_summary.append(
                        f"Ring {ring['nummer']} ({ring['name']}): {', '.join(gaps)}"
                    )
            if ring_summary:
                parts.append(
                    "\n=== TELOS SKILL-GAPS ===\n"
                    + "\n".join(ring_summary)
                    + "\n\nWICHTIG: Dream-Empfehlungen muessen Skill-Gaps adressieren, "
                    "nicht bereits gemeisterte Domains wiederholen."
                )

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

        # Tool-Oekosystem (via Dream-Bridge)
        if self.tool_dream_bridge:
            try:
                tool_mem = self.tool_dream_bridge.gather_tool_memory()
                if tool_mem:
                    parts.append(f"\n=== TOOL-OEKOSYSTEM ===\n{tool_mem}")
            except Exception as e:
                logger.warning(f"Tool-Dream-Bridge fehlgeschlagen: {e}")

        # Behavior Actuator (Parameter-Anpassungen + Meta-Learning-Historie)
        actuator_state = self._safe_load_json(
            self.consciousness_path / "actuator_state.json"
        )
        if actuator_state:
            parts.append(self._format_actuator_for_dream(actuator_state))

        return "\n".join(parts)

    def _format_actuator_for_dream(self, state: dict) -> str:
        """Formatiert Actuator-State als lesbaren Abschnitt fuer Dream-Prompt."""
        lines = ["\n=== BEHAVIOR ACTUATOR ==="]

        # Aktuelle Parameter vs. Defaults
        params = state.get("parameters", {})
        lines.append("Aktuelle Parameter:")
        for key, val in params.items():
            default = ACTUATOR_DEFAULTS.get(key, "?")
            marker = " (ANGEPASST)" if val != default else ""
            lines.append(f"  {key}: {val}{marker} (Default: {default})")

        # Pattern-Hits (welche Probleme erkannt)
        hits = state.get("pattern_hits", {})
        if hits:
            lines.append(f"Pattern-Hits: {hits}")

        # Aenderungshistorie (letzte 10)
        changes = state.get("change_history", [])[-10:]
        if changes:
            lines.append("Letzte Parameteraenderungen:")
            for c in changes:
                status = ("REVERTIERT" if c.get("reverted")
                          else "BEHALTEN" if c.get("evaluated")
                          else "PENDING")
                eff_before = c.get("efficiency_before", 0)
                eff_after = c.get("efficiency_after", 0)
                lines.append(
                    f"  {c.get('parameter')}: {c.get('old_value')} -> {c.get('new_value')} "
                    f"(Trigger: {c.get('trigger')}, Seq {c.get('sequence')}, "
                    f"Eff {eff_before:.0%} -> {eff_after:.0%}, Status: {status})"
                )

        # Uebersprungene Anpassungen (Non-Process-Fehler)
        skipped = state.get("skipped_adjustments", [])[-5:]
        if skipped:
            lines.append("Uebersprungene Anpassungen (Fehler war nicht prozessual):")
            for s in skipped:
                lines.append(
                    f"  Pattern '{s.get('pattern')}' bei Seq {s.get('sequence')} "
                    f"— Grund: {s.get('reason')}"
                )

        # Effizienz-Trend
        eff_hist = state.get("efficiency_history", [])[-10:]
        if eff_hist:
            avg = sum(e["efficiency"] for e in eff_hist) / len(eff_hist)
            zero_out = sum(1 for e in eff_hist if e.get("files", 0) == 0)
            lines.append(f"Effizienz letzte {len(eff_hist)} Seq: {avg:.0%} Durchschnitt")
            if zero_out:
                lines.append(f"  Davon {zero_out} Sequenzen mit 0 Output")

        return "\n".join(lines)

    def _apply_results(self, result: dict) -> str:
        """Wendet die Dream-Ergebnisse an."""
        applied = []

        # Beliefs konsolidieren — MERGE statt Replace, Strings fuer Kompatibilitaet
        # Konfidenz wird in belief_meta.json getrackt (bestehendes System),
        # nicht in den Beliefs selbst — verhindert Crashes in finish_sequence/validate.
        new_beliefs = result.get("consolidated_beliefs", [])
        if new_beliefs and len(new_beliefs) >= 3:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                _KNOWN_KEYS = {"about_self", "about_world", "about_oliver",
                               "formed_from_experience", "wisdom"}
                for key in _KNOWN_KEYS:
                    if key not in beliefs:
                        beliefs[key] = []

                # Beliefs normalisieren: LLM kann Strings oder Dicts liefern → immer Strings
                validated = []
                for b in new_beliefs[:30]:
                    text = b.get("text", "") if isinstance(b, dict) else b if isinstance(b, str) else ""
                    if isinstance(text, str) and len(text) > 5:
                        validated.append(text[:300])

                if len(validated) >= 3:
                    existing = beliefs.get("formed_from_experience", [])
                    # Bestehende Dicts → Strings migrieren (Rueckwaerts-Fix)
                    existing_clean = []
                    for e in existing:
                        if isinstance(e, dict):
                            existing_clean.append(e.get("text", str(e)))
                        elif isinstance(e, str):
                            existing_clean.append(e)
                    # Merge: Neue zu bestehenden HINZUFUEGEN
                    merged = list(existing_clean)
                    added = 0
                    for b in validated:
                        if not self._is_belief_duplicate(b, merged):
                            merged.append(b)
                            added += 1
                    # Max 30 Beliefs — unwichtigste zuerst in Wisdom destillieren
                    if len(merged) > 30:
                        merged.sort(key=_belief_importance)
                        overflow = merged[:len(merged) - 30]
                        merged = merged[len(merged) - 30:]
                        wisdom = beliefs.get("wisdom", [])
                        for old in overflow:
                            if old and not self._is_belief_duplicate(old, wisdom):
                                wisdom.append(old)
                        beliefs["wisdom"] = wisdom[-50:]
                    beliefs["formed_from_experience"] = merged
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(f"Beliefs: {added} neu, {len(merged)} total")
                else:
                    applied.append(f"Beliefs: Validierung fehlgeschlagen")
            except (OSError, json.JSONDecodeError) as e:
                applied.append(f"Beliefs-Update fehlgeschlagen: {e}")

        # Wisdom-Extraktionen: Domain-uebergreifende Prinzipien aus dem LLM
        wisdom_extractions = result.get("wisdom_extractions", [])
        if wisdom_extractions:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                wisdom = beliefs.get("wisdom", [])
                added_w = 0
                for w in wisdom_extractions[:3]:
                    if isinstance(w, str) and len(w) > 10:
                        prefix = "[prinzip] "
                        entry = prefix + w[:300]
                        if not self._is_belief_duplicate(w, wisdom):
                            wisdom.append(entry)
                            added_w += 1
                if added_w > 0:
                    beliefs["wisdom"] = wisdom[-50:]
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(f"Wisdom: {added_w} Prinzipien extrahiert")
            except (OSError, json.JSONDecodeError):
                pass

        # Widerspruchs-Aufloesungen: Konfligierende Beliefs → ein klaerer Belief
        contradictions = result.get("contradictions_resolved", [])
        if contradictions:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                wisdom = beliefs.get("wisdom", [])
                for c in contradictions[:3]:
                    if isinstance(c, dict) and c.get("resolution"):
                        resolution = f"[aufgeloest] {c['resolution'][:300]}"
                        if not self._is_belief_duplicate(c["resolution"], wisdom):
                            wisdom.append(resolution)
                if contradictions:
                    beliefs["wisdom"] = wisdom[-50:]
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(f"Widersprueche: {len(contradictions)} aufgeloest")
            except (OSError, json.JSONDecodeError):
                pass

        # Obsolete Beliefs → Wisdom destillieren (nie loeschen, immer lernen)
        # Max 3 pro Dream-Zyklus — verhindert Belief-Extinction
        # Matching per Jaccard-Similarity statt exaktem String (LLM paraphrasiert)
        obsolete = result.get("obsolete_beliefs", [])
        if obsolete:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                formed = beliefs.get("formed_from_experience", [])
                wisdom = beliefs.get("wisdom", [])
                # Jaccard-basiertes Matching: obsolete Belief aehnlich genug?
                obsolete_texts = [o for o in obsolete if isinstance(o, str) and len(o) > 5]
                removed_beliefs = []
                kept = []
                for b in formed:
                    text = b if isinstance(b, str) else b.get("text", "")
                    if len(removed_beliefs) < 3 and self._is_belief_duplicate(text, obsolete_texts):
                        removed_beliefs.append(b)
                    else:
                        kept.append(b)
                # Entfernte Beliefs → Wisdom-Archiv mit Kontext
                for old in removed_beliefs:
                    text = old if isinstance(old, str) else old.get("text", "")
                    lesson = f"[ueberholt] {text}"
                    if not self._is_belief_duplicate(lesson, wisdom):
                        wisdom.append(lesson)
                if removed_beliefs:
                    beliefs["formed_from_experience"] = kept
                    beliefs["wisdom"] = wisdom[-50:]
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append(
                        f"Beliefs destilliert: {len(removed_beliefs)} → Wisdom "
                        f"(max 3/Zyklus, {len(kept)} aktiv, {len(wisdom)} Wisdom)"
                    )
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
                if len(formed) > 30:
                    formed.sort(key=_belief_importance)
                    formed = formed[len(formed) - 30:]
                beliefs["formed_from_experience"] = formed
                with open(beliefs_path, "w", encoding="utf-8") as f:
                    json.dump(beliefs, f, indent=2, ensure_ascii=False)
                applied.append(f"{len(eff_patterns)} Effizienz-Muster gespeichert")
            except (OSError, json.JSONDecodeError):
                pass

        # Tool-Insights als Belief speichern (wenn vorhanden)
        tool_insights = result.get("tool_insights", "")
        if tool_insights and len(tool_insights) > 20:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                formed = beliefs.get("formed_from_experience", [])
                insight_belief = f"[TOOLS] {tool_insights[:300]}"
                if not self._is_belief_duplicate(insight_belief, formed):
                    formed.append(insight_belief)
                    if len(formed) > 30:
                        formed.sort(key=_belief_importance)
                        formed = formed[len(formed) - 30:]
                    beliefs["formed_from_experience"] = formed
                    with open(beliefs_path, "w", encoding="utf-8") as f:
                        json.dump(beliefs, f, indent=2, ensure_ascii=False)
                    applied.append("Tool-Insights gespeichert")
            except (OSError, json.JSONDecodeError):
                pass

        return ", ".join(applied) if applied else "Keine Aenderungen"

    @staticmethod
    def _is_meta_goal(title: str) -> bool:
        """Erkennt ob ein Goal Meta-Reflexion statt echte Arbeit ist."""
        from .config import is_meta_goal
        return is_meta_goal(title)

    def _apply_recommendations(self, result: dict, goal_stack=None) -> str:
        """Wandelt Dream-Empfehlungen in Goals um (max 2 pro Dream).

        Guard: Meta-Goals (finish_sequence, Reflexion, Uebungen) werden
        geblockt wenn bereits echte Infrastruktur-Goals existieren.
        """
        recommendations = result.get("recommendations", [])
        if not recommendations or goal_stack is None:
            return ""

        try:
            summary = goal_stack.get_summary()
            # Nicht mehr als 3 aktive Goals — Focus > Breite
            active_count = summary.count("[ ]") + summary.count("[→]") if summary else 0
            if active_count >= 3:
                return ""

            # Meta-Goal-Guard: Zaehle bereits aktive Meta-Goals
            active_goals = goal_stack.goals.get("active", [])
            meta_count = sum(
                1 for g in active_goals if self._is_meta_goal(g.get("title", ""))
            )

            created = 0
            max_new = min(2, 3 - active_count)
            for rec in recommendations[:max_new]:
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

                # META-GOAL-GUARD: Max 1 Meta-Goal aktiv
                if self._is_meta_goal(title) and meta_count >= 1:
                    logger.info("Meta-Goal geblockt (max 1): %s", title[:60])
                    continue

                # Duplikat-Check: Jaccard statt nur Prefix
                if self._is_goal_duplicate(title, active_goals):
                    logger.info("Duplikat-Goal geblockt: %s", title[:60])
                    continue

                goal_stack.create_goal(
                    title=title,
                    description=f"[Dream-Empfehlung] {title}",
                    priority="medium",
                    sub_goals=sub_goals,
                )
                created += 1
                if self._is_meta_goal(title):
                    meta_count += 1
                if active_count + created >= 5:
                    break

            if created:
                return f"{created} Dream-Empfehlungen als Goals erstellt"
        except Exception as e:
            logger.warning("Dream-Empfehlungen zu Goals fehlgeschlagen: %s", e)
        return ""

    @staticmethod
    def _is_goal_duplicate(title: str, existing_goals: list,
                           threshold: float = 0.6) -> bool:
        """Prueft ob ein Goal-Titel semantisch zu einem bestehenden passt."""
        new_words = set(title.lower().split())
        if len(new_words) < 3:
            return False
        for goal in existing_goals:
            ex_words = set(goal.get("title", "").lower().split())
            if len(ex_words) < 3:
                continue
            overlap = len(new_words & ex_words)
            union = len(new_words | ex_words)
            if union > 0 and overlap / union >= threshold:
                return True
        return False

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
                "actuator_recommendations": result.get("actuator_recommendations", []),
            })
            log = log[-20:]

            with open(self.dream_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Dream-Log konnte nicht geschrieben werden: %s", e)
