# Phi Audit Findings

> Status: `open` | `in-progress` | `fixed` | `wontfix`
> Severity: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW`
> Alle Findings gegen tatsaechlichen Code verifiziert.
> Verfallsdatum: Findings aelter als 30 Tage ohne Aktivitaet → re-validieren oder wontfix.
> Fixed/wontfix Findings → nach FINDINGS_ARCHIVE.md verschieben.

---

## CRITICAL — Crash bei Aufruf

### C1: self.client existiert nicht in ToolFoundry.combine_tools()
- **Status**: `fixed` (2026-04-03)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/evolution.py:371`
- **Problem**: `self.client.messages.create(...)` — aber `ToolFoundry.__init__()` setzt kein `self.client`. Die Methode `generate_tool()` (gleiche Klasse) erstellt den Client korrekt inline je nach Provider.
- **Auswirkung**: `AttributeError` bei jedem Versuch, zwei Tools zu kombinieren.
- **Fix**: Provider-Logik aus `generate_tool()` extrahieren in `_get_client()` und in beiden Methoden nutzen.
- **Done**: review_phi.py passed + `combine_tools()` wirft keinen AttributeError mehr.

---

## HIGH — Signatur-Fehler in inaktiven Modulen

> H1-H4 sind in Modulen die gebaut aber noch nicht aktiviert sind.
> Sie crashen NICHT im aktuellen Betrieb, aber MUESSEN gefixt werden
> bevor die Module aktiviert werden koennen.

### H1: validate_against_outcome() — falsche Argument-Typen
- **Status**: `wontfix` (2026-04-03 — sequence_finisher.py geloescht, 7 Logik-Abweichungen)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_finisher.py:167`
- **Problem**: Aufruf `strategies.validate_against_outcome(new_beliefs, summary, rating)`.
  Signatur erwartet `(beliefs: list, outcome_positive: bool, context: str)`.
  `summary` (str) wird als `outcome_positive` (bool) interpretiert — immer True.
  `rating` (int) wird als `context` (str) interpretiert.
- **Fix**: `strategies.validate_against_outcome(new_beliefs, rating >= 6, summary[:200])`
- **Done**: Aufruf matcht Signatur in `intelligence.py:772`.

### H2: write_journal() — fehlendes Pflichtargument cycle
- **Status**: `wontfix` (2026-04-03 — sequence_finisher.py geloescht)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_finisher.py:259`
- **Problem**: `comm.write_journal(f"Sequenz {sequences_total}: {summary[:200]}")`.
  Signatur ist `write_journal(content: str, cycle: int)`. `cycle` fehlt.
- **Fix**: `comm.write_journal(f"Sequenz {sequences_total}: {summary[:200]}", sequences_total)`
- **Done**: Aufruf matcht Signatur in `communication.py:140`.

### H3: record_process_pattern() — fehlendes Pflichtargument description
- **Status**: `wontfix` (2026-04-03 — sequence_finisher.py geloescht)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_finisher.py:241`
- **Problem**: `strategies.record_process_pattern(pattern)`.
  Signatur ist `record_process_pattern(pattern_type: str, description: str, occurrences=1)`.
- **Fix**: `strategies.record_process_pattern(pattern, pattern)`
- **Done**: Aufruf matcht Signatur in `intelligence.py:709`.

### H4: SequenceRunner._plan() — 3 falsche Methodensignaturen
- **Status**: `fixed` (2026-04-03)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_runner.py:151-153`
- **Problem**:
  - `engine.rhythm.get_mode()` — braucht `(state: dict)`
  - `engine._classify_task(ctx.perception)` — braucht `(mode, focus)`
  - `engine._get_step_budget(ctx.task_type)` — braucht `(mode, focus)`
- **Fix**:
  - `engine.rhythm.get_mode(engine.state)`
  - `engine._classify_task(ctx.mode, focus)` (focus aus perception extrahieren)
  - `engine._get_step_budget(ctx.mode, focus)`
- **Done**: Alle 3 Aufrufe matchen tatsaechliche Signaturen + review_phi.py passed.

### H5: _load() Methoden ohne try/except bei JSON-Parse (2 Stellen)
- **Status**: `fixed` (2026-04-03)
- **Erstellt**: 2026-04-03
- **Dateien**: `engine/evolution.py:477` (SelfBenchmark._load), `engine/evolution.py:837` (MetaCognition._load)
- **Problem**: Nacktes `json.load()`. Korrupte JSON → Crash beim Konstruktor.
  Hinweis: `LearningEngine._load_log()` (Zeile 709) HAT bereits try/except — als Vorbild nutzen.
- **Fix**: `safe_json_read()` aus config.py verwenden oder try/except wie LearningEngine.
- **Done**: Beide _load()-Methoden haben try/except + korrupte JSON gibt leere Liste zurueck.

### H6: Kein Retry/Fallback im Step-Loop bei API-Fehler
- **Status**: `fixed`
- **Erstellt**: 2026-04-03
- **Gefixt**: 2026-04-03
- **Datei**: `engine/consciousness.py:2576-2599`
- **Problem**: Bei API-Fehler wurde die Sequenz sofort abgebrochen (`break`).
- **Fix**: Step-Level Retry (3 Versuche mit Backoff: 1s, 2s).
  Nachrichten-Sync-Fehler nicht retrybar (sofort break).
  Fallback-Fehler wird jetzt auf Console geloggt.
- **Ergebnis**: Pro Step 3 Versuche × Provider-Retry (3x) + Fallback (DeepSeek)
  = 18 Chancen bevor ein Step die Sequenz abbricht.

---

## ARCHITEKTUR — Inaktive Module & doppelte Logik

### A1a: PerceptionPipeline gebaut aber nicht aktiviert
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/perception_pipeline.py` + `consciousness.py:~659`
- **Detail**: Instanziiert, hat Budget-System + Channel-Gewichtung + Feedback-Learning.
  `build()` wird nie aufgerufen. `_build_perception()` baut Perception manuell.
  0 Channels registriert. Siehe auch T1 (Token-Ersparnis).
- **Done**: `_build_perception()` delegiert an Pipeline, Channels registriert, Feedback fliesst.

### A1b: UnifiedMemory gebaut aber nicht aktiviert
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/unified_memory.py` + `consciousness.py:~651-656`
- **Detail**: Instanziiert mit 5 Adaptern (semantic, experience, failure, skill, strategy).
  `query()` und `get_context_for()` werden nie aufgerufen. Perception macht 4 einzelne
  Memory-Queries. Siehe auch T3.
- **Done**: Perception nutzt `unified_memory.query()` statt 4 separate Abfragen.

### A1c: SequenceRunner gebaut aber nicht aktiviert
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_runner.py` + `consciousness.py:~662`
- **Detail**: Instanziiert, `run()` nie aufgerufen. `_execute()` und `_reflect()` sind `pass`.
  `_run_sequence()` macht alles selbst. Hat Signatur-Bugs (H4) — erst fixen.
- **Done**: `_run_sequence()` delegiert an SequenceRunner, Step-Loop extrahiert.

### A1d: SequenceFinisher gebaut aber nicht aktiviert
- **Status**: `wontfix` (2026-04-03 — Modul geloescht, 7 Logik-Abweichungen zur echten Impl.)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/sequence_finisher.py` + `consciousness.py:~665-681`
- **Detail**: Instanziiert mit 14 Subsystem-Referenzen, `finish()` nie aufgerufen.
  `_handle_finish_sequence()` macht alles selbst. Hat Signatur-Bugs (H1-H3) — erst fixen.
  Doppelte Valenz-Formel (A2) und Wasted-Steps-Logik (A3) muessen konsolidiert werden.
- **Done**: `_handle_finish_sequence()` delegiert an SequenceFinisher, Formeln einheitlich.

### A2: Doppelte Valenz-Berechnung — unterschiedliche Formeln
- **Status**: `wontfix` (2026-04-03 — sequence_finisher.py geloescht, nur noch eine Formel)
- **Dateien**: `engine/consciousness.py` vs `engine/sequence_finisher.py:182`
- **Problem**: consciousness.py nutzt `(rating - 3) / 7.0`.
  sequence_finisher.py nutzt `(rating - 1) / 7 - 0.29` fuer rating<=5,
  `(rating - 5) / 5` fuer rating>5. Unterschiedliche Ergebnisse!
- **Risiko**: Wenn SequenceFinisher aktiviert wird, aendert sich die Valenz-Semantik.

### A3: Doppelte Wasted-Steps-Berechnung — unterschiedliche Logik
- **Status**: `wontfix` (2026-04-03 — sequence_finisher.py geloescht, nur noch eine Logik)
- **Problem**: consciousness.py: `wasted = step_count - output_count`.
  sequence_finisher.py: `wasted = min(errors * 2, steps)`. Komplett andere Logik.

### A4: Vermeintlicher Dead Code — wird von review_phi.py genutzt
- **Status**: `wontfix` (2026-04-03 — review_phi.py importiert select_tools + _get_compact_tools)
- **Datei**: `engine/consciousness.py`
- **Erkenntnis**: select_tools(), _build_compact_tools(), _get_compact_tools() werden
  von review_phi.py fuer Token-Zaehlungen und Tool-Integritaetschecks verwendet.
  KEIN Dead Code — nur im Engine-Runtime nicht mehr genutzt (ToolRegistry hat uebernommen).

---

## TOKEN — Verschwendung ~5.000-9.000 Tokens/Sequenz

### T1: PerceptionPipeline nicht aktiv — groesster Hebel
- **Status**: `open`
- **Datei**: `engine/consciousness.py:659` + `engine/perception_pipeline.py`
- **Ersparnis**: 1.000-2.000 Tok/Seq
- **Detail**: Pipeline ist gebaut, hat Budget-System (max_tokens=3000),
  Channel-Gewichtung, und Feedback-Learning. Wird aber nicht genutzt.
  `_build_perception()` baut Perception manuell mit allen Quellen.

### T2: Failure-Check pro Tool-Call — redundant (Quick-Win)
- **Status**: `fixed` (2026-04-03)
- **Erstellt**: 2026-04-03
- **Datei**: `engine/consciousness.py:~3071-3080` (pro-Tool-Check), `~1362` (Perception-Check)
- **Ersparnis**: 2.000-4.000 Tok/Seq
- **Detail**: `failure_memory.check()` wird bei JEDEM Tool-Call ausgefuehrt
  UND bereits in der Perception. Pro-Tool-Check ist redundant.
- **Quick-Win**: Pro-Tool-Check entfernen, nur Perception behalten.
- **Done**: Nur noch ein failure_memory.check() in der Perception, keiner pro Tool-Call.

### T3: 4 separate Memory-Abfragen statt UnifiedMemory
- **Status**: `open`
- **Datei**: `engine/consciousness.py:1317-1348`
- **Ersparnis**: 400-800 Tok/Seq
- **Detail**: Perception macht 4 einzelne Memory-Queries (experience, semantic,
  failure, composer). UnifiedMemory (Zeile 651-656) koennte das dedupliziert liefern.

### T4: System-Prompt laedt 12 Subsystem-Summaries bei jedem Call
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/consciousness.py:~985-1057` (`_build_system_prompt`, Summaries bei ~1005-1023)
- **Ersparnis**: 800-1.500 Tok/Seq
- **Detail**: Goals, Tools, Tasks, Rating-Trend, Skills, Strategien, Effizienz,
  Kompetenz, Audit, Review, Benchmark, Foundry — alles bei JEDEM Call geladen.
  Viele aendern sich nur alle 5-15 Sequenzen.

### T5: Dream JSON mit indent=2 statt kompakt
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/dream.py:148-206`
- **Ersparnis**: 1.000-2.000 Tok (nur bei Dream-Calls, alle ~10 Seq)
- **Vorschlag**: `json.dumps(data, separators=(',', ':'))` statt `indent=2`
- **VORSICHT**: LLM muss diesen JSON-Block LESEN. Kompaktes JSON kann
  Dream-Qualitaet verschlechtern. Erst testen wenn andere Token-Optimierungen
  ausgeschoepft sind. Severity: LOW.

### T6: Graceful-Finish auf Sonnet statt guenstigerem Modell
- **Status**: `fixed` (2026-04-03)
- **Datei**: `engine/consciousness.py:1957-2058`
- **Detail**: Jede auto-beendete Sequenz macht einen Claude Sonnet Call (~$0.01).
  Mechanischer Fallback erzeugt fast gleiche Qualitaet.
- **Quick-Win**: In TASK_MODEL_MAP `graceful_finish` auf `kimi_k25` routen.

### T7: Static-Prompt Regeln als Prosa statt Stichpunkte
- **Status**: `fixed` (2026-04-03)
- **Datei**: `engine/consciousness.py:954-974`
- **Ersparnis**: ~200 Tok * N Steps/Seq
- **Detail**: Regeln (Duplikat, Qualitaet, Loop-Guard, Evidence-Based) als
  ausfuehrliche Saetze statt kompakte Stichpunkte.

---

## STABILITAET

### S1: SemanticMemory Index hat nur Soft-Limit (teilweise mitigiert)
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/intelligence.py:199`
- **Problem**: `_compress_memories()` greift ab 400 Eintraegen, aber kein hartes Cap.
  `_update_idf()` iteriert ueber ALLE verbleibenden Eintraege bei jedem Store.
  Ueber Wochen koennen dennoch hunderte Eintraege akkumulieren.
- **Fix**: Pruefen ob _compress_memories ausreicht oder hartes Cap (z.B. 500) noetig.
  Severity: LOW-MEDIUM (bereits teilweise mitigiert).

### S2: _file_locks LRU-Eviction ist Insertion-Order
- **Status**: `open`
- **Datei**: `engine/config.py:69-71`
- **Problem**: Bei 200 Locks wird der "aelteste" entfernt, aber nach
  Insertion-Order statt Usage-Order. Haeufig genutzte Locks koennen entfernt werden.
- **Fix**: `move_to_end()` bei Zugriff oder `functools.lru_cache`.

### S3: goal_stack._save() loggt Fehler nur mit print (teilweise mitigiert)
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/goal_stack.py:31-34`
- **Problem**: Nutzt `safe_json_write()` (atomares Schreiben mit temp+rename — robust).
  Aber Fehler werden nur mit `print()` geloggt statt `logging.warning()`.
  Goals im RAM bleiben konsistent, aber Disk-Version kann veraltet sein.
  Severity: LOW (Schreibvorgang selbst ist bereits atomar gesichert).

### S4: Checkpoint speichert keine Message-History
- **Status**: `open`
- **Erstellt**: 2026-04-03
- **Datei**: `engine/checkpoint.py:30-58`
- **Problem**: Kein Kontext ueber vorherige Tool-Calls bei Resume.
  Bei Resume hat Phi keinen Konversations-Kontext — Checkpoint dient aktuell
  nur als Fortschritts-Marker, nicht als echtes Resume-Feature.

### S5: AdaptiveRhythm liest 3x die gleiche goals.json
- **Status**: `fixed` (2026-04-03)
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
