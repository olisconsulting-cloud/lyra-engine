"""
Bootstrap — Universelles Wissen fuer neue Lyra-Instanzen.

Laedt kuratierte Defaults aus engine/bootstrap/*.json und merged sie
mit instanz-spezifischen Daten aus data/consciousness/*.json.

Merge-Semantik: Instanz-Daten gewinnen immer. Bootstrap fuellt Luecken.
"""

import copy
import logging
from pathlib import Path

from ..config import safe_json_read

logger = logging.getLogger(__name__)

BOOTSTRAP_PATH = Path(__file__).parent


def _read_bootstrap(filename: str, default=None):
    """Liest eine Bootstrap-Datei aus engine/bootstrap/."""
    path = BOOTSTRAP_PATH / filename
    return safe_json_read(path, default=default if default is not None else {})


# === Meta-Rules Merge ===

def load_meta_rules(instance_path: Path) -> dict:
    """Laedt Meta-Regeln: Bootstrap-Defaults + Instanz-Overrides.

    Merge by Rule-ID: Instanz-Regeln ueberschreiben gleichnamige Bootstrap-Regeln.
    Pattern-Counts werden per max() gemerged (hoeherer Wert gewinnt).
    """
    bootstrap = _read_bootstrap("meta_rules.json", default={"rules": [], "pattern_counts": {}})
    instance = safe_json_read(instance_path, default=None)

    if instance is None:
        # Frische Instanz — Bootstrap als Startpunkt
        logger.info("Bootstrap: Meta-Regeln geladen (frische Instanz)")
        return copy.deepcopy(bootstrap)

    # Instanz-Regeln nach ID indexieren (defensiv: Regeln ohne ID ignorieren)
    instance_rules = [r for r in instance.get("rules", []) if isinstance(r, dict)]
    instance_ids = {r.get("id") for r in instance_rules if r.get("id")}

    # Bootstrap-Regeln hinzufuegen die in der Instanz fehlen
    merged_rules = list(instance_rules)
    added = 0
    for rule in bootstrap.get("rules", []):
        if not isinstance(rule, dict) or not rule.get("id"):
            continue
        if rule["id"] not in instance_ids:
            merged_rules.append(copy.deepcopy(rule))
            added += 1

    # Pattern-Counts: max() aus beiden Quellen
    merged_counts = dict(bootstrap.get("pattern_counts", {}))
    for key, val in instance.get("pattern_counts", {}).items():
        merged_counts[key] = max(merged_counts.get(key, 0), val)

    if added:
        logger.info(f"Bootstrap: {added} neue Meta-Regeln hinzugefuegt")

    return {"rules": merged_rules, "pattern_counts": merged_counts}


# === Beliefs Merge ===

def load_beliefs(instance_path: Path) -> dict:
    """Laedt Beliefs: Bootstrap-Defaults + Instanz-Overrides.

    Deduplizierung nach Text-Inhalt (lowercase-Vergleich).
    """
    bootstrap = _read_bootstrap("beliefs.json", default={})
    instance = safe_json_read(instance_path, default=None)

    if instance is None:
        logger.info("Bootstrap: Beliefs geladen (frische Instanz)")
        return copy.deepcopy(bootstrap)

    # Fuer jede Kategorie: Bootstrap-Eintraege hinzufuegen die fehlen
    merged = copy.deepcopy(instance)
    added = 0
    for category, items in bootstrap.items():
        if category.startswith("_") or not isinstance(items, list):
            continue
        existing = merged.setdefault(category, [])
        if not isinstance(existing, list):
            continue  # Kategorie hat unerwarteten Typ — nicht anfassen
        existing_lower = {str(b).lower() for b in existing}
        for belief in items:
            if str(belief).lower() not in existing_lower:
                existing.append(belief)
                added += 1

    if added:
        logger.info(f"Bootstrap: {added} neue Beliefs hinzugefuegt")

    return merged


# === Strategies Merge ===

def load_strategies(instance_path: Path) -> list:
    """Laedt Strategies: Bootstrap-Defaults + Instanz-Overrides.

    Deduplizierung nach 'pattern'-Feld.
    """
    bootstrap = _read_bootstrap("strategies.json", default=[])
    instance = safe_json_read(instance_path, default=None)

    if instance is None:
        logger.info("Bootstrap: Strategies geladen (frische Instanz)")
        return copy.deepcopy(bootstrap)

    # Existierende Patterns sammeln (defensiv: non-dict Elemente ignorieren)
    existing_patterns = {s.get("pattern", "") for s in instance if isinstance(s, dict)}

    # Bootstrap-Strategies hinzufuegen die fehlen
    merged = list(instance)
    added = 0
    for strategy in bootstrap:
        if strategy.get("pattern", "") not in existing_patterns:
            merged.append(copy.deepcopy(strategy))
            added += 1

    if added:
        logger.info(f"Bootstrap: {added} neue Strategies hinzugefuegt")

    return merged


# === Actuator Defaults ===

def load_actuator_defaults() -> dict:
    """Laedt getunte Default-Parameter aus Bootstrap.

    Gibt dict zurueck das direkt als DEFAULTS-Konstante genutzt wird.
    """
    bootstrap = _read_bootstrap("actuator_defaults.json", default={})
    params = bootstrap.get("parameters", {})

    # Fallback auf hardcoded Werte wenn Bootstrap-Datei fehlt
    defaults = {
        "step_budget_modifier": 1.0,
        "research_depth_limit": 25,
        "output_checkpoint_step": 20,
    }
    defaults.update(params)
    return defaults


# === Approved Packages Merge ===

def load_approved_packages(instance_approved: set) -> set:
    """Laedt genehmigte Pakete: Bootstrap-Allowlist + Instanz-Genehmigungen.

    Union aus beiden Quellen. Instanz-Set stammt aus state.json.
    """
    bootstrap = _read_bootstrap("approved_packages.json", default={"packages": []})
    bootstrap_set = {p.lower() for p in bootstrap.get("packages", [])}
    instance_lower = {p.lower() for p in instance_approved}
    merged = bootstrap_set | instance_lower
    new_from_bootstrap = bootstrap_set - instance_lower
    if new_from_bootstrap:
        logger.info(f"Bootstrap: {len(new_from_bootstrap)} Pakete aus Allowlist geladen")
    return merged
