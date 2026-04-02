"""
Phi Web-Dashboard — FastAPI Backend.

Liest Phis Bewusstseinsdaten vom Dateisystem und serviert sie als API.
WebSocket fuer Live-Updates wenn Phi arbeitet.

Starten: python run_dashboard_web.py
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from engine.config import (
    CONSCIOUSNESS_PATH,
    JOURNAL_PATH,
    MEMORY_PATH,
    MESSAGES_PATH,
    PROJECTS_PATH,
)

app = FastAPI(title="Phi Dashboard", docs_url=None, redoc_url=None)

WEB_PATH = Path(__file__).parent


# --- Hilfsfunktionen ---

def read_json(path: Path) -> dict | list:
    """Liest JSON-Datei sicher."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, PermissionError, OSError):
        pass
    return {}


def read_text(path: Path) -> str:
    """Liest Textdatei sicher."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except (PermissionError, OSError):
        pass
    return ""


def time_ago(iso_str: str) -> str:
    """Wandelt ISO-Timestamp in 'vor X' String um."""
    if not iso_str:
        return "nie"
    try:
        then = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        seconds = (now - then).total_seconds()
        if seconds < 0:
            return "gerade eben"
        if seconds < 60:
            return f"vor {seconds:.0f}s"
        elif seconds < 3600:
            return f"vor {seconds / 60:.0f} Min"
        elif seconds < 86400:
            return f"vor {seconds / 3600:.1f}h"
        else:
            return f"vor {seconds / 86400:.0f} Tagen"
    except (ValueError, TypeError):
        return "?"


def get_unread_count() -> int:
    """Zaehlt ungelesene Outbox-Nachrichten."""
    outbox = MESSAGES_PATH / "outbox"
    if not outbox.exists():
        return 0
    count = 0
    for f in outbox.glob("*.json"):
        msg = read_json(f)
        if not msg.get("read", True):
            count += 1
    return count


# --- API Endpunkte ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serviert das Dashboard."""
    html_path = WEB_PATH / "templates" / "dashboard.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    """Komplettzustand fuer das Dashboard — ein Request fuer alles."""
    state = read_json(CONSCIOUSNESS_PATH / "state.json")
    goals = read_json(CONSCIOUSNESS_PATH / "goals.json")
    skills = read_json(CONSCIOUSNESS_PATH / "skills.json")
    efficiency = read_json(CONSCIOUSNESS_PATH / "efficiency.json")
    seq_memory = read_json(CONSCIOUSNESS_PATH / "sequence_memory.json")
    personality = read_json(CONSCIOUSNESS_PATH / "personality.json")
    beliefs = read_json(CONSCIOUSNESS_PATH / "beliefs.json")
    mem_index = read_json(MEMORY_PATH / "index.json")
    working_memory = read_text(CONSCIOUSNESS_PATH / "working_memory.md")
    semantic_index = read_json(MEMORY_PATH / "semantic" / "index.json")

    # Skills sortiert nach Erfolgen
    skills_sorted = []
    for name, data in sorted(skills.items(), key=lambda x: x[1].get("successes", 0), reverse=True):
        if isinstance(data, dict):
            skills_sorted.append({
                "name": name,
                "successes": data.get("successes", 0),
                "failures": data.get("failures", 0),
                "streak": data.get("streak", 0),
                "best_streak": data.get("best_streak", 0),
                "level": data.get("level", "?"),
            })

    # Goal-Fortschritt berechnen
    active_goals = []
    for goal in goals.get("active", []):
        sgs = goal.get("sub_goals", [])
        done = sum(1 for sg in sgs if sg.get("status") == "done")
        total = len(sgs)
        active_goals.append({
            "id": goal.get("id", "?"),
            "title": goal.get("title", "?"),
            "description": goal.get("description", ""),
            "progress": done / total if total > 0 else 0,
            "done": done,
            "total": total,
            "sub_goals": sgs,
        })

    # Effizienz-Daten (letzte 50 Sequenzen)
    sequences = efficiency.get("sequences", [])[-50:]
    efficiency_data = {
        "timestamps": [s.get("timestamp", "") for s in sequences],
        "tool_calls": [s.get("tool_calls", 0) for s in sequences],
        "tokens": [s.get("tokens_used", 0) for s in sequences],
        "costs": [s.get("cost", 0) for s in sequences],
        "durations": [s.get("duration_seconds", 0) for s in sequences],
        "errors": [s.get("errors", 0) for s in sequences],
        "files_written": [s.get("files_written", 0) for s in sequences],
    }

    return {
        # Kernstatus
        "sequences_total": state.get("sequences_total", 0),
        "total_tool_calls": state.get("total_tool_calls", 0),
        "last_sequence": state.get("last_sequence", ""),
        "last_sequence_ago": time_ago(state.get("last_sequence", "")),
        "awake_since": state.get("awake_since", ""),
        "born": state.get("born", "?"),

        # Goals
        "goals": active_goals,
        "completed_goals": goals.get("completed", []),

        # Skills
        "skills": skills_sorted,

        # Effizienz
        "efficiency": efficiency_data,
        "total_cost": sum(s.get("cost", 0) for s in efficiency.get("sequences", [])),

        # Sequenz-Gedaechtnis
        "sequence_memory": seq_memory.get("entries", [])[-10:],

        # Working Memory
        "working_memory": working_memory,

        # Persoenlichkeit
        "traits": personality.get("traits", {}),
        "values": personality.get("values", []),
        "style": personality.get("style_vector", []),

        # Beliefs
        "beliefs": beliefs.get("formed_from_experience", []),

        # Memory-Statistiken
        "total_experiences": mem_index.get("total_experiences", 0),
        "total_reflections": mem_index.get("total_reflections", 0),
        "semantic_entries": len(semantic_index.get("entries", [])) if isinstance(semantic_index, dict) else 0,

        # Nachrichten
        "unread_messages": get_unread_count(),

        # Zeitstempel
        "dashboard_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/journal")
async def get_journal() -> list[dict]:
    """Journal-Eintraege — Phis Tagebuch."""
    if not JOURNAL_PATH.exists():
        return []
    entries = []
    for f in sorted(JOURNAL_PATH.glob("*.md")):
        content = read_text(f)
        # Sektionen aufsplitten (## Zyklus ...)
        sections = content.split("\n## ")
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            # Erste Sektion hat den # Header, danach ## Sektionen
            text = section if i == 0 else f"## {section}"
            entries.append({
                "date": f.stem,
                "content": text.strip()[:1000],
            })
    return entries[-30:]  # Letzte 30 Sektionen


@app.get("/api/experiences")
async def get_experiences() -> list[dict]:
    """Erfahrungen — was Phi erlebt hat, mit Valence und Emotionen."""
    exp_path = MEMORY_PATH / "experiences"
    if not exp_path.exists():
        return []
    experiences = []
    for f in sorted(exp_path.glob("*.json"))[-30:]:
        exp = read_json(f)
        if exp:
            experiences.append({
                "id": exp.get("id", "?"),
                "timestamp": exp.get("timestamp", ""),
                "type": exp.get("type", "?"),
                "content": exp.get("content", "")[:300],
                "valence": exp.get("valence", 0),
                "emotions": exp.get("emotions", {}),
                "tags": exp.get("tags", []),
            })
    return experiences


@app.get("/api/projects")
async def get_projects() -> list[dict]:
    """Projekte — von Phi erstellte Projekte."""
    if not PROJECTS_PATH.exists():
        return []
    projects = []
    for d in sorted(PROJECTS_PATH.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        # README oder PLAN lesen fuer Beschreibung
        desc = ""
        for readme_name in ("README.md", "PLAN.md", "PROGRESS.md"):
            readme = d / readme_name
            if readme.exists():
                desc = read_text(readme)[:500]
                break
        # Dateien zaehlen
        files = [f.name for f in d.iterdir() if f.is_file() and not f.name.startswith("_")]
        projects.append({
            "name": d.name,
            "description": desc,
            "files": files,
            "file_count": len(files),
        })
    return projects


@app.post("/api/message")
async def send_message(body: dict) -> dict:
    """Nachricht an Phi senden — wird in die Inbox geschrieben."""
    content = body.get("content", "").strip()
    if not content:
        return {"ok": False, "error": "Leere Nachricht"}
    if len(content) > 2000:
        return {"ok": False, "error": "Nachricht zu lang (max 2000 Zeichen)"}

    inbox = MESSAGES_PATH / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc)
    msg = {
        "from": "oliver",
        "timestamp": timestamp.isoformat(),
        "content": content,
        "channel": "dashboard",
        "read": False,
    }

    # Dateiname mit Mikrosekunden gegen Kollisionen bei schnellen Klicks
    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_dashboard.json"
    msg_path = inbox / filename

    msg_path.write_text(json.dumps(msg, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"ok": True, "message_id": filename}


# --- WebSocket fuer Live-Updates ---

class ConnectionManager:
    """Verwaltet aktive WebSocket-Verbindungen."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except (WebSocketDisconnect, RuntimeError):
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket — pusht Updates wenn sich Phis State aendert."""
    await manager.connect(ws)
    last_hash = ""
    try:
        while True:
            # State-Datei pruefen (leichtgewichtig)
            state_path = CONSCIOUSNESS_PATH / "state.json"
            try:
                current_hash = str(state_path.stat().st_mtime) if state_path.exists() else ""
            except OSError:
                current_hash = ""

            if current_hash != last_hash and current_hash:
                last_hash = current_hash
                state = read_json(state_path)
                await ws.send_json({"type": "state_changed", "sequences_total": state.get("sequences_total", 0)})

            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        manager.disconnect(ws)
