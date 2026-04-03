# Phi Audit Backlog

> Priorisiert. Oben = als Naechstes. Max 15 Items.
> Jedes Item hat eine Done-Definition. Referenz: FINDINGS.md fuer Details.
> Erledigte Items: aus BACKLOG entfernen, in FINDINGS.md Status auf `fixed` setzen.

## JETZT — Quick-Wins + Stabilitaet

1. **T2** — Failure-Check pro Tool-Call entfernen (Quick-Win: 2.000-4.000 Tok/Seq!)
   Done: Nur noch ein failure_memory.check() in Perception, keiner pro Tool-Call

2. **H4** — SequenceRunner: 3 Signaturen anpassen (get_mode, classify_task, get_step_budget)
   Done: Alle 3 Aufrufe matchen tatsaechliche Signaturen + review_phi.py passed

3. **H6** — LLM-Fallback im Step-Loop: Retry + TASK_MODEL_MAP["fallback"] nutzen
   Done: Sequenz ueberlebt transienten API-Fehler + nutzt Fallback automatisch

4. **S5** — AdaptiveRhythm: goals.json nur einmal lesen statt 3x
   Done: Eine JSON-Lese-Operation, 3 Checks auf gleichem Dict

## STABILISIERUNG — Module aktivieren

5. **A1a** — PerceptionPipeline aktivieren (siehe auch T1: 1.000-2.000 Tok/Seq)
   Done: _build_perception() delegiert an Pipeline, Channels registriert

6. **A1b** — UnifiedMemory in Perception einbinden (siehe auch T3: 400-800 Tok/Seq)
   Done: Perception nutzt unified_memory.query() statt 4 separate Abfragen

## VERBESSERUNG — Architektur + Token

7. **A4** — Dead Code entfernen: select_tools, _build_compact_tools, _COMPACT_TOOLS_CACHE
   Done: Grep findet keine Referenzen mehr, review_phi.py passed

8. **T4** — System-Prompt Metadaten konditionalisieren (800-1.500 Tok/Seq)
   Done: Nur die 5 Kern-Felder immer, Rest hinter Relevanz-Gate

9. **T6** — Graceful-Finish auf Kimi statt Sonnet routen
   Done: TASK_MODEL_MAP["graceful_finish"] zeigt auf kimi_k25

10. **T7** — Static-Prompt Regeln komprimieren: Prosa → Stichpunkte
    Done: Regelblock < 100 Tokens statt ~350

## LANGFRISTIG

11. **S1** — SemanticMemory: pruefen ob _compress_memories ausreicht oder hartes Cap noetig
    Done: Entscheidung dokumentiert in DECISIONS.md

12. **S4** — Checkpoint mit Message-History fuer echtes Resume
    Done: Letzte 3 Tool-Results im Checkpoint gespeichert

13. **A1c** — SequenceRunner Step-Loop extrahieren (haertester Schnitt)
    Done: _run_sequence() delegiert an SequenceRunner
