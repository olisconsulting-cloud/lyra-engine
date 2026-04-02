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
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

from .llm_router import MODELS, TASK_MODEL_MAP


class DreamEngine:
    """Konsolidiert Lyras Gedaechtnis im Hintergrund."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.consciousness_path = base_path / "consciousness"
        self.dream_log_path = self.consciousness_path / "dream_log.json"
        self.client = Anthropic()
        self.model = MODELS[TASK_MODEL_MAP["dream"]]["model_id"]

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

Antworte als JSON:
{
  "consolidated_beliefs": ["Liste der 10-15 wichtigsten Ueberzeugungen"],
  "obsolete_beliefs": ["Beliefs die geloescht werden sollen"],
  "strategy_updates": [{"rule": "...", "action": "keep|delete|update", "reason": "..."}],
  "skill_notes": "Freitext-Analyse der Skills",
  "memory_summary": "Was Lyra in letzter Zeit gelernt hat — 2-3 Saetze",
  "recommendations": ["Konkrete Vorschlaege fuer Verbesserungen"]
}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": context}],
            )

            result_text = response.content[0].text

            # JSON parsen
            import re
            # Versuche direktes Parsing oder extrahiere aus Code-Block
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                else:
                    return f"Dream fehlgeschlagen: Konnte Antwort nicht parsen"

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

        # Beliefs konsolidieren (Guard: nie leere Liste uebernehmen)
        new_beliefs = result.get("consolidated_beliefs", [])
        if new_beliefs and len(new_beliefs) >= 3:
            beliefs_path = self.consciousness_path / "beliefs.json"
            try:
                beliefs = self._safe_load_json(beliefs_path) or {}
                beliefs["formed_from_experience"] = new_beliefs
                with open(beliefs_path, "w", encoding="utf-8") as f:
                    json.dump(beliefs, f, indent=2, ensure_ascii=False)
                applied.append(f"Beliefs: {len(new_beliefs)} konsolidiert")
            except Exception:
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
                data["entries"] = data["entries"][-10:]
                with open(seq_mem_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                applied.append("Summary gespeichert")
            except Exception:
                pass

        return ", ".join(applied) if applied else "Keine Aenderungen"

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
            })
            log = log[-20:]

            with open(self.dream_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
