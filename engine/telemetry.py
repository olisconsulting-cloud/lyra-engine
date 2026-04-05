"""
Telemetry — Strukturiertes Event-Logging fuer Lyra.

Schreibt jedes Event als eine JSON-Zeile (JSON-Lines Format) in eine Datei.
Kein externes Framework, kein Server — eine Datei pro Tag, maschinenlesbar.

Events: llm_call, tool_call, sequence_start, sequence_end, fallback, error, dream

Nutzung:
    from engine.telemetry import telemetry
    telemetry.log_llm_call(model="deepseek_v3", task="main_work", ...)
    telemetry.log_tool_call(tool="write_file", success=True, ...)
"""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config


# Maximale Dateigroesse pro Log-Datei (50 MB) — danach wird rotiert
_MAX_FILE_SIZE = 50 * 1024 * 1024

# Maximale Anzahl an Log-Dateien (30 Tage)
_MAX_LOG_FILES = 30


class Telemetry:
    """JSON-Lines Event-Logger fuer Lyra.

    Thread-safe, append-only, eine Datei pro Tag.
    Jede Zeile ist ein eigenstaendiges JSON-Objekt — kein Parsing des ganzen Files noetig.
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self._log_dir = log_dir or config.DATA_PATH / "telemetry"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._current_file: Optional[Path] = None
        self._current_date: Optional[str] = None
        self._sequence_num: int = 0
        self._step_num: int = 0

    # === Kontext-Setter (von consciousness.py pro Sequenz/Step gesetzt) ===

    def set_sequence(self, seq_num: int):
        """Setzt aktuelle Sequenz-Nummer fuer alle folgenden Events."""
        self._sequence_num = seq_num
        self._step_num = 0

    def set_step(self, step: int):
        """Setzt aktuellen Step fuer alle folgenden Events."""
        self._step_num = step

    # === Event-Logger ===

    def log_llm_call(
        self,
        model: str,
        task: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool = True,
        error: str = "",
        cache_hit: bool = False,
    ):
        """LLM-Call mit Modell, Tokens, Kosten, Latenz."""
        self._write({
            "event": "llm_call",
            "model": model,
            "task": task,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
            "latency_ms": latency_ms,
            "success": success,
            "error": error[:200] if error else "",
            "cache_hit": cache_hit,
        })

    def log_tool_call(
        self,
        tool: str,
        success: bool,
        latency_ms: int,
        error: str = "",
        is_blocked: bool = False,
        stuck_count: int = 0,
    ):
        """Tool-Ausfuehrung mit Erfolg/Fehler und Latenz."""
        self._write({
            "event": "tool_call",
            "tool": tool,
            "success": success,
            "latency_ms": latency_ms,
            "error": error[:200] if error else "",
            "is_blocked": is_blocked,
            "stuck_count": stuck_count,
        })

    def log_sequence_start(
        self,
        focus: str,
        mode: str,
        step_budget: int,
        task_type: str = "",
    ):
        """Sequenz-Start mit Fokus und Budget."""
        self._write({
            "event": "sequence_start",
            "focus": focus[:200] if focus else "",
            "mode": mode,
            "step_budget": step_budget,
            "task_type": task_type,
        })

    def log_sequence_end(
        self,
        steps: int,
        duration_s: float,
        errors: int,
        files_written: int,
        tools_built: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        finish_reason: str = "normal",
        rating: int = 0,
    ):
        """Sequenz-Ende mit Gesamt-Metriken."""
        self._write({
            "event": "sequence_end",
            "steps": steps,
            "duration_s": round(duration_s, 1),
            "errors": errors,
            "files_written": files_written,
            "tools_built": tools_built,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6),
            "finish_reason": finish_reason,
            "rating": rating,
            "efficiency": round(files_written / max(steps, 1), 3),
        })

    def log_fallback(
        self,
        from_model: str,
        to_model: str,
        reason: str = "",
    ):
        """Fallback von einem Provider zum naechsten."""
        self._write({
            "event": "fallback",
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason[:200] if reason else "",
        })

    def log_error(
        self,
        category: str,
        message: str,
        context: str = "",
    ):
        """Allgemeiner Fehler (API-Cascade, Message-Sync, etc.)."""
        self._write({
            "event": "error",
            "category": category,
            "message": message[:300],
            "context": context[:200] if context else "",
        })

    def log_dream(
        self,
        duration_s: float,
        beliefs_changed: int = 0,
        strategies_changed: int = 0,
        skills_extracted: int = 0,
    ):
        """Dream-Konsolidierung."""
        self._write({
            "event": "dream",
            "duration_s": round(duration_s, 1),
            "beliefs_changed": beliefs_changed,
            "strategies_changed": strategies_changed,
            "skills_extracted": skills_extracted,
        })

    def log_enforcement(
        self,
        rule: str,
        step: int,
        reason: str = "",
    ):
        """Meta-Rule Enforcement oder Actuator-Eingriff."""
        self._write({
            "event": "enforcement",
            "rule": rule,
            "step": step,
            "reason": reason[:200] if reason else "",
        })

    # === Abfragen (fuer Dashboard / Evaluation) ===

    def get_today_stats(self) -> dict:
        """Liest heutige Events und berechnet Zusammenfassung.

        Returns:
            {sequences, total_cost, total_tokens, errors, avg_latency_ms, tools_used}
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self._log_dir / f"{today}.jsonl"
        if not log_file.exists():
            return {"sequences": 0, "total_cost": 0.0, "total_tokens": 0,
                    "errors": 0, "avg_latency_ms": 0, "tools_used": {}}

        stats = {
            "sequences": 0, "total_cost": 0.0, "total_input_tokens": 0,
            "total_output_tokens": 0, "errors": 0,
            "llm_latencies": [], "tools_used": {},
        }
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

                    event_type = ev.get("event")
                    if event_type == "sequence_end":
                        stats["sequences"] += 1
                        # Kosten NICHT aus sequence_end — sonst doppelt mit llm_call
                    elif event_type == "llm_call":
                        stats["total_input_tokens"] += ev.get("input_tokens", 0)
                        stats["total_output_tokens"] += ev.get("output_tokens", 0)
                        stats["total_cost"] += ev.get("cost_usd", 0)
                        if ev.get("latency_ms"):
                            stats["llm_latencies"].append(ev["latency_ms"])
                        if not ev.get("success"):
                            stats["errors"] += 1
                    elif event_type == "tool_call":
                        tool = ev.get("tool", "unknown")
                        stats["tools_used"][tool] = stats["tools_used"].get(tool, 0) + 1
                        if not ev.get("success"):
                            stats["errors"] += 1
                    elif event_type == "error":
                        stats["errors"] += 1
        except OSError:
            pass

        latencies = stats.pop("llm_latencies")
        stats["avg_latency_ms"] = round(sum(latencies) / max(len(latencies), 1))
        stats["total_tokens"] = stats["total_input_tokens"] + stats["total_output_tokens"]
        return stats

    def get_log_path(self) -> Path:
        """Gibt den Pfad zum aktuellen Log-File zurueck."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"{today}.jsonl"

    # === Internes ===

    def _write(self, event: dict):
        """Schreibt ein Event als JSON-Zeile (thread-safe, append-only)."""
        now = datetime.now(timezone.utc)
        event["timestamp"] = now.isoformat()
        # seq/step nur setzen wenn nicht bereits im Event (log_enforcement setzt eigenen step)
        event.setdefault("seq", self._sequence_num)
        event.setdefault("step", self._step_num)

        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            log_file = self._get_log_file(now)
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass  # Telemetry darf nie die Engine crashen

    def _get_log_file(self, now: datetime) -> Path:
        """Gibt die aktuelle Log-Datei zurueck (eine pro Tag, mit Rotation)."""
        date_str = now.strftime("%Y-%m-%d")

        # Tageswechsel? Neue Datei + alte aufraeumen
        if date_str != self._current_date:
            self._current_date = date_str
            self._current_file = self._log_dir / f"{date_str}.jsonl"
            self._cleanup_old_logs()

        # Dateigroesse pruefen
        if self._current_file.exists():
            try:
                if self._current_file.stat().st_size > _MAX_FILE_SIZE:
                    # Suffix anhaengen statt ueberschreiben
                    ts = now.strftime("%H%M%S")
                    self._current_file = self._log_dir / f"{date_str}_{ts}.jsonl"
            except OSError:
                pass

        return self._current_file

    def _cleanup_old_logs(self):
        """Entfernt Log-Dateien aelter als _MAX_LOG_FILES Tage."""
        try:
            log_files = sorted(self._log_dir.glob("*.jsonl"))
            while len(log_files) > _MAX_LOG_FILES:
                log_files[0].unlink(missing_ok=True)
                log_files.pop(0)
        except OSError:
            pass


# Singleton — wird von allen Modulen importiert
telemetry = Telemetry()
