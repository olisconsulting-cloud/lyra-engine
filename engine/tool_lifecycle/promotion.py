"""
Promotion Engine — Befoerdert exzellente Tools zu Engine-Code-Kandidaten.

Der hoechste Reifegrad im Tool-Lifecycle: Ein Tool das sich als so
wertvoll erwiesen hat, dass es Teil der permanenten Infrastruktur
werden sollte. Die Engine nominiert Kandidaten — Oliver entscheidet.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from engine.toolchain import Toolchain
    from engine.tool_lifecycle.metrics import ToolMetrics

logger = logging.getLogger(__name__)

# Promotion-Kriterien
MIN_HEALTH_SCORE = 8.0
MIN_USES = 20
MIN_SUCCESS_RATE = 0.85
MIN_AGE_DAYS = 7

# Heuristik: Tool-Keywords → Ziel-Modul
TARGET_MODULE_MAP = {
    "api": "engine/handlers/web_handlers.py",
    "http": "engine/handlers/web_handlers.py",
    "security": "engine/security.py",
    "scan": "engine/security.py",
    "file": "engine/handlers/file_handlers.py",
    "checker": "engine/handlers/file_handlers.py",
    "code": "engine/handlers/code_handlers.py",
    "python": "engine/handlers/code_handlers.py",
    "research": "engine/handlers/web_handlers.py",
    "dream": "engine/dream.py",
    "memory": "engine/intelligence.py",
    "goal": "engine/goal_stack.py",
}


class PromotionEngine:
    """Identifiziert und nominiert Tools fuer Promotion zu Engine-Code."""

    def __init__(self, toolchain: "Toolchain", metrics: "ToolMetrics",
                 data_path: Optional[Path] = None):
        self.toolchain = toolchain
        self.metrics = metrics
        self.promotions_path = (
            (data_path or toolchain.tools_path) / "promotions.json"
        )
        self.promotions = self._load()

    # === Persistenz ===

    def _load(self) -> dict:
        """Laedt Promotions-Daten."""
        if self.promotions_path.exists():
            try:
                with open(self.promotions_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"promotions.json korrupt: {e} — starte mit leeren Daten")
        return {"pending": [], "promoted": [], "rejected": []}

    def _save(self) -> None:
        """Persistiert Promotions-Daten."""
        self.promotions_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.promotions_path, "w", encoding="utf-8") as f:
            json.dump(self.promotions, f, indent=2, ensure_ascii=False)

    # === Kandidaten-Bewertung ===

    def evaluate_candidates(self) -> list[dict]:
        """Identifiziert Promotion-Kandidaten.

        Kriterien (alle muessen erfuellt sein):
        - Health-Score >= 8.0
        - Mindestens 20 Nutzungen
        - Success-Rate >= 85%
        - Aelter als 7 Tage
        - Noch nicht nominiert oder promoted

        Returns:
            Liste von {name, health_score, uses, success_rate, age_days, reason}
        """
        now = datetime.now(timezone.utc)
        registry = self.toolchain.registry.get("tools", {})
        already_handled = set(
            p["name"] for p in
            self.promotions.get("pending", [])
            + self.promotions.get("promoted", [])
        )

        candidates = []

        for name, info in registry.items():
            if info.get("status") == "archived":
                continue
            if name in already_handled:
                continue

            metric = self.metrics.metrics.get(name, {})
            health = metric.get("health_score", 0.0)
            uses = metric.get("total_calls", 0)
            success_rate = metric.get("success_rate", 0.0)

            # Alter berechnen
            created = info.get("created", "")
            age_days = 0.0
            if created:
                try:
                    created_dt = datetime.fromisoformat(created)
                    age_days = (now - created_dt).total_seconds() / 86400
                except (ValueError, TypeError):
                    pass

            # Alle Kriterien pruefen
            if (health >= MIN_HEALTH_SCORE
                    and uses >= MIN_USES
                    and success_rate >= MIN_SUCCESS_RATE
                    and age_days >= MIN_AGE_DAYS):

                target = self.suggest_target_module(name)
                candidates.append({
                    "name": name,
                    "health_score": health,
                    "uses": uses,
                    "success_rate": success_rate,
                    "age_days": round(age_days, 1),
                    "suggested_target": target,
                    "reason": (
                        f"Health {health}/10, {uses}x genutzt, "
                        f"{success_rate:.0%} Erfolg, {age_days:.0f} Tage alt"
                    ),
                })

        return sorted(candidates, key=lambda x: x["health_score"], reverse=True)

    def nominate(self, tool_name: str, reason: str) -> str:
        """Nominiert ein Tool fuer Promotion.

        Args:
            tool_name: Name des Tools
            reason: Begruendung fuer die Nomination

        Returns:
            Bestaetigungs-Nachricht.
        """
        # Duplikat-Check
        pending_names = {p["name"] for p in self.promotions.get("pending", [])}
        if tool_name in pending_names:
            return f"'{tool_name}' ist bereits nominiert."

        self.promotions.setdefault("pending", []).append({
            "name": tool_name,
            "reason": reason,
            "nominated_at": datetime.now(timezone.utc).isoformat(),
            "suggested_target": self.suggest_target_module(tool_name),
        })
        self._save()

        logger.info(f"Tool nominiert fuer Promotion: {tool_name} — {reason}")
        return f"PROMOTION-KANDIDAT: '{tool_name}' — {reason}"

    def auto_nominate(self) -> str:
        """Evaluiert und nominiert automatisch.

        Wird im Dream-Zyklus aufgerufen.

        Returns:
            Zusammenfassung oder leerer String.
        """
        candidates = self.evaluate_candidates()
        if not candidates:
            return ""

        nominated = []
        for candidate in candidates[:2]:  # Max 2 pro Durchlauf
            result = self.nominate(candidate["name"], candidate["reason"])
            nominated.append(result)

        return " | ".join(nominated)

    # === Heuristiken ===

    def suggest_target_module(self, tool_name: str) -> str:
        """Schlaegt Ziel-Modul fuer Promotion vor.

        Basiert auf Keyword-Matching gegen TARGET_MODULE_MAP.

        Args:
            tool_name: Name des Tools

        Returns:
            Vorgeschlagener Dateipfad oder "engine/handlers/tool_handlers.py"
        """
        name_lower = tool_name.lower()

        # Beschreibung aus Registry holen
        info = self.toolchain.registry.get("tools", {}).get(tool_name, {})
        description = info.get("description", "").lower()
        search_text = f"{name_lower} {description}"

        for keyword, module in TARGET_MODULE_MAP.items():
            if keyword in search_text:
                return module

        # Default: Tool-Handlers
        return "engine/handlers/tool_handlers.py"

    # === Abfragen ===

    def get_pending(self) -> list[dict]:
        """Gibt alle ausstehenden Nominations zurueck."""
        return self.promotions.get("pending", [])

    def get_summary(self) -> str:
        """Kompakte Zusammenfassung fuer Dashboard/Narrator."""
        pending = len(self.promotions.get("pending", []))
        promoted = len(self.promotions.get("promoted", []))
        rejected = len(self.promotions.get("rejected", []))

        if pending == 0 and promoted == 0:
            return ""

        parts = []
        if pending > 0:
            names = [p["name"] for p in self.promotions["pending"][:3]]
            parts.append(f"Ausstehend: {', '.join(names)}")
        if promoted > 0:
            parts.append(f"Promoted: {promoted}")
        if rejected > 0:
            parts.append(f"Abgelehnt: {rejected}")

        return "TOOL-PROMOTIONS: " + " | ".join(parts)
