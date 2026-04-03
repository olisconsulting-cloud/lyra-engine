"""
Reporting — Narrative Berichte fuer Telegram und Logging.

Extrahiert aus consciousness.py (God-Class Refactoring Phase 2).
"""


def build_narrative_report(
    tool_input: dict, summary: str, bottleneck: str, next_time: str,
    seq_num: int, errors: int,
    active_goals: list, current_focus: str,
    last_reported_progress: tuple | None,
) -> tuple[str, tuple | None]:
    """Baut einen narrativen Telegram-Bericht mit Selbstreflexion.

    Args:
        tool_input: finish_sequence Input mit rating, rating_reason etc.
        summary: Sequenz-Zusammenfassung
        bottleneck: Was hat gebremst
        next_time: Was naechstes Mal besser machen
        seq_num: Aktuelle Sequenz-Nummer
        errors: Fehler in dieser Sequenz
        active_goals: Liste aktiver Ziele
        current_focus: Aktueller Fokus-String
        last_reported_progress: (done, total) der letzten Sequenz oder None

    Returns:
        (report_text, new_progress_state) — Progress-State fuer naechsten Aufruf
    """
    rating = tool_input.get("performance_rating", 0)
    rating_reason = tool_input.get("rating_reason", "")

    # Fortschritt ermitteln
    progress_text = ""
    done, total = 0, 0
    if active_goals:
        sgs = active_goals[0].get("sub_goals", [])
        done = sum(1 for sg in sgs if sg["status"] == "done")
        total = len(sgs)
        if total:
            progress_text = f" ({done}/{total} Teilziele erledigt)"

    # Naechster Schritt
    next_step = ""
    if "Naechster Schritt:" in current_focus:
        next_step = current_focus.split("Naechster Schritt:")[1].strip().split("[")[0].strip()[:100]

    # --- Narrativen Text bauen ---
    parts = []

    # Eroeffnung: Was wurde gemacht?
    if summary:
        parts.append(f"Sequenz {seq_num}: {summary[:300]}")
    else:
        parts.append(f"Sequenz {seq_num} abgeschlossen.")

    # Selbstbewertung — ehrlich und konkret
    if rating and rating <= 3:
        parts.append(f"\nDas lief nicht gut (Selbstbewertung: {rating}/10).")
        if rating_reason:
            parts.append(f"Grund: {rating_reason[:150]}")
    elif rating and rating >= 8:
        parts.append(f"\nDas war produktiv (Selbstbewertung: {rating}/10).")
        if rating_reason:
            parts.append(rating_reason[:150])

    # Fehler-Erkennung
    if errors > 0:
        parts.append(f"\n{errors} Fehler aufgetreten — das muss ich mir anschauen.")

    # Probleme und Learnings — nur wenn vorhanden
    if bottleneck and bottleneck != "Kein explizites finish_sequence aufgerufen":
        parts.append(f"\nWas mich gebremst hat: {bottleneck[:150]}")
    if next_time and next_time != "finish_sequence mit Rating nutzen":
        parts.append(f"Naechstes Mal: {next_time[:150]}")

    # Fortschritt und Ausblick
    if progress_text:
        parts.append(f"\nFortschritt{progress_text}.")
    if next_step:
        parts.append(f"Als naechstes: {next_step}")

    # Loop-Erkennung: Gleicher Fortschritt wie vorher?
    current_progress = (done, total) if total > 0 else None
    if (last_reported_progress and current_progress is not None
            and last_reported_progress == current_progress):
        parts.append("\nHinweis: Kein Fortschritt seit letzter Sequenz — ich pruefe ob ich feststecke.")

    return "\n".join(parts), current_progress
