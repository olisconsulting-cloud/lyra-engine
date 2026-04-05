# Phi Audit Backlog

> Priorisiert. Oben = als Naechstes. Max 15 Items.
> Jedes Item hat eine Done-Definition. Referenz: FINDINGS.md fuer Details.
> Erledigte Items: aus BACKLOG entfernen, in FINDINGS.md Status auf `fixed` setzen.

## JETZT — Module aktivieren

1. ~~**A1a** — PerceptionPipeline aktivieren~~ ✅ (2026-04-04)

2. **A1b** — UnifiedMemory in Perception einbinden (siehe auch T3: 400-800 Tok/Seq)
   Done: Perception nutzt unified_memory.query() statt 4 separate Abfragen

## VERBESSERUNG — Token-Effizienz

3. **T4** — System-Prompt Metadaten konditionalisieren (800-1.500 Tok/Seq)
   Done: Nur die 5 Kern-Felder immer, Rest hinter Relevanz-Gate

## VERBESSERUNG — Telos-Konsistenz

7. **TEL1** — Telos-Sync: Lehrprojekt-Abschluss muss telos.json Domain-Level aktualisieren
   Aktuell: complete_learning_project() aktualisiert "create_project" statt die Domain selbst.
   telos.json Ring-Completion wird nie hochgezaehlt → gleiche Gap wird endlos erkannt.
   Done: Domain-Skill korrekt aktualisiert + telos.json completion nach Projekt-Abschluss synchronisiert

8. **TEL2** — Domain-Classifier priorisieren (Score statt First-Match)
   Aktuell: "API-Datenanalyse" → api_integration (weil "api" vor "daten" matcht).
   Done: _classify_domain() nutzt Score-Ranking statt Reihenfolge

## LANGFRISTIG

4. **S1** — SemanticMemory: pruefen ob _compress_memories ausreicht oder hartes Cap noetig
   Done: Entscheidung dokumentiert in DECISIONS.md

5. **S4** — Checkpoint mit Message-History fuer echtes Resume
   Done: Letzte 3 Tool-Results im Checkpoint gespeichert

6. **A1c** — SequenceRunner Step-Loop extrahieren (haertester Schnitt)
   Done: _run_sequence() delegiert an SequenceRunner
