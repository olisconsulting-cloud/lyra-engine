"""
Tool-Registry — Zentrale Verwaltung aller Tools.

Ersetzt das verteilte Tool-Management:
- TOOLS-Liste (Definitionen)
- TOOL_TIERS (Tier-Zuordnung)
- REQUIRED_FIELDS (Pflichtfelder)
- select_tools() (Tier-basierte Auswahl)
- _execute_tool_inner() (if-elif-else Dispatch)

Jedes Tool wird einmal registriert mit Schema, Handler, Tier und
Pflichtfeldern. Die Registry liefert API-Schemas (full + compact)
und fuehrt Tools mit Pre/Post-Hooks aus.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from .event_bus import EventBus, Events

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Ergebnis einer Tool-Ausfuehrung."""
    success: bool
    output: str
    tool_name: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """Vollstaendige Definition eines Tools."""
    name: str
    description: str
    input_schema: dict
    handler: Optional[Callable[[dict], str]] = None
    tier: int = 1
    required_fields: list[str] = field(default_factory=list)
    requires_approval: bool = False


class ToolRegistry:
    """
    Zentrale Tool-Verwaltung mit Registration, Schema-Generierung und Dispatch.

    Ersetzt das verteilte Tool-Management in consciousness.py:
    - TOOLS + TOOL_TIERS + REQUIRED_FIELDS → register()
    - select_tools() → get_api_schemas()
    - _execute_tool_inner() → execute()
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._tools: dict[str, ToolDefinition] = {}
        self._event_bus = event_bus
        self._compact_cache: Optional[dict[str, dict]] = None
        self._global_pre_hooks: list[Callable] = []
        self._global_post_hooks: list[Callable] = []

    # === Registration ===

    def register(self, tool_def: ToolDefinition):
        """Registriert ein Tool. Ueberschreibt bei gleichem Namen."""
        self._tools[tool_def.name] = tool_def
        self._compact_cache = None  # Cache invalidieren

    def register_from_api_def(self, api_def: dict, tier: int = 1,
                              required_fields: list[str] = None,
                              requires_approval: bool = False):
        """Registriert ein Tool aus einer bestehenden API-Definition (TOOLS-Liste)."""
        td = ToolDefinition(
            name=api_def["name"],
            description=api_def.get("description", api_def["name"]),
            input_schema=api_def.get("input_schema", {"type": "object", "properties": {}}),
            tier=tier,
            required_fields=required_fields or [],
            requires_approval=requires_approval,
        )
        self.register(td)

    def set_handler(self, name: str, handler: Callable[[dict], str]):
        """Setzt den Handler fuer ein registriertes Tool."""
        if name in self._tools:
            self._tools[name].handler = handler
        else:
            raise KeyError(f"Tool '{name}' nicht registriert")

    def add_global_pre_hook(self, hook: Callable):
        """Pre-Hook der vor JEDEM Tool laeuft. Signatur: (name, input) -> None."""
        self._global_pre_hooks.append(hook)

    def add_global_post_hook(self, hook: Callable):
        """Post-Hook der nach JEDEM Tool laeuft. Signatur: (name, input, result) -> None."""
        self._global_post_hooks.append(hook)

    # === Schema-Generierung ===

    def get_api_schemas(self, active_tiers: set[int], compact: bool = False) -> list:
        """
        Gibt Tool-Definitionen im Anthropic-API-Format zurueck.

        Args:
            active_tiers: Welche Tiers aktiv sind (1-5)
            compact: True = minimale Defs ohne Descriptions (spart ~47% Tokens)
        """
        schemas = []
        for td in self._tools.values():
            if td.tier not in active_tiers:
                continue
            if compact:
                schemas.append(self._to_compact_schema(td))
            else:
                schemas.append(self._to_full_schema(td))
        return schemas

    def _to_full_schema(self, td: ToolDefinition) -> dict:
        """Vollstaendige API-Definition mit Descriptions."""
        return {
            "name": td.name,
            "description": td.description,
            "input_schema": td.input_schema,
        }

    def _to_compact_schema(self, td: ToolDefinition) -> dict:
        """Kompakte API-Definition ohne Property-Descriptions."""
        schema = td.input_schema
        props = schema.get("properties", {})
        minimal_props = {}
        for k, v in props.items():
            entry = {"type": v.get("type", "string")}
            # Arrays brauchen items — Gemini/OpenAI lehnen Schema ohne items ab
            if entry["type"] == "array" and "items" in v:
                entry["items"] = v["items"]
            minimal_props[k] = entry
        compact = {
            "name": td.name,
            "description": td.name.replace("_", " "),
            "input_schema": {"type": "object", "properties": minimal_props},
        }
        req = schema.get("required")
        if req:
            compact["input_schema"]["required"] = req
        return compact

    # === Ausfuehrung ===

    def execute(self, name: str, tool_input: dict) -> ToolResult:
        """
        Fuehrt ein Tool aus: Validation → Pre-Hooks → Handler → Post-Hooks → Event.

        Returns:
            ToolResult mit success-Flag und Output.
        """
        td = self._tools.get(name)
        if not td:
            return ToolResult(
                success=False, output=f"FEHLER: Unbekanntes Tool '{name}'",
                tool_name=name,
            )

        if not td.handler:
            return ToolResult(
                success=False, output=f"FEHLER: Kein Handler fuer Tool '{name}'",
                tool_name=name,
            )

        # Pflichtfeld-Validierung
        missing = [f for f in td.required_fields if f not in tool_input]
        if missing:
            return ToolResult(
                success=False,
                output=f"FEHLER: Pflichtfelder fehlen fuer {name}: {missing}",
                tool_name=name,
            )

        # Pre-Hooks
        for hook in self._global_pre_hooks:
            try:
                hook(name, tool_input)
            except Exception as e:
                logger.warning(f"ToolRegistry: Pre-Hook fehlgeschlagen: {e}")

        # Handler ausfuehren
        try:
            output = td.handler(tool_input)
            success = not output.startswith("FEHLER")
        except Exception as e:
            output = f"FEHLER: {e}"
            success = False
            logger.error(f"ToolRegistry: Handler '{name}' Exception: {e}")

        result = ToolResult(success=success, output=output, tool_name=name)

        # Post-Hooks
        for hook in self._global_post_hooks:
            try:
                hook(name, tool_input, result)
            except Exception as e:
                logger.warning(f"ToolRegistry: Post-Hook fehlgeschlagen: {e}")

        return result

    # === Abfragen ===

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_tier(self, name: str) -> int:
        td = self._tools.get(name)
        return td.tier if td else 0

    def needs_approval(self, name: str) -> bool:
        td = self._tools.get(name)
        return td.requires_approval if td else False

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_required_fields(self, name: str) -> list[str]:
        td = self._tools.get(name)
        return td.required_fields if td else []

    def tool_count(self) -> int:
        return len(self._tools)

    def tier_counts(self) -> dict[int, int]:
        """Anzahl Tools pro Tier."""
        counts: dict[int, int] = {}
        for td in self._tools.values():
            counts[td.tier] = counts.get(td.tier, 0) + 1
        return counts
