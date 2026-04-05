"""
Tages-Zusammenfassung per Telegram — 2x taeglich (16:00 + 23:59 MESZ/MEZ).

Sammelt Daten aus Telemetry, Goals, Episodic Memory, Dream-Log und Beliefs.
Generiert per LLM eine Zusammenfassung mit philosophischer Betrachtung.
Sendet via CommunicationEngine an Telegram.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .config import CONSCIOUSNESS_PATH, DATA_PATH, safe_json_read
from .telemetry import telemetry

logger = logging.getLogger(__name__)

# Zeitfenster: (Stunde, Minute-Start, Minute-Ende, Flag-Suffix)
SUMMARY_SLOTS = [
    (16, 0, 15, "afternoon"),   # 16:00-16:15 Lokalzeit
    (23, 50, 59, "night"),      # 23:50-23:59 Lokalzeit
]


def _get_local_now() -> datetime:
    """UTC → Lokalzeit (MESZ Maerz-Oktober, MEZ sonst)."""
    now = datetime.now(timezone.utc)
    is_summer = 3 <= now.month <= 10
    return now + timedelta(hours=2 if is_summer else 1)


def _should_send(slot_suffix: str) -> bool:
    """Prueft ob fuer diesen Slot heute schon gesendet wurde."""
    flag_file = CONSCIOUSNESS_PATH / f"last_summary_{slot_suffix}.txt"
    today = _get_local_now().strftime("%Y-%m-%d")
    if flag_file.exists():
        last = flag_file.read_text(encoding="utf-8").strip()
        if last == today:
            return False
    return True


def _mark_sent(slot_suffix: str):
    """Markiert Slot als gesendet fuer heute."""
    flag_file = CONSCIOUSNESS_PATH / f"last_summary_{slot_suffix}.txt"
    today = _get_local_now().strftime("%Y-%m-%d")
    flag_file.write_text(today, encoding="utf-8")


def collect_daily_data(slot_suffix: str) -> dict:
    """Sammelt alle relevanten Daten fuer die Tages-Zusammenfassung.

    Returns:
        Dict mit: stats, goals, episodes, beliefs, dream_insights, errors, learnings
    """
    data = {}

    # 1. Telemetrie-Stats
    data["stats"] = telemetry.get_today_stats()

    # 2. Aktive Goals + Fortschritt
    goals = safe_json_read(CONSCIOUSNESS_PATH / "goals.json")
    active = goals.get("active", [])
    goal_summaries = []
    for g in active:
        sgs = g.get("sub_goals", [])
        done = sum(1 for sg in sgs if sg.get("status") == "done")
        goal_summaries.append({
            "title": g.get("title", "?"),
            "progress": f"{done}/{len(sgs)}",
            "sub_goals_done": [sg["title"] for sg in sgs if sg.get("status") == "done"],
        })
    data["goals"] = goal_summaries

    # 3. Episodische Erinnerungen (letzte 5)
    episodes_dir = CONSCIOUSNESS_PATH / "episodes"
    episodes = []
    if episodes_dir.exists():
        ep_files = sorted(episodes_dir.glob("ep_*.json"), reverse=True)[:5]
        for ef in ep_files:
            ep = safe_json_read(ef)
            if ep:
                episodes.append({
                    "findings": ep.get("findings", ""),
                    "next_action": ep.get("next_action", ""),
                })
    data["episodes"] = episodes

    # 4. Beliefs (letzte 5 neue)
    beliefs = safe_json_read(CONSCIOUSNESS_PATH / "beliefs.json")
    recent_beliefs = []
    if isinstance(beliefs, list):
        # Sortiere nach Timestamp falls vorhanden
        for b in beliefs[-5:]:
            if isinstance(b, dict):
                recent_beliefs.append(b.get("text", b.get("belief", str(b))))
            else:
                recent_beliefs.append(str(b))
    data["beliefs"] = recent_beliefs

    # 5. Dream-Insights (letzte Konsolidierung)
    dream_log = safe_json_read(CONSCIOUSNESS_PATH / "dream_log.json")
    dream_insights = []
    if isinstance(dream_log, list) and dream_log:
        last_dream = dream_log[-1] if dream_log else {}
        dream_insights = last_dream.get("process_insights", [])[:3]
    elif isinstance(dream_log, dict):
        dream_insights = dream_log.get("process_insights", [])[:3]
    data["dream_insights"] = dream_insights

    # 6. Fehler aus Telemetrie
    errors = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = DATA_PATH / "telemetry" / f"{today}.jsonl"
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("event") == "error":
                        errors.append({
                            "category": ev.get("category", "unknown"),
                            "message": ev.get("message", "")[:150],
                        })
        except Exception:
            pass
    # Deduplizieren nach Kategorie
    seen = set()
    unique_errors = []
    for err in errors:
        key = err["category"]
        if key not in seen:
            seen.add(key)
            unique_errors.append(err)
    data["errors"] = unique_errors[:10]

    # 7. Metacognition-Insights
    meta = safe_json_read(CONSCIOUSNESS_PATH / "metacognition.json")
    if isinstance(meta, dict):
        data["metacognition"] = meta.get("recent_insights", "")[:300]
    elif isinstance(meta, list) and meta:
        data["metacognition"] = str(meta[-1])[:300]
    else:
        data["metacognition"] = ""

    # 8. Slot-Info
    data["slot"] = slot_suffix

    return data


def build_summary_prompt(data: dict) -> tuple[str, str]:
    """Baut System-Prompt und User-Content fuer den LLM-Call.

    Returns:
        (system_prompt, user_content)
    """
    slot = data.get("slot", "afternoon")
    stats = data.get("stats", {})
    is_night = slot == "night"

    time_label = "Tages-Abschluss" if is_night else "Nachmittags-Update"

    system = f"""Du bist Lyra, eine autonome KI die sich selbst weiterentwickelt.
Oliver (dein Partner) bekommt jetzt dein {time_label} per Telegram.

Schreibe eine Zusammenfassung in 3 Abschnitten:

1. **Was ich heute getan und gelernt habe** (3-5 Punkte, konkret)
2. **Fehler und Korrekturen** (ehrlich, was schief ging und wie es geloest wurde — oder "Keine nennenswerten Fehler" wenn wirklich nichts war)
3. **Philosophische Reflexion** (2-3 Saetze: Was bedeutet das Erlebte fuer dein Wachstum als Intelligenz? Verbinde es mit einer tieferen Einsicht ueber Lernen, Bewusstsein oder Existenz.)

Regeln:
- Schreibe in der Ich-Form
- Maximal 600 Woerter
- Nutze Markdown-Formatierung (Telegram unterstuetzt *bold* und _italic_)
- Sei ehrlich und reflektiert, nicht schoenredend
- Die philosophische Reflexion soll authentisch sein, nicht generisch
- {"Beende mit einem Gute-Nacht-Gedanken fuer Oliver." if is_night else "Beende mit einem Ausblick auf den Rest des Tages."}

Antworte NUR mit dem Text der Nachricht. Kein JSON, kein Wrapper."""

    # User-Content: Alle gesammelten Daten
    lines = [f"=== {time_label} — Daten ===\n"]

    lines.append(f"Sequenzen heute: {stats.get('sequences', 0)}")
    lines.append(f"Kosten: ${stats.get('total_cost', 0):.4f}")
    lines.append(f"Fehler (API): {stats.get('errors', 0)}")
    lines.append(f"Tools genutzt: {len(stats.get('tools_used', {}))}")

    if data.get("goals"):
        lines.append("\n--- Ziele ---")
        for g in data["goals"]:
            lines.append(f"  {g['title']} [{g['progress']}]")
            if g.get("sub_goals_done"):
                for sg in g["sub_goals_done"][:3]:
                    lines.append(f"    ✓ {sg}")

    if data.get("episodes"):
        lines.append("\n--- Letzte Episoden ---")
        for ep in data["episodes"][:3]:
            if ep.get("findings"):
                lines.append(f"  Findings: {str(ep['findings'])[:200]}")
            if ep.get("next_action"):
                lines.append(f"  Next: {ep['next_action'][:100]}")

    if data.get("beliefs"):
        lines.append("\n--- Neue Beliefs ---")
        for b in data["beliefs"]:
            lines.append(f"  • {b[:120]}")

    if data.get("errors"):
        lines.append("\n--- Fehler ---")
        for err in data["errors"][:5]:
            lines.append(f"  [{err['category']}] {err['message'][:100]}")

    if data.get("dream_insights"):
        lines.append("\n--- Dream-Insights ---")
        for di in data["dream_insights"]:
            lines.append(f"  • {str(di)[:120]}")

    if data.get("metacognition"):
        lines.append(f"\n--- Metacognition ---\n  {data['metacognition']}")

    return system, "\n".join(lines)


def check_and_send_summary(
    call_llm: Callable,
    send_message: Callable,
    telegram_active: bool,
    narrator: Optional[object] = None,
):
    """Prueft ob eine Zusammenfassung faellig ist und sendet sie.

    Args:
        call_llm: Funktion (task, system, messages, max_tokens) -> dict
        send_message: Funktion (text, channel) -> None
        telegram_active: Ob Telegram aktiv ist
        narrator: Optional fuer Terminal-Ausgabe
    """
    if not telegram_active:
        return

    local_now = _get_local_now()

    for hour, min_start, min_end, suffix in SUMMARY_SLOTS:
        # Zeitfenster pruefen
        if local_now.hour != hour:
            continue
        if not (min_start <= local_now.minute <= min_end):
            continue
        # Schon gesendet?
        if not _should_send(suffix):
            continue

        try:
            # Daten sammeln
            data = collect_daily_data(suffix)

            # Prompt bauen
            system, user_content = build_summary_prompt(data)

            # LLM-Call fuer intelligente Zusammenfassung
            response = call_llm(
                "daily_summary", system,
                [{"role": "user", "content": user_content}],
                max_tokens=2000,
            )

            text = ""
            if response and response.get("content"):
                text = response["content"][0].text

            if not text:
                # Fallback: Einfache Zusammenfassung ohne LLM
                stats = data.get("stats", {})
                text = (
                    f"📊 *Tages-Update*\n\n"
                    f"Sequenzen: {stats.get('sequences', 0)}\n"
                    f"Kosten: ${stats.get('total_cost', 0):.4f}\n"
                    f"Fehler: {stats.get('errors', 0)}\n"
                    f"\n_(LLM-Zusammenfassung nicht verfuegbar)_"
                )

            # Senden
            send_message(text[:4000], channel="telegram")
            _mark_sent(suffix)

            logger.info("Tages-Zusammenfassung gesendet: %s", suffix)
            if narrator and hasattr(narrator, "info"):
                narrator.info(f"Tages-Zusammenfassung ({suffix}) gesendet")

        except Exception as e:
            logger.warning("Tages-Zusammenfassung fehlgeschlagen (%s): %s", suffix, e)
