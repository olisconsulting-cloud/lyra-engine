# Competitive Intelligence — Backlog

> Sortiert nach Hebel (Engine-Audit 2026-04-04). Flywheel: jeder Schritt macht den naechsten wertvoller.

## Phase 1: Stabilitaet + Quick Wins

### CI-3: Cooldown-Tracking + Provider-Probing (RANG 1)

> Ziel: `engine/llm_router.py` — NVIDIA-Instabilitaet ist groesster Flaschenhals

- [ ] Aktuelle Failure-Rate pro Provider messen (1 Woche Logs)
- [ ] ProviderHealth-Klasse: Status (healthy/cooldown/dead) + Timer
- [ ] Exponentieller Backoff statt 2s-Sleep
- [ ] Probe-Mechanismus: Mini-Request vor voller Last nach Cooldown
- [ ] Integration in llm_router.py Fallback-Kette
- [ ] Failure-Rate nachher messen

### CI-4: Smart Dangerous-Command-Approval (RANG 2)

> Ziel: `engine/security.py` — ~120 Zeilen, einfachste Aenderung

- [ ] Aktuelle AST-Block-Liste dokumentieren + False-Positive-Rate
- [ ] Risk-Score (0-10) via Regelwerk implementieren (kein LLM-Call noetig)
- [ ] Approval-History: Welche Blocks wurden schon mal genehmigt?
- [ ] Schwellenwert-Kalibrierung (auto-approve < 3, block > 7, review 3-7)
- [ ] Integration in security.py zwischen AST und DualReview
- [ ] False-Positive-Rate nachher messen

## Phase 2: Effizienz

### CI-2: Session-Compaction (RANG 3)

> Ziel: `engine/consciousness.py` + `engine/message_compression.py` — Kern-KPI Tok/Seq

- [ ] Token-Verbrauch Baseline messen (50 Sequenzen Durchschnitt)
- [ ] Phase 1: Tool-Result-Pruning (nur Zusammenfassung behalten)
- [ ] Phase 2: Themen-Grenzen erkennen (einfache Heuristik)
- [ ] Phase 3: Aeltere Abschnitte zusammenfassen (LLM-Call)
- [ ] Phase 4: Reassembly mit Kontext-Integritaet
- [ ] Token-Verbrauch nachher messen, Qualitaet pruefen

### CI-1: Memory-Backend SQLite + Vektor + FTS (RANG 4)

> Ziel: `engine/intelligence.py` — zusammen mit Unified-Memory-Projekt

- [ ] Baseline messen: Recall@5 + Latenz mit aktuellem TF-IDF
- [ ] SQLite + FTS5 Prototype (ohne Vektor, nur Volltext)
- [ ] Chunking-Strategie (400 Tokens, 80 Overlap) implementieren
- [ ] Hybrid-Ranking: FTS5-Score + Temporal Decay
- [ ] Vektor-Embeddings evaluieren (lokales Modell vs. API-Kosten)
- [ ] Integration mit Unified-Memory abstimmen
- [ ] Recall@5 + Latenz nachher messen, Vergleich dokumentieren

## Phase 3: Frontier

### CI-5: Skill-Security-Scanner (RANG 5)

> Ziel: `engine/tool_lifecycle/` — ToolFoundry-Output absichern

- [ ] ToolFoundry-Output analysieren: Was fuer Code wird generiert?
- [ ] Scanner-Regeln definieren (Pfade, Netzwerk, Execution, Leaks)
- [ ] Scanner implementieren in tool_lifecycle/
- [ ] Integration nach jeder Tool-Erstellung (ToolFoundry-Hook)
- [ ] Test: absichtlich unsicheren Tool-Code generieren, Scanner muss fangen

### CI-6: Trajectory-Learning (RANG 6)

> Ziel: Neues Modul — Frontier, braucht funktionierendes Goal-System + Memory

- [ ] Trajectory-Format definieren (State -> Action -> Reward Schema)
- [ ] Logging-Modul: Jede Sequenz als Trajectory speichern
- [ ] Analyse-Tool: Erfolgreiche vs. gescheiterte Trajectories clustern
- [ ] Pattern-Extraktion: "Bei Goal-Typ X -> Tool Z optimal"
- [ ] Langfristig: Fine-Tuning-Pipeline evaluieren (Kosten, Modell, Daten-Menge)
