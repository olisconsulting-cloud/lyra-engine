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

```
1. Lies .audit/BACKLOG.md              — Was ist das Naechste?
2. Lies .audit/FINDINGS.md             — Kontext zum aktuellen Finding
3. Lies den betroffenen Code           — IMMER erst verstehen, dann aendern
4. Aendere EINE Sache                  — Minimal, testbar
5. Teste: python review_phi.py         — Laeuft es noch?
6. Committe                            — Kleiner Commit, klare Message
7. Update FINDINGS.md                  — Status auf "fixed"
8. Update BACKLOG.md                   — Naechstes Item nach oben
9. Session-Log schreiben               — Was gemacht, was offen
```

## Prinzipien

1. **Inkrementell** — Bauen -> Testen -> Committen -> Naechste Ebene
2. **Beobachten vor Weiterbauen** — Verstehe den Effekt bevor du weitergehst
3. **Nie Big-Bang** — Eine Datei, ein Fix, ein Commit
4. **Erst lesen, dann aendern** — Min. 50 Zeilen Kontext um jede Aenderung
5. **Token-Effizienz ist Kernmetrik** — Jeder Token in Phis Perception kostet Rechenzeit
6. **Stabilitaet vor Features** — Ein Fix > drei neue Features
7. **Agent-Findings verifizieren** — Audit-Agents machen Fehler (2/3 CRITICAL waren falsch)

## Kernmetriken

| Metrik | Aktuell (2026-04-03) | Ziel |
|--------|----------------------|------|
| Token-Verschwendung/Seq | ~5.000-9.000 | <3.000 |
| Verifizierte Bugs | 7 offen | 0 |
| Inaktive Module | 4 von 4 | 0 von 4 |
| Dead Code Zeilen | ~50 | 0 |

## Schluessel-Dateien

| Datei | Zeilen | Rolle |
|-------|--------|-------|
| engine/consciousness.py | ~3.600 | Haupt-Orchestrator |
| engine/intelligence.py | ~987 | SemanticMemory, Skills, Strategies |
| engine/evolution.py | ~932 | Rhythm, Benchmark, ToolFoundry, MetaCog |
| engine/llm_router.py | ~640 | Multi-Provider LLM Routing |
| engine/sequence_intelligence.py | ~428 | Stuck-Detection, Metriken, Planung |
| engine/sequence_finisher.py | ~314 | End-of-Sequence Aktionen (inaktiv) |
| engine/perception_pipeline.py | ~184 | Gewichtete Wahrnehmung (inaktiv) |
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
- Session-Logs: `sessions/YYYY-MM-DD_NNN.md`
