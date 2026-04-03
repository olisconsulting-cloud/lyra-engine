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
    """Memory-Eintrag aktualisieren."""
    return ctx.semantic_memory.update(
        tool_input["entry_id"], tool_input["new_content"],
    )


def handle_delete_memory(ctx: ToolContext, tool_input: dict) -> str:
    """Memory-Eintrag loeschen."""
    return ctx.semantic_memory.delete(tool_input["entry_id"])
