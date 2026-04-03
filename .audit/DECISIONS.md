# Phi Architektur-Entscheidungen

> Format: ADR (Architecture Decision Record)
> Nummerierung: ADR-NNN, fortlaufend

---

### ADR-001: Inkrementelles Audit statt Big-Bang-Rewrite
- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Phi hat 15.000 Zeilen mit 30+ Subsystemen. Ein Rewrite wuerde
  alles gleichzeitig kaputt machen.
- **Entscheidung**: Ein Finding pro Arbeitsblock fixen. Erst CRITICAL, dann HIGH,
  dann MEDIUM. Jeder Fix wird einzeln committed und getestet.
- **Konsequenz**: Langsamer, aber jeder Commit ist ein funktionierender Zustand.

### ADR-002: .audit/ als lokales Tracking statt Issue-Tracker
- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Claude Code hat keinen Kontext zwischen Sessions. GitHub Issues
  erfordern API-Calls und sind nicht im lokalen Repo durchsuchbar.
- **Entscheidung**: Alles in .audit/ als Markdown. Git-tracked, lokal lesbar,
  kein externer Service noetig. BACKLOG.md < 50 Zeilen fuer sofortiges Scannen.
- **Konsequenz**: Manuell gepflegt. Risiko: Veraltet wenn nicht konsequent
  aktualisiert. Mitigation: CLAUDE.md-Workflow erzwingt Update am Session-Ende.

### ADR-003: Bestehende Module aktivieren statt neu schreiben
- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: SequenceRunner, SequenceFinisher, PerceptionPipeline, UnifiedMemory
  existieren als Code, werden instanziiert, aber nie aufgerufen.
- **Entscheidung**: Schrittweise verdrahten statt alternatives Design.
  Erst Signatur-Bugs fixen, dann einzeln aktivieren und testen.
- **Konsequenz**: Weniger neuer Code. Anpassungen noetig wo APIs nicht 1:1 passen.

### ADR-004: review_phi.py als Regressions-Gate
- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Phi hat ein Pre-Flight-Check-Script das 14 Pruefungen ausfuehrt.
- **Entscheidung**: Jeder Fix muss `python review_phi.py` bestehen.
  Script wird bei Bedarf erweitert.
- **Konsequenz**: review_phi.py wird zum Test-Framework bis Unit-Tests aufgebaut sind.

### ADR-005: Agent-Findings immer gegen Code verifizieren
- **Datum**: 2026-04-03
- **Status**: Accepted
- **Kontext**: Beim initialen Audit meldeten Agents 3 CRITICAL Bugs.
  Bei manueller Verifikation waren 2 davon FALSE POSITIVES:
  - `_installed_packages` war korrekt initialisiert (Reihenfolge stimmte)
  - `self.meta_rules` existierte als `self.seq_intel` (Agent las falsch)
  - `LearningEngine._load_log` hatte bereits try/except
- **Entscheidung**: Jedes Agent-Finding wird gegen den tatsaechlichen Code
  verifiziert bevor es in FINDINGS.md aufgenommen oder gefixt wird.
  False Positives werden als FP dokumentiert.
- **Konsequenz**: Mehr Aufwand pro Audit, aber keine falschen Fixes.
