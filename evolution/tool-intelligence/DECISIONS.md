# Tool Intelligence — Architecture Decision Records

## ADR-001: Sliding Window statt historischer Stability (2026-04-04)

**Kontext**: Stability-Metrik berechnet Failure-Rate ueber ALLE Calls.
Ein Tool das 10x fehlschlaegt, dann 2x erfolgreich ist, erholt sich nie.

**Entscheidung**: Letzte 10 Calls als Ring-Buffer, Stability = Success-Rate davon.

**Konsequenz**: Tools koennen sich erholen. Kurzfristige Ausfaelle (API-Downtime)
bestrafen nicht dauerhaft.

## ADR-002: Health-Score Minimum-Gate (2026-04-04)

**Kontext**: Linearer Health-Score erlaubt Health 6.0 bei 50% Failure-Rate
wenn Tool recent und viel genutzt. Das ist semantisch falsch.

**Entscheidung**: success_rate < 0.3 → max Health 3.0; < 0.1 → max Health 1.0.
Non-lineares Gate VOR dem gewichteten Durchschnitt.

**Konsequenz**: Unzuverlaessige Tools werden zuverlaessig erkannt,
unabhaengig von Recency oder Volume.

## ADR-003: Goal-Context als Set statt Liste (2026-04-04)

**Kontext**: Jede Tool-Nutzung hat einen Goal-Kontext.
Speicherung als Liste wuerde unbegrenzt wachsen.

**Entscheidung**: Set der einzigartigen goal_types (recherche, tool_building, etc.)
plus Zaehler pro Typ. Max 20 Typen.

**Konsequenz**: Zeigt Tool-Vielseitigkeit ohne Speicher-Explosion.
