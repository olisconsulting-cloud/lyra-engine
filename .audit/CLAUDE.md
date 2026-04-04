# Phi Audit — Instruktionen fuer Claude Code

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Was ist das hier?

Dieser Ordner ist der Continuous-Improvement-Loop fuer Phi (Lyra).
Oliver und Claude Code arbeiten hier gemeinsam an der Verbesserung der Engine.
Phi selbst ist nicht beteiligt — das ist reine Qualitaetssicherung von aussen.

## Was ist Phi?

Phi ist eine autonome KI-Engine (~15.000 Zeilen Python, 35 Dateien in `engine/`).
Sie arbeitet mit lokalen LLMs in einem agentic Loop:
Perceive -> Plan -> Execute -> Reflect -> Learn.

Kern: `engine/consciousness.py` (~3.600 Zeilen) orchestriert ~30 Subsysteme.
6 neue Module wurden im God-Class-Refactoring extrahiert, aber noch nicht alle aktiviert.

## Dein Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).
Python: 3.14, kein venv noetig.

```
1.  Lies .audit/BACKLOG.md              — Was ist das Naechste?
2.  Lies FINDINGS.md zum naechsten Item — Kontext + Done-Definition
2b. Verifiziere Zeilennummern im Code  — Zeilen koennen sich verschoben haben!
3.  Lies den betroffenen Code           — IMMER erst verstehen, dann aendern
4.  Aendere EINE Sache                  — Minimal, testbar
5.  Teste: python review_phi.py         — Laeuft es noch?
6.  Committe                            — Kleiner Commit, klare Message
7.  Update FINDINGS.md                  — Status auf "fixed", dann nach FINDINGS_ARCHIVE.md
8.  Update BACKLOG.md                   — Erledigtes Item entfernen
9.  Session-Log schreiben               — Was gemacht, was offen
10. Kernmetriken-Tabelle aktualisieren  — Wenn ein Bug gefixt oder Modul aktiviert wurde
```

## Prinzipien

1. **Inkrementell** — Bauen -> Testen -> Committen -> Naechste Ebene
2. **Beobachten vor Weiterbauen** — Verstehe den Effekt bevor du weitergehst
3. **Nie Big-Bang** — Eine Datei, ein Fix, ein Commit
4. **Erst lesen, dann aendern** — Min. 50 Zeilen Kontext um jede Aenderung
5. **Token-Effizienz ist Kernmetrik** — Jeder Token in Phis Perception kostet Rechenzeit
6. **Stabilitaet vor Features** — Ein Fix > drei neue Features
7. **Agent-Findings verifizieren** — JEDEN Zeilenreferenz im Code lesen, JEDE Signatur
   gegen die `def`-Zeile pruefen. Agents halluzinieren Zeilennummern und Parameter-
   reihenfolgen. Beim initialen Audit waren 2/3 CRITICAL-Findings falsch.

## Kernmetriken

| Metrik | Aktuell (2026-04-04) | Ziel |
|--------|----------------------|------|
| Token-Verschwendung/Seq | ~8.000 (Pipeline-Budget) | <3.000 |
| Verifizierte Bugs | 0 offen | 0 |
| Inaktive Module | 2 von 3 | 0 von 3 |
| Dead Code Zeilen | ~50 | 0 |

Aktualisiere diese Tabelle am Ende jeder Session die einen Bug fixt oder ein Modul aktiviert.

## Schluessel-Dateien

| Datei | Zeilen | Rolle |
|-------|--------|-------|
| engine/consciousness.py | ~3.600 | Haupt-Orchestrator |
| engine/intelligence.py | ~987 | SemanticMemory, Skills, Strategies |
| engine/evolution.py | ~932 | Rhythm, Benchmark, ToolFoundry, MetaCog |
| engine/llm_router.py | ~640 | Multi-Provider LLM Routing |
| engine/sequence_intelligence.py | ~428 | Stuck-Detection, Metriken, Planung |
| engine/sequence_finisher.py | ~314 | End-of-Sequence Aktionen (inaktiv) |
| engine/perception_pipeline.py | ~184 | Gewichtete Wahrnehmung (AKTIV) |
| engine/unified_memory.py | ~197 | Cross-Domain Memory (inaktiv) |
| engine/sequence_runner.py | ~180 | Composable Sequenz-Phasen (inaktiv) |
| review_phi.py | ~354 | Pre-Flight-Check (14 Pruefungen) |

## Vision

Phi entwickelt sich Richtung sichere, kompetente Superintelligenz.
Jede Session macht Phi ein kleines Stueck besser.
Nicht schneller. Nicht groesser. Besser. Stabiler. Effizienter. Sicherer.

## Konventionen

- Code-Kommentare: Deutsch (Umlaute als ae/oe/ue in Code)
- Commit-Messages: Deutsch, Format `typ: beschreibung`
- Kein Code ohne Regressions-Check (`python review_phi.py`)
- .audit/ Dateien immer mit-committen
- Session-Logs: `sessions/YYYY-MM-DD_kurzbeschreibung.md`
- Fixed Findings: nach `FINDINGS_ARCHIVE.md` verschieben, FINDINGS.md nur fuer offene
- Bei Merge-Konflikten in .audit/: IMMER manuell loesen, beide Versionen lesen

## Aktueller Status (nach jeder Session aktualisieren)

- **Naechster Fix**: A1b (UnifiedMemory Perception-Einbindung) — siehe BACKLOG.md
- **Offene Bugs**: 0 — alle verifzierten Bugs gefixt
- **Gefixt**: C1, H4, H5, H6, T2, T6, T7, S5, A1a. H1-H3/A1d/A2/A3/A4 wontfix.
- **Inaktive Module**: 2 (UnifiedMemory [teilweise aktiv], SequenceRunner)
- **Letzte Session**: 2026-04-04 (PerceptionPipeline aktiviert — 19 Channels, 8k Budget)
