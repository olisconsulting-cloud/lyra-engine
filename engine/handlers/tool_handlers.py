"""
Handler fuer Tool-Erstellung und -Nutzung:
create_tool, use_tool, generate_tool, combine_tools.
"""

from .context import ToolContext


def handle_create_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Neues Tool erstellen mit Curator-Gate und Skill-Kompositions-Hint."""
    name = tool_input.get("name", "")
    desc = tool_input.get("description", "")

    # Curator-Gate: Duplikate verhindern
    if ctx.curator:
        check = ctx.curator.check_before_create(
            name, desc, force=tool_input.get("force", False),
        )
        if not check["allowed"]:
            similar_names = [t["name"] for t in check.get("similar_tools", [])]
            return f"BLOCKIERT: {check['reason']}\nAehnliche Tools: {similar_names}"

    composition_hint = ctx.composer.suggest_composition(desc)
    result = ctx.toolchain.create_tool(name, desc, tool_input["code"])
    if composition_hint:
        result += f"\n{composition_hint}"
    return result


def handle_use_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Bestehendes Tool ausfuehren."""
    return ctx.toolchain.use_tool(
        tool_input["name"],
        **(tool_input.get("arguments") or {}),
    )


def handle_generate_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Tool per Foundry generieren mit Skill-Kompositions-Hint."""
    try:
        # Composition-Hint isoliert abfragen (kann fehlschlagen)
        try:
            composition_hint = ctx.composer.suggest_composition(
                tool_input.get("description", ""),
            )
        except Exception:
            composition_hint = None

        name = tool_input.get("name", "")
        desc = tool_input.get("description", "")
        if not name or not desc:
            return "FEHLER: name und description erforderlich."

        result = ctx.foundry.generate_tool(name, desc, ctx.toolchain)

        if composition_hint and isinstance(result, str):
            result += f"\n{composition_hint}"
        return result
    except Exception as e:
        return f"FEHLER: generate_tool fehlgeschlagen: {e}"


def handle_combine_tools(ctx: ToolContext, tool_input: dict) -> str:
    """Zwei Tools zu einem neuen kombinieren."""
    return ctx.foundry.combine_tools(
        tool_input["tool_a"],
        tool_input["tool_b"],
        tool_input["new_name"],
        ctx.toolchain,
    )
