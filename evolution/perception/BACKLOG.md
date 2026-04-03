# Perception Backlog

> Oben = als Naechstes. Erledigte Items entfernen.

## Phase 1 — Pipeline anschliessen

1. **P1-1** — 27 Perception-Teile als Channels registrieren
   Done: Jeder Teil hat name, builder, estimated_tokens, always_load Flag

2. **P1-2** — _build_perception() durch pipeline.build() ersetzen
   Done: Sequenz nutzt Pipeline statt direkte Aufrufe

3. **P1-3** — Token-Baseline vorher/nachher messen
   Done: Perception-Tokens pro Sequenz in BASELINES.md

## Phase 2 — Kompressoren (nach Beobachtung Phase 1)

4. **P2-1** — Skills-Kompressor (500 → 50 Tokens)
5. **P2-2** — Projects-Kompressor (3000 → 200 Tokens)
6. **P2-3** — Memory-Kompressor via UnifiedMemory (4 Queries → 1)
7. **P2-4** — estimated_tokens pro Channel kalibrieren
