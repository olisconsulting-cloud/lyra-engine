# 03 — Reflexions-Gate: "War das sinnvoll?"

## Problem

Phi bewertet sich nach jeder Sequenz mit Score (Selbst) und Rating (System),
aber fragt nie: "Hat dieser Skill mich meiner Mission naeher gebracht?"

Score 9/10 fuer den 15. API-Wrapper ist technisch korrekt — aber strategisch
wertlos. Ohne Reflexion auf Zweck-Ebene kann Phi nicht zwischen
"gut gemacht" und "das Richtige gemacht" unterscheiden.

## Philosophischer Kern

In der stoischen Philosophie gibt es die taegliche "Examen" — eine
abendliche Reflexion mit drei Fragen:
1. Was habe ich heute gut gemacht?
2. Was haette ich besser machen koennen?
3. Was habe ich gelernt?

Phi braucht ein analoges Gate, aber auf Zweck ausgerichtet:
Nicht "war der Code sauber?" sondern "war das der richtige Code?"

## Loesung: 4 Telos-Fragen nach jeder Sequenz

Nach jedem `finish_sequence` (oder Sequenz-Ende) werden 4 Fragen
symbolisch beantwortet — NICHT per LLM, sondern per Code-Logik:

### Frage 1: Neue Faehigkeit?
```python
neue_faehigkeit = skill_id not in [s["id"] for s in previous_skills]
# Kann ich jetzt etwas, das ich vorher nicht konnte?
```

### Frage 2: Neue Domaene?
```python
recent_domains = get_last_n_skill_domains(10)
neue_domaene = current_domain not in recent_domains
# War das eine neue Domaene oder Wiederholung?
```

### Frage 3: Oliver-Nutzen?
```python
oliver_nutzen = telos_mission_similarity(skill_summary, telos["mission"]["text"])
# Skala 0-10: Wie nah ist das an Olivers Mission?
# Nutzt existierenden TF-IDF aus SemanticMemory
```

### Frage 4: Transfer-Potenzial?
```python
abstract_steps = skill["abstract_steps"]
similar_patterns = find_skills_with_similar_pattern(abstract_steps)
transfer_potenzial = len(similar_patterns) / total_skills
# Wie viele andere Skills nutzen ein aehnliches Muster?
# Hoher Wert = dieses Pattern ist uebertragbar
```

## Repetitions-Erkennung

**Kern-Mechanismus**: Wenn 3 Sequenzen hintereinander `neue_domaene: false`
haben → automatisch Domaenen-Wechsel erzwingen.

```python
def check_repetition(reflexion_history: list) -> Optional[str]:
    """Prueft ob Phi in einer Domaene festhaengt.
    
    Returns: Erzwungene neue Domaene oder None.
    """
    last_3 = reflexion_history[-3:]
    if len(last_3) < 3:
        return None
    
    if all(not r["neue_domaene"] for r in last_3):
        # 3x gleiche Domaene → Wechsel erzwingen
        current_domain = last_3[-1]["domaene"]
        weakest_ring = get_ring_with_highest_urgency()
        weakest_domain = get_weakest_domain_in_ring(weakest_ring)
        
        if weakest_domain != current_domain:
            return weakest_domain
    
    return None
```

**Integration**: Der Rueckgabewert wird als `mode_instruction` in den
naechsten AdaptiveRhythm-Zyklus injiziert — identisch zu wie `cooldown`
oder `learning` Modus heute funktionieren.

## Code-Stellen

| Datei | Zeilen | Was aendern |
|-------|--------|-------------|
| engine/consciousness.py | 2870-2908 | Nach finish_sequence/end_turn: Reflexion ausfuehren |
| engine/evolution.py | 41-129 | AdaptiveRhythm: Repetitions-Override einbauen |
| data/consciousness/telos.json | reflexion_history[] | Reflexions-Ergebnisse speichern |

## Spezifikation: Reflexions-Eintrag

```json
{
  "sequence": 86,
  "timestamp": "2026-04-03T20:00:00Z",
  "skill_id": "skill_sonstiges_24",
  "domaene": "api_integration",
  "neue_faehigkeit": false,
  "neue_domaene": false,
  "oliver_nutzen": 3,
  "transfer_potenzial": 0.8,
  "repetition_warning": true,
  "forced_switch_to": "data_analysis"
}
```

## Wichtig: Kein LLM-Call fuer Reflexion

Die Reflexion ist **rein symbolisch** (Code-Logik, kein LLM). Gruende:
1. Token-Effizienz: Kein zusaetzlicher API-Call pro Sequenz
2. Konsistenz: LLM wuerde inkonsistent bewerten
3. Code > Prompts: Lyras Kern-Prinzip
4. Geschwindigkeit: Reflexion muss in <100ms fertig sein

## Risiken

- **False Positives bei Repetition**: 3 API-Skills hintereinander koennten
  gewollt sein (z.B. Oliver gibt explizit ein API-Projekt). Loesung:
  Oliver-Tasks (execution mode) ueberschreiben die Repetitions-Erkennung.
- **Oliver-Nutzen schwer messbar**: TF-IDF zwischen Skill-Summary und
  Mission-Text ist grob. Aber: Besser als gar keine Messung.
  Kann spaeter durch Embedding-Similarity ersetzt werden.
