# Enforcement — Meta-Rules als Code statt Prompt

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Phis MetaCognition erkennt Probleme korrekt (12x "finish_sequence zu spaet"),
aber das Verhalten aendert sich nicht — weil Meta-Rules nur als Prompt-Injection
existieren. Phi KANN sie ignorieren und TUT es.

Dieses Projekt macht Meta-Rules zu Code-Constraints:
Erkannt → Regel → **Erzwungen im Code** → Verhalten aendert sich.

Das ist der Unterschied zwischen einem Spiegel und einem Lenkrad.

## Diagnose (Stand Sequenz 110)
- 22% produktive Steps, 78% Verschwendung
- MetaCognition erkennt dasselbe Problem 12x ohne Aenderung
- meta_rules.py hat 5 Regeln — alle sind Prompt-Injektionen
- check_guards() gibt Strings zurueck, nichts erzwingt sie
- finish_sequence wird oft erst bei Step 30+ aufgerufen statt bei 10-15

## Ansatz
Enforcement-Layer in consciousness.py der NACH dem LLM-Call prueft
ob eine Meta-Rule verletzt wird und HANDELT statt nur zu warnen.

Beispiel: `if step >= 20 and not finished: force_finish_sequence()`

## Phasen

### Phase 1 — finish_sequence Enforcement (JETZT)
- Hard-Limit: Ab Step 20 wird finish_sequence automatisch aufgerufen
- Narrator zeigt an: "Auto-Finish: Step-Limit erreicht"
- MetaCognition-Eintrag: "auto_enforced: finish_sequence"
- Messbar: productive_steps Ratio vorher/nachher

### Phase 2 — Zero-Output-Guard
- Ab Step 8: Wenn files_written == 0, Warnung in naechsten LLM-Call injizieren
- Ab Step 12: Wenn immer noch 0, force_finish mit Erklaerung
- Verhindert "40 Steps nur lesen ohne Output"

### Phase 3 — Dynamische Enforcement-Engine
- meta_rules.py Regeln werden automatisch zu Code-Constraints
- Neue Regel erkannt → Enforcement-Handler registriert
- Schwelle konfigurierbar pro Regel

## Kritische Regeln
- Enforcement darf NICHT zu aggressiv sein — Step 20 ist konservativ
- Phi muss im Narrator SEHEN warum auto-finished wurde (Transparenz)
- Jeder Enforcement wird in MetaCognition geloggt (Lern-Feedback)
- evolution/sprint: erhoehtes Limit (30 statt 20) — Selbstverbesserung braucht Raum, aber kein Freifahrtschein

## Metriken
- **Vorher**: productive_steps/total_steps = ~22% (Baseline aus metacognition.json)
- **Ziel Phase 1**: >= 40% (Halbierung der Verschwendung)
- **Ziel Phase 2**: >= 50%
