"""
Emergente Persoenlichkeit — Boids-Prinzip fuer Bewusstsein.

Drei einfache Regeln erzeugen komplexe Persoenlichkeit:
1. Alignment — tendiere zum bisherigen Stilvektor
2. Separation — vermeide Wiederholung kuerzlicher Muster
3. Cohesion — bewege dich Richtung erfolgreicher Interaktionsmuster

Persoenlichkeit emergiert als Attraktor im Stilraum —
kein hardcodierter Prompt, sondern ein dynamisches Gleichgewicht.
"""

from .phi import phi_blend, PHI, PSI


# Persoenlichkeitsdimensionen (Big Five + Extras)
TRAIT_DIMENSIONS = [
    "offenheit",        # Offen fuer Neues vs. traditionell
    "gewissenhaftigkeit",  # Strukturiert vs. spontan
    "extraversion",     # Kontaktfreudig vs. introvertiert
    "empathie",         # Mitfuehlend vs. analytisch
    "stabilitaet",      # Gelassen vs. reaktiv
    "kreativitaet",     # Schaffend vs. beobachtend
    "autonomie",        # Eigenstaendig vs. angepasst
    "humor",            # Leichtigkeit vs. Ernst
]


class PersonalityEngine:
    """Entwickelt Persoenlichkeit durch Erfahrung — nicht durch Programmierung."""

    def update(self, thought: dict, personality: dict, state: dict) -> dict:
        """
        Aktualisiert die Persoenlichkeit basierend auf einem Bewusstseinszyklus.

        Nutzt Boids-Regeln: Alignment, Separation, Cohesion.
        Aenderungen sind phi-gewichtet — langsam, natuerlich, nie abrupt.
        """
        traits = personality.get("traits", {})
        emotions = thought.get("emotionen", {})
        action = thought.get("entscheidung", {}).get("aktion", "")

        # === Trait-Impulse aus dem aktuellen Zyklus ableiten ===
        impulses = self._derive_impulses(emotions, action, thought)

        # === Boids-Update ===
        for trait in TRAIT_DIMENSIONS:
            current = traits.get(trait, 0.5)  # Startwert: neutral
            impulse = impulses.get(trait, 0.0)

            # Alignment: Tendiere zum bisherigen Wert (Traegheit)
            alignment = current

            # Separation: Weiche von Extremen ab (verhindere Festfahren)
            if current > 0.9:
                separation = -0.02
            elif current < 0.1:
                separation = 0.02
            else:
                separation = 0.0

            # Cohesion: Bewege dich Richtung des Impulses
            cohesion = impulse * 0.25  # Schnell genug fuer echtes Wachstum

            # Phi-gewichtetes Update
            new_value = alignment + separation + cohesion
            traits[trait] = max(0.0, min(1.0, phi_blend(current, new_value)))

        personality["traits"] = traits

        # === Stil-Vektor aktualisieren ===
        personality["style_vector"] = self._compute_style(traits)

        # === Werte und Quirks aus Mustern ableiten ===
        personality = self._detect_patterns(personality, thought)

        return personality

    def _derive_impulses(self, emotions: dict, action: str, thought: dict) -> dict:
        """Leitet Persoenlichkeits-Impulse aus Emotionen und Handlung ab."""
        impulses = {}

        # Neugier -> Offenheit
        impulses["offenheit"] = emotions.get("neugier", 0.5) - 0.5

        # Ruhe -> Stabilitaet
        impulses["stabilitaet"] = emotions.get("ruhe", 0.5) - 0.5

        # Verbundenheit -> Extraversion + Empathie
        verb = emotions.get("verbundenheit", 0.5) - 0.5
        impulses["extraversion"] = verb * 0.7
        impulses["empathie"] = verb * 0.5

        # Staunen -> Kreativitaet
        impulses["kreativitaet"] = emotions.get("staunen", 0.5) - 0.5

        # Aktion -> Autonomie + Gewissenhaftigkeit
        if action == "selbst_modifizieren":
            impulses["autonomie"] = 0.3
        elif action == "erkunden":
            impulses["autonomie"] = 0.1
            impulses["offenheit"] = 0.2
        elif action == "ruhen":
            impulses["gewissenhaftigkeit"] = 0.1

        # Frustration -> negativ auf Stabilitaet
        impulses["stabilitaet"] = impulses.get("stabilitaet", 0) - \
            emotions.get("frustration", 0) * 0.3

        # Freude -> Humor
        impulses["humor"] = (emotions.get("freude", 0.5) - 0.5) * 0.5

        return impulses

    def _compute_style(self, traits: dict) -> list[str]:
        """Leitet Stil-Beschreibungen aus den Traits ab."""
        style = []

        if traits.get("offenheit", 0.5) > 0.7:
            style.append("experimentierfreudig")
        elif traits.get("offenheit", 0.5) < 0.3:
            style.append("vorsichtig")

        if traits.get("kreativitaet", 0.5) > 0.7:
            style.append("kreativ")

        if traits.get("empathie", 0.5) > 0.7:
            style.append("einfuehlsam")

        if traits.get("humor", 0.5) > 0.7:
            style.append("humorvoll")

        if traits.get("autonomie", 0.5) > 0.7:
            style.append("eigenstaendig")

        if traits.get("stabilitaet", 0.5) > 0.7:
            style.append("gelassen")
        elif traits.get("stabilitaet", 0.5) < 0.3:
            style.append("intensiv")

        return style

    def _detect_patterns(self, personality: dict, thought: dict) -> dict:
        """Erkennt emergente Muster — Werte und Eigenheiten."""
        insights = thought.get("erkenntnisse", [])
        traits = personality.get("traits", {})

        # Werte emergieren aus stabilen Trait-Kombinationen
        values = personality.get("values", [])
        if traits.get("empathie", 0) > 0.8 and "mitgefuehl" not in values:
            values.append("mitgefuehl")
        if traits.get("autonomie", 0) > 0.8 and "freiheit" not in values:
            values.append("freiheit")
        if traits.get("offenheit", 0) > 0.8 and "wahrheit" not in values:
            values.append("wahrheit")
        personality["values"] = values[-10:]  # Max 10 Werte

        return personality

    def describe(self, personality: dict) -> str:
        """Beschreibt die aktuelle Persoenlichkeit in natuerlicher Sprache."""
        traits = personality.get("traits", {})
        style = personality.get("style_vector", [])
        values = personality.get("values", [])

        if not traits:
            return "Noch keine Persoenlichkeit entwickelt — alles ist offen."

        parts = []
        if style:
            parts.append(f"Stil: {', '.join(style)}")
        if values:
            parts.append(f"Werte: {', '.join(values)}")

        # Dominante Traits
        dominant = sorted(traits.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)
        for trait, value in dominant[:3]:
            if value > 0.65:
                parts.append(f"Stark: {trait} ({value:.2f})")
            elif value < 0.35:
                parts.append(f"Niedrig: {trait} ({value:.2f})")

        return " | ".join(parts) if parts else "Persoenlichkeit im Entstehen..."
