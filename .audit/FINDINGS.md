# Phi Audit Findings

> Status: `open` | `in-progress` | `fixed` | `wontfix`
> Severity: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW`
> Alle Findings sind gegen den tatsaechlichen Code verifiziert.

---

## CRITICAL — Crash bei Aufruf

### C1: self.client existiert nicht in ToolFoundry.combine_tools()
- **Status**: `open`
- **Datei**: `engine/evolution.py:371`
- **Problem**: `self.client.messages.create(...)` — aber `ToolFoundry.__init__()` setzt kein `self.client`. Die Methode `generate_tool()` (gleiche Klasse) erstellt den Client korrekt inline je nach Provider.
- **Auswirkung**: `AttributeError` bei jedem Versuch, zwei Tools zu kombinieren.
- **Fix**: Provider-Logik aus `generate_tool()` extrahieren in `_get_client()` und in beiden Methoden nutzen.

---

## HIGH — Signatur-Fehler in inaktiven Modulen

> H1-H4 sind in Modulen die gebaut aber noch nicht aktiviert sind.
> Sie crashen NICHT im aktuellen Betrieb, aber MUESSEN gefixt werden
> bevor die Module aktiviert werden koennen.

### H1: validate_against_outcome() — falsche Argument-Typen
- **Status**: `open`
- **Datei**: `engine/sequence_finisher.py:167`
- **Problem**: Aufruf `strategies.validate_against_outcome(new_beliefs, summary, rating)`.
  Signatur erwartet `(beliefs: list, outcome_positive: bool, context: str)`.
  `summary` (str) wird als `outcome_positive` (bool) interpretiert — immer True.
  `rating` (int) wird als `context` (str) interpretiert.
- **Fix**: `strategies.validate_against_outcome(new_beliefs, rating >= 6, summary[:200])`

### H2: write_journal() — fehlendes Pflichtargument cycle
- **Status**: `open`
- **Datei**: `engine/sequence_finisher.py:259`
- **Problem**: `comm.write_journal(f"Sequenz {sequences_total}: {summary[:200]}")`.
  Signatur ist `write_journal(content: str, cycle: int)`. `cycle` fehlt.
- **Fix**: `comm.write_journal(f"Sequenz {sequences_total}: {summary[:200]}", sequences_total)`

### H3: record_process_pattern() — fehlendes Pflichtargument description
- **Status**: `open`
- **Datei**: `engine/sequence_finisher.py:241`
- **Problem**: `strategies.record_process_pattern(pattern)`.
  Signatur ist `record_process_pattern(pattern_type: str, description: str, occurrences=1)`.
- **Fix**: `strategies.record_process_pattern(pattern, pattern)`

### H4: SequenceRunner._plan() — 3 falsche Methodensignaturen
- **Status**: `open`
- **Datei**: `engine/sequence_runner.py:151-153`
- **Problem**:
  - `engine.rhythm.get_mode()` — braucht `(state: dict)`
  - `engine._classify_task(ctx.perception)` — braucht `(mode, focus)`
  - `engine._get_step_budget(ctx.task_type)` — braucht `(mode, focus)`
- **Fix**: Signaturen an tatsaechliche API anpassen.

### H5: _load() Methoden ohne try/except bei JSON-Parse
- **Status**: `open`
- **Dateien**: `engine/evolution.py:477` (SelfBenchmark), `engine/evolution.py:837` (MetaCognition)
- **Problem**: Nacktes `json.load()`. Korrupte JSON → Crash beim Konstruktor.
  Hinweis: `LearningEngine._load_log()` (Zeile 709) HAT bereits try/except — als Vorbild nutzen.
- **Fix**: `safe_json_read()` aus config.py verwenden oder try/except wie LearningEngine.

### H6: Kein Retry/Fallback im Step-Loop bei API-Fehler
- **Status**: `open`
- **Datei**: `engine/consciousness.py:2913-2924`
- **Problem**: Bei API-Fehler wird die Sequenz sofort abgebrochen (`break`).
  Kein Retry, kein Fallback auf alternatives Modell.
  `TASK_MODEL_MAP["fallback"]` existiert bereits, wird aber nie automatisch genutzt.
- **Fix**: Max 2 Retries, dann Fallback-Modell, dann erst Sequenz abbrechen.

---

## ARCHITEKTUR — Inaktive Module & doppelte Logik

### A1: 4 Module gebaut aber nicht aktiviert
- **Status**: `open`
- **Module**: SequenceRunner, SequenceFinisher, PerceptionPipeline, UnifiedMemory
- **Detail**: Alle 4 werden in `consciousness.py:651-681` instanziiert.
  Keines wird im aktiven Code-Pfad aufgerufen. `_run_sequence()` und
  `_handle_finish_sequence()` in consciousness.py machen alles selbst.
- **Strategie**: Schrittweise aktivieren (ADR-003). Erst Bugs fixen (H1-H4),
  dann einzeln verdrahten.

### A2: Doppelte Valenz-Berechnung — unterschiedliche Formeln
- **Status**: `open`
- **Dateien**: `engine/consciousness.py` vs `engine/sequence_finisher.py:182`
- **Problem**: consciousness.py nutzt `(rating - 3) / 7.0`.
  sequence_finisher.py nutzt `(rating - 1) / 7 - 0.29` fuer rating<=5,
  `(rating - 5) / 5` fuer rating>5. Unterschiedliche Ergebnisse!
- **Risiko**: Wenn SequenceFinisher aktiviert wird, aendert sich die Valenz-Semantik.

### A3: Doppelte Wasted-Steps-Berechnung — unterschiedliche Logik
- **Status**: `open`
- **Problem**: consciousness.py: `wasted = step_count - output_count`.
  sequence_finisher.py: `wasted = min(errors * 2, steps)`. Komplett andere Logik.

### A4: Dead Code
- **Status**: `open`
- **Datei**: `engine/consciousness.py`
- **Stellen**:
  - `select_tools()` (Zeile ~550-558) — ersetzt durch ToolRegistry
  - `_build_compact_tools()` (Zeile ~525-539) — ersetzt durch ToolRegistry
  - `_get_compact_tools()` (Zeile ~542-547) — ersetzt durch ToolRegistry
  - `_COMPACT_TOOLS_CACHE` (Zeile ~522) — nie genutzt

---

## TOKEN — Verschwendung ~5.000-9.000 Tokens/Sequenz

### T1: PerceptionPipeline nicht aktiv — groesster Hebel
- **Status**: `open`
- **Datei**: `engine/consciousness.py:659` + `engine/perception_pipeline.py`
- **Ersparnis**: 1.000-2.000 Tok/Seq
- **Detail**: Pipeline ist gebaut, hat Budget-System (max_tokens=3000),
  Channel-Gewichtung, und Feedback-Learning. Wird aber nicht genutzt.
  `_build_perception()` baut Perception manuell mit allen Quellen.

### T2: Failure-Check pro Tool-Call — redundant
- **Status**: `open`
- **Datei**: `engine/consciousness.py:2992-3001`
- **Ersparnis**: 2.000-4.000 Tok/Seq
- **Detail**: `failure_memory.check()` wird bei JEDEM Tool-Call ausgefuehrt
  UND bereits in der Perception (Zeile 1327). Pro-Tool-Check ist redundant.
- **Quick-Win**: Pro-Tool-Check entfernen, nur Perception behalten.

### T3: 4 separate Memory-Abfragen statt UnifiedMemory
- **Status**: `open`
- **Datei**: `engine/consciousness.py:1317-1348`
- **Ersparnis**: 400-800 Tok/Seq
- **Detail**: Perception macht 4 einzelne Memory-Queries (experience, semantic,
  failure, composer). UnifiedMemory (Zeile 651-656) koennte das dedupliziert liefern.

### T4: System-Prompt laedt 12 Subsystem-Summaries bei jedem Call
- **Status**: `open`
- **Datei**: `engine/consciousness.py:976-1051` (`_build_system_prompt`)
- **Ersparnis**: 800-1.500 Tok/Seq
- **Detail**: Goals, Tools, Tasks, Rating-Trend, Skills, Strategien, Effizienz,
  Kompetenz, Audit, Review, Benchmark, Foundry — alles bei JEDEM Call geladen.
  Viele aendern sich nur alle 5-15 Sequenzen.

### T5: Dream JSON mit indent=2 statt kompakt
- **Status**: `open`
- **Datei**: `engine/dream.py:148-206`
- **Ersparnis**: 1.000-2.000 Tok (nur bei Dream-Calls, alle ~10 Seq)
- **Quick-Win**: `json.dumps(data, separators=(',', ':'))` statt `indent=2`

### T6: Graceful-Finish auf Sonnet statt guenstigerem Modell
- **Status**: `open`
- **Datei**: `engine/consciousness.py:1957-2058`
- **Detail**: Jede auto-beendete Sequenz macht einen Claude Sonnet Call (~$0.01).
  Mechanischer Fallback erzeugt fast gleiche Qualitaet.
- **Quick-Win**: In TASK_MODEL_MAP `graceful_finish` auf `kimi_k25` routen.

### T7: Static-Prompt Regeln als Prosa statt Stichpunkte
- **Status**: `open`
- **Datei**: `engine/consciousness.py:954-974`
- **Ersparnis**: ~200 Tok * N Steps/Seq
- **Detail**: Regeln (Duplikat, Qualitaet, Loop-Guard, Evidence-Based) als
  ausfuehrliche Saetze statt kompakte Stichpunkte.

---

## STABILITAET

### S1: SemanticMemory Index waechst unbegrenzt
- **Status**: `open`
- **Datei**: `engine/intelligence.py:199`
- **Problem**: `self.index["entries"].append(entry)` ohne Limit.
  `_update_idf()` iteriert ueber ALLE Eintraege bei jedem Store.
- **Fix**: Max 500 Eintraege, Importance-basierte Eviction.

### S2: _file_locks LRU-Eviction ist Insertion-Order
- **Status**: `open`
- **Datei**: `engine/config.py:69-71`
- **Problem**: Bei 200 Locks wird der "aelteste" entfernt, aber nach
  Insertion-Order statt Usage-Order. Haeufig genutzte Locks koennen entfernt werden.
- **Fix**: `move_to_end()` bei Zugriff oder `functools.lru_cache`.

### S3: goal_stack._save() schluckt Fehler
- **Status**: `open`
- **Datei**: `engine/goal_stack.py:31-34`
- **Problem**: Nur `print()` bei Save-Fehler. Goals im RAM != Disk nach Crash.

### S4: Checkpoint speichert keine Message-History
- **Status**: `open`
- **Datei**: `engine/checkpoint.py:30-58`
- **Problem**: Kein Kontext ueber vorherige Tool-Calls bei Resume.

### S5: AdaptiveRhythm liest 3x die gleiche goals.json
- **Status**: `open`
- **Datei**: `engine/evolution.py:175-209`
- **Problem**: `_has_pending_tasks()`, `_has_active_goals()`, `_has_audit_goals()`
  oeffnen jeweils eigene Dateien, obwohl alles in goals.json steht.

---

## FALSE POSITIVES — Agent-Fehler dokumentiert

> Diese wurden von Audit-Agents als CRITICAL gemeldet, sind aber KEINE Bugs.
> Dokumentiert als Referenz fuer zukuenftige Audits (ADR-005).

### FP1: _installed_packages nicht initialisiert
- **Agent-Claim**: `self._installed_packages` wird in `_register_all_tools()` genutzt
  bevor es gesetzt wird.
- **Realitaet**: `load_state()` (Zeile 644) setzt `_installed_packages` (Zeile 848).
  `_register_all_tools()` wird erst in Zeile 648 aufgerufen. Reihenfolge ist korrekt.

### FP2: self.meta_rules / self.checkpointer existieren nicht
- **Agent-Claim**: SequenceFinisher erhaelt `self.meta_rules` das nicht existiert.
- **Realitaet**: Code uebergibt `self.seq_intel` (Zeile 673-674), nicht `self.meta_rules`.
  `self.seq_intel` wird in Zeile 624 initialisiert. Kein Bug.

### FP3: LearningEngine._load_log ohne try/except
- **Agent-Claim**: Kein Exception-Handling beim JSON-Load.
- **Realitaet**: Hat try/except in Zeile 709-713. Agent hat die Datei nicht genau gelesen.
