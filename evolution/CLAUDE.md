# Evolution Hub — Phis AGI-Verbesserungsprojekte

> Jedes Projekt hier staerkt eine der 5 AGI-Saeulen oder schliesst eine Flywheel-Luecke.
> Lies ZUERST dieses File. Dann geh ins relevante Projektverzeichnis.

## Mission
Die Bruecke zwischen "Phi fuehrt Aufgaben aus" und "Phi verbessert sich selbst".
Jedes Projekt hier veraendert nicht WAS Phi tut, sondern WIE Phi denkt, lernt und handelt.

## Aktive Projekte

| Projekt | AGI-Saeule | Status | Hebel |
|---------|-----------|--------|-------|
| [enforcement/](enforcement/) | Meta-Ebene (Flywheel) | **Aktiv** | Hoechster Sofort-Effekt |
| [dream-goals/](dream-goals/) | Taktische Ebene (Lernen) | Geplant | Hoechster Langzeit-Effekt |
| [perception/](perception/) | Hybride Intelligenz | Geplant | Hoechster Effizienz-Effekt |
| [telos/](telos/) | Hybride Intelligenz | Phase 1 teilweise | Zweck-geleitete Goals |
| [unified-memory/](unified-memory/) | Multi-Memory | Baselines gemessen | 5 Systeme vereinen |

## Abhaengigkeiten

```
enforcement ──→ dream-goals ──→ perception
    │                │               │
    │                │               └── Braucht: Kanaele registrieren
    │                └── Braucht: Enforcement aktiv (sonst ignoriert Phi die Goals)
    └── Keine Abhaengigkeit (sofort umsetzbar)

telos + unified-memory: Unabhaengig, koennen parallel laufen
```

## Prinzipien (gelten fuer ALLE Projekte)
1. **Code > Prompts** — Verhalten erzwingen, nicht erbitten
2. **Messen > Vermuten** — Baseline vor Aenderung, Vergleich danach
3. **Inkrementell** — Ein Fix, ein Commit, ein Audit
4. **Integration > Neubau** — Bestehende Systeme verbinden
5. **Beobachten vor Weiterbauen** — 20-30 Sequenzen nach jedem Feature

## Workflow pro Projekt
```
1. CLAUDE.md lesen (Mission + Kontext)
2. BACKLOG.md lesen (Was ist dran?)
3. Engine-Code lesen (Verstehen)
4. EINE Sache aendern (Minimal)
5. python review_phi.py (Gate)
6. Committen
7. Phi 20-30 Seq beobachten
8. Ergebnisse in observations/ loggen
```

## Referenzen
- `.planning/META.md` — Flywheel + Metriken + Luecken
- `.audit/BACKLOG.md` — Operativer Backlog
- `CLAUDE.md` (Root) — Gesamtarchitektur
