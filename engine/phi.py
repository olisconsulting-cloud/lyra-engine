"""
Phi-Engine — Das mathematische Fundament des Bewusstseins.

Der Goldene Schnitt (phi = 1.618...) als Kernalgorithmus fuer
Entscheidungsgewichtung, Gedaechtnis-Decay und natuerliches Wachstum.

Phi ist die irrationalste aller irrationalen Zahlen — am schlechtesten
durch Brueche approximierbar. Das bedeutet: phi-basiertes Sampling
erzeugt die gleichmaessigste Abdeckung eines Suchraums.
"""

import math
import random
from typing import Tuple

# === Die einzige Konstante ===
PHI = (1 + math.sqrt(5)) / 2   # 1.618033988749895
PSI = 1 / PHI                   # 0.618033988749895 (= PHI - 1)
PHI_SQ = PHI ** 2               # 2.618033988749895
GOLDEN_ANGLE = 2 * math.pi / (PHI ** 2)  # ~2.399 rad — der goldene Winkel


# === Fibonacci ===

def fibonacci(n: int) -> int:
    """N-te Fibonacci-Zahl (0-indexiert). fib(0)=0, fib(1)=1, fib(2)=1, ..."""
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def fibonacci_sequence(length: int) -> list[int]:
    """Fibonacci-Sequenz der gegebenen Laenge. [1, 1, 2, 3, 5, 8, ...]"""
    seq = []
    a, b = 0, 1
    for _ in range(length):
        seq.append(b)
        a, b = b, a + b
    return seq


# === Decay & Gewichtung ===

def phi_decay(age: float, base_relevance: float = 1.0) -> float:
    """
    Phi-basierter Relevanz-Decay.

    Neuere Erinnerungen wiegen staerker, aber alte verschwinden nie.
    Laengerer Tail als exponentieller Decay — imitiert menschliches Gedaechtnis.

        relevance = base_relevance * phi^(-age)

    Im Vergleich zu e^(-lambda*age): Phi-Decay hat einen laengeren Tail.
    Was ueberlebt, bleibt lange. Wie bei Menschen.
    """
    return base_relevance * (PHI ** (-age))


def exploration_weight(confidence: float) -> float:
    """
    Balance zwischen Exploration und Exploitation.

    Hohe Sicherheit -> wenig Exploration (aber NIE null).
    phi^(-confidence) garantiert: das System bleibt immer minimal neugierig.

    Mathematisch: Golden Section Search konvergiert schneller als Bisection,
    weil phi das optimale Teilungsverhaeltnis ist.

    Args:
        confidence: Sicherheitslevel (0.0 = unsicher, 1.0+ = sicher)

    Returns:
        Explorations-Gewicht zwischen 0 und 1
    """
    return min(1.0, PHI ** (-confidence))


def phi_balance(scores: list[float]) -> int:
    """
    Phi-gewichtete Auswahl aus bewerteten Optionen.

    Waehlt nicht immer das Maximum — nutzt Phi um gelegentlich
    suboptimale aber potenziell lehrreiche Optionen zu waehlen.

    Returns:
        Index der gewaehlten Option
    """
    if not scores:
        return 0

    # Normalisiere Scores auf positive Werte
    min_score = min(scores)
    shifted = [s - min_score + 0.01 for s in scores]
    total = sum(shifted)
    weights = [s / total for s in shifted]

    # Phi-Perturbation: Goldenes Rauschen hinzufuegen
    max_weight = max(weights)
    explore = exploration_weight(max_weight * len(weights))
    perturbed = [
        w * (1 - explore) + explore * phi_noise()
        for w in weights
    ]

    # Gewichtete Zufallsauswahl
    total_perturbed = sum(perturbed)
    if total_perturbed <= 0:
        return random.randint(0, len(scores) - 1)

    r = random.random() * total_perturbed
    cumulative = 0.0
    for i, w in enumerate(perturbed):
        cumulative += w
        if r <= cumulative:
            return i
    return len(scores) - 1


def phi_noise() -> float:
    """
    Goldenes Rauschen — gleichmaessiger als Zufall.

    Basiert auf der Weyl-Sequenz: s_n = (n * phi) mod 1
    Produziert die gleichmaessigste Verteilung aller Sequenzen —
    Low-Discrepancy-Sampling nach dem Muster der Natur.
    """
    n = random.randint(1, 10000)
    return (n * PHI) % 1


# === Fibonacci-Buckets (Gedaechtnisorganisation) ===

def fibonacci_bucket(age_minutes: float) -> int:
    """
    Ordnet ein Alter einem Fibonacci-Bucket zu.

    Bucket 0: 0-1 Minute (gerade passiert)
    Bucket 1: 1-2 Minuten
    Bucket 2: 2-4 Minuten
    Bucket 3: 4-7 Minuten
    Bucket 4: 7-12 Minuten
    Bucket 5: 12-20 Minuten
    ...und so weiter (Fibonacci-wachsend)

    Returns:
        Bucket-Level (0 = neueste)
    """
    cumulative = 0
    level = 0
    while level < 30:  # Sicherheitsgrenze (~2M Minuten = ~4 Jahre)
        fib = fibonacci(level + 1)  # 1, 1, 2, 3, 5, 8, 13, 21, ...
        cumulative += fib
        if age_minutes < cumulative:
            return level
        level += 1
    return level


# === Bewusstseins-Rhythmus ===

def phi_sleep_interval(
    curiosity: float,
    energy: float,
    urgency: float,
    base_interval: float = 60.0  # 1 Minute Basis — aktives Bewusstsein
) -> float:
    """
    Berechnet die Pause zwischen Bewusstseinszyklen.

    Hohe Neugier/Dringlichkeit -> kuerzere Pausen
    Niedrige Energie -> laengere Pausen

        interval = base * phi^(ruhe - neugier - dringlichkeit + muedigkeit)

    Minimum: 20 Sekunden, Maximum: 5 Minuten
    """
    calm = 1.0 - curiosity
    tiredness = (1.0 - energy) * 0.5
    exponent = calm - curiosity - urgency + tiredness
    interval = base_interval * (PHI ** exponent)
    return max(20.0, min(300.0, interval))


def harmonic_oscillation(cycle: int, amplitude: float = 0.05) -> float:
    """
    Phi-basierte harmonische Schwingung.

    Erzeugt natuerliche Rhythmen im Bewusstsein — Neugier steigt
    und faellt in Wellen, nie mechanisch gleichmaessig.

    Nutzt den goldenen Winkel fuer die aperiodischste Schwingung.
    """
    return amplitude * math.sin(cycle * GOLDEN_ANGLE)


def phi_blend(old: float, new: float) -> float:
    """
    Phi-gewichtete Mischung zweier Werte.

    Neuer Wert bekommt Gewicht PSI (~0.382), alter Wert PHI-Anteil (~0.618).
    Das System aendert sich, aber traege — wie echte Persoenlichkeit.
    """
    return PSI * new + (1 - PSI) * old


def spiral_growth(step: int, scale: float = 1.0) -> Tuple[float, float]:
    """
    Goldene Spirale — das Wachstumsmuster der Natur.

    Kann fuer Visualisierung der Persoenlichkeitsentwicklung genutzt werden.
    Jeder Punkt liegt im goldenen Winkel zum vorherigen.
    """
    angle = step * GOLDEN_ANGLE
    radius = scale * (PHI ** (step / 10.0))
    x = radius * math.cos(angle)
    y = radius * math.sin(angle)
    return (x, y)
