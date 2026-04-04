# Policy Engine — Backlog

> Sortiert nach Phase. Jede Phase ist unabhaengig wertvoll.
> Stufe 1 (Bestrafung) → Stufe 2 (Verstaendnis) → Stufe 3 (Generalisierung)

## Phase 1: Decision Gates + Kausal-Tags

### 1.1 engine/policy.py erstellen

- [ ] PolicyVerdict Dataclass (allowed, reason, alternative, confidence)
- [ ] FailureCategory Enum (capability, input_error, logic_error, unknown)
      NICHT infrastructure — das macht ProviderHealth im Router
- [ ] PolicyEngine.__init__: policies.json laden/erstellen
- [ ] PolicyEngine._make_context_key(tool, input, goal): Normalisierter Key
- [ ] PolicyEngine._classify_failure(error_msg, tool_name): Kausal-Tag ableiten
- [ ] PolicyEngine._is_infrastructure_error(error_msg): True → IGNORIEREN (Router-Sache)
- [ ] DecisionGate.check(): Weight pruefen, Kausal-Tag beruecksichtigen
  - capability: Block 24h (permanent bis System-Change)
  - input_error: Weight sinkt, kein Block (andere Inputs probieren)
  - logic_error: Weight sinkt stark, Recovery nach Tool-Fix
  - unknown: Wie logic_error (konservativ)
- [ ] DecisionGate.update_from_failure(): Adaptive Lernrate lr=0.3/sqrt(n)
- [ ] DecisionGate.update_from_success(): Adaptive Lernrate + Block aufheben
- [ ] PolicyEngine.check_before_tool(): Zentraler Entry-Point
- [ ] PolicyEngine.record_after_tool(): Lernen nach Ausfuehrung
- [ ] PolicyEngine._suggest_alternative(): Andere Tools mit weight > 0.5 finden
- [ ] PolicyEngine._bootstrap(): failures.json + strategies.json fuer initiale Weights
- [ ] PolicyEngine._save(): policies.json schreiben (thread-safe)

### 1.2 Exploration-Mechanismus

- [ ] `can_retry_after` Feld pro blockierter Policy
  - Default nach Kategorie: capability +100, logic_error +30, unknown +50
- [ ] Probe-Logik: Wenn can_retry_after erreicht → 1 vorsichtiger Versuch
  - Erfolg: Weight += 0.3, Block aufgehoben
  - Failure: can_retry_after verdoppeln (exponentieller Backoff)
- [ ] Rate-Limit: Max 1 Exploration pro 10 Sequenzen

### 1.3 sequence_intelligence.py erweitern

- [ ] Import PolicyEngine
- [ ] __init__: self._policy = PolicyEngine(consciousness_path)
- [ ] check_blocked(): goal_context Parameter (Default ""), Policy-Gate nach Stuck-Check
- [ ] after_tool(): goal_context Parameter (Default ""), Policy-Recording

### 1.4 consciousness.py anpassen

- [ ] Zeile ~3021: goal_context=focus an check_blocked durchreichen
- [ ] Zeile ~3045: goal_context=focus an after_tool durchreichen

### 1.5 Testen

- [ ] python review_phi.py bestehen
- [ ] Manueller Test: 3 Failures mit capability-Tag → Block (Exploration +100 Seq)
- [ ] Manueller Test: 3 Failures mit logic_error-Tag → Block (Exploration +30 Seq)
- [ ] Manueller Test: Infrastructure-Fehler werden IGNORIERT (nicht in policies.json)
- [ ] Manueller Test: Exploration-Probe nach can_retry_after
- [ ] Phi 10 Seq laufen lassen, policies.json pruefen

## Phase 2: Gewichtete Strategie-Auswahl + Adaptive Lernrate

### 2.1 PolicyWeights Klasse

- [ ] WeightedStrategy Dataclass (strategy_id, description, weight, status)
- [ ] get_weights(goal_type): Gewichtete Strategien zurueckgeben
- [ ] update_weight(strategy_id, success): Adaptive EMA (lr=0.3/sqrt(n))
- [ ] classify_status(): <0.2 blocked, >0.8 preferred
- [ ] Transfer-Ansatz: Aehnliche Tool-Patterns gruppieren (z.B. browser_*)

### 2.2 Integration in Prompt

- [ ] sequence_intelligence.py: init_sequence() mit Policy-Strategien erweitern
- [ ] meta_rules.py: get_prompt_injections() mit gewichteten Strategien
- [ ] Top-3 preferred: prominent im Prompt mit "BEVORZUGT"
- [ ] Blocked Strategien: ENTFERNEN aus Prompt (nicht warnen — weg)
- [ ] Mittlere Strategien: normal anzeigen mit Weight-Indikator

### 2.3 Testen

- [ ] Unit-Test: Weight-Decay (lr=0.3 bei n=1, lr=0.06 bei n=25)
- [ ] Unit-Test: Transfer — browser_selenium blocked → browser_playwright gewarnt
- [ ] Phi 10 Seq: Strategien verschwinden/erscheinen basierend auf Weight

## Phase 3: Failure → Goal Feedback + Generalisierung

### 3.1 FailureGoalLoop Klasse

- [ ] AlternativeApproach Dataclass (original, alternative, reasoning, confidence)
- [ ] generate_alternative(): Pattern-basiert + LLM-Call fuer kreative Faelle
- [ ] adjust_goal_weights(): goal_type Success/Failure → Telos-Weight
- [ ] Generalisierung: Failure-Kategorien uebergreifend lernen
  - "3x Browser-Tool gescheitert" → "Browser-Automation generell riskant"
  - Nicht nur Tool+Kontext, sondern Tool-KLASSEN lernen

### 3.2 Goal-Stack Integration

- [ ] goal_stack.py: fail_subgoal() → Policy-Callback
- [ ] goal_stack.py: _telos_score() → Policy Weight-Adjustment
- [ ] consciousness.py: Callback verdrahten
- [ ] Retry-Sub-Goals mit "[RETRY]" Prefix + anderem Ansatz

### 3.3 Testen

- [ ] Unit-Test: Sub-Goal Failure → Alternative generiert (pattern-basiert)
- [ ] Unit-Test: Sub-Goal Failure → LLM-Alternative wenn kein Pattern
- [ ] Unit-Test: 10x Goal-Typ Failure → Telos-Score sinkt
- [ ] Unit-Test: Generalisierung — Selenium blocked → Playwright gewarnt
- [ ] Phi 20 Seq: Retry-Sub-Goals erscheinen nach Failures
