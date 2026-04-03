# Phi Audit Backlog

> Priorisiert. Oben = als Naechstes. Max 15 Items.
> Jedes Item hat eine Done-Definition. Referenz: FINDINGS.md fuer Details.
> Erledigte Items: aus BACKLOG entfernen, in FINDINGS.md Status auf `fixed` setzen.

## JETZT — Echte Bugs fixen

1. **C1** — combine_tools() crash: `_get_client()` extrahieren
   Done: review_phi.py passed + combine_tools() wirft keinen AttributeError

2. **H1** — validate_against_outcome: `(new_beliefs, rating >= 6, summary[:200])`
   Done: Aufruf matcht Signatur in intelligence.py:772

3. **H2** — write_journal: cycle-Arg ergaenzen
   Done: Aufruf matcht Signatur in communication.py:140

4. **H3** — record_process_pattern: description-Arg ergaenzen
   Done: Aufruf matcht Signatur in intelligence.py:709

5. **H5** — SelfBenchmark._load + MetaCognition._load: safe_json_read (2 Stellen)
   Done: Beide _load() haben try/except, korrupte JSON gibt leere Liste

## DANACH — Stabilitaet + Quick-Wins

6. **H4** — SequenceRunner: 3 Signaturen anpassen (get_mode, classify_task, get_step_budget)
   Done: Alle 3 Aufrufe matchen tatsaechliche Signaturen + review_phi.py passed

7. **T2** — Failure-Check pro Tool-Call entfernen (Quick-Win: 2.000-4.000 Tok/Seq!)
   Done: Nur noch ein failure_memory.check() in Perception, keiner pro Tool-Call

8. **H6** — LLM-Fallback im Step-Loop: Retry + TASK_MODEL_MAP["fallback"] nutzen
   Done: Sequenz ueberlebt transienten API-Fehler + nutzt Fallback automatisch

9. **S5** — AdaptiveRhythm: goals.json nur einmal lesen statt 3x
   Done: Eine JSON-Lese-Operation, 3 Checks auf gleichem Dict

## STABILISIERUNG — Module aktivieren

10. **A1a** — PerceptionPipeline aktivieren (siehe auch T1: 1.000-2.000 Tok/Seq)
    Done: _build_perception() delegiert an Pipeline, Channels registriert

11. **A1b** — UnifiedMemory in Perception einbinden (siehe auch T3: 400-800 Tok/Seq)
    Done: Perception nutzt unified_memory.query() statt 4 separate Abfragen

12. **A1d** — SequenceFinisher aktivieren (nach H1-H3 fix + A2/A3 konsolidieren)
    Done: _handle_finish_sequence() delegiert an Finisher, Formeln einheitlich

## VERBESSERUNG — Architektur + Token

13. **A2/A3** — Valenz + Wasted-Steps Formeln konsolidieren (Vorbedingung fuer A1d)
    Done: Eine Valenz-Formel, eine Wasted-Steps-Formel, in sequence_finisher.py

14. **A4** — Dead Code entfernen: select_tools, _build_compact_tools, _COMPACT_TOOLS_CACHE
    Done: Grep findet keine Referenzen mehr, review_phi.py passed

15. **T4** — System-Prompt Metadaten konditionalisieren (800-1.500 Tok/Seq)
    Done: Nur die 5 Kern-Felder immer, Rest hinter Relevanz-Gate
