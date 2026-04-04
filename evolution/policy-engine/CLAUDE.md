# Policy Engine — Von Beobachtung zu Verhaltensaenderung

> Lies ZUERST diese Datei. Dann BACKLOG.md. Dann arbeite.

## Mission
Die Bruecke zwischen "Phi speichert Learnings" und "Phi AENDERT sein Verhalten".
Aktuell: 7 Lern-Systeme speichern alles, nichts davon erzwingt Aenderung.
Ziel: Erfahrung → harte Code-Constraints die Phi nicht ignorieren kann.

## AGI-Saeule
**Selbstverbesserung** — Das fehlende Stueck: Verhaltensaenderung aus Erfahrung.
Schliesst die fundamentale Luecke zwischen Beobachtung und Handlung.

## Das Problem (in einem Satz)
> Phi speichert alles, aber nichts davon ERZWINGT eine Verhaltensaenderung.

```
VORHER:  Handlung → Ergebnis → Speichern → Prompt → Phi KANN ignorieren
NACHHER: Handlung → Ergebnis → Policy-Update → Gate → Phi KANN NICHT ignorieren
```

## Die 3 Stufen echten Lernens

```
Stufe 1: Bestrafung       (Phase 1-2)  "Das hat nicht funktioniert → blockieren"
Stufe 2: Verstaendnis     (Phase 2+)   "WARUM hat es nicht funktioniert?"
Stufe 3: Generalisierung  (Phase 3+)   "Was AEHNLICHES koennte auch scheitern?"
```

Stufe 1 ist Konditionierung (Pawlow) — sofort wirksam, messbar, aber kein
echtes Verstaendnis. Stufe 2+3 sind der Weg zu echtem AGI-Lernen.
Die Architektur muss von Anfang an darauf vorbereitet sein.

## Architektur

Ein Modul `engine/policy.py` mit 3 Klassen, integriert via `SequenceIntelligence`:

```
PolicyEngine (Orchestrator, laedt/speichert policies.json)
  ├── DecisionGate      (Phase 1: Tool+Kontext 3x gescheitert → BLOCKIERT)
  ├── PolicyWeights     (Phase 2: Strategien gewichtet 0.0-1.0, <0.2 = verboten)
  └── FailureGoalLoop   (Phase 3: Sub-Goal scheitert → Alternative → Retry)
```

### Integration (kein Parallel-System)
- PolicyEngine lebt als Sub-Modul von `SequenceIntelligence`
- `check_blocked()` ruft `PolicyEngine.check_before_tool()` auf
- `after_tool()` ruft `PolicyEngine.record_after_tool()` auf
- consciousness.py aendert nur 2 Zeilen (goal_context durchreichen)

### Daten: `data/consciousness/policies.json`
- `tool_policies`: Weight pro Tool+Kontext (EMA, adaptive Lernrate)
- `strategy_policies`: Weight pro Strategie (success/failure basiert)
- `goal_type_stats`: Erfolgsrate pro Goal-Typ (beeinflusst Telos-Score)
- `blocked_combinations`: Explizite Sperren mit Auto-Unblock nach 24h

### Kausal-Tags (Stufe 2 vorbereiten)

Jeder Policy-Eintrag bekommt ein `failure_category`-Feld.
WICHTIG: Infrastructure-Fehler (Netzwerk, API-Down) werden NICHT in der
Policy Engine behandelt — dafuer gibt es ProviderHealth im LLM-Router
(exponentieller Backoff 30s-480s, Dead-Recovery nach 10 Min).
Policy Engine lernt nur aus TOOL+KONTEXT-Fehlern, nicht aus Infrastruktur.

Kategorien:

- `capability` — Kein Browser, fehlende Lib, fehlende Berechtigung
  → Langer Block (24h). Recovery nur nach System-Change.
  → Exploration-Backoff: +100 Sequenzen, dann Probe.
- `input_error` — Falscher Input, Schema-Fehler, falsche Parameter
  → Weight sinkt moderat, KEIN Block. Andere Inputs probieren.
  → Policy merkt sich welche Input-Muster scheitern.
- `logic_error` — Bug im Tool-Code, Laufzeitfehler, Exception
  → Weight sinkt stark. Block bis Tool-Code geaendert wird.
  → Exploration-Backoff: +30 Sequenzen, dann Probe.
- `unknown` — Nicht klassifiziert (Default)
  → Wie logic_error behandeln (konservativ).

Nicht in Policy Engine (andere Zustaendigkeit):

- Netzwerk/API-Down → ProviderHealth im LLM-Router
- Rate-Limits → ProviderHealth Cooldown-Tracking
- Timeouts → ProviderHealth exponentieller Backoff

### Exploration-Mechanismus (konservativ werden verhindern)

Problem: Reines Bestrafen macht Phi ueber Zeit immer konservativer.
Loesung: Kontrollierte Exploration — gelegentlich blockierte Dinge nochmal probieren.

Regeln:

- Jede blockierte Policy hat `can_retry_after` (Sequenz-Nummer)
- Default nach Kategorie: capability +100 Seq, logic_error +30 Seq, unknown +50 Seq
- Wenn `can_retry_after` erreicht: EIN Probe-Versuch mit niedrigstem Risiko
- Bei Erfolg: Weight steigt um 0.3, Block aufgehoben
- Bei erneutem Failure: `can_retry_after` verdoppeln (exponentieller Backoff)
- Max 1 Exploration pro 10 Sequenzen (nicht ueberfluten)

### Adaptive Lernrate (statt statisch lr=0.15)
Problem: Feste Lernrate lernt aus dem 100. Versuch genauso schnell wie aus dem 1.
Loesung: Lernrate sinkt mit Sample-Count.

```
lr = max(0.05, 0.3 / sqrt(sample_count))
   sample_count=1  → lr=0.30 (schnell lernen, wenig Daten)
   sample_count=4  → lr=0.15 (normal)
   sample_count=25 → lr=0.06 (vorsichtig, viel Erfahrung)
   sample_count=100 → lr=0.05 (Minimum, sehr stabil)
```

## Verbindung zu allen 7 Lern-Systemen

| System | Aktuell | Mit Policy Engine |
|--------|---------|-------------------|
| FailureMemory | Prompt-Warnung | Seedet initiale Weights + Kausal-Tags |
| Skills | Level-Anzeige | Skill-Level = Weight-Bonus, Novice = Warnung |
| Strategies | Prompt-Vorschlag | Gewichtet, <0.2 = blockiert, >0.8 = bevorzugt |
| Dream | Konsolidiert | Trigger: Stale Policies prunen, Exploration-Reset |
| MetaCognition | Bottleneck-Log | Failure-Kategorien ableiten, goal_type Weights senken |
| Beliefs | Prompt-Anzeige | Hochkonfident → Policy, "challenged" → Weight senken |
| Goal-Tracking | Sackgasse | Alternative → Retry, Generalisierung ueber Goal-Typen |

## Phasen

### Phase 1: Decision Gates + Kausal-Tags (Stufe 1+2 Basis)

Tool+Kontext 3x gescheitert → BLOCKIERT (Code-Enforcement, nicht Prompt).
Cross-Sequenz-Gedaechtnis via policies.json. Bootstrap aus failures.json.
Kausal-Tags (`infrastructure`/`capability`/`input_error`/`logic_error`)
bestimmen Block-Dauer und Recovery-Verhalten von Anfang an.
Exploration-Mechanismus verhindert konservatives Einfrieren.

### Phase 2: Gewichtete Strategie-Auswahl + Adaptive Lernrate

Jede Strategie bekommt Score (0.0-1.0). Erfolg → hoeher, Misserfolg → tiefer.
Unter 0.2 = aus Prompt entfernt. Ueber 0.8 = prominent "BEVORZUGT".
Adaptive Lernrate: lr = 0.3/sqrt(n) — schnell bei wenig Daten, stabil bei vielen.
Transfer-Ansatz: Aehnliche Tool-Patterns (z.B. Browser-Tools) teilen Basis-Weight.

### Phase 3: Failure → Goal Feedback Loop + Generalisierung

Sub-Goal scheitert → Alternative generiert (pattern-basiert + LLM fuer kreative Faelle).
Retry mit anderem Ansatz. Haeufig scheiternde Goal-Typen → Telos-Score sinkt.
Generalisierung: Failure-Kategorien uebergreifend lernen —
"Browser-Automation generell riskant" statt nur "Selenium blockiert".

## Workflow

Working Directory: `c:\Users\olisc\Claude\Lyra` (Repo-Root).

```
1.  BACKLOG.md lesen                    — Welche Phase/Task ist dran?
2.  Ziel-Code lesen                     — IMMER erst verstehen
3.  EINE Sache aendern                  — Minimal, testbar
4.  python review_phi.py                — Gate
5.  Committen
6.  Phi 10-20 Seq beobachten            — policies.json pruefen
7.  Ergebnisse in observations/ loggen
```

## Prinzipien
1. **Code > Prompts** — PolicyVerdict.allowed=False = Tool wird NICHT ausgefuehrt
2. **Integration > Neubau** — Durch SequenceIntelligence, kein Parallel-System
3. **Messen** — Vorher: Wiederholte Failures zaehlen. Nachher: vergleichen
4. **Inkrementell** — Jede Phase unabhaengig wertvoll
5. **Bootstrap** — Bestehende Daten nutzen (failures.json, strategies.json)

## Kritische Regeln
- KEINE Breaking Changes an SequenceIntelligence-Interface
- Jede Aenderung muss `python review_phi.py` bestehen
- policies.json Auto-Backup vor jeder Schema-Aenderung
- Neue Parameter immer mit Default-Wert (bestehende Caller nicht brechen)

## Referenzen
- `engine/sequence_intelligence.py` — Integrations-Fassade
- `engine/meta_rules.py` — Bestehendes Rule-System (erweitern, nicht ersetzen)
- `engine/quantum.py` — FailureMemory (Bootstrap-Quelle)
- `engine/intelligence.py` — StrategyEvolution + Skills (Weight-Quellen)
- `engine/consciousness.py:3019-3045` — Tool-Execution-Loop (Integration)
- `engine/goal_stack.py:319` — fail_subgoal (Phase 3 Hook)
- `.planning/META.md` — Flywheel-Luecken
