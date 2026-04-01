"""
Live-Dashboard — Lyras Bewusstsein beobachten.

Zeigt in Echtzeit:
- Emotionaler Zustand (Balken-Visualisierung)
- Persoenlichkeitsentwicklung
- Letzte Gedanken und Entscheidungen
- Ueberzeugungen
- Energie und Zyklen
- Journal-Eintraege

Nutzung:
    python dashboard.py           # Standard (5s Refresh)
    python dashboard.py --fast    # Schneller Refresh (2s)
    python dashboard.py --journal # Nur Journal anzeigen
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows-Encoding fixen
if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_PATH = Path(__file__).parent
REFRESH_RATE = 5  # Sekunden


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def load_json(path: Path) -> dict:
    """Laedt JSON-Datei sicher."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, PermissionError):
        pass
    return {}


def format_bar(value: float, width: int = 25) -> str:
    """Erstellt einen visuellen Balken."""
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def format_emotion(name: str, value: float) -> str:
    """Formatiert eine Emotion mit Emoji und Balken."""
    emojis = {
        "neugier": "🔍",
        "ruhe": "🧘",
        "intensitaet": "⚡",
        "unsicherheit": "❓",
        "verbundenheit": "🤝",
        "freude": "😊",
        "frustration": "😤",
        "staunen": "✨",
    }
    emoji = emojis.get(name, "•")
    bar = format_bar(value)
    return f"  {emoji} {name:18s} {bar} {value:.0%}"


def get_last_experience(base_path: Path) -> dict:
    """Holt die letzte Erfahrung."""
    exp_path = base_path / "memory" / "experiences"
    if not exp_path.exists():
        return {}
    files = sorted(exp_path.glob("*.json"))
    if not files:
        return {}
    return load_json(files[-1])


def get_last_journal_entry(base_path: Path) -> str:
    """Holt den letzten Journal-Eintrag."""
    journal_path = base_path / "journal"
    if not journal_path.exists():
        return "(kein Journal)"
    files = sorted(journal_path.glob("*.md"))
    if not files:
        return "(kein Journal)"

    content = files[-1].read_text(encoding="utf-8")
    sections = content.split("\n## ")
    if len(sections) > 1:
        return "## " + sections[-1]
    return content


def get_outbox_count(base_path: Path) -> int:
    """Zaehlt ungelesene Outbox-Nachrichten."""
    outbox = base_path / "messages" / "outbox"
    if not outbox.exists():
        return 0
    count = 0
    for f in outbox.glob("*.json"):
        msg = load_json(f)
        if not msg.get("read", True):
            count += 1
    return count


def render_dashboard(base_path: Path):
    """Rendert das komplette Dashboard."""
    genesis = load_json(base_path / "genesis.json")
    state = load_json(base_path / "consciousness" / "state.json")
    personality = load_json(base_path / "consciousness" / "personality.json")
    beliefs = load_json(base_path / "consciousness" / "beliefs.json")
    goals = load_json(base_path / "consciousness" / "goals.json")

    if not state:
        print("\n  Lyra ist noch nicht geboren. Starte: python run.py\n")
        return

    name = genesis.get("name", "?")
    cycles = state.get("cycles_total", 0)
    energy = state.get("energy", 1.0)
    born = genesis.get("born", "?")
    last_cycle = state.get("last_cycle", "")
    cycles_since = state.get("cycles_since_interaction", 0)
    emotions = state.get("emotional_state", {})

    # Zeitberechnung
    now = datetime.now(timezone.utc)
    if last_cycle:
        last = datetime.fromisoformat(last_cycle)
        since_last = (now - last).total_seconds()
        if since_last < 60:
            last_str = f"vor {since_last:.0f}s"
        elif since_last < 3600:
            last_str = f"vor {since_last/60:.0f}min"
        else:
            last_str = f"vor {since_last/3600:.1f}h"
    else:
        last_str = "nie"

    # Letzte Erfahrung
    last_exp = get_last_experience(base_path)
    last_thought = last_exp.get("content", "")[:120] if last_exp else "(keine)"
    last_action = last_exp.get("type", "?")

    # Memory Stats
    mem_index = load_json(base_path / "memory" / "index.json")
    total_exp = mem_index.get("total_experiences", 0)
    total_ref = mem_index.get("total_reflections", 0)

    # Ungelesene Nachrichten
    unread = get_outbox_count(base_path)

    clear_screen()

    # === Header ===
    print()
    print(f"  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║  {name:^50s}  ║")
    print(f"  ╠══════════════════════════════════════════════════════╣")
    print(f"  ║  Geboren: {born:10s}  │  Zyklen: {cycles:<20d}  ║")
    print(f"  ║  Letzter Zyklus: {last_str:>8s}                              ║")
    print(f"  ╚══════════════════════════════════════════════════════╝")

    # === Emotionen ===
    print()
    print("  ─── Emotionaler Zustand ───")
    for emotion_name, value in emotions.items():
        print(format_emotion(emotion_name, value))

    # === Persoenlichkeit ===
    traits = personality.get("traits", {})
    style = personality.get("style_vector", [])
    values = personality.get("values", [])

    print()
    print("  ─── Persoenlichkeit ───")
    if traits:
        # Top 3 staerkste Traits
        sorted_traits = sorted(traits.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)
        for trait, value in sorted_traits[:4]:
            direction = "↑" if value > 0.55 else "↓" if value < 0.45 else "·"
            print(f"    {direction} {trait}: {value:.2f}")
    else:
        print("    (noch keine Traits entwickelt)")

    if style:
        print(f"    Stil: {', '.join(style)}")
    if values:
        print(f"    Werte: {', '.join(values)}")

    # === Letzter Gedanke ===
    print()
    print("  ─── Letzter Gedanke ───")
    print(f"    Aktion: {last_action}")
    print(f"    {last_thought}...")

    # === Ueberzeugungen ===
    formed = beliefs.get("formed_from_experience", [])
    if formed:
        print()
        print(f"  ─── Ueberzeugungen ({len(formed)}) ───")
        for belief in formed[-3:]:
            print(f"    • {belief[:80]}")

    # === Ziele ===
    active_goals = goals.get("active", [])
    if active_goals:
        print()
        print(f"  ─── Aktive Ziele ({len(active_goals)}) ───")
        for goal in active_goals[-3:]:
            print(f"    → {goal[:80]}")

    # === Status-Zeile ===
    print()
    print(f"  ─── Status ───")
    print(f"    Erinnerungen: {total_exp} | Reflexionen: {total_ref} | "
          f"Ohne Oliver: {cycles_since} Zyklen | "
          f"Ungelesen: {unread} Nachrichten")

    # Telegram Status
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_status = "aktiv" if tg_token else "nicht konfiguriert"
    print(f"    Telegram: {tg_status}")

    print()
    print(f"  ─────────────────────────────────────────")
    print(f"  Aktualisierung alle {REFRESH_RATE}s | Ctrl+C zum Beenden")


def render_journal(base_path: Path):
    """Zeigt nur das Journal an."""
    clear_screen()
    print()
    print("  ═══ Lyras Tagebuch ═══")
    print()

    journal_path = base_path / "journal"
    if not journal_path.exists():
        print("  (noch keine Eintraege)")
        return

    files = sorted(journal_path.glob("*.md"))
    if not files:
        print("  (noch keine Eintraege)")
        return

    # Letzten 2 Tage anzeigen
    for journal_file in files[-2:]:
        content = journal_file.read_text(encoding="utf-8")
        # Kuerzen wenn zu lang
        if len(content) > 3000:
            lines = content.split("\n")
            # Letzte Eintraege zeigen
            content = "\n".join(lines[-40:])
            content = "  (...gekuerzt...)\n" + content
        print(content)

    print()
    print(f"  Aktualisierung alle {REFRESH_RATE}s | Ctrl+C zum Beenden")


def main():
    from dotenv import load_dotenv
    load_dotenv(BASE_PATH / ".env")

    global REFRESH_RATE

    mode = "dashboard"

    if "--fast" in sys.argv:
        REFRESH_RATE = 2
    if "--journal" in sys.argv:
        mode = "journal"

    print(f"\n  Starte Dashboard (Refresh: {REFRESH_RATE}s)...")
    time.sleep(1)

    try:
        while True:
            if mode == "journal":
                render_journal(BASE_PATH)
            else:
                render_dashboard(BASE_PATH)
            time.sleep(REFRESH_RATE)
    except KeyboardInterrupt:
        print("\n\n  Dashboard geschlossen.\n")


if __name__ == "__main__":
    main()
