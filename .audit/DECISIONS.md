# Phi Architektur-Entscheidungen

> Format: ADR (Architecture Decision Record) — Nygard-Format erweitert.
> Nummerierung: ADR-NNN, fortlaufend.
> Nur lesen wenn eine neue Architektur-Entscheidung ansteht.

---

### ADR-001: Inkrementelles Audit statt Big-Bang-Rewrite

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Phi hat 15.000 Zeilen mit 30+ Subsystemen. Ein Rewrite wuerde
  alles gleichzeitig kaputt machen.
- **Entscheidung**: Ein Finding pro Arbeitsblock fixen. Erst CRITICAL, dann HIGH,
  dann MEDIUM. Jeder Fix wird einzeln committed und getestet.
- **Gewinn**: Jeder Commit ist ein funktionierender Zustand. Rollback jederzeit moeglich.
- **Risiko**: Langsamer als Rewrite. Mitigation: Quick-Wins zuerst, groesste Hebel priorisieren.
- **Revisit wenn**: Engine-Groesse > 25.000 Zeilen oder > 50 offene Findings akkumulieren.

### ADR-002: .audit/ als lokales Tracking statt Issue-Tracker

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Claude Code hat keinen Kontext zwischen Sessions. GitHub Issues
  erfordern API-Calls und sind nicht im lokalen Repo durchsuchbar.
- **Entscheidung**: Alles in .audit/ als Markdown. Git-tracked, lokal lesbar,
  kein externer Service noetig. BACKLOG.md < 50 Zeilen fuer sofortiges Scannen.
- **Gewinn**: Sofortiger Context-Aufbau bei Session-Start. Keine externe Abhaengigkeit.
- **Risiko**: Veraltet wenn nicht konsequent aktualisiert. Mitigation: Workflow in
  CLAUDE.md erzwingt Update. Verfallsdaten auf Findings.
- **Revisit wenn**: > 30 Findings gleichzeitig offen oder > 3 aktive Contributors.

### ADR-003: Bestehende Module aktivieren statt neu schreiben

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: SequenceRunner, SequenceFinisher, PerceptionPipeline, UnifiedMemory
  existieren als Code, werden instanziiert, aber nie aufgerufen.
- **Entscheidung**: Schrittweise verdrahten statt alternatives Design.
  Erst Signatur-Bugs fixen, dann einzeln aktivieren und testen.
- **Gewinn**: Weniger neuer Code, schnellere Aktivierung, bestehendes Design nutzen.
- **Risiko**: APIs passen nicht 1:1 zur bestehenden Logik. Mitigation: Pro Modul
  pruefen, Adapter-Schicht wenn noetig.
- **Revisit wenn**: Ein Modul > 3 Adapter braucht um zu funktionieren — dann Redesign.

### ADR-004: review_phi.py als Regressions-Gate

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Phi hat ein Pre-Flight-Check-Script das 14 Pruefungen ausfuehrt.
- **Entscheidung**: Jeder Fix muss `python review_phi.py` bestehen.
  Script wird bei Bedarf erweitert.
- **Gewinn**: Automatisiertes Regressions-Gate ohne extra Test-Framework.
- **Risiko**: review_phi.py selbst koennte Bugs haben oder zu wenig pruefen.
  Mitigation: Bei Bedarf um quantitative Metriken erweitern (ruff, radon).
- **Revisit wenn**: Unit-Tests mit pytest aufgebaut sind — dann review_phi.py als
  Smoke-Test behalten, pytest als primaeres Gate.

### ADR-005: Agent-Findings immer gegen Code verifizieren

- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Beim initialen Audit meldeten Agents 3 CRITICAL Bugs.
  Bei manueller Verifikation waren 2 davon FALSE POSITIVES:
  - `_installed_packages` war korrekt initialisiert (Reihenfolge stimmte)
  - `self.meta_rules` existierte als `self.seq_intel` (Agent las falsch)
  - `LearningEngine._load_log` hatte bereits try/except
- **Entscheidung**: Jedes Agent-Finding wird gegen den tatsaechlichen Code
  verifiziert. JEDEN Zeilenreferenz lesen, JEDE Signatur pruefen.
  False Positives als FP in FINDINGS.md dokumentieren.
- **Gewinn**: Keine falschen Fixes. Vertrauen in die Findings-Liste.
- **Risiko**: Mehr Aufwand pro Audit. Mitigation: Nur Top-10 Findings verifizieren,
  LOW-Severity kann mit Vorbehalt uebernommen werden.
- **Revisit wenn**: False-Positive-Rate unter 5% sinkt — dann Verifikation lockern.
