"""
LLM-Ops — Entkoppelte LLM-basierte Operationen.

Cross-Model-Review, Opus-Validierung, Goal-Planning.
Jede Funktion bekommt ein call_llm Callable statt self._call_llm.
Extrahiert aus consciousness.py (God-Class Refactoring Phase 2).
"""

import json
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from . import config

logger = logging.getLogger(__name__)


def _extract_response_text(response: dict) -> str:
    """Extrahiert Text aus einer LLM-Response (Anthropic-Format)."""
    text = ""
    for block in response.get("content", []):
        if hasattr(block, "text"):
            text += block.text
    return text


def _parse_llm_json_object(text: str) -> Optional[dict]:
    """Parst ein JSON-Objekt aus LLM-Antwort (mit Markdown-Fence-Bereinigung).

    Versucht zuerst den gesamten Text, dann sucht nach {}-Bloecken.
    """
    if not text:
        return None

    # Markdown-Fence entfernen
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl > 0:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    # Versuch 1: Gesamter Text als JSON
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Versuch 2: Erstes valides {}-Objekt suchen
    for match in re.finditer(r'\{[^{}]*\}', cleaned):
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


def _parse_llm_json_list(text: str) -> Optional[list]:
    """Parst eine JSON-Liste aus LLM-Antwort."""
    if not text:
        return None

    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return None


def cross_model_review(
    project_name: str, code_files: list[Path], call_llm: Callable
) -> Optional[dict]:
    """
    Cross-Model-Review: Ein anderes Modell prueft den Projekt-Code.

    Hauptarbeit laeuft auf Gemini → Review auf Claude (oder umgekehrt).
    Verschiedene Modelle finden verschiedene Probleme.

    Returns:
        {"approved": bool, "reason": str, "issues": list} oder None bei Fehler
    """
    # Code sammeln
    code_context = f"PROJEKT: {project_name}\n\n"
    for filepath in code_files[:5]:
        try:
            content = filepath.read_text(encoding="utf-8")[:2000]
            code_context += f"--- {filepath.name} ---\n{content}\n\n"
        except (OSError, UnicodeDecodeError):
            continue

    # PLAN.md fuer Kontext
    plan_path = config.DATA_PATH / "projects" / project_name / "PLAN.md"
    if plan_path.exists():
        plan = plan_path.read_text(encoding="utf-8")[:1000]
        code_context += f"--- PLAN.md ---\n{plan}\n"

    prompt = (
        "Du bist ein Code-Reviewer. Pruefe ob dieses Projekt die Anforderungen "
        "aus PLAN.md erfuellt und ob der Code qualitativ hochwertig ist.\n\n"
        "Pruefe auf:\n"
        "1. Erfuellt der Code die beschriebenen Ziele?\n"
        "2. Gibt es Bugs oder logische Fehler?\n"
        "3. Ist die Architektur sauber?\n"
        "4. Fehlt etwas Wichtiges?\n\n"
        "Antworte als JSON:\n"
        '{"approved": true/false, "reason": "Kurze Begruendung", '
        '"issues": ["Problem 1", ...] oder []}\n\n'
        "Sei streng aber fair."
    )

    try:
        response = call_llm(
            "fallback", prompt,
            [{"role": "user", "content": code_context}],
            max_tokens=1000,
        )
        text = _extract_response_text(response)
        return _parse_llm_json_object(text)
    except Exception:
        return None  # Review-Fehler blockt nicht den Abschluss


def opus_result_validation(
    project_name: str, criteria: list[str], verified: list[str],
    call_llm: Callable,
) -> Optional[dict]:
    """
    Nutzt Opus 4.6 zur Validierung ob Projekt-Ergebnisse inhaltlich sinnvoll sind.
    Prueft Akzeptanzkriterien gegen tatsaechlich erstellte Dateien.

    Returns:
        {"approved": bool, "reason": str} oder None bei Fehler
    """
    try:
        project_path = config.DATA_PATH / "projects" / project_name
        files_content = []
        for f in sorted(project_path.iterdir()):
            if f.is_file() and f.name != "tests.py" and f.suffix in (".py", ".md", ".json"):
                content = f.read_text(encoding="utf-8")[:2000]
                files_content.append(f"--- {f.name} ---\n{content}")
            if len(files_content) >= 5:
                break

        if not files_content:
            return None

        response = call_llm(
            "result_validation",
            system=(
                "Du bist ein Qualitaets-Pruefer. Bewerte ob die Projekt-Dateien "
                "die Akzeptanzkriterien WIRKLICH erfuellen. Pruefe auf: "
                "(1) Vollstaendigkeit, (2) inhaltliche Korrektheit, "
                "(3) abgebrochene/unvollstaendige Saetze, (4) Halluzinationen. "
                "Antworte NUR mit JSON: {\"approved\": true/false, \"reason\": \"...\"}"
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Projekt: {project_name}\n"
                    f"Kriterien: {criteria}\n"
                    f"Verifiziert als: {verified}\n\n"
                    f"Dateien:\n{''.join(files_content)}"
                ),
            }],
            max_tokens=500,
        )
        text = _extract_response_text(response)
        if not text:
            return {"approved": False, "reason": "Opus hat keine Antwort geliefert"}

        result = _parse_llm_json_object(text)
        if result and "approved" in result:
            return result
        return {"approved": False, "reason": "Kein gueltiges JSON in Opus-Antwort"}
    except Exception as e:
        print(f"  [Opus Validierung Fehler: {e}]")
    return None


def opus_goal_planning(
    title: str, description: str, call_llm: Callable
) -> Optional[list[str]]:
    """
    Nutzt Opus 4.6 fuer hochwertige Goal-Zerlegung.
    Wird nur aufgerufen wenn Sub-Goals fehlen oder zu wenige sind.

    Returns:
        Liste von Sub-Goal-Titeln oder None bei Fehler
    """
    try:
        response = call_llm(
            "goal_planning",
            system=(
                "Du bist ein Strategie-Berater. Zerlege das gegebene Ziel in "
                "3-6 konkrete, sequentielle Sub-Goals. Jedes Sub-Goal muss: "
                "(1) ein messbares Ergebnis haben, (2) in 1-3 Sequenzen erreichbar sein, "
                "(3) auf dem vorherigen aufbauen. "
                "Antworte NUR mit einer JSON-Liste von Strings. Keine Erklaerung."
            ),
            messages=[{
                "role": "user",
                "content": f"Ziel: {title}\nBeschreibung: {description or 'Keine'}",
            }],
            max_tokens=1000,
        )
        text = _extract_response_text(response)
        result = _parse_llm_json_list(text)
        if result and all(isinstance(s, str) for s in result):
            return result[:6]
    except Exception as e:
        print(f"  [Opus Goal-Planning Fehler: {e}]")
    return None
