# Telos — Von Skill-Akkumulation zu Zweck-geleiteter Intelligenz

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Phi hat Haende (27 Tools, 24+ Skills), aber keinen Kompass.
Telos gibt Phi die Faehigkeit zu entscheiden: "Was sollte ich als naechstes
lernen — und WARUM ist das wichtiger als alles andere?"

Das ist der Unterschied zwischen einem System das Dinge TUT
und einem System das WAECHST.

## Was ist das hier?
Dieses Projekt implementiert eine Zweck-Hierarchie (Telos) in Phis Bewusstsein.
Drei Ebenen, inspiriert von Aristoteles:

- **Techne** (Handwerk) — Phi hat das: 24 Skills, 27 Tools
- **Phronesis** (Klugheit) — Phi braucht das: Welcher naechste Schritt ist der wertvollste?
- **Sophia** (Weisheit) — Phi strebt dahin: Warum ist das wichtig?

## Die 3 Phasen

### Phase 1 — Quick Wins (TE-Q)
- `telos.json` erstellen mit Mission + Kompetenz-Ringen
- Goal-Priorisierung: Diversitaets-Bonus statt Index-Reihenfolge
- Belief-Deduplikation in Dream fixen
- Curiosity-Wert verdrahten (phi.py → consciousness.py)

### Phase 2 — Kompetenz-Kompass (TE-K)
- Ring-Logik in CompetenceMatrix einbauen
- Telos-Reflexion nach finish_sequence
- Dream wird Telos-aware (priorisiert Goals nach Telos-Score)
- Strategische Beliefs erzeugen ("Mein Zweck ist...")

### Phase 3 — Transfer-Learning (TE-T)
- ARC-aehnliche Mini-Tests: Kann Phi Wissen transferieren?
- Messung: Sequenzen pro neue Domaene MIT vs. OHNE Transfer
- Forschungs-Phase, Ergebnisse bestimmen naechste Schritte

## Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).

```
1.  Lies BACKLOG.md                    — Was ist als Naechstes dran?
2.  Lies BASELINES.md                  — Wo stehen die Metriken?
3.  Lies das relevante Konzept-Dokument — Was ist die Idee dahinter?
4.  Lies den betroffenen Engine-Code   — IMMER erst verstehen, dann aendern
5.  Aendere EINE Sache                 — Minimal, testbar
6.  Teste: python review_phi.py        — Laeuft es noch?
7.  Committe                           — Kleiner Commit, klare Message
8.  Update BACKLOG.md                  — Erledigtes Item entfernen
9.  Beobachte Phi (20-30 Sequenzen)    — Wirkt die Aenderung?
10. Ergebnisse in observations/ loggen — Vorher/Nachher dokumentieren
11. Session-Log in sessions/ schreiben — Was gemacht, was offen
```

## Beruehrte Engine-Dateien

| Datei | Was wird geaendert | Phase |
|-------|--------------------:|:-----:|
| engine/goal_stack.py | get_current_focus() → Telos-Score statt Index | 1 |
| engine/evolution.py | CompetenceMatrix → Ring-Logik, LearningEngine | 2 |
| engine/dream.py | Goal-Priorisierung, Belief-Deduplikation | 1+2 |
| engine/consciousness.py | Curiosity verdrahten, Telos-Reflexion | 1+2 |
| engine/phi.py | exploration_weight() aktivieren | 1 |
| engine/intelligence.py | classify_goal_type() verbessern | 1 |
| data/consciousness/telos.json | NEU: Zweck-Hierarchie + Kompetenz-Ringe | 1 |

## Abhaengigkeiten

- **Unified Memory** (Schwester-Projekt): Kein Konflikt. UM = Gedaechtnis-Integration,
  Telos = Zweck-System. Synergie: Besseres Memory macht bessere Reflexionen moeglich.
- **Reihenfolge**: Unabhaengig, koennen parallel laufen.

## Prinzipien
1. **Zweck > Faehigkeit** — Erst wissen WARUM, dann lernen WIE
2. **Integration > Neubau** — Bestehende Systeme erweitern, nicht ersetzen
3. **Inkrementell** — Jede Phase liefert messbaren Wert
4. **Code > Prompts** — Verhalten im Code erzwingen, nicht per Prompt bitten
5. **Messen vor Optimieren** — Erst Baseline, dann Aenderung, dann Vergleich
6. **Einfachste Loesung zuerst** — Kein Over-Engineering

## Kritische Regeln
- KEINE Breaking Changes an bestehenden Interfaces
- Jede Aenderung muss `python review_phi.py` bestehen
- Erst Phase abschliessen und beobachten bevor naechste Phase starten
- Beobachten vor Weiterbauen: 20-30 Sequenzen nach jeder Phase
- Agent-Findings immer gegen Code verifizieren (~30% False Positives)
- Konzept-Dateien ZUERST durchdenken, dann Code schreiben

## Dokumente

| Datei | Inhalt |
|-------|--------|
| BACKLOG.md | Priorisierte Arbeitsliste — was ist dran? |
| BASELINES.md | Quantitative Messungen — wo stehen wir? |
| DECISIONS.md | Architektur-Entscheidungen (ADR-Format) |
| konzept/01-telos-hierarchie.md | Mission → Faehigkeiten → Skills |
| konzept/02-kompetenz-ringe.md | 5 Ringe mit Aufstiegs-Logik |
| konzept/03-reflexions-gate.md | Post-Sequence Telos-Reflexion |
| konzept/04-goal-priorisierung.md | Smart Goal Selection Algorithmus |
| konzept/05-dream-telos.md | Dream + Belief-Deduplikation |
| konzept/06-transfer-learning.md | AGI-Sprung: Wissen transferieren |
| sessions/ | Session-Logs (was wurde gemacht?) |
| observations/ | Phi-Beobachtungen (wirkt die Aenderung?) |

## Aktueller Status

- **Phase**: 0 — Konzept + Baselines
- **Blocker**: Keine
- **Letzte Session**: 2026-04-03 (Projektordner aufgesetzt)
- **Naechste Aktion**: Konzept-Dateien durcharbeiten, dann TE-Q1 starten
