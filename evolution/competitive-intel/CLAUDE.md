# Competitive Intelligence — Best Practices aus Open-Source-AGI-Systemen

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Die besten Ideen aus Hermes Agent und OpenClaw extrahieren und in Phis Architektur
integrieren — nicht als Kopie, sondern als Upgrade fuer Phis AGI-Kern.
Jede Integration muss Phis bestehende Staerken VERSTAERKEN, nicht verwassern.

## Herkunft
Audit vom 2026-04-04: Vergleich Hermes Agent (NousResearch) + OpenClaw (347k Stars)
mit Lyra/Phi. Ergebnis: Phi ist architektonisch weiter Richtung AGI (Autonomie,
Goal-Stack, Selbstmodifikation, Multi-Memory, Dream). Aber 6 Engineering-Upgrades
identifiziert, die Phis Kern staerken.

## Phis Vorteile (NICHT aufgeben)
- Autonomer Loop mit eigenem Goal-Stack (beide Konkurrenten: reaktiv)
- Selbstmodifikation mit DualReview + Rollback (beide: keine)
- Task-basiertes Multi-LLM-Routing via TASK_MODEL_MAP (beide: ein Modell/Session)
- Multi-Memory mit Dream-Konsolidierung (beide: nur Retrieval)
- Meta-Kognition + Phi-Mathematik (beide: keine)

## Die 6 Integrations-Kandidaten

| Rang | Kandidat | Quelle | Ziel-Saeule | Schwierigkeit |
|------|----------|--------|-------------|---------------|
| 1 | **CI-3: Cooldown-Tracking + Provider-Probing** | OpenClaw | LLM-Router | MEDIUM |
| 2 | **CI-4: Smart Dangerous-Command-Approval** | Hermes | Sicherheit | EASY |
| 3 | **CI-2: Session-Compaction** (4-Phasen-Kompression) | OpenClaw | Token-Effizienz | MEDIUM |
| 4 | **CI-1: Memory-Backend: SQLite + Vektor + FTS** | OpenClaw | Multi-Memory | HARD |
| 5 | **CI-5: Skill-Security-Scanner** fuer ToolFoundry | OpenClaw | Sicherheit | MEDIUM |
| 6 | **CI-6: Trajectory-Learning (RL-Pipeline)** | Hermes | Selbstverbesserung | HARD |

## Detailbeschreibung

### CI-1: Memory-Backend Upgrade (SQLite + Vektor + FTS)
**Problem:** Phis TF-IDF-Suche ist O(n) und skaliert schlecht bei wachsender Memory.
**Loesung:** SQLite mit FTS5 (Volltext) + Vektor-Embeddings (Cosine-Similarity) +
Hybrid-Ranking. OpenClaws Implementierung: Chunking (400 Tokens, 80 Overlap),
Temporal Decay, MMR-Diversifizierung (Maximum Marginal Relevance).
**Integration:** Unified-Memory-Projekt als Basis. TF-IDF durch SQLite+FTS5 ersetzen.
Vektor-Embeddings optional (lokales Modell oder API).
**Metrik:** Recall@5 vorher/nachher, Latenz vorher/nachher.
**Abhaengigkeit:** Synergie mit `evolution/unified-memory/`.

### CI-2: Session-Compaction (Token-Effizienz)
**Problem:** Phi verbraucht 5.000-9.000 Tok/Seq, Ziel <3.000.
**Loesung:** 4-Phasen-Algorithmus aus OpenClaw:
1. Tool-Results prunen (nur Zusammenfassung behalten)
2. Konversations-Grenzen erkennen (Themen-Wechsel)
3. Aeltere Abschnitte strukturiert zusammenfassen
4. Komprimierten Kontext reassemblieren
**Integration:** Neues Modul `engine/compaction.py` oder in Perception-Pipeline.
**Metrik:** Tokens/Sequenz vorher/nachher bei gleichem Output-Qualitaet.
**Abhaengigkeit:** Synergie mit `evolution/perception/`.

### CI-3: Cooldown-Tracking + Provider-Probing
**Problem:** NVIDIA-API-Instabilitaet fuehrt zu blinden Retries und verschwendeten Tokens.
**Loesung:** OpenClaws Ansatz: Provider-Status tracken (healthy/cooldown/dead),
automatische Cooldown-Perioden nach Failures, Probing mit kleinen Requests
bevor volle Last. Auth-Profile-Rotation bei Rate-Limits.
**Integration:** `engine/llm_router.py` erweitern. ProviderHealth-Klasse mit
Cooldown-Timer, Success-Rate-Tracking, automatischem Failover.
**Metrik:** Fehlgeschlagene API-Calls/Stunde vorher/nachher.

### CI-4: Smart Dangerous-Command-Approval
**Problem:** Phis AST-Blocking ist binaer (erlaubt/blockiert). Kein Graubereich.
**Loesung:** Hermes' Smart-Mode: LLM bewertet Befehle auf Gefaehrlichkeit (0-10).
Unterhalb Schwelle: auto-approve. Oberhalb: blockieren oder Review anfordern.
Regex-Patterns fuer bekannte Gefahren + LLM-Fallback fuer unbekannte.
**Integration:** `engine/security.py` erweitern. Neue Schicht zwischen AST und DualReview.
**Metrik:** False-Positive-Rate (sichere Befehle blockiert) vorher/nachher.

### CI-5: Skill-Security-Scanner fuer ToolFoundry
**Problem:** ToolFoundry erzeugt Tools zur Laufzeit — kein Security-Check danach.
**Loesung:** Automatischer Scanner der generierten Tool-Code prueft auf:
Prompt-Injection-Vektoren, File-System-Zugriff ausserhalb erlaubter Pfade,
Netzwerk-Calls, Code-Execution-Patterns, sensitive Daten-Leaks.
**Integration:** `engine/tool_lifecycle/` erweitern. Scanner nach jeder Tool-Erstellung.
**Metrik:** Anzahl unsicherer Tools die den Scanner passieren (Ziel: 0).
**Abhaengigkeit:** Synergie mit `evolution/tool-intelligence/`.

### CI-6: Trajectory-Learning (RL-Pipeline)
**Problem:** Phi erzeugt hunderte Sequenzen mit Entscheidungen und Outcomes —
dieses Wissen geht verloren (nur implizit in Memory/Skills).
**Loesung:** Hermes' Tinker-Atropos-Ansatz adaptiert:
1. Jede Sequenz als Trajectory loggen (State → Action → Reward)
2. Erfolgreiche Trajectories vs. Failures clustern
3. Muster extrahieren: "Bei Goal-Typ X mit Kontext Y ist Tool Z optimal"
4. Langfristig: Fine-Tuning eines lokalen Modells auf Phis eigene Trajectories
**Integration:** Neues Modul. Logging in Phase 1, Analyse in Phase 2, Training in Phase 3.
**Metrik:** Goal-Success-Rate vorher/nachher.
**Abhaengigkeit:** Braucht funktionierendes Goal-System + Memory.

## Phasen

### Phase 1: Stabilitaet + Quick Wins (CI-3, CI-4)
Provider-Stabilisierung und Security-Upgrade — sofortiger ROI, niedriges Risiko.
CI-3 behebt NVIDIA-Instabilitaet (groesster Flaschenhals). CI-4 ist ~120 Zeilen.

### Phase 2: Effizienz (CI-2, CI-1)
Token-Kompression und Memory-Backend — direkte, messbare Verbesserungen.
CI-2 auf Kern-KPI (Tok/Seq). CI-1 zusammen mit Unified-Memory-Projekt.

### Phase 3: Frontier (CI-5, CI-6)
Security-Scanner fuer generierte Tools und Trajectory-Learning —
das sind die AGI-relevanten Upgrades. Setzen Phase 1+2 voraus.

## Prinzipien
1. **Adaptieren, nicht kopieren** — Phis Architektur fuehrt, externe Ideen ergaenzen
2. **Messen vor und nach** — Jede Integration mit Baseline + Vergleich
3. **Bestehende Module erweitern** — Kein Parallel-System, Integration in Engine
4. **Ein Kandidat, ein Commit** — Nicht buendeln
5. **Phi-Vorteile schuetzen** — Keine Integration darf Autonomie/Goals/Memory schwaechen

## Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).

```
1.  BACKLOG.md lesen                    — Welcher Kandidat ist dran?
2.  Quell-Repo studieren                — Originalcode verstehen
3.  Phis Ziel-Code lesen                — Wo integriert das?
4.  Design-Entscheidung dokumentieren   — In DECISIONS.md
5.  EINE Aenderung machen               — Minimal, testbar
6.  python review_phi.py                — Gate
7.  Committen + Beobachten (20-30 Seq)
8.  Ergebnisse in observations/ loggen
```

## Referenzen
- **Hermes Agent:** https://github.com/nousresearch/hermes-agent
- **OpenClaw:** https://github.com/openclaw/openclaw
- `engine/llm_router.py` — Ziel fuer CI-3
- `engine/security.py` — Ziel fuer CI-4, CI-5
- `engine/intelligence.py` — Ziel fuer CI-1 (SemanticMemory)
- `engine/tool_lifecycle/` — Ziel fuer CI-5
- `evolution/unified-memory/` — Synergie mit CI-1
- `evolution/perception/` — Synergie mit CI-2
- `evolution/tool-intelligence/` — Synergie mit CI-5
