"""
Handler fuer Tool-Erstellung und -Nutzung:
create_tool, use_tool, generate_tool, combine_tools.
"""

from .context import ToolContext


def handle_create_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Neues Tool erstellen mit Skill-Kompositions-Hint."""
    desc = tool_input.get("description", "")
    composition_hint = ctx.composer.suggest_composition(desc)
    result = ctx.toolchain.create_tool(
        tool_input["name"], desc, tool_input["code"],
    )
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
    composition_hint = ctx.composer.suggest_composition(tool_input["description"])
    result = ctx.foundry.generate_tool(
        tool_input["name"],
        tool_input["description"],
        ctx.toolchain,
    )
    if composition_hint:
        result += f"\n{composition_hint}"
    return result


def handle_combine_tools(ctx: ToolContext, tool_input: dict) -> str:
    """Zwei Tools zu einem neuen kombinieren."""
    return ctx.foundry.combine_tools(
        tool_input["tool_a"],
        tool_input["tool_b"],
        tool_input["new_name"],
        ctx.toolchain,
    )
