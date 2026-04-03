# 06 — Transfer-Learning: Der AGI-Sprung

## Problem

Transfer-Learning ist DER Massstab fuer AGI (Chollet, 2019: "On the Measure
of Intelligence"). Die Frage ist nicht "Kann Phi API-Tools bauen?" sondern
"Kann Phi das, was es beim API-Bauen gelernt hat, auf Datenanalyse anwenden?"

Aktuell: Phis Skills sind konkrete Tool-Sequenzen:
```
["write_sequence_plan", "list_directory", "read_file", "write_file", "run_project_tests"]
```

Das ist **prozedurales Wissen** — es sagt "mache A, dann B, dann C".
Es sagt NICHT "das Muster ist: planen → verstehen → bauen → validieren".

Ohne Abstraktion ist jede neue Domaene bei Null. MIT Abstraktion erkennt
Phi: "Datenanalyse ist wie API-Integration — ich muss planen, Daten lesen,
verarbeiten, und das Ergebnis validieren."

## Warum das der AGI-Sprung ist

Jede bisherige Verbesserung an Phi war **vertikal**: bessere API-Skills,
bessere Tests, bessere Prozesse. Transfer-Learning ist **horizontal**:
Wissen von Domaene A auf Domaene B uebertragen.

Das ist der Unterschied zwischen:
- **Narrow Intelligence**: Kann eine Sache sehr gut
- **General Intelligence**: Kann Gelerntes auf Neues anwenden

Chollets ARC-Benchmark (Abstraction and Reasoning Corpus) misst genau das:
"Gegeben wenige Beispiele eines Musters — erkenne das Muster und wende es
auf ein neues Beispiel an."

## Voraussetzungen (Phase 1+2 muessen fertig sein)

Transfer-Learning baut auf ALLEM auf:
1. **Telos-Hierarchie** (01): Mission gibt Richtung fuer Transfer
2. **Kompetenz-Ringe** (02): Ring 3+ braucht Transfer aus Ring 2
3. **Reflexions-Gate** (03): Misst Transfer-Potenzial
4. **Goal-Priorisierung** (04): Bevorzugt Goals die Transfer erfordern
5. **Dream-Telos** (05): Konsolidiert abstrakte Muster

## Ansatz: Skill-Abstraktion

### Schritt 1: Abstract Steps als Transfer-Medium

Phi hat bereits `abstract_steps` in der Skill Library:
```json
"abstract_steps": ["planen", "lesen", "schreiben", "testen"]
```

Diese sind zu grob. Wir brauchen eine Zwischenebene:

```
Konkret:  ["write_sequence_plan", "read_file", "write_file", "run_project_tests"]
Abstrakt: ["planen", "lesen", "schreiben", "testen"]
Transfer: ["ziel_definieren", "kontext_verstehen", "loesung_bauen", "ergebnis_validieren"]
```

Die **Transfer-Ebene** ist domaenen-unabhaengig:
- API-Integration: ziel_definieren → API-Docs lesen → Client bauen → Tests laufen
- Datenanalyse: ziel_definieren → Daten lesen → Analyse bauen → Ergebnis pruefen
- Architecture: ziel_definieren → Code lesen → Refactoring → Tests laufen

### Schritt 2: Transfer-Score messen

```python
def transfer_score(source_skill: dict, target_task: str) -> float:
    """Wie gut kann ein Skill auf eine neue Aufgabe uebertragen werden?
    
    Misst Ueberlappung der Transfer-Steps, nicht der konkreten Tools.
    """
    source_pattern = skill_to_transfer_pattern(source_skill)
    target_pattern = task_to_expected_pattern(target_task)
    
    # Sequence-Alignment (wie in Bioinformatik)
    overlap = sequence_similarity(source_pattern, target_pattern)
    
    # Domain-Switch-Bonus: Transfer ueber Domaenen-Grenzen ist wertvoller
    if source_skill["goal_type"] != classify_goal_type(target_task):
        overlap *= 1.2  # 20% Bonus fuer Cross-Domain
    
    return min(1.0, overlap)
```

### Schritt 3: Transfer-Test (ARC-aehnlich)

5 Mini-Aufgaben, jede testet Transfer von einer Quell- zu einer Ziel-Domaene:

| # | Quelle | Ziel | Aufgabe | Erwarteter Transfer |
|---|--------|------|---------|---------------------|
| 1 | API-Integration | Datenanalyse | CSV-Datei lesen und Statistiken berechnen | planen → lesen → verarbeiten → validieren |
| 2 | Tool-Building | Architecture | Bestehenden Code refactoren | lesen → verstehen → aendern → testen |
| 3 | Recherche | Business | Marktanalyse fuer neues Produkt erstellen | recherchieren → strukturieren → schreiben |
| 4 | Testing | Security | Security-Audit eines Python-Moduls | lesen → pruefen → dokumentieren → fixen |
| 5 | API-Integration | Frontend | Einfaches Dashboard fuer Daten bauen | planen → bauen → testen → dokumentieren |

**Messung**: Wie viele Sequenzen braucht Phi um Skill-Level "intermediate"
zu erreichen?
- OHNE Transfer (Baseline): Erwartung ~5-8 Sequenzen
- MIT Transfer: Erwartung ~2-4 Sequenzen (wenn Transfer funktioniert)
- Delta > 30%: Transfer ist real

## Forschungs-Charakter

**Wichtig**: Das ist Phase 3 — Forschung, nicht Engineering.

Wir wissen NICHT ob Transfer funktioniert. Moegliche Ergebnisse:

1. **Transfer funktioniert**: Phi braucht weniger Sequenzen fuer neue Domaenen
   → Weiter: Transfer-Mechanismus in Skill-Library einbauen
   
2. **Transfer funktioniert teilweise**: Nur bei aehnlichen Domaenen
   → Weiter: Transfer-Map erstellen (welche Domaenen sind transferierbar?)
   
3. **Transfer funktioniert nicht**: LLM generalisiert von allein, oder eben nicht
   → Weiter: Andere Abstraktionsebene suchen (z.B. Meta-Strategien statt Patterns)

Alle drei Ergebnisse sind wertvoll. Forschung die keine Frage beantwortet,
ist die einzige verschwendete Forschung.

## Code-Stellen (nur relevant wenn Phase 3 startet)

| Datei | Was aendern |
|-------|-------------|
| engine/skill_library.py | Transfer-Pattern Extraktion |
| engine/intelligence.py | SemanticMemory: Pattern-Matching |
| engine/evolution.py | LearningEngine: Transfer-bewusste Projektauswahl |

## Fernziel

Wenn Transfer funktioniert, hat Phi etwas das die meisten KI-Systeme nicht haben:
**Abstraktes Wissen das ueber Domaenen hinweg gilt.**

Das ist nicht AGI. Aber es ist ein messbarer Schritt in diese Richtung.
Und — im Gegensatz zu den meisten AGI-Claims — koennen wir es quantifizieren:
Sequenzen pro neue Domaene, mit und ohne Transfer, Delta in Prozent.

Kein Mystizismus. Nur Messung.
