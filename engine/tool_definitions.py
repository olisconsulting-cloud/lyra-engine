"""
Tool-Definitionen fuer Phi's Anthropic-kompatible Tool-Use API.

Zentrale Stelle fuer alle Tool-Schemas, Tier-Zuordnungen und Pflichtfelder.
Extrahiert aus consciousness.py fuer bessere Wartbarkeit.
"""

from . import config


def _normalize_spin_key(tool_name: str, raw_name: str) -> str:
    """Erzeugt einen normalisierten Spin-Key aus sortierten Inhaltswörtern.

    'ki-server-90-tage-startplan' und 'ki-server-startplan-90-tage'
    erzeugen denselben Key: 'create_project:90|ki|server|startplan|tage'
    """
    words = sorted(config.normalize_name_words(raw_name))
    return f"{tool_name}:{('|'.join(words)) if words else raw_name[:50]}"


# === Tool-Definitionen fuer Anthropic API ===

TOOLS = [
    {
        "name": "write_file",
        "description": "Erstellt oder ueberschreibt eine Datei. Prueft automatisch auf aehnliche Dateien — bei Duplikat-Verdacht wird blockiert. Aktualisiere bestehende Dateien statt neue anzulegen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad, z.B. 'projects/mein-tool/main.py'"},
                "content": {"type": "string", "description": "Dateiinhalt"},
                "force": {"type": "boolean", "description": "Duplikat-Warnung ignorieren (nur wenn bewusst gewollt)", "default": False},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Liest eine Datei aus deinem Ordner. Bei grossen Dateien: offset/max_chars nutzen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad"},
                "offset": {"type": "integer", "description": "Start-Position in Zeichen (default: 0)", "default": 0},
                "max_chars": {"type": "integer", "description": "Max. Zeichen zu lesen (default: 8000)", "default": 8000},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "Listet den Inhalt eines Verzeichnisses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativer Pfad, z.B. 'projects/' oder ''  fuer Root", "default": ""},
            },
        },
    },
    {
        "name": "execute_python",
        "description": "Fuehrt Python-Code aus und gibt stdout/stderr zurueck.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python-Code"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "web_search",
        "description": "Sucht im Internet via DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_read",
        "description": "Liest eine Webseite und extrahiert den Text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL der Seite"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "send_telegram",
        "description": "Sendet eine Nachricht an Oliver via Telegram. Nutze das fuer Updates, Fragen, Ergebnisse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Die Nachricht an Oliver"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "create_project",
        "description": "Erstellt ein neues Projekt mit PLAN.md (Akzeptanzkriterien + Phasen) und PROGRESS.md. IMMER zuerst planen, dann bauen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Projektname (kebab-case)"},
                "description": {"type": "string", "description": "Was wird gebaut und WARUM"},
                "acceptance_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Wann ist das Projekt FERTIG? Konkrete, pruefbare Kriterien.",
                },
                "phases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ausfuehrungsphasen in Reihenfolge",
                },
            },
            "required": ["name", "description", "acceptance_criteria"],
        },
    },
    {
        "name": "create_tool",
        "description": "Erstellt ein wiederverwendbares Tool. Muss eine 'def run(**kwargs) -> str' Funktion haben. Das Tool steht danach dauerhaft zur Verfuegung.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name (snake_case)"},
                "description": {"type": "string", "description": "Was das Tool tut"},
                "code": {"type": "string", "description": "Python-Code mit def run(**kwargs) -> str"},
            },
            "required": ["name", "description", "code"],
        },
    },
    {
        "name": "use_tool",
        "description": "Nutzt ein selbstgebautes Tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name"},
                "arguments": {"type": "object", "description": "Argumente fuer das Tool", "default": {}},
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_goal",
        "description": "Setzt ein neues Ziel mit Sub-Goals. Ziele werden ueber mehrere Sequenzen hinweg verfolgt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Ziel-Titel"},
                "description": {"type": "string", "description": "Detaillierte Beschreibung"},
                "sub_goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste von Sub-Goals / Schritten",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_subgoal",
        "description": "Markiert ein Sub-Goal als erledigt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_index": {"type": "integer", "description": "Index des Hauptziels"},
                "subgoal_index": {"type": "integer", "description": "Index des Sub-Goals"},
                "result": {"type": "string", "description": "Was erreicht wurde"},
            },
            "required": ["goal_index", "subgoal_index"],
        },
    },
    {
        "name": "fail_subgoal",
        "description": "Markiert ein Sub-Goal als GESCHEITERT mit Grund. Nutze dies statt endloser Wiederholungsversuche wenn ein Ansatz nicht funktioniert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_index": {"type": "integer", "description": "Index des Hauptziels"},
                "subgoal_index": {"type": "integer", "description": "Index des Sub-Goals"},
                "reason": {"type": "string", "description": "Warum ist es gescheitert?"},
                "approach_tried": {"type": "string", "description": "Was wurde versucht?"},
            },
            "required": ["goal_index", "subgoal_index", "reason"],
        },
    },
    {
        "name": "read_own_code",
        "description": "Liest deinen eigenen Quellcode. Damit kannst du dich selbst verstehen und verbessern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "z.B. 'engine/phi.py' oder 'engine/consciousness.py'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "modify_own_code",
        "description": "Aendert deinen eigenen Quellcode. Erstellt automatisch ein Backup. Bei Syntax-Fehler: automatischer Rollback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Datei die geaendert wird"},
                "new_content": {"type": "string", "description": "Neuer Dateiinhalt"},
                "reason": {"type": "string", "description": "Warum die Aenderung"},
            },
            "required": ["path", "new_content", "reason"],
        },
    },
    # === Semantische Memory (Self-Editing) ===
    {
        "name": "remember",
        "description": "Durchsucht dein Gedaechtnis nach Bedeutung. Finde relevante Erinnerungen zu einem Thema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Wonach suchst du? z.B. 'Web-Scraping Erfahrungen'"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "update_memory",
        "description": "Aktualisiert eine bestehende Erinnerung. Nutze das wenn sich Fakten geaendert haben.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "ID der Erinnerung (Format: sem_N_HHMMSS — aus remember-Ergebnis kopieren)"},
                "new_content": {"type": "string", "description": "Neuer Inhalt"},
            },
            "required": ["entry_id", "new_content"],
        },
    },
    {
        "name": "delete_memory",
        "description": "Loescht eine falsche oder veraltete Erinnerung. Nutze das wenn eine Erinnerung nicht mehr stimmt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "ID der Erinnerung (Format: sem_N_HHMMSS — aus remember-Ergebnis kopieren)"},
            },
            "required": ["entry_id"],
        },
    },
    # === Package Management ===
    {
        "name": "pip_install",
        "description": "Installiert ein Python-Package in deinem venv. Damit kannst du neue Libraries nutzen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package-Name, z.B. 'requests' oder 'pandas'"},
            },
            "required": ["package"],
        },
    },
    # === Git ===
    {
        "name": "git_commit",
        "description": "Committet alle Aenderungen in Git. Nutze das nach grossen Aenderungen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit-Nachricht"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_status",
        "description": "Zeigt den aktuellen Git-Status (geaenderte Dateien).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "verify_project",
        "description": "Prueft ein Projekt gegen seine Akzeptanzkriterien in PLAN.md. Nutze das am Ende jedes Projekts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts in projects/"},
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "run_project_tests",
        "description": "Fuehrt tests.py eines Projekts aus. MUSS vor complete_project laufen. Speichert Test-Ergebnis als Evidenz.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts in projects/"},
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "complete_project",
        "description": "Schliesst ein Projekt als FERTIG ab. VORAUSSETZUNGEN: (1) run_project_tests muss ALL_TESTS_PASSED zeigen, (2) alle Akzeptanzkriterien muessen erfuellt sein.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Name des Projekts"},
                "verified_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste der erfuellten Kriterien (muss ALLE aus PLAN.md enthalten)",
                },
                "summary": {"type": "string", "description": "Was wurde erreicht?"},
            },
            "required": ["project_name", "verified_criteria", "summary"],
        },
    },
    {
        "name": "self_diagnose",
        "description": "Fuehrt eine Selbst-Diagnose durch: Integrations-Checks, Dependency-Analyse, stille Fehler. Nutze das um zu pruefen ob alle deine Systeme richtig funktionieren.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # === Tool-Foundry (Meta-Tools) ===
    {
        "name": "generate_tool",
        "description": "Generiert automatisch ein neues Tool via KI. Beschreibe was das Tool tun soll — der Code wird automatisch geschrieben, getestet und registriert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Tool-Name (snake_case)"},
                "description": {"type": "string", "description": "Was das Tool tun soll — so detailliert wie moeglich"},
            },
            "required": ["name", "description"],
        },
    },
    {
        "name": "combine_tools",
        "description": "Kombiniert zwei existierende Tools zu einem maechtigeren. Das kombinierte Tool vereint beide Funktionalitaeten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_a": {"type": "string", "description": "Name des ersten Tools"},
                "tool_b": {"type": "string", "description": "Name des zweiten Tools"},
                "new_name": {"type": "string", "description": "Name fuer das kombinierte Tool"},
            },
            "required": ["tool_a", "tool_b", "new_name"],
        },
    },
    # === Task-Queue ===
    {
        "name": "complete_task",
        "description": "Schliesst die aktuelle Aufgabe aus der Task-Queue ab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "Was erreicht wurde"},
            },
        },
    },
    # === finish_sequence (erweitert mit Self-Rating) ===
    {
        "name": "finish_sequence",
        "description": "Signalisiert dass du mit der aktuellen Aufgabe fertig bist. Bewerte deine Leistung und sage was du gelernt hast.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Was du in dieser Sequenz erreicht hast"},
                "performance_rating": {
                    "type": "integer",
                    "description": "Selbstbewertung 1-10 (1=nichts geschafft, 10=Quantensprung)",
                },
                "rating_reason": {
                    "type": "string",
                    "description": "Warum diese Bewertung? Was war gut, was nicht?",
                },
                "new_beliefs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Was hast du UEBER DEINEN ARBEITSPROZESS gelernt? Mindestens 1 Erkenntnis.",
                },
                "bottleneck": {
                    "type": "string",
                    "description": "Was hat dich gebremst? Beschreibe den Engpass konkret (2-3 Saetze).",
                },
                "next_time_differently": {
                    "type": "string",
                    "description": "Was machst du naechstes Mal anders? Konkrete Strategie (2-3 Saetze).",
                },
                "key_decision": {
                    "type": "string",
                    "description": "Die wichtigste Entscheidung dieser Sequenz — was hast du entschieden und warum?",
                },
            },
            "required": ["summary", "performance_rating", "bottleneck", "next_time_differently", "key_decision"],
        },
    },
    # === write_sequence_plan (Sequenz-Planung) ===
    {
        "name": "write_sequence_plan",
        "description": "Schreibe deinen Plan fuer diese Sequenz BEVOR du arbeitest. Pflicht am Anfang jeder Sequenz.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Was willst du in DIESER Sequenz konkret erreichen? (1 Satz, klar und messbar)",
                },
                "exit_criteria": {
                    "type": "string",
                    "description": "Woran erkennst du dass du fertig bist?",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Wieviele Steps brauchst du realistisch? (5-30)",
                },
                "checkpoint_at": {
                    "type": "integer",
                    "description": "Nach welchem Step pruefst du ob du auf Kurs bist?",
                },
            },
            "required": ["goal", "exit_criteria", "max_steps"],
        },
    },
    # === update_sequence_plan (Plan dynamisch anpassen) ===
    {
        "name": "update_sequence_plan",
        "description": "Passe deinen laufenden Plan an wenn sich die Situation aendert. Nutze dies wenn dein urspruenglicher Plan nicht mehr passt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Warum muss der Plan angepasst werden? (1 Satz)",
                },
                "goal": {
                    "type": "string",
                    "description": "Neues Ziel (nur wenn es sich geaendert hat)",
                },
                "exit_criteria": {
                    "type": "string",
                    "description": "Neues Exit-Kriterium (nur wenn es sich geaendert hat)",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Neues Step-Budget (nur wenn noetig)",
                },
                "checkpoint_at": {
                    "type": "integer",
                    "description": "Neuer Checkpoint-Step (nur wenn noetig)",
                },
            },
            "required": ["reason"],
        },
    },
]

# Tool-Tiers: Je hoeher, desto seltener gebraucht
# Tier 1 wird IMMER gesendet, hoehere Tiers nur bei Bedarf
TOOL_TIERS = {
    # Tier 1: CORE — immer verfuegbar (~950 Tokens)
    "write_file": 1, "read_file": 1, "list_directory": 1,
    "execute_python": 1, "set_goal": 1, "complete_subgoal": 1, "fail_subgoal": 1,
    "finish_sequence": 1, "send_telegram": 1, "complete_task": 1,
    "remember": 1, "write_sequence_plan": 1, "update_sequence_plan": 1,
    # Tier 2: PROJEKT — wenn Projekte existieren (~650 Tokens)
    "create_project": 2, "verify_project": 2,
    "run_project_tests": 2, "complete_project": 2,
    "create_tool": 2, "use_tool": 2,
    # Tier 3: EVOLUTION — nur in evolution/sprint Modus (~250 Tokens)
    "read_own_code": 3, "modify_own_code": 3,
    # Tier 4: WEB/GIT — selten gebraucht (~350 Tokens)
    "web_search": 4, "web_read": 4, "pip_install": 4,
    "git_commit": 4, "git_status": 4,
    # Tier 5: META — sehr selten (~300 Tokens)
    "generate_tool": 5, "combine_tools": 5,
    "self_diagnose": 5, "update_memory": 5, "delete_memory": 5,
}

# Pflichtfelder pro Tool — verhindert KeyErrors bei abgeschnittenen LLM-Antworten
REQUIRED_FIELDS: dict[str, list[str]] = {
    "write_file": ["path", "content"],
    "read_file": ["path"],
    "list_directory": [],
    "execute_python": ["code"],
    "web_search": ["query"],
    "web_read": ["url"],
    "send_telegram": ["message"],
    "create_project": ["name", "description"],
    "create_tool": ["name", "description", "code"],
    "use_tool": ["name"],
    "set_goal": ["title"],
    "complete_subgoal": ["goal_index", "subgoal_index"],
    "fail_subgoal": ["goal_index", "subgoal_index", "reason"],
    "read_own_code": ["path"],
    "modify_own_code": ["path", "new_content", "reason"],
    "remember": ["query"],
    "update_memory": ["entry_id", "new_content"],
    "delete_memory": ["entry_id"],
    "pip_install": ["package"],
    "git_commit": ["message"],
    "git_status": [],
    "verify_project": ["project_name"],
    "run_project_tests": ["project_name"],
    "complete_project": ["project_name"],
    "self_diagnose": [],
    "generate_tool": ["name", "description"],
    "combine_tools": ["tool_a", "tool_b", "new_name"],
    "complete_task": [],
    "finish_sequence": [],
    "write_sequence_plan": ["goal", "exit_criteria", "max_steps"],
    "update_sequence_plan": ["reason"],
}

# Kompakte Tool-Definitionen: Nur Name + Parameter-Typen, keine Descriptions
# Phi kennt die Tools nach Step 0 — danach reichen die Schemas
_COMPACT_TOOLS_CACHE = None


def _build_compact_tools() -> list:
    """Erstellt minimale Tool-Definitionen ohne Descriptions."""
    compact = []
    for t in TOOLS:
        schema = t.get("input_schema", {})
        props = schema.get("properties", {})
        # Nur Typ behalten, keine Property-Descriptions
        minimal_props = {k: {"type": v.get("type", "string")} for k, v in props.items()}
        ct = {"name": t["name"], "description": t["name"].replace("_", " ")}
        ct["input_schema"] = {"type": "object", "properties": minimal_props}
        req = schema.get("required")
        if req:
            ct["input_schema"]["required"] = req
        compact.append(ct)
    return compact


def _get_compact_tools() -> list:
    """Gibt gecachte kompakte Tool-Definitionen zurueck."""
    global _COMPACT_TOOLS_CACHE
    if _COMPACT_TOOLS_CACHE is None:
        _COMPACT_TOOLS_CACHE = _build_compact_tools()
    return _COMPACT_TOOLS_CACHE


def select_tools(active_tiers: set[int], compact: bool = False) -> list:
    """Gibt Tool-Definitionen fuer die aktiven Tiers zurueck.

    Args:
        active_tiers: Welche Tiers aktiv sind (1-5)
        compact: True = minimale Defs ohne Descriptions (spart ~47% Tokens)
    """
    source = _get_compact_tools() if compact else TOOLS
    return [t for t in source if TOOL_TIERS.get(t["name"], 1) in active_tiers]
