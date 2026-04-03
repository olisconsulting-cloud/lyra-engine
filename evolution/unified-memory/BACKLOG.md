# Unified Memory Backlog

> Priorisiert. Oben = als Naechstes. Max 15 Items.
> Jedes Item hat eine Done-Definition.
> Erledigte Items: aus BACKLOG entfernen, in sessions/ dokumentieren.
> ID-Schema: UM-B (Baseline), UM-Q (Quick Win), UM-D (Dream), UM-R (Retrieval), UM-T (Transfer)

## JETZT — Phase 1: Baselines messen

1. **UM-B1** — Skill-Hit-Rate messen: 30 Sequenzen loggen, zaehlen wo build_skill_prompt() != ""
   Done: Zahl in BASELINES.md eingetragen, Messmethode dokumentiert

2. **UM-B2** — FailureMemory-Match-Rate messen: 30 Sequenzen loggen, zaehlen wo check() != ""
   Done: Zahl in BASELINES.md eingetragen

3. **UM-B3** — Wiederholungsfehler-Rate messen: failures.json analysieren, gleiche Fehler-Typen zaehlen
   Done: Zahl in BASELINES.md eingetragen

4. **UM-B4** — Perception-Token pro Sequenz messen: Token-Verbrauch des Perception-Blocks loggen
   Done: Durchschnitt in BASELINES.md eingetragen

5. **UM-B5** — Phi-Rating MIT vs OHNE Skill-Prompt vergleichen
   Done: Beide Durchschnitte in BASELINES.md, Differenz berechnet

## DANACH — Phase 1: Quick Wins

6. **UM-Q1** — ProactiveLearner: success_count >= 2 auf >= 1 senken
   Done: proactive_learner.py:117 geaendert, review_phi.py gruen

7. **UM-Q2** — Skill-Extraktion: FailureMemory-Lektionen als anti_patterns einbetten
   Done: SkillEnricher Modul erstellt, in consciousness.py verdrahtet

8. **UM-Q3** — Skill-Retrieval: Semantische Suche zusaetzlich zu goal_type
   Done: build_skill_prompt() nutzt TF-IDF aus SemanticMemory als Fallback

9. **UM-Q4** — Baselines NACH Quick Wins erneut messen (gleiche 5 Metriken)
   Done: Phase-1-Spalte in BASELINES.md befuellt, Vergleich dokumentiert

10. **UM-Q5** — 20-30 Sequenzen beobachten, Ergebnisse in observations/ loggen
    Done: observations/phase-1_YYYY-MM-DD.md geschrieben

## SPAETER — Phase 2: Dream-Integration

11. **UM-D1** — Dream liest skill_library/index.json mit ein
    Done: dream.py _gather_all_memory() erweitert, Dream-Prompt angepasst

12. **UM-D2** — Dream mergt aehnliche Skills (Jaccard auf abstract_steps)
    Done: Konsolidierungs-Logik in _apply_results(), Test mit 2+ aehnlichen Skills

13. **UM-D3** — Dream prunet Skills mit avg_score < 5
    Done: Pruning-Logik aktiv, Skills mit Score < 5 werden entfernt

14. **UM-D4** — Dream generiert "why"-Feld pro Skill (LLM-Zusammenfassung)
    Done: Skill-Eintraege haben why-Feld, build_skill_prompt() zeigt es an
