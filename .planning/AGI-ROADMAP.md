# AGI-Roadmap: 7 Hebel zum Self-Sustaining Learner

> Erstellt: 2026-04-05 | Basis: 60+ Quellen (Chollet, ARC-2025, SOAR, Voyager, DGM, AlphaEvolve)
> Kern-Erkenntnis: Struktur > Skalierung. Alle Teile existieren — der Hebel ist der geschlossene Loop.
> Intelligenz = Skill-Acquisition Efficiency bei unbekannten Aufgaben (Chollet)

---

## Hebel 1: EVALUATION (Messen = Sehen) — LIVE

**Warum #1:** Ohne Messung kann sich nichts systematisch verbessern.

**Implementiert:**
- `engine/evaluation.py` — EvaluationEngine, Score 0-100
- 4 KPIs: Effizienz-Ratio (35%), Fehlerrate-Inv (30%), Output/Token (20%), Kosten-Effizienz (15%)
- goal_completion_rate deaktiviert (Gewicht 0%) bis GoalStack echte Daten liefert
- Checkpoints alle 10 Sequenzen, Langzeit-Trends, automatische Alerts
- Trend im System-Prompt sichtbar: `EVAL: 62.4/100 ↑ verbessernd`

**Offen:**
- GoalStack-Integration (goals_completed/attempted echte Werte)
- Dream-Integration (get_detailed_report() in Konsolidierung einspeisen)
- Magic Numbers kalibrieren nach 100+ Sequenzen Baseline

---

## Hebel 2: REFINEMENT LOOPS (Iterieren = Denken) — OFFEN

**Warum #2:** "Refinement is Intelligence" — dominierende Erkenntnis ARC-2025.

**Was fehlt:**
- Phi macht einen Versuch pro Sub-Goal. Scheitern → loggen → weiter.
- Kein Critic-Loop: "das war 60% richtig, verbessere Teil X"
- `quantum.py` Critic existiert, ist aber passiv

**Was zu bauen:**
- Nach jedem Tool-Call: Ergebnis bewerten (success/partial/failure)
- Bei partial: Reflexion + gezielter Retry (max 3 Loops)
- Critic in `quantum.py` aktiv machen: Revision vorschlagen, nicht nur speichern
- Budget: Max 3 Refinement-Loops pro Sub-Goal (Cost-Control)

**Dateien:** `engine/quantum.py`, `engine/consciousness.py`

---

## Hebel 3: META-LEARNING (Lernen zu Lernen) — OFFEN

**Warum #3:** Nur 5% der Neuro-Symbolic-Forschung, aber groesster Bottleneck.

**Was fehlt:**
- MetaRuleEngine: 4 Regel-Templates, nur 2 Guards implementiert
- Kein Feedback-Loop: "Regel X erstellt — hat sie geholfen?"
- Keine automatische Eskalation Muster → Code-Aenderung

**Was zu bauen:**
- Regel-Wirksamkeits-Tracking (Vor/Nach-Vergleich)
- Automatische Deaktivierung unwirksamer Regeln
- Eskalations-Pipeline: Muster → Regel → Code → Validierung → Beibehaltung/Rollback

**Dateien:** `engine/meta_rules.py`, `engine/evolution.py`

**KIPPPUNKT: Nach Hebel 1-3 traegt sich der Self-Improvement-Loop selbst.**

---

## Hebel 4: AUTOMATIC CURRICULUM (Neugierde = Wachstum) — OFFEN

**Warum #4:** Ohne Curriculum lernt Phi nur reaktiv. Voyager zeigte:
selbst-generierte Aufgaben = exponentielles Lernen.

**Was zu bauen:**
- Skill-Gap-Analyse → Uebungsaufgaben generieren
- Difficulty-Scaling basierend auf Erfolgsrate
- Curriculum-Goals als eigene Kategorie im Goal-Stack
- "Explore Mode": Alle 20 Seq nach neuem Terrain suchen

**Dateien:** `engine/goal_stack.py`, `engine/evolution.py`

---

## Hebel 5: HINDSIGHT LEARNING (Scheitern = Daten) — OFFEN

**Warum #5:** SOAR verdoppelte ARC-Performance damit.

**Was zu bauen:**
- FailureMemory: `alternative_use` Feld ("wofuer WAERE das nuetzlich?")
- Skill-Extraktion auch aus gescheiterten Versuchen
- Cross-Goal-Matching: Bei neuem Goal → FailureMemory durchsuchen

**Dateien:** `engine/quantum.py`, `engine/intelligence.py`

---

## Hebel 6: CONSTITUTIONAL SELF-CRITIQUE (Verfassung = Alignment) — OFFEN

**Warum #6:** DGM loeschte eigenen Fehlererkennungscode — Goodhart auf Steroiden.

**Was zu bauen:**
- Verfassungs-Prinzipien: positiv formuliert, verhaltensbasiert
- Vor jedem Self-Modify: Critique gegen Verfassung
- Policy-Engine auf LLM-Outputs erweitern
- Unumgehbare Safety-Invarianten per Code

**Dateien:** `engine/meta_rules.py`, `engine/policy.py`, `engine/security.py`

---

## Hebel 7: STRUCTURED MEMORY (Graph > Vektoren) — OFFEN

**Warum #7:** TF-IDF findet aehnliche Texte, keine kausalen Zusammenhaenge.

**Was zu bauen:**
1. Beziehungs-Edges zwischen Skills/Strategies/Beliefs
2. Dream clustert zu abstrakten Konzepten
3. Aktives Vergessen mit Relevanz-Score
4. Kausale Annotations ("weil", "verursacht", "verhindert")

**Dateien:** `engine/intelligence.py`, `engine/dream.py`

---

## Anti-Hebel (was Phi NICHT braucht)

- Fine-Tuning (API-basiert, Prompt+Workflow ist der Hebel)
- Eigene Foundation Models
- Riesige Vector-DBs (AutoGPT-Lektion: Overkill)
- Embodiment/Robotik (Tool-Use = digitales Embodiment)

---

## Verifikation

- Nach jeder Phase: `python review_phi.py` als Gate
- Nach Hebel 1: Phi kann zeigen ob sie besser/schlechter wird ✅
- Nach Hebel 2: Mehr Goals pro Sequenz (messbar via Hebel 1)
- Nach Hebel 3: Meta-Rules werden automatisch deaktiviert wenn unwirksam
- Nach Hebel 4: Phi generiert eigene Uebungsaufgaben und loest sie
- Laufend: 20-30 Sequenzen beobachten zwischen Phasen

---

## Quellen (Top 10)

- Chollet: On the Measure of Intelligence — arxiv.org/abs/1911.01547
- DeepMind: Levels of AGI — arxiv.org/abs/2311.02462
- ARC Prize 2025 — arcprize.org/blog/arc-prize-2025-results-analysis
- Self-Evolving Agents Survey — arxiv.org/abs/2507.21046
- Darwin Goedel Machine — sakana.ai/dgm/
- AlphaEvolve — deepmind.google/blog/alphaevolve
- SOAR — arxiv.org/abs/2507.14172
- Voyager — arxiv.org/abs/2305.16291
- ALMA — arxiv.org/abs/2602.07755
- Neuro-Symbolic AI Review — arxiv.org/abs/2501.05435
