# Tool Intelligence — Von Akkumulation zu Adaption

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Phis selbstgebaute Tools von statischen Dateien zu **lernenden Faehigkeiten** machen.
Aktuell: Tools werden gebaut, gezaehlt, manchmal geloescht. Keine echte Intelligenz.
Ziel: Phi versteht WARUM Tools funktionieren, passt Schwellen adaptiv an,
korreliert Tool-Qualitaet mit Goal-Erfolg und lernt aus Failure-Patterns.

## AGI-Saeule
**Multi-Memory + Selbstverbesserung** — Tools sind Phis erweiterte Kognition.
Schliesst Flywheel-Luecke L1 (Evaluations-Framework) und L3 (Learning-Transfer).

## Was existiert bereits
6 Module in `engine/tool_lifecycle/`:
- **metrics.py** — Health-Score (Success-Rate, Recency, Volume, Stability)
- **pruner.py** — Auto-Archivierung ungenutzter/schlechter Tools
- **dream_bridge.py** — Tool-Bewusstsein in Dream-Konsolidierung
- **meta_patterns.py** — Anti-Patterns (Sprawl, Failure-Loop, Orphans)
- **consolidator.py** — Auto-Merge aehnlicher Tools via ToolFoundry
- **promotion.py** — Exzellente Tools → Engine-Code-Kandidaten

## Was fehlt (die 6 AGI-Luecken)

| # | Luecke | Warum AGI-kritisch | Phase |
|---|--------|-------------------|-------|
| L1 | **Failure-Pattern-Analyse** | "Alle API-Tools scheitern an Timeout" erkennen | 1 |
| L2 | **Goal-Tool-Korrelation** | Tool-Wert haengt an WELCHE Ziele es ermoeglicht | 1 |
| L3 | **Adaptive Schwellenwerte** | Starre Konstanten vs. kontextabhaengige Entscheidungen | 2 |
| L4 | **Non-linearer Health-Score** | 50% Failure = unbrauchbar, nicht "mittelgut" | 2 |
| L5 | **Konsolidierungs-Wissenstransfer** | Merge darf akkumuliertes Wissen nicht verlieren | 3 |
| L6 | **Promotion-Feedback-Loop** | Phi muss lernen WAS exzellente Tools ausmacht | 3 |

## Phasen

### Phase 1: Kontextbewusstsein (Goal-Korrelation + Failure-Clustering)
- `record_use()` bekommt `goal_context` durchgereicht
- Failure-Reasons werden geclustert (aehnliche Fehler gruppieren)
- Dream-Bridge zeigt: "Dieses Tool half bei 5 verschiedenen Goal-Typen"
- Metrik: % der Tool-Nutzungen MIT Goal-Kontext

### Phase 2: Adaptive Intelligenz (Schwellen + Health-Formel)
- Health-Score mit Minimum-Gate: success_rate < 30% → max Health 3.0
- Pruning-Schwellen lernen aus Phi-Verhalten (letzte 50 Sequenzen)
- Kategorie-spezifische Thresholds (API-Tools vs. File-Tools)
- Metrik: False-Positive-Rate beim Pruning (gute Tools faelschlich archiviert)

### Phase 3: Wissenstransfer (Merge-Intelligenz + Promotion-Feedback)
- Bei Konsolidierung: Health-Score = gewichteter Durchschnitt der Quellen
- Promotion-Bericht: Welche Tool-Patterns machen Tools erfolgreich?
- ToolFoundry lernt aus promoted Tools (Prompt-Enrichment)
- Metrik: Health-Score neuer Tools vs. Durchschnitt

## Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).

```
1.  Lies BACKLOG.md                    — Was ist als Naechstes dran?
2.  Lies den betroffenen Engine-Code   — IMMER erst verstehen, dann aendern
3.  Aendere EINE Sache                 — Minimal, testbar
4.  Teste: python review_phi.py        — Laeuft es noch?
5.  Committe                           — Kleiner Commit, klare Message
6.  Beobachte Phi (20-30 Sequenzen)    — Misst der Fix was er soll?
7.  Ergebnisse in observations/ loggen — Vorher/Nachher dokumentieren
```

## Prinzipien
1. **Messen vor Optimieren** — Erst Baseline, dann Aenderung, dann Vergleich
2. **Code > Prompts** — Verhalten erzwingen, nicht erbitten
3. **Einfachste Loesung zuerst** — Adaptive Schwellen erst wenn starre versagen
4. **Integration > Neubau** — Bestehende 6 Module erweitern, nicht ersetzen
5. **Inkrementell** — Ein Fix, ein Commit, ein Audit

## Kritische Regeln
- KEINE Breaking Changes an bestehenden tool_lifecycle-Interfaces
- Jede Aenderung muss `python review_phi.py` bestehen
- Health-Score-Aenderungen immer mit Vorher/Nachher-Vergleich
- Schwellenwert-Aenderungen dokumentieren in DECISIONS.md

## Referenzen
- `engine/tool_lifecycle/` — Die 6 bestehenden Module
- `engine/evolution.py` — ToolCurator + ToolFoundry (Konsolidierung)
- `engine/toolchain.py` — Tool-Erstellung und -Nutzung
- `.planning/META.md` — Flywheel-Luecken L1-L4
- `data/tools/registry.json` — Aktuelle Tool-Registry
- `data/tools/metrics.json` — Aktuelle Metriken (sobald befuellt)
