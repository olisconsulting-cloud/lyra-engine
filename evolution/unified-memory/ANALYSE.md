# Analyse: Phis Lern-Systeme — Ist-Zustand

## Die 5 Systeme im Detail

### 1. SkillLibrary (`engine/skill_library.py`)
**Was:** Prozedurale Templates aus erfolgreichen Sequenzen (Voyager-inspiriert)
**Speichert:** Tool-Reihenfolgen + abstrakte Steps + Score/Rating
**Retrieval:** Nur über `goal_type` (eindimensional)
**Trigger:** Bei finish_sequence wenn plan_score >= 5 UND rating >= 5
**Max:** 30 Skills, schlechteste fliegen raus
**Aktuell:** 12 Skills, davon 7x "sonstiges" (→ classify_goal_type fix am 03.04.)

**Problem:** Die abstract_steps sind mechanische Tool→Phase-Mappings:
```
read_file → "lesen", web_search → "recherche", write_file → "schreiben"
```
Das ist Level 1 (Voyager). Für AGI brauchen wir Level 2 (MemP):
"Erst Interface verstehen, dann minimal implementieren, dann testen"
→ Strategie, nicht Tool-Sequenz.

### 2. FailureMemory (`engine/quantum.py`)
**Was:** Strukturierte Fehler mit Ziel/Ansatz/Error/Lektion
**Speichert:** Auch Erfolge (seit Phase 2 des Refactors)
**Retrieval:** Wort-Overlap auf goal + approach (min 2 Wörter)
**Trigger:** Bei Tool-Fehlern + bei Successes
**Max:** 100 Einträge

**Problem:** Komplett isoliert von SkillLibrary. Wenn Phi einen
"api_integration"-Skill abruft, bekommt es die Erfolgs-Vorlage,
aber NICHT die 3 bekannten Fallen aus FailureMemory.

### 3. SemanticMemory (`engine/intelligence.py`)
**Was:** TF-IDF-basierte Erkenntnisse aus finish_sequence
**Speichert:** Content + Metadata (goal_type, importance)
**Retrieval:** Cosine-Similarity + Goal-Type-Boost + Importance
**Max:** Unbegrenzt (wird nicht gepruned)

**Stärke:** Bestes Retrieval-System (semantisch + mehrdimensional)
**Schwäche:** Wird von SkillLibrary nicht genutzt.
SkillLibrary hat eigenes, primitives Retrieval (nur goal_type).

### 4. MetaRuleEngine (`engine/meta_rules.py`)
**Was:** Harte Guards aus 3x erkannten Mustern
**Speichert:** Pattern-Counts + Rule-Templates
**Retrieval:** Wird direkt in Perception injiziert
**Trigger:** MetaCognition-Analyse + step_limit checks

**Stärke:** Code erzwingt Verhalten (Code > Prompts Prinzip)
**Problem:** Statische Templates, kein Lernen aus neuen Mustern

### 5. MetaCognition (`engine/evolution.py`)
**Was:** Bottleneck + Strategy-Change pro Sequenz
**Speichert:** Auch wasted_steps, productive_steps, key_decision
**Retrieval:** Letzte 3 Einträge in Perception + Pattern-Analyse
**Trigger:** Bei jeder finish_sequence

**Stärke:** Prozess-Wissen ("WIE arbeite ich"), nicht Fakten-Wissen
**Problem:** Feeds in MetaRuleEngine, aber nicht in SkillLibrary

## Datenfluss-Analyse

```
finish_sequence aufgerufen
    │
    ├──→ SkillLibrary.extract_from_sequence()  [nur Erfolge]
    ├──→ SemanticMemory.store()                [Erkenntnisse]
    ├──→ MetaCognition.record()                [Bottlenecks]
    ├──→ FailureMemory.record()                [bei Fehlern]
    └──→ MetaRuleEngine.learn_from_metacog()   [Pattern-Counts]

Nächste Sequenz startet
    │
    ├──→ SkillLibrary.build_skill_prompt()     [goal_type Match]
    ├──→ FailureMemory.check()                 [Wort-Overlap]
    ├──→ FailureMemory.get_summary()           [Top 3 Lektionen]
    ├──→ ProactiveLearner.build_context()      [Skill + Semantic + Cache]
    ├──→ MetaCognition.get_recent_insights()   [Letzte 3 Reflexionen]
    └──→ MetaRuleEngine.get_prompt_injections()[Harte Regeln]
```

**Beobachtung:** 6 separate Prompt-Injektionen die unabhängig voneinander
in die Perception fließen. Keine Priorisierung, keine Deduplizierung,
keine Cross-Referenzierung.

## Quantitative Fakten

| Metrik | Wert |
|---|---|
| Skills gespeichert | 12 |
| Skills mit success_count > 1 | 1 (von 12) |
| Skills die ProactiveLearner nutzen kann | 0 (braucht >= 2) |
| Failure-Einträge | ~50+ |
| Semantic-Memory Einträge | ~100+ |
| MetaCognition Einträge | 30+ |
| Meta-Regeln aktiv | ~4 |
| Dream konsolidiert Skill-Library | NEIN |

## Der AGI-Gap

**Chollet-Definition (ARC):** AGI = Transferlernen auf neue, ungesehene Aufgaben.

Phis aktuelles System kann:
- ✓ Sich merken was funktioniert hat (SkillLibrary)
- ✓ Sich merken was schiefging (FailureMemory)
- ✓ Harte Regeln aus Mustern ableiten (MetaRuleEngine)
- ✗ Wissen zwischen Domains transferieren
- ✗ Aus N ähnlichen Erfahrungen eine abstrakte Strategie ableiten
- ✗ Positiv- und Negativ-Wissen in einem Kontext kombinieren
- ✗ Eigenes Lernverhalten reflektieren und optimieren

Das fehlende Stück: **Generalisierung + Integration**
