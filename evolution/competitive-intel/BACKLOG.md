# Competitive Intelligence — Backlog

> Sortiert nach Phase. Innerhalb der Phase nach Hebel.

## Phase 1: Quick Wins

### CI-1: Memory-Backend (SQLite + Vektor + FTS)
- [ ] Baseline messen: Recall@5 + Latenz mit aktuellem TF-IDF
- [ ] SQLite + FTS5 Prototype (ohne Vektor, nur Volltext)
- [ ] Chunking-Strategie (400 Tokens, 80 Overlap) implementieren
- [ ] Hybrid-Ranking: FTS5-Score + Temporal Decay
- [ ] Vektor-Embeddings evaluieren (lokales Modell vs. API-Kosten)
- [ ] Integration mit Unified-Memory abstimmen
- [ ] Recall@5 + Latenz nachher messen, Vergleich dokumentieren

### CI-2: Session-Compaction
- [ ] Token-Verbrauch Baseline messen (50 Sequenzen Durchschnitt)
- [ ] Phase 1: Tool-Result-Pruning (nur Zusammenfassung behalten)
- [ ] Phase 2: Themen-Grenzen erkennen (einfache Heuristik)
- [ ] Phase 3: Aeltere Abschnitte zusammenfassen (LLM-Call)
- [ ] Phase 4: Reassembly mit Kontext-Integritaet
- [ ] Token-Verbrauch nachher messen, Qualitaet pruefen

## Phase 2: Robustheit

### CI-3: Cooldown-Tracking + Provider-Probing
- [ ] Aktuelle Failure-Rate pro Provider messen (1 Woche Logs)
- [ ] ProviderHealth-Klasse: Status (healthy/cooldown/dead) + Timer
- [ ] Probe-Mechanismus: Mini-Request vor voller Last
- [ ] Integration in llm_router.py Fallback-Kette
- [ ] Failure-Rate nachher messen

### CI-4: Smart Dangerous-Command-Approval
- [ ] Aktuelle AST-Block-Liste dokumentieren + False-Positive-Rate
- [ ] Gefahren-Score (0-10) via LLM-Bewertung implementieren
- [ ] Schwellenwert-Kalibrierung (auto-approve < 3, block > 7, review 3-7)
- [ ] Integration in security.py zwischen AST und DualReview
- [ ] False-Positive-Rate nachher messen

## Phase 3: Frontier

### CI-5: Skill-Security-Scanner
- [ ] ToolFoundry-Output analysieren: Was fuer Code wird generiert?
- [ ] Scanner-Regeln definieren (Pfade, Netzwerk, Execution, Leaks)
- [ ] Scanner implementieren in tool_lifecycle/
- [ ] Integration nach jeder Tool-Erstellung (ToolFoundry-Hook)
- [ ] Test: absichtlich unsicheren Tool-Code generieren, Scanner muss fangen

### CI-6: Trajectory-Learning
- [ ] Trajectory-Format definieren (State → Action → Reward Schema)
- [ ] Logging-Modul: Jede Sequenz als Trajectory speichern
- [ ] Analyse-Tool: Erfolgreiche vs. gescheiterte Trajectories clustern
- [ ] Pattern-Extraktion: "Bei Goal-Typ X → Tool Z optimal"
- [ ] Langfristig: Fine-Tuning-Pipeline evaluieren (Kosten, Modell, Daten-Menge)
