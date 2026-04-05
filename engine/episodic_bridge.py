"""EpisodicBridge — Strukturierte Findings zwischen Sequenzen bewahren.

Extrahiert am Ende jeder Sequenz die wichtigsten Erkenntnisse
(Fehler-Ursachen, funktionierende Ansaetze, Datei-Wissen) und
speichert sie als Episode. Am Anfang der naechsten Sequenz werden
diese Findings in den Goal-Context injiziert.

Das ist Phis episodisches Gedaechtnis — die Bruecke zwischen
"was habe ich gelernt" und "was weiss ich beim naechsten Mal".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import safe_json_write

logger = logging.getLogger(__name__)


class EpisodicBridge:
    """Extrahiert und speichert strukturierte Findings pro Sequenz."""

    def __init__(self, data_path: Path) -> None:
        self.episodes_dir = data_path / "consciousness" / "episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)

    def save_episode(
        self,
        sequence_num: int,
        focus: str,
        summary: str,
        errors: int,
        files_written: list[str],
        files_read: list[str],
        tool_sequence: list[dict],
        bottleneck: str = "",
    ) -> dict:
        """Extrahiert Findings aus einer abgeschlossenen Sequenz.

        Rein heuristisch — kein LLM-Call noetig, kein API-Cost, kein Risiko.

        Args:
            sequence_num: Aktuelle Sequenz-Nummer.
            focus: Goal-Focus der Sequenz.
            summary: LLM-generierte Zusammenfassung.
            errors: Anzahl Fehler in der Sequenz.
            files_written: Liste geschriebener Dateipfade.
            files_read: Liste gelesener Dateipfade.
            tool_sequence: Liste der Tool-Aufrufe [{name, input}, ...].
            bottleneck: Erkannter Engpass (aus finish_sequence).

        Returns:
            Episode-Dict mit findings, file_insights, next_action.
        """
        episode = self._extract_findings(
            sequence_num, focus, summary, errors,
            files_written, files_read, tool_sequence, bottleneck,
        )
        episode["sequence"] = sequence_num
        episode["focus"] = focus[:200]
        episode["timestamp"] = datetime.now(timezone.utc).isoformat()

        self._save(sequence_num, episode)
        return episode

    def load_recent(self, focus: str = "", max_episodes: int = 3) -> list[dict]:
        """Laedt die letzten N Episoden, optional gefiltert nach Focus.

        Args:
            focus: Wenn gesetzt, nur Episoden mit aehnlichem Focus laden.
            max_episodes: Maximale Anzahl zurueckgegebener Episoden.

        Returns:
            Liste von Episode-Dicts (neueste zuerst).
        """
        episodes = sorted(self.episodes_dir.glob("ep_*.json"), reverse=True)
        result: list[dict] = []
        for path in episodes[:max_episodes * 3]:  # Mehr lesen falls Filter greift
            try:
                with open(path, "r", encoding="utf-8") as f:
                    ep = json.load(f)
                if focus and ep.get("focus", ""):
                    # Einfacher Wort-Overlap als Relevanz-Check
                    ep_words = set(ep["focus"].lower().split())
                    focus_words = set(focus.lower().split())
                    if len(ep_words & focus_words) < 2:
                        continue
                result.append(ep)
                if len(result) >= max_episodes:
                    break
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def _extract_findings(
        self,
        sequence_num: int,
        focus: str,
        summary: str,
        errors: int,
        files_written: list[str],
        files_read: list[str],
        tool_sequence: list[dict],
        bottleneck: str,
    ) -> dict:
        """Regelbasierte Extraktion — immer verfuegbar, kein LLM noetig."""
        findings: list[dict] = []

        # 1. Fehler-Hinweis wenn Sequenz fehlerhaft war
        if errors > 0:
            # Haeufigste Tools zaehlen (oft ist das Problem-Tool das am meisten genutzte)
            tool_counts: dict[str, int] = {}
            for t in tool_sequence:
                name = t.get("name", "?")
                tool_counts[name] = tool_counts.get(name, 0) + 1
            top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:3]
            tools_str = ", ".join(f"{n}({c}x)" for n, c in top_tools)
            findings.append({
                "type": "error",
                "content": f"{errors} Fehler mit Tools: {tools_str}",
            })

        # 2. Bottleneck als Finding
        if bottleneck:
            findings.append({
                "type": "blocker",
                "content": bottleneck[:150],
            })

        # 3. Erfolgreiche Aktionen (geschriebene Dateien = produktive Schritte)
        if files_written and errors <= 1:
            findings.append({
                "type": "success",
                "content": f"Erfolgreich: {', '.join(Path(f).name for f in files_written[-3:])}",
            })

        # Max 3 Findings behalten (kompakt)
        findings = findings[:3]

        # 4. File-Insights: Was wurde geschrieben und gelesen
        file_insights: dict[str, str] = {}

        for f in files_written[-5:]:
            short_path = self._short_path(f)
            file_insights[short_path] = f"Geschrieben in Seq {sequence_num}"

        # Gelesene Dateien die NICHT geschrieben wurden = Kontext-Dateien
        written_set = {self._short_path(f) for f in files_written}
        for f in list(files_read)[-5:]:
            short_path = self._short_path(f)
            if short_path not in written_set and short_path not in file_insights:
                file_insights[short_path] = "Gelesen (Kontext)"

        # Max 5 File-Insights
        if len(file_insights) > 5:
            file_insights = dict(list(file_insights.items())[:5])

        # 5. Next-Action: Kurzfassung der Summary (Kontext fuer naechste Sequenz)
        next_action = summary[:120] if summary else ""

        return {
            "findings": findings,
            "file_insights": file_insights,
            "next_action": next_action,
        }

    @staticmethod
    def _short_path(filepath: str) -> str:
        """Kuerzt einen Pfad auf die letzten 2-3 Segmente (lesbar + eindeutig)."""
        parts = Path(filepath).parts
        if len(parts) <= 2:
            return Path(filepath).name
        # projects/circuit-breaker/tests.py statt nur tests.py
        return "/".join(parts[-3:]) if len(parts) >= 3 else "/".join(parts[-2:])

    def _save(self, sequence_num: int, episode: dict) -> None:
        """Speichert Episode und haelt max 20 Dateien (FIFO)."""
        path = self.episodes_dir / f"ep_{sequence_num:05d}.json"
        try:
            safe_json_write(path, episode)
        except Exception as e:
            logger.warning("Episode speichern fehlgeschlagen: %s", e)
            return

        # FIFO: Aelteste loeschen wenn > 20
        episodes = sorted(self.episodes_dir.glob("ep_*.json"))
        while len(episodes) > 20:
            try:
                episodes[0].unlink()
                episodes.pop(0)
            except OSError:
                break
