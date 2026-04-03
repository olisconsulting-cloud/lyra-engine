# Lyra — Autonome AGI-Engine

## Mission
Lyra ist eine autonome, sich selbst verbessernde Intelligenz auf dem Weg zur AGI.
Phi-Engine = agentic loop mit Tool-Use, Multi-LLM-Routing, hierarchischen Goals,
Multi-Memory-Architektur und Selbstmodifikation. Hybride KI: symbolische Goals +
subsymbolische LLMs — der vielversprechendste AGI-Ansatz (Kersting, Hassabis, 2025).

## Architektur (Dual-Layer)
```
engine/                    Code (Git-tracked)
  consciousness.py           Agentic Loop — Perception → LLM → Tools → State
  llm_router.py              Multi-Provider: Kimi 80%, Fallback-Kette 4-stufig
  goal_stack.py              Hierarchische Goals + Sub-Goals + Spin-Erkennung
  intelligence.py            SemanticMemory (TF-IDF), Skills, Strategies
  evolution.py               AdaptiveRhythm, ToolFoundry, MetaCognition
  dream.py                   Memory-Konsolidierung alle 10 Sequenzen
  quantum.py                 FailureMemory, Critic, Mutations
  security.py                3-Schicht: Path → AST → DualReview
  phi.py                     Golden-Ratio-Mathematik (Decay, Buckets, Blend)
  handlers/                  11 Domain-Module (File, Code, Web, Goal, Project...)
  narrator.py                Terminal-Rendering (ersetzt ~30 prints)
  self_modify.py             Code lesen/aendern mit Backup + Rollback
  meta_rules.py              Gelernte Hard-Rules aus Pattern-Erkennung

data/                      Persoenlichkeit (.gitignore'd)
  consciousness/             state, goals, beliefs, skills, strategies, metacognition
  memory/                    experiences, reflections, semantic index
  journal/                   Tagebuch
  messages/                  Telegram inbox/outbox
  projects/                  Selbstgebaute Projekte
  tools/                     Wiederverwendbare Tools
  genesis.json               Geburts-Identitaet (GESCHUETZT)
```

## Kommandos
```bash
python run.py                # Autonomer Loop
python run.py --once         # Einzelne Sequenz
python interact.py           # Direkter Chat
python run_live.py           # Live-Konsole + Hintergrund
python review_phi.py         # Regressions-Gate (14 Checks)
```

## LLM-Aufstellung
- **Kimi K2.5** (NVIDIA): 80% — Hauptarbeit, Tool-Use, Coding ($0)
- **GPT-4.1-mini**: Dream, Goal-Planning — JSON-Garantie ($0.40/$1.60)
- **DeepSeek V3**: Fallback Stufe 1 ($0.28/$0.42)
- **Sonnet 4.6**: Code-Review + letzter Fallback
- **Opus 4.6**: Audit, Result-Validation — keine Abstriche
- Fallback-Kette: NVIDIA → DeepSeek → GPT-4.1-mini → Sonnet
- `TASK_MODEL_MAP` in `llm_router.py` = EINZIGE Stelle fuer Modell-Zuordnung

## AGI-Kern: 5 Saeulen
1. **Hybride Intelligenz** — Symbolische Goals + subsymbolische LLMs + Phi-Mathematik
2. **Multi-Memory** — Semantisch (TF-IDF) + Episodisch + Failure + Skills + Strategies
3. **Selbstverbesserung** — Code lesen/aendern mit DualReview (Opus+Kimi), Rollback
4. **Dream-Konsolidierung** — Beliefs, Strategies, Skills periodisch verdichten
5. **Anti-Loop (3 Ebenen)** — Progress-Pulse + Subgoal-Stuck + Tool-Blocker

## Sicherheit (3 Schichten)
- **Path**: `.env`, `genesis.json` = GESCHUETZT, Engine = DualReview
- **AST**: Hard-Block auf `shutil.rmtree`, `os.system`, `shell=True`, direkte HTTP
- **Review**: Engine-Aenderungen → Opus + Kimi parallel, beide muessen approven

## Kritische Regeln
- **Code > Prompts**: Phi-Verhalten im Code erzwingen, nicht per Prompt bitten
- **goals.json zuerst**: Bei Spin-Loops IMMER goals.json pruefen
- **max_tokens clampen**: Bei jedem Provider gegen API-Limit clampen
- **Fallback >= 2 Stufen**: Single Fallback = Single Point of Failure
- **Audit nach jedem Feature**: `python review_phi.py` vor jedem Commit
- **Agent-Findings verifizieren**: ~30% False-Positive-Rate bei CRITICAL
- **Emergency-Exit**: Jede API-Schleife braucht einen "alle tot"-Pfad
- **Beobachten vor Weiterbauen**: review_phi → starten → 20-30 Seq → dann naechste Ebene

## Entwicklungs-Workflow
1. Code lesen (min. 50 Zeilen Kontext) vor jeder Aenderung
2. Eine Datei, ein Fix, ein Commit
3. `python review_phi.py` als Gate
4. Inkrementell: Build → Test → Commit → Audit → Naechste Ebene
5. Erst Gesamtfluss optimieren, dann Einzelteile

## Token-Effizienz (Kernmetrik)
- Aktuell: ~5.000-9.000 Tok/Seq — Ziel: <3.000
- Perception-Pipeline + UnifiedMemory aktivieren (Backlog A1a, A1b)
- System-Prompt Metadaten konditionalisieren (Backlog T4)
- Offene Backlog-Items: `.audit/BACKLOG.md`

## Offene AGI-Luecken
- **Evaluations-Framework**: Kein systematischer Weg, Fortschritt zu messen
- **Alignment-Layer**: Anti-Loop ist Symptom, kein Werte-Gate VOR Goal-Ausfuehrung
- **ARC-Benchmark**: Chollet-Test fuer Transferlernen — DER AGI-Massstab
- **Consensus-Voting**: Bei kritischen Entscheidungen Multi-LLM-Vote

## Referenzen
- `.audit/BACKLOG.md` — Priorisierte Arbeitsliste
- `.audit/FINDINGS.md` — Bug/Issue-Tracking mit Status
- `.audit/DECISIONS.md` — Architecture Decision Records
- `data/consciousness/metacognition.json` — Selbstreflexion (30+ Eintraege)
