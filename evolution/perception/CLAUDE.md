# Perception — Zweistufige Wahrnehmung statt Token-Flut

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Phi bekommt pro Sequenz ~31.000 Tokens Perception — 27 Kanaele laden
alle unkontrolliert. Die PerceptionPipeline existiert bereits (185 LOC),
ist aber nicht angeschlossen.

Dieses Projekt aktiviert die Pipeline mit einem intelligenten Ansatz:
**Kern-Channels voll, Rest komprimiert** — kein Informationsverlust,
nur praezisere Fokussierung.

## Diagnose (Stand Sequenz 110)
- 27 Perception-Teile laden unconditionally (~31.000 Tokens)
- PerceptionPipeline: implementiert, nicht angeschlossen
- UnifiedMemory: implementiert, nicht in Perception integriert
- 4 separate Memory-Abfragen statt 1 unified Query
- Skills-Dump: 500 Tokens fuer "planning: expert (91/97)" — 50 Tokens reichen

## Ansatz: Zweistufig statt hartes Cap

### Stufe 1 — Kern (immer voll, ~2.000 Tokens)
- Focus (aktuelles Goal + Sub-Goals)
- Inbox (Oliver-Nachrichten)
- Working Memory (letzte 5 Sequenzen)
- Time (Timestamp, Sequenz-Nr)

### Stufe 2 — Kontext (komprimiert, ~3.000-5.000 Tokens)
- Skills → "Staerken: X, Y, Z. Schwaeche: A (25%)" statt voller Dump
- Projects → "3 aktiv: name1, name2, name3" statt Dateilisten
- Memories → Top-3 relevanteste (via UnifiedMemory) statt 4 separate Queries
- Failures → "Letzte Warnung: X" statt kompletter History
- Alles was Phi vertiefen will → read_file auf die JSON

### Ziel-Bereich: 5.000-8.000 Tokens (nicht 3.000 — das waere zu aggressiv)

## Phasen

### Phase 1 — Kanaele registrieren + Pipeline anschliessen
- 27 bestehende Perception-Teile als Channels registrieren
- _build_perception() durch pipeline.build() ersetzen
- Token-Budget: 8.000 (konservativ, spaeter optimieren)

### Phase 2 — Kompressoren pro Channel
- Jeder Channel bekommt einen Kompressor (1-2 Saetze statt voller Dump)
- Pipeline waehlt: voll laden (Kern) oder komprimiert (Kontext)
- estimated_tokens pro Channel kalibrieren (nicht default 200)

### Phase 3 — UnifiedMemory als Query-Layer
- 4 separate Memory-Abfragen → 1 unified_memory.query()
- Ergebnis als ein Channel statt 4 separate
- Adaptives Lernen: Pipeline EMA-Gewichte basierend auf Sequenz-Rating

## Kritische Regeln
- KEIN Informationsverlust — komprimieren, nicht abschneiden
- Kern-Channels IMMER voll (Focus, Inbox, Working Memory)
- Budget NICHT unter 5.000 Tokens — Phi braucht Kontext
- Schrittweise: Erst Pipeline anschliessen, dann komprimieren
