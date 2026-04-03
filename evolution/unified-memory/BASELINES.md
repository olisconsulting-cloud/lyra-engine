# Unified Memory — Baselines

> Gemessen VOR jeder Phase-Aenderung. Vergleichs-Grundlage fuer Wirksamkeit.
> Regel: Keine Code-Aenderung ohne vorherige Baseline-Messung.

## Phase 0 — Ist-Zustand (vor jeder Aenderung)

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| Skill-Hit-Rate | ? | 30 Seq loggen, zaehlen wo `build_skill_prompt() != ""` | — |
| FailureMemory-Match-Rate | ? | 30 Seq loggen, zaehlen wo `check() != ""` | — |
| Wiederholungsfehler-Rate | ? | `failures.json` analysieren: gleiche goal+approach Paare zaehlen | — |
| Perception-Token/Seq | ? | Token-Verbrauch des gesamten Perception-Blocks (Durchschnitt ueber 30 Seq) | — |
| Rating MIT Skill-Prompt | ? | Durchschnittliches Phi-Rating wenn Skill-Prompt vorhanden war | — |
| Rating OHNE Skill-Prompt | ? | Durchschnittliches Phi-Rating wenn kein Skill-Prompt | — |
| Skills gesamt | 12 | `len(skill_library/index.json["skills"])` | 2026-04-03 |
| Skills mit success_count > 1 | 1 | Zaehlung in index.json | 2026-04-03 |
| Skills von ProactiveLearner nutzbar | 0 | Braucht success_count >= 2, nur 1 Skill hat das | 2026-04-03 |
| Prompt-Injektionen/Seq | 6 | Bekannt aus Code-Analyse (6 separate Bloecke in Perception) | 2026-04-03 |
| goal_type "sonstiges" Rate | ~58% | 7 von 12 Skills als "sonstiges" klassifiziert (vor classify-Fix) | 2026-04-03 |

### Bekannte Fakten (ohne Messung ableitbar)

- 11 von 12 Skills haben `success_count: 1` → ProactiveLearner ignoriert sie (Threshold >= 2)
- SkillLibrary und FailureMemory sind komplett isoliert (kein Code-Pfad verbindet sie)
- Dream liest `skills.json` (Tracker), NICHT `skill_library/index.json` (Templates)
- SemanticMemory hat das beste Retrieval (TF-IDF + Boost), wird von SkillLibrary nicht genutzt
- classify_goal_type hatte Bug (Teilwort-Matching), am 2026-04-03 gefixt (10 Typen statt 7)

## Phase 1 — Nach Quick Wins

| Metrik | Wert | Methode | Datum |
|--------|------|---------|-------|
| Skill-Hit-Rate | — | Gleiche Methode wie Phase 0 | — |
| FailureMemory-Match-Rate | — | Gleiche Methode wie Phase 0 | — |
| Wiederholungsfehler-Rate | — | Gleiche Methode wie Phase 0 | — |
| Perception-Token/Seq | — | Gleiche Methode wie Phase 0 | — |
| Rating MIT Skill-Prompt | — | Gleiche Methode wie Phase 0 | — |
| Rating OHNE Skill-Prompt | — | Gleiche Methode wie Phase 0 | — |
| Skills von ProactiveLearner nutzbar | — | Nach Threshold-Senkung auf >= 1 | — |

### Erwartete Effekte der Quick Wins

- **UM-Q1** (Threshold senken): Skills nutzbar steigt von 0 auf ~12
- **UM-Q2** (Anti-Patterns): Skill-Prompt enthaelt Warnungen aus FailureMemory
- **UM-Q3** (Semantische Suche): Skill-Hit-Rate steigt (Cross-Domain-Matches)

## Phase 2 — Nach Dream-Integration

(wird nach Phase 2 befuellt)

## Phase 3 — Nach Unified Retrieval

(wird nach Phase 3 befuellt)
