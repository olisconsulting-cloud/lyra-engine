# 05 — Dream-Telos: Konsolidierung mit Zweck

## Problem

Dreams aktuelle Rolle (dream.py:40-120, 322-366):
1. Sammelt Memory-Dateien
2. LLM analysiert Muster → max 2 neue Goals
3. _apply_recommendations() haengt Goals an active-Liste AN

**Drei Defizite**:

1. **Keine Priorisierung**: Dream-Goals landen am Ende der Liste.
   Da get_current_focus() Index 0 nimmt, kommen sie nie dran.
   
2. **Keine Deduplikation**: Beliefs werden ohne Aehnlichkeitspruefung
   eingefuegt → 5 Duplikate in beliefs.json aktuell.
   
3. **Keine strategischen Beliefs**: Alle 37 Beliefs sind taktisch
   ("Tests zuerst", "Dateien pruefen"). Keiner beschreibt Phis
   Zweck oder Olivers Beduerfnisse.

## Loesung 1: Dream-Goals nach Telos-Score einsortieren

```python
def _apply_recommendations_v2(self, recommendations: list):
    """Dream-Goals werden nach Telos-Score einsortiert, nicht angehaengt."""
    for rec in recommendations:
        if rec.get("type") == "goal":
            goal = self.goal_stack.create_goal(rec["text"], rec["sub_goals"])
            
            # NEU: Telos-Score berechnen
            score = self.goal_stack.telos_score(goal)
            
            # Einsortieren statt anhaengen
            self.goal_stack.insert_goal_by_score(goal, score)
```

**Effekt**: Dream-Goals die eine neue Domaene erschliessen, werden
BEVORZUGT statt ignoriert.

## Loesung 2: Belief-Deduplikation

Vor jedem Belief-Insert: Aehnlichkeit mit existierenden Beliefs pruefen.

```python
def _add_belief_deduplicated(self, new_belief: str, beliefs: list, 
                              threshold: float = 0.75) -> bool:
    """Fuegt Belief nur hinzu wenn kein aehnlicher existiert.
    
    Nutzt existierenden TF-IDF aus SemanticMemory.
    Threshold 0.75: Hoch genug um echte Duplikate zu fangen,
    niedrig genug um aehnliche-aber-verschiedene Beliefs zu erlauben.
    """
    for existing in beliefs:
        text = existing if isinstance(existing, str) else existing.get("text", "")
        similarity = tfidf_similarity(new_belief, text)
        
        if similarity > threshold:
            # Duplikat gefunden → Update statt Insert
            # Behalte den laengeren/praeziseren Text
            if len(new_belief) > len(text):
                existing["text"] = new_belief  # oder existing = new_belief
            return False  # Nicht eingefuegt
    
    beliefs.append(new_belief)
    return True  # Eingefuegt
```

**Sofort-Aktion (Phase 1 Quick Win)**: Die 5 existierenden Duplikate
in beliefs.json manuell entfernen als Teil von TE-Q3.

## Loesung 3: Strategische Beliefs erzeugen

Dream bekommt eine zusaetzliche Anweisung im Konsolidierungs-Prompt:

```python
dream_prompt_addition = """
Neben taktischen Erkenntnissen, pruefe auch:
- Was sagt das ueber meinen ZWECK aus? (about_self)
- Was habe ich ueber die WELT gelernt? (about_world)  
- Was braucht OLIVER von mir? (about_oliver)

Formuliere min. 1 strategischen Belief pro Kategorie wenn moeglich.
Beispiele:
  about_self: "Meine Staerke liegt im systematischen Aufbau — ich bin
   am produktivsten wenn ich planen → bauen → testen kann"
  about_oliver: "Oliver braucht Business-Analysen mehr als weitere
   API-Tools — sein KI-Server-Business ist die Prioritaet"
"""
```

**Warum per Prompt und nicht per Code?**
Strategische Beliefs sind zu nuanciert fuer regelbasierte Erkennung.
Das ist einer der wenigen Faelle wo LLM > Code stimmt.
Aber: Der Prompt ist FEST im Code, nicht variabel.

## Code-Stellen

| Datei | Zeilen | Was aendern |
|-------|--------|-------------|
| engine/dream.py | 322-366 | _apply_recommendations() → Score-basiert einsortieren |
| engine/dream.py | 77-86 | Konsolidierungs-Prompt erweitern |
| engine/goal_stack.py | NEU | insert_goal_by_score() Methode |
| engine/intelligence.py | 225+ | SemanticMemory: tfidf_similarity() exponieren |

## Spezifikation: Belief-Kategorien nach Telos

```json
{
  "about_self": [
    {
      "text": "Meine Staerke liegt im systematischen Aufbau",
      "confidence": 0.85,
      "formed_from": "Analyse von 24 Skills — alle folgen planen→bauen→testen",
      "formed_at": "2026-04-03T20:00:00Z"
    }
  ],
  "about_world": [],
  "about_oliver": [
    {
      "text": "Oliver braucht Business-Analysen — sein Fokus ist das KI-Server-Business",
      "confidence": 0.80,
      "formed_from": "Olivers Mission in telos.json + Recherche-Skills 0-2",
      "formed_at": "2026-04-03T20:00:00Z"
    }
  ],
  "from_experience": [
    "... (bestehende taktische Beliefs, dedupliziert)"
  ]
}
```

## Risiken

- **Dream-Overhead**: Telos-Score-Berechnung in Dream koennte zu langsam sein.
  Loesung: Dream laeuft alle 10 Sequenzen, nicht bei jeder — Overhead vertretbar.
- **Strategische Beliefs zu vage**: LLM koennte Plattitueden erzeugen.
  Loesung: Im Prompt fordern: "Nenne konkrete Evidenz fuer jeden Belief."
  Plus: confidence-Wert muss >0.7 sein fuer Aufnahme.
- **Deduplikation zu aggressiv**: Aehnliche aber verschiedene Beliefs
  koennten geloescht werden. Loesung: Threshold 0.75 ist konservativ.
  Lieber ein Duplikat zu viel als ein wertvoller Belief geloescht.
