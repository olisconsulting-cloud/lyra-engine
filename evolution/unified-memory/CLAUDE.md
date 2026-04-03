# Unified Memory — Phis Lernmaschine

## Mission
Die 5 isolierten Lern-Systeme zu EINEM kohärenten Gedächtnis vereinen.
Nicht "5 Datenbanken die nebeneinander existieren" — sondern ein System
das aus Erfolgen UND Fehlern lernt, Muster generalisiert und Wissen transferiert.

Das ist der AGI-Kern: Nicht die Loop, nicht die Tools, nicht die LLMs —
sondern WIE Phi aus Erfahrung lernt und dieses Wissen auf neue Situationen anwendet.

## Problem (Status Quo)
```
SkillLibrary ──── speichert Tool-Reihenfolgen aus Erfolgen
FailureMemory ─── speichert was schiefging
SemanticMemory ── speichert Erkenntnisse (TF-IDF)
MetaRuleEngine ── erzwingt harte Guards aus Mustern
MetaCognition ─── speichert Bottlenecks + Strategy-Changes
Dream ─────────── konsolidiert Beliefs/Strategies, NICHT Skills
```

Diese 5 Systeme reden NICHT miteinander:
- Skills lernen nur aus Erfolgen, nie aus Fehlern
- Kein Transfer zwischen ähnlichen Skills
- Dream konsolidiert die Skill-Library nicht
- Skill-Retrieval ist eindimensional (nur goal_type)
- Abstract Steps codieren WAS (Tool-Reihenfolge), nicht WARUM (Strategie)

## Ziel-Architektur
```
UnifiedMemory (ein Interface, ein Retrieval)
  ├── Positiv-Wissen: "Das hat funktioniert" (aus SkillLibrary)
  ├── Negativ-Wissen: "Das ist gescheitert" (aus FailureMemory)
  ├── Semantisch: "Das weiss ich" (aus SemanticMemory)
  ├── Prozess: "So arbeite ich am besten" (aus MetaCognition)
  └── Guards: "Das darf nie passieren" (aus MetaRuleEngine)

Konsolidierung (Dream):
  - Ähnliche Skills mergen → generalisierte Muster
  - Failure-Lektionen in Skills einbetten
  - Veraltete Skills prunen

Retrieval (eine Anfrage → bestes Wissen):
  - Semantische Suche über ALLE Quellen
  - Skill + Anti-Pattern + Kontext in einem Prompt-Block
```

## Architektur-Prinzipien
1. **Integration > Neubau** — Bestehende Systeme verbinden, nicht ersetzen
2. **Inkrementell** — Jede Phase liefert messbaren Wert für Phi
3. **Code > Prompts** — Verhalten im Code erzwingen, nicht per Prompt bitten
4. **Messen vor Optimieren** — Erst Baseline, dann Änderung, dann Vergleich
5. **Einfachste Lösung zuerst** — Kein Over-Engineering

## Phasen

### Phase 1: Baseline + Quick Wins
- [ ] Messen: Wie oft bekommt Phi aktuell einen Skill-Prompt? (Logging)
- [ ] Messen: Wie oft matcht FailureMemory.check() auf aktuelle Goals?
- [ ] Fix: success_count >= 2 → >= 1 im ProactiveLearner
- [ ] Fix: Bei Skill-Extraktion FailureMemory-Lektionen mit einbetten
- [ ] Fix: Skill-Retrieval um semantische Suche erweitern (TF-IDF aus SemanticMemory nutzen)

### Phase 2: Dream-Integration
- [ ] Dream liest skill_library/index.json
- [ ] Dream mergt ähnliche Skills (Jaccard auf abstract_steps)
- [ ] Dream prunet Skills mit avg_score < 5
- [ ] Dream generiert "why"-Feld pro Skill (LLM-Zusammenfassung)

### Phase 3: Unified Retrieval
- [ ] Ein build_context() das Skills + Failures + SemanticMemory kombiniert
- [ ] Anti-Pattern-Injection: "NICHT so: ..." bei bekannten Fallen
- [ ] Cross-Domain-Transfer: Ähnliche Skills aus anderen goal_types finden

### Phase 4: Transfer-Learning
- [ ] Meta-Patterns aus Skill-Clustern ableiten
- [ ] Skill-Komposition: Zwei Skills zu einem neuen kombinieren
- [ ] Generalisierte Strategien die über goal_types hinweg gelten

## Quell-Dateien (im Lyra-Repo)
- `engine/skill_library.py` — SkillLibrary Klasse
- `engine/intelligence.py` — SemanticMemory + classify_goal_type
- `engine/quantum.py` — FailureMemory, CriticAgent, SkillComposer
- `engine/meta_rules.py` — MetaRuleEngine
- `engine/evolution.py` — MetaCognition, AdaptiveRhythm
- `engine/dream.py` — DreamEngine (Konsolidierung)
- `engine/consciousness.py` — Hauptloop (nutzt alle Systeme)
- `engine/proactive_learner.py` — ProactiveLearner (Retrieval-Orchestrator)
- `data/skill_library/index.json` — 12 gespeicherte Skills
- `data/consciousness/failures.json` — Failure-Memory
- `data/consciousness/skills.json` — Skill-Tracker (Zähler)
- `data/consciousness/metacognition.json` — Selbstreflexionen

## Metriken (Wie messen wir Fortschritt?)
- **Skill-Hit-Rate**: % der Sequenzen wo ein passender Skill gefunden wird
- **Skill-Relevanz**: Phi's Rating in Sequenzen MIT vs OHNE Skill-Prompt
- **Wiederholungsfehler**: Gleicher Fehler-Typ tritt erneut auf trotz FailureMemory
- **Transfer-Score**: Skill aus Domain A wird erfolgreich in Domain B genutzt
- **Dream-Effektivität**: Skills vor/nach Dream-Konsolidierung

## Kritische Regeln
- KEINE Breaking Changes an bestehenden Interfaces
- Jede Änderung muss mit `python review_phi.py` bestehen
- Erst Phase 1 abschließen und beobachten bevor Phase 2 starten
- Beobachten vor Weiterbauen: 20-30 Sequenzen nach jeder Phase
