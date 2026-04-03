# Unified Memory — Architektur-Entscheidungen

> Format: ADR (Architecture Decision Record) — Nygard-Format erweitert.
> Nummerierung: ADR-UM-NNN (getrennt von .audit/DECISIONS.md).
> Nur lesen wenn eine neue Architektur-Entscheidung ansteht.

---

### ADR-UM-001: Integration-Layer ueber bestehende Systeme statt Neubau

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Phi hat 5 funktionierende Lern-Systeme (SkillLibrary, FailureMemory,
  SemanticMemory, MetaRuleEngine, MetaCognition). Das Problem ist nicht die Qualitaet
  der Teile — es ist das Fehlen der Verbindungen.
- **Entscheidung**: Neue Module (SkillEnricher, UnifiedRetrieval, DreamSkillConsolidator)
  UEBER die bestehenden Systeme legen. Keine Klasse wird geloescht oder umgeschrieben.
  Bestehende APIs bleiben stabil.
- **Gewinn**: Kein Risiko fuer bestehende Funktionalitaet. Inkrementell testbar.
  Jedes neue Modul liefert isoliert Wert.
- **Risiko**: Integration-Layer koennte zu duenner Wrapper werden der nichts
  Neues leistet. Mitigation: Jede Phase hat messbare Metriken (BASELINES.md).
- **Revisit wenn**: Ein bestehendes System so fundamental geaendert werden muss
  dass der Wrapper mehr Komplexitaet erzeugt als ein Redesign.

### ADR-UM-002: Baseline messen bevor Code geaendert wird

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Ohne Vorher-Messung koennen wir nicht wissen ob eine Aenderung
  die Skill-Hit-Rate verbessert oder verschlechtert hat. "Fuehlt sich besser an"
  ist kein AGI-taugliches Qualitaets-Gate.
- **Entscheidung**: Phase 1 beginnt mit reinen Messungen (UM-B1 bis UM-B5).
  Erst wenn alle Baselines in BASELINES.md stehen, werden Code-Aenderungen gemacht.
  Nach jeder Phase: gleiche Metriken erneut messen, Vorher/Nachher vergleichen.
- **Gewinn**: Evidenzbasierte Entwicklung. Koennen nachweisen ob Unified Memory
  Phi tatsaechlich verbessert — nicht nur architektonisch "schoener" macht.
- **Risiko**: Messung kostet Zeit und Sequenzen (30 pro Baseline-Runde).
  Mitigation: Messungen koennen teilweise automatisiert werden (Logging in consciousness.py).
- **Revisit wenn**: Automatisierte Metriken in review_phi.py integriert sind —
  dann manuelle Baseline-Runden ersetzen.

### ADR-UM-003: Eigener Projektordner mit eigener CLAUDE.md

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Unified Memory ist kein einzelner Fix oder Feature. Es ist ein
  Multi-Phasen-Architektur-Projekt das die Grundlage fuer Phis Lernfaehigkeit baut.
  Es braucht eigene Arbeitslisten, Metriken, Entscheidungen und Session-Logs —
  unabhaengig vom Haupt-.audit/-Zyklus.
- **Entscheidung**: `evolution/unified-memory/` als eigenstaendige Projekt-Einheit
  mit eigenem CLAUDE.md (Workflow), BACKLOG.md (Arbeit), BASELINES.md (Metriken),
  DECISIONS.md (ADRs), sessions/ (Logs), observations/ (Phi-Beobachtungen).
  Format folgt den bewaehrten Patterns aus `.audit/`.
- **Gewinn**: Session-Kontinuitaet. Jede neue Claude-Session liest CLAUDE.md →
  BACKLOG.md → letzte Session und weiss sofort wo es weitergeht.
  Trennung von Engine-Audit (.audit/) und Architektur-Projekt (evolution/).
- **Risiko**: Zwei parallele Tracking-Systeme (.audit/ + evolution/unified-memory/)
  koennten divergieren. Mitigation: Engine-Bugs gehen immer in .audit/FINDINGS.md,
  nie in den Projektordner. Klare Grenze: .audit/ = Bugs + Ops, evolution/ = Architektur.
- **Revisit wenn**: Mehr als 3 Projekte unter evolution/ laufen — dann ggf.
  uebergreifendes Tracking noetig.
