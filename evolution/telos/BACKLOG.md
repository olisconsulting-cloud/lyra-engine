# Backlog — Telos

> Max 15 Items. Jedes Item hat eine Done-Definition.
> Reihenfolge = Prioritaet. Oberstes zuerst.

## Phase 1 — Quick Wins

1. **TE-Q1** — telos.json erstellen: Zweck-Hierarchie + Kompetenz-Ringe als Datenstruktur
   Done: `data/consciousness/telos.json` existiert, Schema validiert, alle existierenden
   Skills auf Ringe gemappt, `review_phi.py` PASS

2. **TE-Q2** — Goal-Priorisierung: Diversitaets-Bonus in get_current_focus()
   Done: `goal_stack.py:get_current_focus()` bevorzugt Goals in unterrepraesentierten
   Domaenen. Test: 2 Goals (API vs. Datenanalyse) → Datenanalyse wird bevorzugt.
   `review_phi.py` PASS

3. **TE-Q3** — Belief-Deduplikation: Dream erkennt und mergt doppelte Beliefs
   Done: `dream.py` prueft Cosine-Similarity vor Belief-Insert. Duplikate in
   beliefs.json von 5 auf 0 reduziert. `review_phi.py` PASS

4. **TE-Q4** — Curiosity verdrahten: phi.py exploration_weight() in consciousness.py nutzen
   Done: `consciousness.py` setzt Curiosity-Wert basierend auf Domaenen-Repetition.
   Hohe Repetition → hohe Curiosity → kuerzere Sleep-Intervalle. `review_phi.py` PASS

## Phase 2 — Kompetenz-Kompass

5. **TE-K1** — Ring-Logik: CompetenceMatrix berechnet Ring-Levels
   Done: `evolution.py:CompetenceMatrix` hat Ring-Zuordnung. 60%-Schwelle fuer
   Ring-Aufstieg. Phi kann nicht 20 Skills in Ring 2 bauen ohne Ring 3 zu beruehren.
   `review_phi.py` PASS

6. **TE-K2** — Telos-Reflexion: 4 Fragen nach jeder finish_sequence
   Done: `consciousness.py` stellt nach finish_sequence 4 Telos-Fragen.
   Ergebnisse in `telos.json` gespeichert. 3x gleiche Domaene → Wechsel erzwungen.
   `review_phi.py` PASS

7. **TE-K3** — Dream-Telos: Dream priorisiert Goals nach Telos-Score
   Done: `dream.py:_apply_recommendations()` sortiert neue Goals nach Telos-Score
   statt sie am Ende anzuhaengen. Dream-Goals werden bevorzugt wenn sie neue
   Domaenen erschliessen. `review_phi.py` PASS

8. **TE-K4** — Strategische Beliefs: Dream erzeugt Zweck-Beliefs
   Done: `beliefs.json` enthaelt min. 3 Beliefs in Kategorie "about_self" mit
   Zweck-Bezug ("Mein Zweck ist...", "Oliver braucht..."). `review_phi.py` PASS

## Phase 3 — Transfer-Learning

9. **TE-T1** — Transfer-Test definieren: ARC-aehnliche Mini-Aufgaben
   Done: 5 Transfer-Aufgaben dokumentiert in `konzept/06-transfer-learning.md`.
   Jede Aufgabe hat: Quell-Domaene, Ziel-Domaene, erwartetes Transfer-Pattern.

10. **TE-T2** — Transfer messen: Sequenzen pro neue Domaene mit/ohne Transfer
    Done: Baseline-Messung (Sequenzen bis Skill-Level "intermediate" OHNE Transfer)
    vs. Messung MIT Transfer. Delta dokumentiert in BASELINES.md.

11. **TE-T3** — Transfer-Mechanismus: Skill-Abstraktion in Skill-Library
    Done: Nur wenn TE-T2 zeigt dass Transfer moeglich ist. Skill-Library speichert
    abstrakte Patterns ("planen → lesen → bauen → testen") statt konkrete Tool-Sequenzen.

## Erledigt

(Noch keine Items erledigt.)
