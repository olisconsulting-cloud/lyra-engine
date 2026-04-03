# Phi Audit Backlog

> Priorisiert. Oben = als Naechstes. Max 15 Items.
> Referenz: FINDINGS.md fuer Details zu jeder ID.

## JETZT — Echte Bugs fixen

1. **C1** — combine_tools() crash: self.client → _get_client() extrahieren
2. **H1** — validate_against_outcome: Signatur fixen (bool, str)
3. **H2** — write_journal: cycle-Arg ergaenzen
4. **H3** — record_process_pattern: description-Arg ergaenzen
5. **H5** — SelfBenchmark + MetaCognition: safe_json_read nutzen

## DANACH — Stabilitaet

6. **H4** — SequenceRunner Signaturen anpassen
7. **H6** — LLM-Fallback im Step-Loop einbauen
8. **S1** — SemanticMemory Index begrenzen (max 500)
9. **S5** — AdaptiveRhythm: goals.json nur einmal lesen

## STABILISIERUNG — Module aktivieren

10. **A1** — PerceptionPipeline aktivieren (Token-Ersparnis T1)
11. **A1** — UnifiedMemory in Perception einbinden (T3)
12. **A1** — SequenceFinisher aktivieren (nach H1-H3 fix)
13. **A2/A3** — Valenz + Wasted-Steps Formeln konsolidieren

## VERBESSERUNG — Token-Diaet

14. **T2** — Failure-Check pro Tool-Call entfernen (Quick-Win)
15. **T5** — Dream JSON kompakt formatieren (Quick-Win)
