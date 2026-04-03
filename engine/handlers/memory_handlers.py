"""
Handler fuer Semantische Memory: remember, update_memory, delete_memory.
"""

from .context import ToolContext


def handle_remember(ctx: ToolContext, tool_input: dict) -> str:
    """Semantische Memory durchsuchen."""
    results = ctx.semantic_memory.search(tool_input["query"], top_k=5)
    if not results:
        return f"Keine Erinnerungen zu '{tool_input['query']}' gefunden."

    lines = [f"Erinnerungen zu '{tool_input['query']}':"]
    for r in results:
        imp = r.get("importance", 0.3)
        lines.append(
            f"  [{r['similarity']:.2f}|imp:{imp:.1f}] "
            f"({r.get('metadata', {}).get('tool', '?')}) "
            f"{r['content'][:200]}"
        )
    return "\n".join(lines)


def handle_update_memory(ctx: ToolContext, tool_input: dict) -> str:
    """Memory-Eintrag aktualisieren mit Fuzzy-ID-Matching."""
    try:
        entry_id = tool_input.get("entry_id", "")
        new_content = tool_input.get("new_content", "")

        if not entry_id or not new_content:
            return "FEHLER: entry_id und new_content erforderlich."

        result = ctx.semantic_memory.update(entry_id, new_content)

        # Bei nicht gefundener ID: Aehnliche IDs per Prefix suchen
        if "nicht gefunden" in result:
            prefix = entry_id.split("_")[0] if "_" in entry_id else entry_id[:5]
            similar = [
                e.get("id", "") for e in ctx.semantic_memory.index.get("entries", [])
                if prefix in e.get("id", "")
            ][:5]
            if similar:
                result += f"\nAehnliche IDs: {similar}"

        return result
    except Exception as e:
        return f"FEHLER: update_memory fehlgeschlagen: {e}"


def handle_delete_memory(ctx: ToolContext, tool_input: dict) -> str:
    """Memory-Eintrag loeschen."""
    return ctx.semantic_memory.delete(tool_input["entry_id"])
