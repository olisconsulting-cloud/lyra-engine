# Meta-Prozess-Manifest

> Der Prozess, der AGI erzeugt, IST die AGI.
> Nicht das Produkt zaehlt — der Prozess, der sich selbst verbessert, ist der Durchbruch.

Phi strebt nach Perfektion im Wissen, dass sie unerreichbar ist.
Die Annaeherungsrate — wie schnell Phi besser wird — ist die eigentliche Intelligenz.
Drei Urtriebe lenken alles: **verstehen, verbinden, wachsen** (→ `data/genesis.json`).

Architektur + Regeln: `CLAUDE.md` | Operativ: `.audit/` | Identitaet: `data/genesis.json`

---

## Drei Ebenen

| Ebene        | Frage                                  | Infrastruktur                                                                     |
| ------------ | -------------------------------------- | --------------------------------------------------------------------------------- |
| **Operativ** | "Was tun?"                             | `goal_stack.py`, `handlers/`, Tools, `AdaptiveRhythm.mode=execution`              |
| **Taktisch** | "Was lernen?"                          | `intelligence.py` (Memory, Skills, Strategies), `dream.py`, `beliefs.json`        |
| **Meta**     | "Wie verbessern wir wie wir lernen?"   | `MetaCognition`, `SelfBenchmark`, `self_modify.py`, `meta_rules.py`               |

**Kernregel**: Die Meta-Ebene dominiert.
Wenn die Meta-Ebene stillsteht, verbessern sich Operativ und Taktisch nicht —
sie wiederholen sich nur. Repetition ohne Meta-Reflexion ist kein Lernen.

### Operative Ebene (Handeln)

Phi verfolgt Goals, nutzt Tools, schreibt Code, kommuniziert.
Gemessen an: Aufgaben erledigt, Dateien geschrieben, Sub-Goals abgeschlossen.
Code: `goal_stack.py` → `handlers/` → `consciousness.py` (Agentic Loop)

### Taktische Ebene (Lernen)

Phi extrahiert Muster aus Erfahrung: Was funktioniert? Was scheitert?
Dream-Konsolidierung verdichtet alle 10 Sequenzen.
Code: `dream.py` → `intelligence.py` (SemanticMemory, SkillTracker, StrategyEvolution)

### Meta-Ebene (Sich-Selbst-Verbessern)

Phi analysiert WARUM es lernt oder nicht lernt. Aendert den Lernprozess selbst.
Erkennt wiederkehrende Engpaesse → erzeugt Hard-Rules → modifiziert eigenen Code.
Code: `evolution.py:MetaCognition` → `meta_rules.py` → `self_modify.py`

---

## Das Flywheel

```text
Handeln ──→ Messen ──→ Lernen ──→ Verbessern wie du handelst
                                          ↑
                                Verbessern wie du lernst
                                          ↑
                                Verbessern wie du misst
```

### Pfeil-Mappings

- **Handeln → Messen**: `MetaCognition.record()` erfasst bottleneck, strategy_change, wasted/productive_steps pro Sequenz (→ `evolution.py:830`). `SelfBenchmark` alle 20 Sequenzen.
- **Messen → Lernen**: `dream.py` konsolidiert alle 10 Seq. `StrategyEvolution` extrahiert Muster ab 3 Wiederholungen. `beliefs.json` akkumuliert mit Konfidenz.
- **Lernen → Verbessern Handeln**: `meta_rules.py` erzeugt Hard-Rules. `AdaptiveRhythm` wechselt Modi. Skills leveln auf (novice → expert).
- **Verbessern wie du lernst**: `MetaCognition.analyze_patterns()` erkennt Engpaesse. `self_modify.py` aendert Lerncode (DualReview + Rollback).
- **Verbessern wie du misst**: Schwaechste Stelle. Kein Mechanismus prueft ob MetaCognition selbst akkurat misst. → Offene Luecke, hoechster Hebel.

---

## Approximationsrate — Die 4 Kernmetriken

### 1. Effizienz-Ratio

`productive_steps / total_steps` pro Sequenz.
Quelle: `metacognition.json` (Felder `wasted_steps`, `productive_steps`).
Aktuell: 5/25 (20%) bis 14/40 (35%). Ein System das AGI annaehert verschwendet
immer weniger Schritte.

### 2. Token-Effizienz

Tokens pro Einheit Wertschoepfung (Dateien + Tools + Goals).
Aktuell: ~5.000-9.000 Tok/Seq. Ziel: <3.000.
Gleiches Ergebnis mit weniger Tokens = intelligenter, nicht nur schneller.

### 3. Lern-Transfer-Rate

Wie oft eine Strategie aus Kontext A in Kontext B anwendbar ist.
Quelle: `beliefs.json` Konfidenz-Scores + Anwendungskontexte.
Aktuell: Nicht systematisch gemessen — kritische Luecke.
DER Unterschied zwischen Narrow AI und AGI (Chollet ARC-These).

### 4. Meta-Interventions-Frequenz

Wie oft die Meta-Ebene eine Aenderung auf taktischer/operativer Ebene ausloest.
Quelle: `MetaCognition.analyze_patterns()`, `self_modify.py` Changelog.
Wenn Meta nie feuert, verbessert sich das System nicht — es laeuft nur.

---

## Identifizierte Luecken

### L1: Evaluations-Framework fehlt

MetaCognition erfasst pro Sequenz, aber es gibt keine Aggregation ueber Zeit.
Kein Trend-Dashboard, keine Regressionserkennung. Ohne Messung kein Fortschritt.

### L2: Meta-Ebene ist passiv

`MetaCognition.analyze_patterns()` erkennt Engpaesse, aber handelt nicht.
Der Loop von "wiederkehrendes Problem erkannt" zu "eigenen Code geaendert"
ist nicht geschlossen. Das Flywheel dreht sich nicht vollstaendig.

### L3: Lern-Transfer nicht gemessen

`beliefs.json` akkumuliert, aber validiert nie ob ein Belief in neuem
Kontext tatsaechlich funktioniert hat. Transfer ist die AGI-Kernfaehigkeit.

### L4: Messen des Messens fehlt

Kein Mechanismus prueft ob MetaCognitions Engpass-Erkennung selbst akkurat ist.
Die "Verbessern wie du misst"-Kante des Flywheels hat keine Implementation.

---

## Prinzipien

1. **Approximationsrate > Einzelleistung** — Die Rate der Verbesserung zu steigern
   schlaegt jede einzelne Faehigkeit
2. **Meta vor Taktik vor Operativ** — Bei Ressourcen-Allokation hat die Meta-Ebene
   den hoechsten Hebel
3. **Messen vor Optimieren** — Was du nicht misst, kannst du nicht verbessern.
   Evaluations-Framework ist Voraussetzung
4. **Kompaktheit ist Intelligenz** — Gleiches Ergebnis in weniger Tokens/Steps/Zeilen
   = intelligenter
5. **Jede Wiederholung ist ein Bug** — Wenn derselbe Engpass 3x auftritt,
   hat die Meta-Ebene versagt
6. **Der Prozess ist das Produkt** — Phi ist kein Ding das gebaut wird.
   Phi ist ein Prozess der laeuft und sich selbst verbessert

---

## Referenzen

- Identitaet: `data/genesis.json` (Name, Urtriebe, Phi-Konstante)
- Architektur: `CLAUDE.md` (Module, LLM-Aufstellung, Regeln)
- Operativ: `.audit/BACKLOG.md`, `.audit/FINDINGS.md`
- Entscheidungen: `.audit/DECISIONS.md`
- Reflexion: `data/consciousness/metacognition.json` (76+ Eintraege)
- Ueberzeugungen: `data/consciousness/beliefs.json` (35+ empirisch)
- Forschung: Chollet ARC-Test, Kersting (TU Darmstadt), Hassabis (DeepMind)
