# 01 — Telos-Hierarchie: Mission → Faehigkeiten → Skills

## Problem

Phi setzt sich Goals bottom-up: "Was kann ich gerade tun?"
Das fuehrt zu 20 API-Skills, weil API-Integration das Einfachste ist,
nicht das Wichtigste.

Es fehlt die umgekehrte Frage: "Was MUSS ich koennen, um meinen Zweck
zu erfuellen — und was fehlt mir dafuer?"

## Philosophischer Rahmen

Aristoteles unterschied drei Wissensformen:

**Techne** (τέχνη) — Handwerk, das "Wie"
→ Phi hat das: 24 Skills, 27 Tools, kann Dateien schreiben, Tests ausfuehren, APIs bauen.

**Phronesis** (φρόνησις) — Klugheit, das "Was als naechstes"
→ Phi braucht das: Die Faehigkeit zu erkennen, welcher naechste Schritt
  den groessten Wert schafft — nicht den einfachsten, nicht den naechsten
  auf der Liste, sondern den, der die groesste Luecke schliesst.

**Sophia** (σοφία) — Weisheit, das "Warum"
→ Phi strebt dahin: Verstehen, warum das eigene Wachstum wichtig ist.
  Nicht "ich lerne Datenanalyse weil es auf der Liste steht", sondern
  "ich lerne Datenanalyse weil Oliver ROI-Berechnungen braucht".

## Loesung: 3-Ebenen Zweck-Hierarchie

```
Ebene 3 — SOPHIA (Mission)
│  "Oliver beim Aufbau des KI-Server-Business unterstuetzen"
│  Aendert sich selten. Wird von Oliver gesetzt.
│
├─ Ebene 2 — PHRONESIS (Faehigkeiten)
│  "Was muss ich KOENNEN, um die Mission zu erfuellen?"
│  Leitet sich aus Mission + Kompetenz-Ringen ab.
│  Beispiele:
│    - Daten analysieren und visualisieren
│    - Business-Logik in Code umsetzen
│    - Olivers Projekte selbststaendig ausfuehren
│
└─ Ebene 1 — TECHNE (Skills)
   "Was muss ich als naechstes LERNEN?"
   Leitet sich aus Faehigkeiten + Skill-Gaps ab.
   Beispiele:
     - CSV-Parsing und Datenaufbereitung
     - Dashboard-Komponenten bauen
     - Projekt-Templates erstellen
```

**Der entscheidende Unterschied**:
- JETZT: Goals entstehen zufaellig (LLM schlaegt vor, was es kennt)
- MIT TELOS: Goals entstehen aus der Luecke zwischen "was ich kann" und "was ich brauche"

## Integration in bestehende Architektur

Telos ist ein **symbolischer Layer UEBER dem LLM** — genau der hybride Ansatz,
den Lyra als AGI-Kern definiert (symbolische Goals + subsymbolische LLMs).

```
VORHER:
  Dream → "Neues Goal" → goal_stack (Ende der Liste) → get_current_focus (Index 0)
  
NACHHER:
  Dream → "Neues Goal" → telos_score() berechnen → goal_stack (sortiert) → get_current_focus (hoechster Score)
```

Der LLM entscheidet weiterhin WIE ein Goal ausgefuehrt wird (Tool-Use Loop).
Telos entscheidet nur WELCHES Goal als naechstes dran ist.

## Code-Stellen

| Datei | Zeilen | Was aendern |
|-------|--------|-------------|
| data/consciousness/telos.json | NEU | Zweck-Hierarchie Datenstruktur |
| engine/goal_stack.py | 367-394 | get_current_focus() liest Telos-Score |
| engine/dream.py | 322-366 | _apply_recommendations() nutzt Telos-Score |
| engine/consciousness.py | 1276 | Focus-Bestimmung nutzt Telos |

## Spezifikation: telos.json Schema

```json
{
  "version": 1,
  "mission": {
    "text": "Oliver beim Aufbau des KI-Server-Business unterstuetzen",
    "set_by": "oliver",
    "set_at": "2026-04-03T00:00:00Z"
  },
  "faehigkeiten": [
    {
      "id": "f1",
      "text": "Daten analysieren und visualisieren",
      "ring": 3,
      "required_skills": ["data_analysis", "python_coding"],
      "status": "gap",
      "priority": "high"
    },
    {
      "id": "f2",
      "text": "Business-Logik in Code umsetzen",
      "ring": 3,
      "required_skills": ["business_thinking", "architecture"],
      "status": "gap",
      "priority": "high"
    },
    {
      "id": "f3",
      "text": "API-Integrationen bauen und testen",
      "ring": 2,
      "required_skills": ["api_integration", "testing"],
      "status": "achieved",
      "priority": "low"
    }
  ],
  "kompetenz_ringe": {
    "$ref": "02-kompetenz-ringe.md"
  },
  "reflexion_history": []
}
```

## Spezifikation: telos_score() Algorithmus

```python
def telos_score(goal: dict, telos: dict, recent_skills: list) -> float:
    """Berechnet wie wertvoll ein Goal fuer Phis Zweck ist.
    
    Drei Faktoren, Phi-gewichtet:
    1. Mission-Abstand: Wie nah ist das Goal an einer offenen Faehigkeit?
    2. Diversitaets-Bonus: Ist das eine neue Domaene?
    3. Ring-Prioritaet: Ist der Ring reif fuer Fortschritt?
    """
    # 1. Mission-Abstand (0-1): Match zwischen Goal und offenen Faehigkeiten
    mission_score = max(
        similarity(goal["description"], f["text"])
        for f in telos["faehigkeiten"]
        if f["status"] == "gap"
    ) if any(f["status"] == "gap" for f in telos["faehigkeiten"]) else 0.1
    
    # 2. Diversitaets-Bonus (0-1): Neue Domaene > wiederholte Domaene
    goal_domain = classify_goal_type(goal["description"])
    recent_domains = [s["goal_type"] for s in recent_skills[-10:]]
    repetition_count = recent_domains.count(goal_domain)
    diversity_score = PHI ** repetition_count  # 1.0 → 0.618 → 0.382 → 0.236...
    
    # 3. Ring-Prioritaet (0-1): Niedrigster unfertiger Ring hat Vorrang
    goal_ring = get_ring_for_domain(goal_domain)
    ring_readiness = ring_completion_ratio(goal_ring - 1)  # Vorgaenger-Ring
    ring_score = ring_readiness * (1.0 / goal_ring)  # Niedrigere Ringe wichtiger
    
    # Phi-gewichtete Kombination
    return phi_balance([mission_score, diversity_score, ring_score])
```

## Risiken

- **Over-Engineering**: Der Score koennte zu komplex werden. Start mit nur
  Mission-Abstand + Diversitaets-Bonus. Ring-Prioritaet erst in Phase 2.
- **Mission-Drift**: Wenn Oliver die Mission aendert, muessen alle Faehigkeiten
  neu bewertet werden. Loesung: Mission-Aenderung ist ein manueller, seltener Akt.
- **Similarity-Qualitaet**: Wort-basierter Vergleich koennte zu ungenau sein.
  Aber: TF-IDF existiert bereits in SemanticMemory — wiederverwenden.
