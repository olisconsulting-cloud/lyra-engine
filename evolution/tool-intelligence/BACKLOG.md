# Tool Intelligence — Backlog

## Phase 1: Kontextbewusstsein

- [ ] **TI-1a**: Goal-Context in metrics.record_use() durchreichen
  - Toolchain-Callback um goal_context erweitern
  - consciousness.py: aktuellen Goal-Titel beim Tool-Call mitleiefern
  - metrics.json: goal_contexts als Set pro Tool speichern

- [ ] **TI-1b**: Failure-Pattern-Clustering
  - Aehnliche Fehlergruende gruppieren (Jaccard auf Woertern)
  - Top-3 Failure-Cluster pro Tool in Dream-Bridge anzeigen
  - Erkennung: "80% der Failures sind Timeout-Fehler"

- [ ] **TI-1c**: Dream-Bridge um Goal-Kontext erweitern
  - Anzeigen: "Tool X half bei Goal-Typen: recherche, api_integration, tool_building"
  - Anzeigen: "Tool Y scheitert hauptsaechlich bei: file_management"

## Phase 2: Adaptive Intelligenz

- [ ] **TI-2a**: Health-Score Minimum-Gate
  - success_rate < 0.3 → Health max 3.0 (egal wie recent/viel genutzt)
  - success_rate < 0.1 → Health max 1.0 (praktisch tot)

- [ ] **TI-2b**: Stability als Sliding Window (statt historisch)
  - Letzte 10 Calls tracken (Ring-Buffer)
  - Stability = Success-Rate der letzten 10, nicht aller Zeiten

- [ ] **TI-2c**: Kategorie-spezifische Schwellenwerte
  - Tool-Kategorien aus Namen/Beschreibung ableiten
  - API-Tools: hoehere Fehlertoleranz (externe Abhaengigkeiten)
  - File-Tools: niedrigere Fehlertoleranz (sollten immer funktionieren)

## Phase 3: Wissenstransfer

- [ ] **TI-3a**: Konsolidierungs-Metriken-Transfer
  - Bei Merge: Health = gewichteter Avg der Quell-Tools
  - Uses/Successes/Failures summieren
  - goal_contexts vereinigen

- [ ] **TI-3b**: Promotion-Feedback an ToolFoundry
  - Promoted-Tool-Patterns extrahieren (Code-Laenge, Imports, Error-Handling-Stil)
  - ToolFoundry-Prompt um "Lerne von erfolgreichen Tools" erweitern

- [ ] **TI-3c**: Promotion-Bericht fuer Dream
  - "Tool X promoted weil: 95% Erfolg bei 50 Calls ueber 3 Wochen"
  - In Dream-Context aufnehmen fuer Belief-Bildung
