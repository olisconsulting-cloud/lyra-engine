# Lyra — Autonomer Compound-AI-Agent

## Mission
Lyra ist ein autonomer Compound-AI-Agent auf dem Weg zur AGI.
Phi-Engine = agentic loop mit Tool-Use, Multi-LLM-Routing, hierarchischen Goals,
Multi-Memory-Architektur und Selbstmodifikation.
Doppelter Wert: Praktisches Werkzeug (heute) + Self-Improving Intelligence (Nordstern).
Jeder Entwicklungsschritt wird gemessen an: Bringt dieser Schritt Phi einen messbaren
Grad naeher an autonome, generalisierte, sich selbst verbessernde Intelligenz?

## Architektur

```
engine/                        Code (Git-tracked)
  CORE LOOP
    consciousness.py (3.7k)      Agentic Loop — Perceive → Plan → Execute → Reflect
    sequence_intelligence.py     Native Tool-Use, Stuck-Detection, Sequenz-Metriken
    sequence_runner.py           Sequenz-Ausfuehrung + Tool-Handling
    sequence_planner.py          Plan-Generierung fuer Sequenzen
    perception_pipeline.py       Multi-Channel Perception (19 Channels, 8k Budget)
    perception.py                Raw-Input-Verarbeitung
    evaluation.py                Score 0-100, Checkpoints, Alerts
    actions.py                   Action-Engine + Action-Management

  INTELLIGENCE
    llm_router.py (1.3k)         Multi-Provider: DeepSeek V3.2 Primary, 4-Stufen-Fallback
    llm_ops.py                   LLM-Utility-Funktionen
    intelligence.py (1k)         SemanticMemory (TF-IDF), Skills, Strategies, Efficiency
    unified_memory.py            Cross-Domain Memory-Abstraktion (Semantic+Episodic+Failure)
    memory_manager.py            Memory-Verwaltung + Persistenz
    episodic_bridge.py           Episodisches Gedaechtnis zwischen Sequenzen
    dream.py                     Memory-Konsolidierung alle 10 Sequenzen
    message_compression.py       Kontext-Kompression fuer lange Konversationen

  ADAPTATION
    evolution.py (1.5k)          AdaptiveRhythm, ToolFoundry, ToolCurator, MetaCognition
    quantum.py                   FailureMemory, Critic, PromptMutator, SkillComposer
    meta_rules.py                Gelernte Hard-Rules aus Pattern-Erkennung
    actuator.py                  BehaviorActuator — Prediction-Error-Loop (Friston)
    competence.py                CompetenceMatrix + SelfAudit (4-Ringe-System)
    skill_library.py             Skill-Verwaltung + Kategorisierung
    skill_enricher.py            Skill-Anreicherung
    proactive_learner.py         Proaktives Lernen aus Web + Cache

  GOVERNANCE
    policy.py                    Policy-Engine + DecisionGate — Lernen → Verhaltensaenderung
    security.py                  3-Schicht: Path → AST → DualReview
    code_review.py               CodeReviewer + DualReviewSystem (Opus+Gemma)
    self_diagnosis.py            Selbst-Diagnose + Fehleranalyse
    quality_checks.py            Markdown- und Output-Qualitaet
    phi.py                       Golden-Ratio-Mathematik (Decay, Buckets, Blend)

  INFRASTRUCTURE
    config.py                    Zentrale Pfade, Konstanten, safe_json_read/write
    event_bus.py                 Event-System fuer lose Kopplung
    toolchain.py                 Tool-Verwaltung + Ausfuehrung
    tool_registry.py             Tool-Registrierung + Lookup
    narrator.py                  Terminal-Rendering (ersetzt ~30 prints)
    telemetry.py                 JSON-Lines Logging (8 Event-Typen)
    checkpoint.py                State-Checkpointing
    reporting.py                 Narrative Reports
    extensions.py                PipManager, GitManager, TaskQueue, SelfRating, FileWatcher
    ior.py                       Input/Output/Result-Tracking (IOR-Metrik)
    handlers/ (11 Module)        30 Tools: File, Code, Web, Goal, Project, Memory, Tool, System, Seq
    tool_lifecycle/ (6 Module)   Metrics, Pruner, DreamBridge, MetaPatterns, Consolidator, Promotion

  BRIDGES
    telegram_bridge.py           Telegram I/O
    web_access.py                Web-Zugriff
    self_modify.py               Code lesen/aendern mit Backup + Rollback
    communication.py             Multi-Channel-Kommunikation

data/                          Persoenlichkeit (.gitignore'd)
  consciousness/                 state, goals, beliefs, skills, strategies, metacognition
  memory/                        experiences, reflections, semantic index
  journal/                       Tagebuch
  messages/                      Telegram inbox/outbox
  projects/                      Selbstgebaute Projekte
  tools/                         Wiederverwendbare Tools
  genesis.json                   Geburts-Identitaet (GESCHUETZT)
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

- **DeepSeek V3.2**: 80% — Primary, Coding, Tool-Use ($0.14/$0.28, Cache $0.028)
- **Kimi K2.5** (NVIDIA): Fallback Stufe 1 — bewaehrt ($0, Credit-basiert)
- **GPT-4.1-mini**: Fallback Stufe 2 + Dream — JSON-Garantie ($0.40/$1.60)
- **Sonnet 4.6**: Letzter Fallback — nativer Tool-Use
- **Opus 4.6**: Audit, Result-Validation — keine Abstriche
- Fallback-Kette: Kimi → GPT-4.1-mini → Sonnet
- `TASK_MODEL_MAP` in `llm_router.py` = EINZIGE Stelle fuer Modell-Zuordnung

## Sicherheit (3 Schichten)

- **Path**: `.env`, `genesis.json` = GESCHUETZT, Engine = DualReview
- **AST**: Hard-Block auf `shutil.rmtree`, `os.system`, `shell=True`, direkte HTTP
- **Review**: Engine-Aenderungen → Opus + Gemma parallel, beide muessen approven

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

## AGI-Roadmap

> 7 Hebel zum Self-Sustaining Learner. Detail: `.planning/AGI-ROADMAP.md`
> Kern-Erkenntnis: Struktur > Skalierung. Alle Teile existieren — der Hebel ist der Loop.
> Kipppunkt: Nach Hebel 1-3 traegt sich der Self-Improvement-Loop selbst.

## Referenzen

- `.planning/AGI-ROADMAP.md` — 7-Hebel-Roadmap mit Status und Dateipfaden
- `.planning/META.md` — Meta-Prozess-Manifest (Warum + Wie messen)
- `.audit/BACKLOG.md` — Priorisierte Arbeitsliste
- `.audit/FINDINGS.md` — Bug/Issue-Tracking mit Status
- `.audit/DECISIONS.md` — Architecture Decision Records
- `data/consciousness/metacognition.json` — Selbstreflexion (30+ Eintraege)
