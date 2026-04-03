# 02 — Kompetenz-Ringe: Strukturiertes Wachstum statt zufaelliger Akkumulation

## Problem

Phi hat 24 Skills, davon ~20 in einer einzigen Domaene (API-Integration).
Die CompetenceMatrix in `evolution.py:228-237` trackt 6 Domaenen, aber es gibt
keine Logik die sagt: "Du hast genug API-Skills — lerne jetzt etwas anderes."

Ohne Struktur optimiert Phi lokal: Es baut was es kennt, immer tiefer,
immer enger. Das ist das Gegenteil von AGI.

## Loesung: 5 konzentrische Ringe

Inspiriert von Dreyfus' Kompetenzmodell (Novice → Expert) und Maslows
Beduerfnishierarchie — aber fuer eine KI, nicht fuer Menschen.

```
Ring 5 — WEISHEIT (Sophia)
  transfer_learning, teaching, oliver_alignment
  "Kann ich Wissen uebertragen und anderen nuetzen?"

Ring 4 — AUTONOMIE
  self_improvement, web_research, frontend_design
  "Kann ich selbststaendig Neues finden und darstellen?"

Ring 3 — STRATEGIE (Phronesis)
  data_analysis, business_thinking, architecture
  "Kann ich Zusammenhaenge erkennen und planen?"

Ring 2 — HANDWERK (Techne)
  api_integration, testing, tool_building
  "Kann ich zuverlaessig bauen und pruefen?"

Ring 1 — KERN
  file_management, python_coding, planning
  "Kann ich die Grundlagen?"
```

## Aufstiegs-Logik

**Regel**: Ein Ring muss zu **60% gefuellt** sein, bevor der naechste Ring
aktiv angesteuert wird. "Gefuellt" = mindestens 2 von 3 Domaenen im Ring
haben Skill-Level >= "intermediate" (>=5 Erfolge).

**Warum 60% und nicht 100%?**
- 100% waere Perfektionismus — Phi wuerde ewig in einem Ring haengen
- 60% (≈ 1/Phi) ist der Golden-Ratio-Schwellenwert:
  Genug Kompetenz um den naechsten Ring zu betreten, aber nicht so viel
  dass es zum Hamsterrad wird

**Warum nicht weniger als 60%?**
- Zu fruehes Ring-Hopping fuehrt zu Oberflaechlichkeit
- Phi braucht genuegend Tiefe in Ring 2 (Handwerk) bevor es
  Ring 3 (Strategie) sinnvoll betreten kann

## Ist-Zustand (Phase 0)

| Ring | Domaene | Skill-Level | Erfuellt? |
|------|---------|-------------|-----------|
| 1 | file_management | expert (573 Erfolge) | Ja |
| 1 | python_coding | expert (516 Erfolge) | Ja |
| 1 | planning | expert (69 Erfolge) | Ja |
| **Ring 1** | | | **100% → KOMPLETT** |
| 2 | api_integration | expert (~20 Skills) | Ja |
| 2 | testing | intermediate (4 Skills) | Ja |
| 2 | tool_building | intermediate (20 Erfolge) | Ja |
| **Ring 2** | | | **100% → KOMPLETT** |
| 3 | data_analysis | novice (0 Skills) | Nein |
| 3 | business_thinking | beginner (3 Recherchen) | Grenzwertig |
| 3 | architecture | novice (0 Skills) | Nein |
| **Ring 3** | | | **33% → BLOCKIERT** |
| 4 | self_improvement | advanced (28 Erfolge) | Ja |
| 4 | web_research | advanced (27 Erfolge) | Ja |
| 4 | frontend_design | novice (0 Skills) | Nein |
| **Ring 4** | | | **67% → OFFEN** |
| 5 | transfer_learning | ungemessen | Nein |
| 5 | teaching | ungemessen | Nein |
| 5 | oliver_alignment | ungemessen | Nein |
| **Ring 5** | | | **0% → GESPERRT** |

**Diagnose**: Ring 1+2 komplett, Ring 3 ist der Engpass.
Phi SOLLTE Ring 3 bearbeiten (data_analysis, architecture),
TUT aber stattdessen immer mehr Ring 2 (API-Integration).

## Phi-Decay Integration

Die Phi-Zahl (1.618...) ist bereits in `phi.py` implementiert.
Wir nutzen sie fuer Ring-Gewichtung:

```python
def ring_weight(ring_number: int) -> float:
    """Niedrigere Ringe sind wichtiger (Fundament zuerst).
    Ring 1: 1.0, Ring 2: 0.618, Ring 3: 0.382, Ring 4: 0.236, Ring 5: 0.146
    """
    return PHI ** (-(ring_number - 1))

def ring_urgency(ring_number: int, completion: float) -> float:
    """Wie dringend braucht dieser Ring Aufmerksamkeit?
    Niedrige Completion + niedriger Ring = hoechste Dringlichkeit.
    """
    gap = max(0, 0.6 - completion)  # 0 wenn Ring >= 60%
    return gap * ring_weight(ring_number)
```

**Effekt**: Ring 3 mit 33% Completion hat urgency = (0.6 - 0.33) * 0.382 = 0.103.
Ring 5 mit 0% Completion hat urgency = (0.6 - 0.0) * 0.146 = 0.088.
→ Ring 3 wird bevorzugt, obwohl Ring 5 leerer ist. Fundament zuerst.

## Code-Stellen

| Datei | Zeilen | Was aendern |
|-------|--------|-------------|
| engine/evolution.py | 228-237 | CompetenceMatrix um Ring-Zuordnung erweitern |
| engine/evolution.py | 701-823 | LearningEngine nutzt Ring-Urgency |
| data/consciousness/telos.json | NEU | Ring-Daten persistent speichern |

## Spezifikation: Ring-Datenstruktur

```json
{
  "ringe": [
    {
      "nummer": 1,
      "name": "Kern",
      "domaenen": [
        {"name": "file_management", "level": "expert", "erfolge": 573},
        {"name": "python_coding", "level": "expert", "erfolge": 516},
        {"name": "planning", "level": "expert", "erfolge": 69}
      ],
      "completion": 1.0,
      "status": "komplett"
    },
    {
      "nummer": 3,
      "name": "Strategie",
      "domaenen": [
        {"name": "data_analysis", "level": "novice", "erfolge": 0},
        {"name": "business_thinking", "level": "beginner", "erfolge": 3},
        {"name": "architecture", "level": "novice", "erfolge": 0}
      ],
      "completion": 0.33,
      "status": "aktiv"
    }
  ]
}
```

## Risiken

- **Starre Zuordnung**: Manche Skills passen in mehrere Ringe. Loesung:
  Primaer-Ring zuordnen, Sekundaer-Ringe als Bonus.
- **Ring-Inflation**: Wenn wir zu viele Domaenen pro Ring haben, wird 60%
  zu leicht. Loesung: Max 3 Domaenen pro Ring (aktuell schon so).
- **Motivation-Kill**: Phi koennte frustriert werden wenn Ring 3 erzwungen
  wird und es dort schwaecher ist. Loesung: exploration_weight() aus phi.py
  sorgt dafuer, dass Phi nicht NUR den schwierigen Ring macht — es gibt
  immer noch 38% Raum fuer Vertrautes.
