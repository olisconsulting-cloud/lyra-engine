"""
Promotion Engine — Befoerdert exzellente Tools zu Engine-Code.

Der hoechste Reifegrad im Tool-Lifecycle: Ein Tool das sich als so
wertvoll erwiesen hat, dass es Teil der permanenten Infrastruktur wird.

Autonome Promotion mit 3-Stufen-Sicherheit:
1. Kriterien-Gate (Health >= 9.0, Uses >= 25, Success >= 90%, Alter >= 14 Tage)
2. DualReview (Opus prueft den Code — fail-closed)
3. Telegram-Benachrichtigung an Oliver
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from engine.config import ROOT_PATH

if TYPE_CHECKING:
    from engine.toolchain import Toolchain
    from engine.tool_lifecycle.metrics import ToolMetrics
    from engine.code_review import DualReviewSystem
    from engine.communication import CommunicationEngine

logger = logging.getLogger(__name__)

# Nomination-Kriterien (Vorschlag an Oliver)
MIN_HEALTH_SCORE = 8.0
MIN_USES = 20
MIN_SUCCESS_RATE = 0.85
MIN_AGE_DAYS = 7

# Auto-Promotion-Kriterien (strengere Schwelle fuer autonome Integration)
AUTO_MIN_HEALTH = 9.0
AUTO_MIN_USES = 25
AUTO_MIN_SUCCESS_RATE = 0.90
AUTO_MIN_AGE_DAYS = 14

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

    # === Autonome Promotion (mit 3-Stufen-Sicherheit) ===

    def evaluate_auto_candidates(self) -> list[dict]:
        """Findet Tools die die strengeren Auto-Promotion-Kriterien erfuellen.

        Strengere Schwellen als Nomination:
        Health >= 9.0, Uses >= 25, Success >= 90%, Alter >= 14 Tage.
        """
        now = datetime.now(timezone.utc)
        registry = self.toolchain.registry.get("tools", {})
        already = set(
            p["name"] for p in
            self.promotions.get("promoted", [])
            + self.promotions.get("rejected", [])
        )

        candidates = []
        for name, info in registry.items():
            if info.get("status") == "archived" or name in already:
                continue

            metric = self.metrics.metrics.get(name, {})
            health = metric.get("health_score", 0.0)
            uses = metric.get("total_calls", 0)
            sr = metric.get("success_rate", 0.0)

            created = info.get("created", "")
            age_days = 0.0
            if created:
                try:
                    age_days = (now - datetime.fromisoformat(created)
                                ).total_seconds() / 86400
                except (ValueError, TypeError):
                    pass

            if (health >= AUTO_MIN_HEALTH
                    and uses >= AUTO_MIN_USES
                    and sr >= AUTO_MIN_SUCCESS_RATE
                    and age_days >= AUTO_MIN_AGE_DAYS):
                candidates.append({
                    "name": name,
                    "health_score": health,
                    "uses": uses,
                    "success_rate": sr,
                    "age_days": round(age_days, 1),
                    "suggested_target": self.suggest_target_module(name),
                })

        return sorted(candidates, key=lambda x: x["health_score"], reverse=True)

    def auto_promote(
        self,
        dual_review: "DualReviewSystem",
        communication: Optional["CommunicationEngine"] = None,
    ) -> str:
        """Autonome Promotion: DualReview-Gate + Telegram-Info.

        3-Stufen-Sicherheit:
        1. Strengere Kriterien (Health 9+, Uses 25+, Success 90%+, 14+ Tage)
        2. DualReview prueft den Tool-Code (Opus, fail-closed)
        3. Oliver wird via Telegram informiert

        Max 1 Promotion pro Dream-Zyklus.

        Returns:
            Zusammenfassung oder leerer String.
        """
        candidates = self.evaluate_auto_candidates()
        if not candidates:
            return ""

        candidate = candidates[0]  # Nur den besten pro Zyklus
        tool_name = candidate["name"]
        target_module = candidate["suggested_target"]

        # Tool-Code lesen
        tool_info = self.toolchain.registry.get("tools", {}).get(tool_name, {})
        tool_file = self.toolchain.tools_path / tool_info.get("file", "")
        if not tool_file.exists():
            logger.warning("Auto-Promote: Tool-Datei nicht gefunden: %s", tool_file)
            return ""

        tool_code = tool_file.read_text(encoding="utf-8")

        # === STUFE 1b: AST-Security-Check (deterministisch, vor LLM-Review) ===
        from engine.security import SecurityGateway
        from engine.config import DATA_PATH
        security = SecurityGateway(ROOT_PATH, DATA_PATH)
        check = security.check_code_execution(tool_code)
        if not check["allowed"]:
            self.promotions.setdefault("rejected", []).append({
                "name": tool_name,
                "reason": f"Security-Block: {check.get('hard_blocks', [])}",
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            })
            self._save()
            logger.warning("Auto-Promote Security-Block: %s — %s",
                           tool_name, check.get("hard_blocks"))
            return f"Promotion blockiert (Security): {tool_name}"

        # Ziel-Datei lesen und Tool-Code als neue Funktion anhaengen
        target_path = Path(target_module)
        target_full = ROOT_PATH / target_path
        if not target_full.exists():
            logger.warning("Auto-Promote: Ziel-Modul nicht gefunden: %s", target_full)
            return ""

        existing_code = target_full.read_text(encoding="utf-8")

        # Integration: Tool-Code als Funktion am Ende anhaengen
        integration_block = self._build_integration_block(
            tool_name, tool_code, tool_info.get("description", ""),
        )
        new_content = existing_code.rstrip() + "\n\n" + integration_block + "\n"

        # === STUFE 2: DualReview (fail-closed) ===
        reason = (
            f"Auto-Promotion: Tool '{tool_name}' hat sich bewaehrt "
            f"(Health {candidate['health_score']}/10, "
            f"{candidate['uses']}x genutzt, "
            f"{candidate['success_rate']:.0%} Erfolg, "
            f"{candidate['age_days']:.0f} Tage alt). "
            f"Integration in {target_module}."
        )

        review = dual_review.review_and_apply_fix(
            file_path=target_module,
            new_content=new_content,
            reason=reason,
        )

        if not review.get("accepted"):
            # Review abgelehnt — als rejected markieren
            self.promotions.setdefault("rejected", []).append({
                "name": tool_name,
                "reason": f"DualReview abgelehnt: {review.get('reason', '?')}",
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            })
            self._save()
            logger.info("Auto-Promote abgelehnt: %s — %s",
                        tool_name, review.get("reason"))
            return f"Promotion abgelehnt (DualReview): {tool_name}"

        # === STUFE 3: Erfolg — Markieren + Telegram ===
        self.promotions.setdefault("promoted", []).append({
            "name": tool_name,
            "target_module": target_module,
            "reason": reason,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "review": review.get("reviews", {}),
        })
        # Aus pending entfernen falls dort
        self.promotions["pending"] = [
            p for p in self.promotions.get("pending", [])
            if p["name"] != tool_name
        ]
        self._save()

        # Telegram-Benachrichtigung
        msg = (
            f"TOOL PROMOTED: '{tool_name}' ist jetzt Teil von {target_module}. "
            f"Health {candidate['health_score']}/10, "
            f"{candidate['uses']}x genutzt, "
            f"{candidate['success_rate']:.0%} Erfolg. "
            f"DualReview: bestanden."
        )
        if communication:
            channel = ("telegram" if communication.telegram_active
                       else "outbox")
            communication.send_message(msg, channel=channel)

        logger.info("AUTO-PROMOTE ERFOLGREICH: %s → %s", tool_name, target_module)
        return f"PROMOTED: {tool_name} → {target_module}"

    @staticmethod
    def _build_integration_block(
        tool_name: str, tool_code: str, description: str,
    ) -> str:
        """Baut einen integrierbaren Code-Block aus einem Tool.

        - Imports werden entfernt (Ziel-Modul hat eigene)
        - run() wird zu promoted_{name}() umbenannt
        - Header mit Herkunft und Datum
        """
        safe_name = tool_name.replace("-", "_").replace(" ", "_")

        # Imports und Code-Body trennen
        code_lines = []
        for line in tool_code.split("\n"):
            stripped = line.strip()
            # Import-Zeilen am Datei-Anfang ueberspringen
            if stripped.startswith(("import ", "from ")) and not code_lines:
                continue
            # Leere Zeilen zwischen Imports ueberspringen
            if not stripped and not code_lines:
                continue
            code_lines.append(line)

        # run() → promoted_{safe_name}() umbenennen
        body = "\n".join(code_lines)
        body = body.replace("def run(", f"def promoted_{safe_name}(")

        header = (
            f"\n# === Auto-Promoted: {tool_name} ===\n"
            f"# Ursprung: data/tools/{tool_name}.py\n"
            f"# Promotion: {datetime.now(timezone.utc).isoformat()[:10]}\n"
        )
        return header + body
