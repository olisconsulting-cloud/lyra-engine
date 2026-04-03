# Baselines — Telos

> Phase 0: Ist-Zustand VOR jeder Aenderung. Gemessen am 2026-04-03.

## Phase 0 — Ist-Zustand

### Skill-Verteilung (24 Skills total)

| Goal-Typ | Anzahl | Anteil |
|-----------|-------:|-------:|
| sonstiges | 13 | 54% |
| testing | 4 | 17% |
| recherche | 3 | 13% |
| tool_building | 2 | 8% |
| bug_fix | 1 | 4% |
| **Gesamt** | **24** | **100%** |

**Problem**: "sonstiges" ist Catch-All — 54% der Skills sind unkategorisiert.
Tatsaechliche Domaene: fast alle API-Integration.

### Domaenen-Abdeckung

| Domaene | Skills | Status |
|---------|-------:|--------|
| api_integration | ~20 | Ueberrepresentiert |
| data_analysis | 0 | Unberuehrt |
| testing | 4 | Aktiv |
| architecture | 0 | Unberuehrt |
| business_thinking | 3 | Recherche-only |
| frontend_design | 0 | Unberuehrt |

**Domaenen-Diversitaet**: 3 von 6 Domaenen beruehrt (50%).
Effektiv: 1 Domaene dominant (API), 2 marginal.

### Belief-Qualitaet (37 Beliefs)

| Kategorie | Anzahl |
|-----------|-------:|
| Taktisch (Tools, Tests, Prozess) | 37 |
| Strategisch (Zweck, Mission) | 0 |
| Duplikate | 5 |
| about_self | 0 |
| about_world | 0 |
| about_oliver | 0 |

### Goal-Diversitaet

| Metrik | Wert |
|--------|------|
| Abgeschlossene Goals | 5 |
| Davon API-bezogen | 5 (100%) |
| Aktive Goals | 0 |
| Goal-Typen (unique) | 1 |

### Kompetenz-Ring-Verteilung (Mapping existierender Skills)

| Ring | Domaenen | Abdeckung |
|------|----------|-----------|
| 1 — Kern | file_management, python_coding, planning | 3/3 (100%) |
| 2 — Handwerk | api_integration, testing, tool_building | 3/3 (100%) |
| 3 — Strategie | data_analysis, business_thinking, architecture | 1/3 (33%) |
| 4 — Autonomie | self_improvement, web_research, frontend_design | 2/3 (67%) |
| 5 — Weisheit | transfer_learning, teaching, oliver_alignment | 0/3 (0%) |

### Kern-Metriken

| Metrik | Wert | Methode |
|--------|------|---------|
| Domaenen-Diversitaet | 3/6 (50%) | Unique Domaenen mit >=1 Skill |
| Ring-Progression | Ring 2 complete, Ring 3 blocked | 60%-Schwelle pro Ring |
| Belief-Strategisch-Rate | 0% | strategische / total Beliefs |
| Repetitions-Rate | 83% | Skills in dominanter Domaene / total |
| Curiosity-Verdrahtung | 0% (Dead Code) | phi.py:exploration_weight → consciousness |
| Transfer-Faehigkeit | Ungemessen | Noch kein Test moeglich |

## Phase 1 — Nach Quick Wins

(Wird nach Phase 1 befuellt.)

## Phase 2 — Nach Kompetenz-Kompass

(Wird nach Phase 2 befuellt.)
