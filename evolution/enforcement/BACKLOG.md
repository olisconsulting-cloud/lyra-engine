# Enforcement Backlog

> Oben = als Naechstes. Erledigte Items entfernen.

## Phase 1 — finish_sequence Enforcement

1. **E1-1** — Force-Finish ab Step 15 in consciousness.py
   Code: Im Step-Loop nach Tool-Execution, VOR naechstem LLM-Call pruefen
   Done: step >= 15 → _graceful_finish() aufgerufen, Narrator informiert

2. **E1-2** — Enforcement-Ausnahme fuer evolution/sprint Modus
   Done: Kein Auto-Finish wenn mode in ("evolution", "sprint")

3. **E1-3** — MetaCognition-Logging bei Auto-Finish
   Done: Eintrag in metacognition.json mit "enforcement": "auto_finish_step_15"

4. **E1-4** — Baseline-Messung dokumentieren
   Done: productive_steps Ratio aus den letzten 20 Sequenzen in BASELINES.md

## Phase 2 — Zero-Output-Guard (nach Beobachtung Phase 1)

5. **E2-1** — Warnung bei files_written == 0 ab Step 8
6. **E2-2** — Force-Finish bei files_written == 0 ab Step 12
