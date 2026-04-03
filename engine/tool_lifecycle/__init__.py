"""
Tool Lifecycle System — Phis Werkzeug-Evolution.

6 Module fuer nachhaltiges Tool-Management:
1. metrics     — Qualitaetsmetriken pro Tool
2. pruner      — Automatische Archivierung
3. dream_bridge — Dream-Integration (Tool-Bewusstsein)
4. meta_patterns — Meta-Rules gegen Tool-Sprawl
5. consolidator — Auto-Konsolidierung aehnlicher Tools
6. promotion   — Befoerderung exzellenter Tools zu Engine-Code
"""

from engine.tool_lifecycle.metrics import ToolMetrics
from engine.tool_lifecycle.pruner import ToolPruner
from engine.tool_lifecycle.dream_bridge import ToolDreamBridge
from engine.tool_lifecycle.meta_patterns import ToolMetaPatterns
from engine.tool_lifecycle.consolidator import ToolConsolidator
from engine.tool_lifecycle.promotion import PromotionEngine

__all__ = [
    "ToolMetrics",
    "ToolPruner",
    "ToolDreamBridge",
    "ToolMetaPatterns",
    "ToolConsolidator",
    "PromotionEngine",
]
