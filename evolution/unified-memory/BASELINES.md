# Unified Memory — Baselines

> Gemessen VOR jeder Phase-Aenderung. Vergleichs-Grundlage fuer Wirksamkeit.
> Regel: Keine Code-Aenderung ohne vorherige Baseline-Messung.

## Phase 0 — Ist-Zustand (vor jeder Aenderung)

> Datengrundlage: 85 Sequenzen, 100 Efficiency-Eintraege, 50 Ratings, 100 Failures.
> Gemessen am 2026-04-03 aus bestehenden JSON-Dateien + Code-Analyse.

### Kern-Metriken

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| Skill-Hit-Rate | LOGGING AKTIV | `BASELINE: skill_hit=` in consciousness.py, 30 Seq abwarten | 2026-04-03 |
| FailureMemory-Match-Rate | LOGGING AKTIV | `BASELINE: fm_match=` in consciousness.py, 30 Seq abwarten | 2026-04-03 |
| Wiederholungsfehler-Rate | **56.2%** | failures.json: 18/32 Failures haben identisches goal+approach Paar | 2026-04-03 |
| Doppelte-Lesson-Rate | **75.0%** | failures.json: 24/32 Failures haben gleichen Lesson-Text | 2026-04-03 |
| Perception-Token/Seq | **~31.700** | efficiency.json: Durchschnitt ueber 48 non-zero Sequenzen | 2026-04-03 |
| Durchschn. Rating (gesamt) | **6.50** | ratings.json: 50 Eintraege, bimodal (Peak bei 5 und 9) | 2026-04-03 |
| Effizienz-Ratio | **18.9%** | metacognition.json: 143 produktive / 700 gesamt Steps | 2026-04-03 |

### Skill-Library Metriken

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| Skills gesamt | 23 | skill_library/index.json | 2026-04-03 |
| Skills mit success_count > 1 | **0** | Alle 23 Skills haben success_count=1 | 2026-04-03 |
| Skills von ProactiveLearner nutzbar | **0** | Threshold >= 2, kein Skill erreicht das | 2026-04-03 |
| goal_type "sonstiges" Rate | **56.5%** | 13 von 23 Skills als "sonstiges" (vor classify-Fix) | 2026-04-03 |
| Avg Skill-Score | 7.70 | Durchschnitt avg_score in index.json | 2026-04-03 |
| Avg Skill-Rating | 8.39 | Durchschnitt avg_rating (nur Erfolge, Bias!) | 2026-04-03 |
| Prompt-Injektionen/Seq | 6 | Code-Analyse: 6 separate Bloecke in Perception | 2026-04-03 |

### Failures Breakdown

| Tool | Failures | Anteil | Top-Problem |
|------|----------|--------|-------------|
| complete_project | 14 | 43.8% | Tests nicht bestanden (14x gleicher Loop!) |
| execute_python | 10 | 31.3% | Import-Fehler, exec()-Warnungen |
| read_file | 2 | 6.3% | Datei nicht gefunden |
| create_tool | 2 | 6.3% | Kein def run() |
| write_file | 2 | 6.3% | — |
| create_project | 1 | 3.1% | Aehnliches Projekt existiert |
| complete_subgoal | 1 | 3.1% | — |

### Schlimmster Loop

`complete_project` wurde **14x hintereinander** mit dem gleichen Fehler aufgerufen
(44 Minuten, 37-45 Sekunden zwischen Versuchen). Phi hat blind retried ohne
den Root Cause zu beheben. Die FailureMemory hatte die Lektion gespeichert,
aber Phi hat sie nicht abgerufen/angewendet.

### Bekannte strukturelle Fakten

- SkillLibrary und FailureMemory: **komplett isoliert** (kein Code-Pfad verbindet sie)
- Dream liest `skills.json` (Tracker), **NICHT** `skill_library/index.json` (Templates)
- SemanticMemory (bestes Retrieval) wird von SkillLibrary **nicht genutzt**
- classify_goal_type: Bug gefixt am 2026-04-03 (Teilwort-Matching → Anti-Pattern-Guards, 7 → 10 Typen)
- 52% der Efficiency-Eintraege sind Zero-Token Ghost-Sequenzen (Infrastruktur-Loop)
- Rating-Verteilung bimodal: 36% bei Score 5 (default), 28% bei Score 9 (High-Quality)

## Phase 1 — Nach Quick Wins

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| Skill-Hit-Rate | — | Gleiche Methode wie Phase 0 | — |
| FailureMemory-Match-Rate | — | Gleiche Methode wie Phase 0 | — |
| Wiederholungsfehler-Rate | — | Gleiche Methode wie Phase 0 | — |
| Doppelte-Lesson-Rate | — | Gleiche Methode wie Phase 0 | — |
| Perception-Token/Seq | — | Gleiche Methode wie Phase 0 | — |
| Durchschn. Rating | — | Gleiche Methode wie Phase 0 | — |
| Skills von ProactiveLearner nutzbar | — | Nach Threshold-Senkung auf >= 1 | — |
| goal_type "sonstiges" Rate | — | Nach classify_goal_type Fix | — |

### Erwartete Effekte der Quick Wins

- **UM-Q1** (Threshold senken): Skills nutzbar steigt von 0 auf ~23
- **UM-Q2** (Anti-Patterns): Skill-Prompt enthaelt Warnungen aus FailureMemory
- **UM-Q3** (Semantische Suche): Skill-Hit-Rate steigt (Cross-Domain-Matches)

### IOR Meta-Metrik (neu ab 2026-04-03)

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| IOR-Level | **linear** | engine/ior.py: Noch keine Daten, startet bei "linear" | 2026-04-03 |
| IOR-Ratio (Durchschnitt) | — | ior.json: Wird nach 20-30 Sequenzen befuellt | — |
| Leverage-Sequenzen | — | ior.json: Sequenzen mit skills_reused > 0 | — |
| Emergenz-Sequenzen | — | ior.json: Sequenzen mit cross_transfers > 0 | — |

> **IOR als Erfolgsmetrik fuer Unified Memory:** Wenn SkillLibrary und FailureMemory
> tatsaechlich integriert sind, steigt die IOR von "linear" Richtung "leverage".
> Skill-Wiederverwendung ist der direkteste Indikator fuer erfolgreiche Integration.
> Cross-Domain-Transfer (Emergenz) ist das Fernziel.

## Phase 2 — Nach Dream-Integration

(wird nach Phase 2 befuellt)

## Phase 3 — Nach Unified Retrieval

(wird nach Phase 3 befuellt)
