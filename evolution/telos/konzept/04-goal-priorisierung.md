# 04 — Goal-Priorisierung: Smart Selection statt Index-Reihenfolge

## Problem

`goal_stack.py:get_current_focus()` (Zeilen 367-394) nimmt einfach das
ERSTE aktive Goal (Index-Reihenfolge). Das bedeutet:

- Aeltere Goals werden immer bevorzugt (FIFO)
- Dream-Goals landen am Ende und kommen nie dran
- Kein Bezug zu Phis Mission oder Kompetenz-Luecken
- Kein Anreiz, Domaenen zu wechseln

Das ist die **technisch einfachste** und **strategisch duemmste** Loesung.

## Loesung: Telos-Score basierte Auswahl

Statt Index-Reihenfolge: Score berechnen, hoechsten Score waehlen.

```
VORHER:
  goals = [goal_0, goal_1, goal_2]  # Index-Reihenfolge
  focus = goals[0]                   # Immer der Erste

NACHHER:
  goals = [goal_0, goal_1, goal_2]
  scores = [telos_score(g) for g in goals]
  focus = goals[argmax(scores)]      # Der Wertvollste
```

## Der Algorithmus

### Phase 1 (Quick Win): Nur Diversitaets-Bonus

Minimale Aenderung, maximaler Effekt:

```python
def get_current_focus_v2(self) -> str:
    """Waehlt das wertvollste aktive Goal, nicht das aelteste."""
    active = [g for g in self.goals if g["status"] == "active"]
    if not active:
        return "Keine aktiven Ziele."
    
    # Letzte 10 Skills: welche Domaenen waren aktiv?
    recent_domains = self._get_recent_domains(10)
    
    best_goal = None
    best_score = -1
    
    for goal in active:
        domain = classify_goal_type(goal["description"])
        
        # Basis-Score: Hat pending Sub-Goals?
        pending = [s for s in goal.get("sub_goals", []) if s["status"] == "pending"]
        if not pending:
            continue
        base_score = 1.0
        
        # Diversitaets-Bonus: Neue Domaene = hoeher
        repetitions = recent_domains.count(domain)
        diversity = PHI ** repetitions  # 1.0 → 0.618 → 0.382...
        
        score = base_score * diversity
        
        if score > best_score:
            best_score = score
            best_goal = goal
    
    if not best_goal:
        best_goal = active[0]  # Fallback: altes Verhalten
    
    return self._format_focus(best_goal)
```

### Phase 2: Voller Telos-Score

Erweitert um Mission-Abstand und Ring-Prioritaet (siehe 01-telos-hierarchie.md):

```python
def telos_score(self, goal: dict) -> float:
    """Voller Telos-Score: Mission + Diversitaet + Ring."""
    domain = classify_goal_type(goal["description"])
    
    # 1. Mission-Abstand (0-1)
    mission = self.telos.get("mission", {}).get("text", "")
    if mission:
        mission_score = tfidf_similarity(goal["description"], mission)
    else:
        mission_score = 0.5  # Neutral wenn keine Mission
    
    # 2. Diversitaets-Bonus (0-1)
    recent = self._get_recent_domains(10)
    diversity_score = PHI ** recent.count(domain)
    
    # 3. Ring-Prioritaet (0-1)
    ring = self.telos_rings.get_ring_for_domain(domain)
    ring_score = ring_urgency(ring)
    
    # Phi-Balance: Nicht einfach addieren, sondern gewichten
    return phi_balance([mission_score, diversity_score, ring_score],
                       weights=[0.4, 0.35, 0.25])
```

## Abwaertskompatibilitaet

**Kritisch**: Wenn kein `telos.json` existiert oder leer ist, muss das
alte Verhalten (Index-Reihenfolge) erhalten bleiben. Kein Breaking Change.

```python
def get_current_focus(self) -> str:
    if self._has_telos():
        return self.get_current_focus_v2()
    else:
        return self._get_current_focus_legacy()  # Altes Verhalten
```

## Code-Stellen

| Datei | Zeilen | Was aendern |
|-------|--------|-------------|
| engine/goal_stack.py | 367-394 | get_current_focus() → Score-basiert |
| engine/intelligence.py | 157-224 | classify_goal_type() verbessern (weniger "sonstiges") |
| engine/phi.py | 83-121 | phi_balance() fuer Score-Gewichtung nutzen |

## Spezifikation: classify_goal_type() Verbesserung

Aktuell fallen 54% der Skills in "sonstiges" weil die Keyword-Erkennung
in `intelligence.py:157-224` zu eng ist. Erweiterung:

```python
# Neue Keywords fuer bestehende Kategorien:
"data_analysis": ["daten", "analyse", "csv", "json", "statistik", "visualis",
                   "chart", "graph", "tabelle", "metrik", "dashboard"],
"architecture":  ["architektur", "refactor", "modul", "interface", "design",
                   "pattern", "struktur", "abhaengig", "dependency"],
"business_thinking": ["business", "markt", "preis", "roi", "kunde", "nische",
                      "strategie", "wettbewerb", "skalier"],
```

## Risiken

- **Score-Oszillation**: Phi springt zwischen Goals hin und her weil Scores
  sich nach jeder Sequenz aendern. Loesung: Score wird nur bei Goal-WAHL
  berechnet, nicht bei jedem Step. Einmal gewaehlt, bleibt ein Goal aktiv
  bis es fertig oder stuck ist.
- **Overfitting auf Mission-Keywords**: TF-IDF koennte "KI-Server" Woerter
  bevorzugen und alles andere benachteiligen. Loesung: Mission-Score hat
  max 40% Gewicht, nie allein entscheidend.
