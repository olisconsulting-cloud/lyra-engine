# Architektur: Unified Memory System

## Design-Entscheidung: Integration, kein Neubau

Die 5 bestehenden Systeme funktionieren einzeln. Das Problem ist nicht
die Qualität der Teile — es ist das Fehlen der Verbindungen.

**Ansatz:** Einen Integration-Layer ÜBER die bestehenden Systeme legen.
Keine Klasse wird gelöscht oder umgeschrieben. Neue Verbindungen werden
als eigenständige Module gebaut.

## Ziel-Architektur

```
┌─────────────────────────────────────────────────┐
│               Perception (consciousness.py)      │
│   "Was weiss ich zu diesem Goal?"                │
│                     │                            │
│                     ▼                            │
│          ┌──────────────────┐                    │
│          │  UnifiedRetrieval │ ◄── NEU           │
│          │  (ein Interface)  │                    │
│          └────────┬─────────┘                    │
│                   │                              │
│     ┌─────────┬───┴───┬──────────┬───────┐      │
│     ▼         ▼       ▼          ▼       ▼      │
│  Skill    Failure  Semantic  MetaCog  MetaRule   │
│  Library  Memory   Memory    nition   Engine    │
│     │         │       │          │       │      │
│     └─────────┴───┬───┴──────────┘       │      │
│                   ▼                      │      │
│          ┌──────────────────┐            │      │
│          │  SkillEnricher   │ ◄── NEU    │      │
│          │  (beim Speichern) │            │      │
│          └──────────────────┘            │      │
│                   │                      │      │
│                   ▼                      │      │
│          ┌──────────────────┐            │      │
│          │  DreamIntegration│ ◄── NEU    │      │
│          │  (Konsolidierung) │            │      │
│          └──────────────────┘            │      │
└─────────────────────────────────────────────────┘
```

## 3 neue Module

### 1. SkillEnricher (`engine/skill_enricher.py`)
**Wann:** Bei jeder Skill-Extraktion (finish_sequence)
**Was:** Reichert den Skill mit Kontext aus anderen Systemen an

```python
class SkillEnricher:
    """Reichert Skills mit Cross-System-Wissen an."""

    def enrich(self, skill: dict, focus: str) -> dict:
        # 1. Failure-Lektionen einbetten
        skill["anti_patterns"] = failure_memory.check(focus)

        # 2. Strategie-Zusammenfassung (aus MetaCognition)
        skill["why"] = metacognition.get_strategy_for(focus)

        # 3. Semantische Erkenntnisse verlinken
        skill["related_insights"] = semantic_memory.search(focus, top_k=2)

        return skill
```

### 2. UnifiedRetrieval (`engine/unified_retrieval.py`)
**Wann:** Bei jeder neuen Sequenz (Perception-Phase)
**Was:** Eine Anfrage → bestes Wissen aus ALLEN Quellen

```python
class UnifiedRetrieval:
    """Ein Interface für alle Wissensquellen."""

    def query(self, focus: str, goal_type: str) -> str:
        # 1. Bester Skill (semantisch, nicht nur goal_type)
        skill = self._find_best_skill(focus, goal_type)

        # 2. Relevante Fehler-Lektionen
        warnings = failure_memory.check(focus)

        # 3. Semantische Erinnerungen
        memories = semantic_memory.search(focus, top_k=2)

        # 4. Aktive Meta-Regeln
        guards = meta_rules.get_prompt_injections()

        # 5. Zu EINEM Prompt-Block zusammenbauen
        return self._compose(skill, warnings, memories, guards)
```

### 3. DreamSkillConsolidator (in `engine/dream.py` integriert)
**Wann:** Bei jedem Dream-Zyklus (alle 10 Sequenzen)
**Was:** Skills konsolidieren, mergen, abstrahieren

```python
# In DreamEngine._gather_all_memory() ergänzen:
skill_index = self._safe_load_json(data_path / "skill_library" / "index.json")
if skill_index:
    parts.append(f"=== SKILL-LIBRARY ===\n{json.dumps(skill_index)}")

# Dream-Prompt ergänzen um:
# 8. SKILL-KONSOLIDIERUNG: Welche Skills sind ähnlich und sollten gemergt werden?
#    Welche abstract_steps sind zu mechanisch — was ist die STRATEGIE dahinter?
```

## Integrationspunkte (wo im bestehenden Code)

| Stelle | Datei:Zeile | Änderung |
|---|---|---|
| Skill-Extraktion | consciousness.py:1833 | SkillEnricher aufrufen |
| Perception | consciousness.py:1251-1262 | UnifiedRetrieval statt 6 separate Calls |
| Dream | dream.py:144 | Skill-Library mit einlesen |
| ProactiveLearner | proactive_learner.py:117 | success_count >= 1 |
| classify_goal_type | intelligence.py:155 | Bereits gefixt (03.04.) |

## Was sich NICHT ändert
- SkillLibrary Klasse bleibt (wird erweitert, nicht ersetzt)
- FailureMemory API bleibt identisch
- SemanticMemory API bleibt identisch
- MetaRuleEngine bleibt unverändert
- MetaCognition bleibt unverändert
- Alle bestehenden Tests bleiben grün

## Token-Budget-Impact
Aktuell: 6 separate Prompt-Injektionen → oft redundant
Nachher: 1 komponierter Block → kompakter, relevanter
Geschätzte Einsparung: ~500-1000 Tokens/Sequenz bei ähnlicher Informationsdichte
