# Unified Memory — Phis Lernmaschine

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Phis 5 isolierte Lern-Systeme zu EINEM kohaerenten Gedaechtnis vereinen.
Der AGI-Kern: WIE Phi aus Erfahrung lernt und Wissen auf neue Situationen uebertraegt.

## Was ist das hier?
Dieses Projekt baut die Bruecken zwischen SkillLibrary, FailureMemory,
SemanticMemory, MetaRuleEngine und MetaCognition. Integration ueber bestehende
Systeme — kein Neubau, keine Breaking Changes.

## Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).

```
1.  Lies BACKLOG.md                    — Was ist als Naechstes dran?
2.  Lies BASELINES.md                  — Wo stehen die Metriken?
3.  Lies den betroffenen Engine-Code   — IMMER erst verstehen, dann aendern
4.  Aendere EINE Sache                 — Minimal, testbar
5.  Teste: python review_phi.py        — Laeuft es noch?
6.  Committe                           — Kleiner Commit, klare Message
7.  Update BACKLOG.md                  — Erledigtes Item entfernen
8.  Beobachte Phi (20-30 Sequenzen)    — Misst der Fix was er soll?
9.  Ergebnisse in observations/ loggen — Vorher/Nachher dokumentieren
10. Session-Log in sessions/ schreiben — Was gemacht, was offen
```

## Prinzipien
1. **Integration > Neubau** — Bestehende Systeme verbinden, nicht ersetzen
2. **Inkrementell** — Jede Phase liefert messbaren Wert fuer Phi
3. **Code > Prompts** — Verhalten im Code erzwingen, nicht per Prompt bitten
4. **Messen vor Optimieren** — Erst Baseline, dann Aenderung, dann Vergleich
5. **Einfachste Loesung zuerst** — Kein Over-Engineering

## Kritische Regeln
- KEINE Breaking Changes an bestehenden Interfaces
- Jede Aenderung muss `python review_phi.py` bestehen
- Erst Phase abschliessen und beobachten bevor naechste Phase starten
- Beobachten vor Weiterbauen: 20-30 Sequenzen nach jeder Phase
- Agent-Findings immer gegen Code verifizieren (~30% False Positives)

## Dokumente

| Datei | Inhalt |
|-------|--------|
| BACKLOG.md | Priorisierte Arbeitsliste — was ist dran? |
| BASELINES.md | Quantitative Messungen — wo stehen wir? |
| DECISIONS.md | Architektur-Entscheidungen (ADR-Format) |
| ANALYSE.md | Ist-Zustand der 5 Systeme (Snapshot vor Phase 1) |
| ARCHITEKTUR.md | Ziel-Architektur, 3 neue Module, Integrationspunkte |
| sessions/ | Session-Logs (was wurde gemacht?) |
| observations/ | Phi-Beobachtungen (wirkt die Aenderung?) |

## Aktueller Status

- **Phase**: 1 — Baseline + Quick Wins
- **Blocker**: Keine
- **Letzte Session**: 2026-04-03 (Projektordner aufgesetzt, Analyse abgeschlossen)
- **Naechste Aktion**: Baselines messen (UM-B1, UM-B2 in BACKLOG.md)
