# Tool-Lifecycle Refactoring Plan

## Ziel
ToolCurator + ToolFoundry aus evolution.py hierher extrahieren.
evolution.py wird von 1413 auf ~700 Zeilen entlastet.

## Status: GEPLANT (naechste dedizierte Session)

## Aktueller Zustand
```
engine/tool_lifecycle/           ← 6 Module existieren schon
├── metrics.py                   ToolMetrics (Qualitaetsmetriken)
├── pruner.py                    ToolPruner (Auto-Archivierung)
├── dream_bridge.py              ToolDreamBridge (Dream-Integration)
├── meta_patterns.py             ToolMetaPatterns (Anti-Sprawl-Rules)
├── consolidator.py              ToolConsolidator (Auto-Merge) — IMPORTIERT ToolCurator
├── promotion.py                 PromotionEngine (Tool → Engine-Code)
└── __init__.py                  Exportiert alle 6
```

## Nach Refactoring
```
engine/tool_lifecycle/
├── curator.py                   ← NEU: aus evolution.py extrahiert
│   └── ToolCurator              challenge(), evaluate(), evolve_merge()
├── foundry.py                   ← NEU: aus evolution.py extrahiert
│   └── ToolFoundry              generate_tool(), combine_tools()
├── metrics.py                   (unveraendert)
├── pruner.py                    (unveraendert)
├── dream_bridge.py              (unveraendert)
├── meta_patterns.py             (unveraendert)
├── consolidator.py              Import aendern: from .curator import ToolCurator
├── promotion.py                 (unveraendert)
└── __init__.py                  + ToolCurator, ToolFoundry
```

## Import-Aenderungen noetig in:
- engine/consciousness.py (Zeile 41: from .evolution import → from .tool_lifecycle import)
- engine/handlers/tool_handlers.py (indirekt via context.py)
- engine/tool_lifecycle/consolidator.py (Zeile 14: TYPE_CHECKING import)
- engine/evolution.py (entfernt ToolCurator + ToolFoundry Klassen)

## Risiken
- Viele Import-Pfade aendern sich → gruendlich testen
- Phi laeuft ggf. parallel → Phi vorher stoppen
- consolidator.py referenziert ToolCurator schon → Zyklen vermeiden

## Voraussetzungen
- Phi gestoppt
- Aktueller Stand committet
- review_phi.py muss PASS nach Refactoring
