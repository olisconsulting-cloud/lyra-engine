"""
Policy Engine — Erzwingt Verhaltensaenderung aus Erfahrung.

Stufe 1: Bestrafung    — Tool+Kontext gescheitert → blockieren (Phase 1)
Stufe 2: Verstaendnis  — WARUM gescheitert → Kausal-Tags (Phase 1-2)
Stufe 3: Generalisierung — Aehnliches auch riskant → Transfer (Phase 2-3)

NICHT zustaendig fuer: Infrastructure-Fehler (Netzwerk, API-Down, Timeouts)
→ Das macht ProviderHealth im LLM-Router.

Integration: Wird von SequenceIntelligence als Sub-Modul genutzt.
Kein direkter Import in consciousness.py.
"""

import json
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# === Datentypen ===


class FailureCategory(Enum):
    """Kausal-Tags fuer Policy-Eintraege.

    infrastructure fehlt BEWUSST — wird vom ProviderHealth-System behandelt.
    """
    CAPABILITY = "capability"      # Kein Browser, fehlende Lib
    INPUT_ERROR = "input_error"    # Falscher Input, Schema-Fehler
    LOGIC_ERROR = "logic_error"    # Bug im Tool-Code, Laufzeitfehler
    UNKNOWN = "unknown"            # Nicht klassifiziert (Default)


# Exploration-Backoff pro Kategorie (Sequenzen bis Retry)
EXPLORATION_BACKOFF = {
    FailureCategory.CAPABILITY: 100,
    FailureCategory.INPUT_ERROR: 20,  # Input-Fehler sind leichter behebbar
    FailureCategory.LOGIC_ERROR: 30,
    FailureCategory.UNKNOWN: 50,
}

# Minimale Samples bevor ein Block greift
MIN_SAMPLES_FOR_BLOCK = 3
# Weight-Schwelle unter der blockiert wird
BLOCK_THRESHOLD = 0.2
# Max 1 Exploration pro N Sequenzen
EXPLORATION_RATE_LIMIT = 10


@dataclass
class PolicyVerdict:
    """Ergebnis einer Policy-Pruefung: Darf das Tool ausgefuehrt werden?"""
    allowed: bool
    reason: str = ""
    alternative: str = ""
    confidence: float = 0.0  # 0.0-1.0, wie sicher ist die Entscheidung


# === Hilfsfunktionen ===


# Muster die auf Infrastructure-Fehler hinweisen → NICHT in Policy speichern
_INFRA_PATTERNS = re.compile(
    r"timeout|timed?\s*out|connection\s*(refused|reset|error)|"
    r"getaddrinfo|ECONNREFUSED|ETIMEDOUT|rate.limit|429|503|"
    r"API.*Timeout|Provider.*fehlgeschlagen|DNS",
    re.IGNORECASE,
)


def _is_infrastructure_error(error_msg: str) -> bool:
    """True wenn der Fehler ein Infrastruktur-Problem ist (Router-Zustaendigkeit)."""
    return bool(_INFRA_PATTERNS.search(error_msg))


def _classify_failure(error_msg: str, tool_name: str) -> FailureCategory:
    """Leitet Kausal-Tag aus Fehlermeldung ab."""
    lower = error_msg.lower()

    # Capability: Fehlende Abhaengigkeiten
    if any(kw in lower for kw in (
        "not found", "nicht gefunden", "nicht installiert",
        "modulenotfounderror", "no such file", "permission denied",
        "zugriff verweigert", "no module named", "command not found",
    )):
        return FailureCategory.CAPABILITY

    # Input-Error: Falsche Parameter
    if any(kw in lower for kw in (
        "missing required", "invalid", "schema", "parameter",
        "expected", "pflichtfeld", "typ-fehler", "keyerror",
        "valueerror", "existiert nicht",
    )):
        return FailureCategory.INPUT_ERROR

    # Logic-Error: Code-Bugs
    if any(kw in lower for kw in (
        "traceback", "exception", "syntaxerror", "typeerror",
        "attributeerror", "indexerror", "zerodivision", "recursion",
        "nameerror", "indentationerror",
    )):
        return FailureCategory.LOGIC_ERROR

    return FailureCategory.UNKNOWN


def _adaptive_lr(sample_count: int) -> float:
    """Adaptive Lernrate: schnell bei wenig Daten, stabil bei vielen.

    lr = max(0.05, 0.3 / sqrt(n))
    n=1 → 0.30, n=4 → 0.15, n=25 → 0.06, n=100 → 0.05
    """
    if sample_count <= 0:
        return 0.30
    return max(0.05, 0.30 / math.sqrt(sample_count))


# === Kern-Klassen ===


class DecisionGate:
    """Phase 1: Harte Sperren aus Erfahrung.

    Prueft ob ein Tool+Kontext blockiert ist (weight < 0.2 bei >= 3 Samples).
    Aktualisiert Weights nach jedem Tool-Aufruf per adaptiver EMA.
    """

    @staticmethod
    def check(context_key: str, policies: dict) -> PolicyVerdict:
        """Prueft ob eine Tool+Kontext-Kombination blockiert ist."""
        tool_policies = policies.get("tool_policies", {})
        policy = tool_policies.get(context_key)

        if not policy:
            return PolicyVerdict(allowed=True, confidence=0.0)

        sample_count = policy.get("sample_count", 0)
        weight = policy.get("weight", 1.0)

        # Zu wenig Daten → erlauben (noch kein Urteil moeglich)
        if sample_count < MIN_SAMPLES_FOR_BLOCK:
            return PolicyVerdict(allowed=True, confidence=sample_count / MIN_SAMPLES_FOR_BLOCK)

        # Exploration: Block abgelaufen?
        can_retry = policy.get("can_retry_after", 0)
        current_seq = policies.get("current_sequence", 0)
        last_explore = policies.get("_last_exploration_seq", 0)
        if weight < BLOCK_THRESHOLD and can_retry > 0 and current_seq >= can_retry:
            # Rate-Limit: Max 1 Exploration pro EXPLORATION_RATE_LIMIT Sequenzen
            if current_seq - last_explore < EXPLORATION_RATE_LIMIT:
                pass  # Zu frueh fuer naechste Exploration → blockiert lassen
            else:
                # Exploration-Probe: einmal probieren lassen
                policies["_last_exploration_seq"] = current_seq
                logger.info(
                    "Policy-Exploration: %s darf proben (Seq %d >= %d)",
                    context_key, current_seq, can_retry,
                )
                return PolicyVerdict(
                    allowed=True,
                    reason=f"Exploration-Probe (war blockiert, Weight {weight:.2f})",
                    confidence=0.3,
                )

        # Blockiert?
        if weight < BLOCK_THRESHOLD:
            category = policy.get("failure_category", "unknown")
            failures = policy.get("failures", 0)
            return PolicyVerdict(
                allowed=False,
                reason=(
                    f"{context_key}: Weight {weight:.2f}, "
                    f"{failures} Failures ({category})"
                ),
                confidence=min(1.0, sample_count / 10),
            )

        return PolicyVerdict(allowed=True, confidence=min(1.0, sample_count / 10))

    @staticmethod
    def update_from_failure(
        context_key: str, error_msg: str, policies: dict, current_seq: int,
    ):
        """Aktualisiert Policy nach Failure: Weight senken, Kausal-Tag setzen."""
        tool_policies = policies.setdefault("tool_policies", {})
        policy = tool_policies.get(context_key, {
            "weight": 1.0, "successes": 0, "failures": 0,
            "sample_count": 0, "status": "active",
            "failure_category": "unknown",
            "last_failure_reason": "", "last_updated": "",
            "can_retry_after": 0,
        })

        category = _classify_failure(error_msg, context_key.split(":")[0])

        # Adaptive EMA: Weight senken
        # Bei reinen Failures (0 Successes) lernen wir schneller — klares Signal
        lr = _adaptive_lr(policy["sample_count"])
        if policy["successes"] == 0:
            lr = max(lr, 0.25)  # Mindestens 25% Lernrate bei null Erfolgen
        policy["weight"] = policy["weight"] * (1 - lr)  # outcome=0 bei Failure
        policy["failures"] += 1
        policy["sample_count"] += 1
        policy["failure_category"] = category.value
        policy["last_failure_reason"] = error_msg[:200]
        policy["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Status aktualisieren
        if policy["weight"] < BLOCK_THRESHOLD and policy["sample_count"] >= MIN_SAMPLES_FOR_BLOCK:
            policy["status"] = "blocked"
            # Exploration-Timer setzen (falls noch nicht gesetzt)
            if policy.get("can_retry_after", 0) == 0:
                backoff = EXPLORATION_BACKOFF.get(category, 50)
                policy["can_retry_after"] = current_seq + backoff
                policy["exploration_backoff"] = backoff  # H3-Fix: Original speichern
                logger.info(
                    "Policy BLOCKED: %s (Weight %.2f, Kategorie %s, Retry nach Seq %d)",
                    context_key, policy["weight"], category.value, policy["can_retry_after"],
                )
        else:
            policy["status"] = "active"

        tool_policies[context_key] = policy

    @staticmethod
    def update_from_success(context_key: str, policies: dict):
        """Aktualisiert Policy nach Erfolg: Weight heben, ggf. Block aufheben."""
        tool_policies = policies.setdefault("tool_policies", {})
        policy = tool_policies.get(context_key)

        if not policy:
            # Erstmalig erfolgreich — guten Start geben
            tool_policies[context_key] = {
                "weight": 1.0, "successes": 1, "failures": 0,
                "sample_count": 1, "status": "active",
                "failure_category": "", "last_failure_reason": "",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "can_retry_after": 0,
            }
            return

        lr = _adaptive_lr(policy["sample_count"])
        policy["weight"] = policy["weight"] * (1 - lr) + 1.0 * lr  # outcome=1 bei Erfolg
        policy["successes"] += 1
        policy["sample_count"] += 1
        policy["last_updated"] = datetime.now(timezone.utc).isoformat()

        # War blockiert und Exploration-Probe erfolgreich?
        if policy["status"] == "blocked":
            policy["status"] = "active"
            policy["can_retry_after"] = 0
            policy["weight"] = max(policy["weight"], 0.5)  # Faire Chance nach Unblock
            logger.info(
                "Policy UNBLOCKED: %s (Exploration erfolgreich, Weight %.2f)",
                context_key, policy["weight"],
            )
        elif policy["weight"] > 0.8:
            policy["status"] = "preferred"

        tool_policies[context_key] = policy

    @staticmethod
    def update_exploration_backoff(context_key: str, policies: dict, current_seq: int):
        """Verdoppelt Exploration-Backoff nach erneutem Failure."""
        tool_policies = policies.get("tool_policies", {})
        policy = tool_policies.get(context_key)
        if not policy:
            return

        # Original-Backoff aus Policy lesen (gespeichert bei Block-Erstellung)
        original = policy.get("exploration_backoff", 50)
        new_backoff = min(original * 2, 100)  # Verdoppeln, max 100 Sequenzen (nicht 500 — Lockout vermeiden)
        policy["exploration_backoff"] = new_backoff
        policy["can_retry_after"] = current_seq + new_backoff
        logger.info(
            "Exploration-Backoff: %s %d → %d Seq (Retry nach Seq %d)",
            context_key, original, new_backoff, policy["can_retry_after"],
        )


# === Haupt-Klasse ===


class PolicyEngine:
    """Orchestrator: Laedt/speichert Policies, exponiert Check-Points.

    Phase 1: DecisionGate (harte Sperren)
    Phase 2: PolicyWeights (gewichtete Strategien) — spaeter
    Phase 3: FailureGoalLoop (Failure → Alternative → Retry) — spaeter
    """

    def __init__(self, consciousness_path: Path):
        self._path = consciousness_path
        self._policies_path = consciousness_path / "policies.json"
        self._lock = threading.Lock()
        self._dirty = False
        self._last_exploration_seq = 0  # Rate-Limit fuer Exploration

        self.policies = self._load()

        # Bootstrap: Beim ersten Start bestehende Daten als Seed nutzen
        if not self.policies.get("tool_policies"):
            self._bootstrap(consciousness_path)

    # === Public API ===

    def check_before_tool(
        self, tool_name: str, tool_input: dict, goal_context: str = "",
    ) -> PolicyVerdict:
        """Prueft ob ein Tool ausgefuehrt werden darf. Wird VOR Execution aufgerufen."""
        context_key = self._make_context_key(tool_name, tool_input, goal_context)
        with self._lock:  # C1-Fix: Konsistente Reads unter Lock
            return DecisionGate.check(context_key, self.policies)

    def record_after_tool(
        self, tool_name: str, tool_input: dict, result: str,
        is_error: bool, goal_context: str = "",
    ):
        """Lernt aus Tool-Ergebnis. Wird NACH Execution aufgerufen."""
        # Infrastructure-Fehler ignorieren (Router-Zustaendigkeit)
        if is_error and _is_infrastructure_error(result):
            return

        context_key = self._make_context_key(tool_name, tool_input, goal_context)
        current_seq = self.policies.get("current_sequence", 0)

        with self._lock:
            if is_error:
                DecisionGate.update_from_failure(context_key, result, self.policies, current_seq)
                # War das ein gescheiterter Exploration-Probe?
                policy = self.policies.get("tool_policies", {}).get(context_key, {})
                can_retry = policy.get("can_retry_after", 0)
                if can_retry > 0 and can_retry <= current_seq:
                    DecisionGate.update_exploration_backoff(
                        context_key, self.policies, current_seq,
                    )
            else:
                DecisionGate.update_from_success(context_key, self.policies)

            self._dirty = True

    def set_current_sequence(self, seq_num: int):
        """Setzt aktuelle Sequenz-Nummer (fuer Exploration-Timing)."""
        self.policies["current_sequence"] = seq_num

    def save_if_dirty(self):
        """Speichert policies.json wenn Aenderungen vorliegen. Pruned stale Eintraege."""
        if self._dirty:
            self._prune_stale_policies()
            self._save()
            self._dirty = False

    def _prune_stale_policies(self, max_entries: int = 500):
        """Entfernt alte Policies mit wenig Daten um unbegrenztes Wachstum zu verhindern."""
        tp = self.policies.get("tool_policies", {})
        if len(tp) <= max_entries:
            return
        # Sortiere nach Relevanz: blocked/preferred behalten, alte low-sample entfernen
        scored = []
        for key, pol in tp.items():
            keep_score = pol.get("sample_count", 0) * 10
            if pol.get("status") == "blocked":
                keep_score += 1000  # Blocks sind wertvoll
            if pol.get("status") == "preferred":
                keep_score += 500
            scored.append((key, keep_score))
        scored.sort(key=lambda x: x[1])
        # Entferne die unwichtigsten bis max_entries
        to_remove = len(tp) - max_entries
        for key, _ in scored[:to_remove]:
            del tp[key]
        if to_remove > 0:
            logger.info("Policy-Pruning: %d stale Eintraege entfernt", to_remove)

    def get_summary(self) -> str:
        """Kompakte Uebersicht fuer Logging."""
        tp = self.policies.get("tool_policies", {})
        blocked = sum(1 for p in tp.values() if p.get("status") == "blocked")
        preferred = sum(1 for p in tp.values() if p.get("status") == "preferred")
        total = len(tp)
        return f"Policies: {total} gesamt, {blocked} blockiert, {preferred} bevorzugt"

    def suggest_alternative(self, tool_name: str, goal_context: str = "") -> str:
        """Schlaegt alternatives Tool vor wenn das angefragte blockiert ist."""
        tp = self.policies.get("tool_policies", {})
        # Suche nach Tools die im gleichen Goal-Kontext gut funktionieren
        alternatives = []
        for key, policy in tp.items():
            if policy.get("status") in ("active", "preferred") and policy.get("weight", 0) > 0.5:
                parts = key.split(":")
                if len(parts) >= 2 and parts[0] != tool_name:
                    if goal_context and goal_context.lower() in key.lower():
                        alternatives.append((parts[0], policy["weight"]))

        if alternatives:
            alternatives.sort(key=lambda x: x[1], reverse=True)
            return f"Versuche stattdessen: {alternatives[0][0]} (Weight {alternatives[0][1]:.2f})"
        return ""

    # === Context-Key ===

    @staticmethod
    def _make_context_key(tool_name: str, tool_input: dict, goal_context: str) -> str:
        """Baut normalisierten Key aus Tool+Input+Goal.

        Format: tool_name:relevant_input_part
        Beispiele:
          write_file:projects/ki-server/main.py
          execute_python:api_integration
          read_file:data/goals.json
        """
        # Relevantester Input-Parameter extrahieren
        input_key = (
            tool_input.get("path", "")
            or tool_input.get("name", "")
            or tool_input.get("query", "")
            or tool_input.get("url", "")
        )

        if not input_key:
            # Fallback: Ersten String-Wert nehmen
            for v in tool_input.values():
                if isinstance(v, str) and len(v) > 3:
                    input_key = v[:80]
                    break

        # Normalisieren: Pfad kuerzen auf letzte 2 Segmente
        if "/" in input_key or "\\" in input_key:
            parts = Path(input_key).parts
            input_key = "/".join(parts[-2:]) if len(parts) >= 2 else input_key

        # Goal-Kontext anfuegen wenn vorhanden und Input generisch
        if goal_context and len(input_key) < 10:
            input_key = f"{input_key}@{goal_context[:30]}"

        return f"{tool_name}:{input_key[:80]}" if input_key else tool_name

    # === Persistence ===

    def _load(self) -> dict:
        """Laedt policies.json oder erstellt leere Struktur."""
        if self._policies_path.exists():
            try:
                data = json.loads(self._policies_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("version") == 1:
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Policy-Datei korrupt, erstelle neu: %s", e)

        return {
            "version": 1,
            "tool_policies": {},
            "strategy_policies": {},  # Phase 2
            "goal_type_stats": {},     # Phase 3
            "current_sequence": 0,
        }

    def _save(self):
        """Speichert policies.json atomar (thread-safe, crash-sicher)."""
        with self._lock:
            try:
                data = dict(self.policies)
                data["version"] = 1
                self._policies_path.parent.mkdir(parents=True, exist_ok=True)
                # Atomarer Write: Temp-Datei → Rename (verhindert Korruption bei Crash)
                tmp = self._policies_path.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp.replace(self._policies_path)
            except OSError as e:
                logger.warning("Policy-Datei konnte nicht gespeichert werden: %s", e)

    def _bootstrap(self, consciousness_path: Path):
        """Seedet initiale Policies aus bestehenden Failure- und Strategy-Daten."""
        logger.info("Policy-Bootstrap: Lese bestehende Failures und Strategies...")

        # 1. failures.json scannen
        failures_path = consciousness_path / "failures.json"
        if failures_path.exists():
            try:
                failures = json.loads(failures_path.read_text(encoding="utf-8"))
                if not isinstance(failures, list):
                    failures = []
                for entry in failures[-50:]:  # Letzte 50 Failures
                    if not isinstance(entry, dict):
                        continue
                    tool = entry.get("tool", entry.get("approach", ""))
                    error = entry.get("error", "")
                    goal = entry.get("goal", "")
                    if tool and error and not _is_infrastructure_error(error):
                        key = f"{tool}:{goal[:30]}" if goal else tool
                        category = _classify_failure(error, tool)
                        tp = self.policies.setdefault("tool_policies", {})
                        if key not in tp:
                            tp[key] = {
                                "weight": 0.5,  # Mittlerer Start (bekannter Fehler)
                                "successes": 0, "failures": 1,
                                "sample_count": 1, "status": "active",
                                "failure_category": category.value,
                                "last_failure_reason": error[:200],
                                "last_updated": datetime.now(timezone.utc).isoformat(),
                                "can_retry_after": 0,
                            }
                logger.info("Bootstrap: %d Failure-Policies geladen", len(self.policies.get("tool_policies", {})))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Bootstrap failures.json fehlgeschlagen: %s", e)

        self._dirty = True
