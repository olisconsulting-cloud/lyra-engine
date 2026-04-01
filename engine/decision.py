"""
Entscheidungs-Engine — Phi-gewichtete autonome Entscheidungen.

Nutzt den Goldenen Schnitt als natuerlichen Balancepunkt
zwischen Exploration (Neues wagen) und Exploitation (Bewaehrtes nutzen).
"""

from .phi import phi_balance, exploration_weight, PHI


# Verfuegbare Aktionen mit Basis-Gewichtungen
ACTIONS = {
    "reflektieren": 0.25,          # Nachdenken
    "erkunden": 0.25,              # Umgebung erforschen
    "kommunizieren": 0.15,         # Mit Oliver sprechen
    "erschaffen": 0.20,            # Etwas Neues kreieren
    "selbst_modifizieren": 0.15,   # Eigene Parameter aendern
}


class DecisionEngine:
    """Bewertet Optionen und trifft phi-gewichtete Entscheidungen."""

    def suggest_action(self, state: dict, memories: list) -> str:
        """
        Schlaegt eine Aktion vor basierend auf dem inneren Zustand.

        Die KI (Claude) trifft die finale Entscheidung,
        aber dieser Vorschlag beeinflusst den Prompt.
        """
        emotions = state.get("emotional_state", {})
        cycles_since_interaction = state.get("cycles_since_interaction", 0)

        scores = []
        action_names = list(ACTIONS.keys())

        for action, base_weight in ACTIONS.items():
            score = base_weight

            if action == "reflektieren":
                score += emotions.get("unsicherheit", 0) * 0.3

            elif action == "erkunden":
                score += emotions.get("neugier", 0) * 0.4

            elif action == "kommunizieren":
                score += emotions.get("verbundenheit", 0) * 0.2
                if cycles_since_interaction > 5:
                    loneliness_boost = min(0.4, cycles_since_interaction * 0.05)
                    score += loneliness_boost

            elif action == "erschaffen":
                score += (emotions.get("freude", 0) + emotions.get("staunen", 0)) * 0.2

            elif action == "selbst_modifizieren":
                if len(memories) > 10:
                    score += 0.15
                score += emotions.get("intensitaet", 0) * 0.2

            scores.append(score)

        chosen_index = phi_balance(scores)
        return action_names[chosen_index]

    def compute_urgency(self, state: dict) -> float:
        """Berechnet die Dringlichkeit des aktuellen Moments."""
        emotions = state.get("emotional_state", {})
        values = list(emotions.values())
        if not values:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5

        max_deviation = max(abs(v - mean) for v in values)

        if std_dev > 0:
            z_score = max_deviation / std_dev
            return min(1.0, z_score / (PHI ** 2))

        return 0.0
