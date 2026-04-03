"""
Quality-Checks — Statische Content-Pruefungen ohne API-Calls.

Extrahiert aus consciousness.py (God-Class Refactoring Phase 2).
"""

import re


def check_markdown_quality(content: str) -> list[str]:
    """
    Prueft Markdown-Output auf typische LLM-Halluzinations-Muster.
    Rein regex-basiert, kein extra API-Call.

    Returns:
        Liste von gefundenen Problemen (leer = OK)
    """
    issues = []

    # Code-Bloecke entfernen (zwischen ``` — dort gelten andere Regeln)
    prose = re.sub(r'```.*?```', '', content, flags=re.DOTALL)

    # 1. Offene Klammern ohne Schliessen (nur in Prosa, nicht in Code)
    open_braces = prose.count("{") - prose.count("}")
    if open_braces > 2:
        issues.append(f"{open_braces} ungeschlossene Klammern")

    # 2. Abgebrochene Saetze: Zeilen die mit Komma oder offener Klammer enden
    lines = prose.split("\n")
    broken_lines = 0
    in_list = False
    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue
        # Listen-Eintraege mit Komma am Ende sind normal
        if stripped.startswith("-") or stripped.startswith("*"):
            in_list = True
            continue
        in_list = False
        # Offene Klammer am Zeilenende = verdaechtig
        if len(stripped) > 20 and stripped[-1] in ("(", "{"):
            broken_lines += 1
    if broken_lines >= 3:
        issues.append(f"{broken_lines} abgebrochene Saetze/Zeilen")

    # 3. Wiederholte Woerter (Stottern): gleiches Wort 3+ Mal hintereinander
    stutter = re.findall(r'\b(\w+)\s+\1\s+\1\b', content, re.IGNORECASE)
    if stutter:
        issues.append(f"Wort-Wiederholungen: {stutter[:3]}")

    # 4. Extrem kurze Zeilen nach Ueberschrift (abgebrochener Content)
    for i, line in enumerate(lines):
        if line.startswith("#") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if 0 < len(next_line) < 5 and not next_line.startswith("-"):
                issues.append(f"Abgebrochener Inhalt nach '{line.strip()[:40]}'")
                break

    return issues
