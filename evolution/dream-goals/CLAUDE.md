# Dream-Goals — Konkrete Sub-Goals statt vager Saetze

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Dream-Konsolidierung erkennt gute Muster, aber die Empfehlungen werden
als ganze Saetze zu Goal-Titeln: "Finish_sequence sollte konsequent und
fruehzeitig innerhalb von 15-20 Steps eingesetzt werden, sobald..."

Goals MIT Sub-Goals werden erledigt (5/5 Checkliste).
Goals OHNE Sub-Goals drehen endlos.

Dieses Projekt sorgt dafuer, dass jedes Dream-Goal automatisch
3 konkrete, messbare Sub-Goals mit Done-Kriterien bekommt.

## Diagnose (Stand Sequenz 110)
- Dream erzeugt Empfehlungen mit title[:100] — ganze Saetze, nicht ausfuehrbar
- _apply_recommendations() erstellt Goals ohne Sub-Goals
- Completed Goals mit Sub-Goals: 100% Erfolgsrate
- Active Goals ohne Sub-Goals: 0% Fortschritt

## Ansatz
Dream nutzt einen LLM-Call um aus jeder Empfehlung 3 Sub-Goals zu generieren:
- Titel: max 60 Zeichen, aktionsbasiert ("Implementiere X", "Messe Y")
- Done-Kriterium: messbar ("Ratio > 40%", "5 Sequenzen ohne Fehler")
- Reihenfolge: abhaengigkeitsbasiert

## Phasen

### Phase 1 — Sub-Goal-Generator in Dream
- _apply_recommendations() ruft LLM auf: "Generiere 3 Sub-Goals fuer: {empfehlung}"
- Format: {"title": str, "done_criterion": str}
- Fallback wenn LLM-Call fehlschlaegt: Goal trotzdem erstellen (wie bisher)

### Phase 2 — Goal-Titel kuerzen
- title = erste 60 Zeichen oder erster Satz (was kuerzer ist)
- description = voller Text der Empfehlung

### Phase 3 — Dream-Quality-Gate
- Dream-Empfehlungen die zu aehnlich zu bestehenden Goals sind → nicht erstellen
- Duplikat-Check: Cosine-Similarity > 0.7 mit aktiven Goals → skip
- Max 3 aktive Goals gleichzeitig (statt 5) — Fokus > Breite

## Kritische Regeln
- Sub-Goal-LLM-Call muss GUENSTIG sein (GPT-4.1-mini, nicht Opus)
- Fallback bei API-Fehler: Goal ohne Sub-Goals erstellen (nicht blockieren)
- Goal-Titel MUESSEN kurz und aktionsbasiert sein
