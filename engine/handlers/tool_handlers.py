"""
Handler fuer Tool-Erstellung und -Nutzung:
create_tool, use_tool, generate_tool, combine_tools.
"""

from .context import ToolContext


def handle_create_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Neues Tool erstellen mit Evolution-Challenge und Evaluation."""
    name = tool_input.get("name", "")
    desc = tool_input.get("description", "")

    # Schritt 1: Challenge — Benchmark finden (blockiert NICHT)
    challenge_info = None
    if ctx.curator:
        challenge_info = ctx.curator.challenge(name, desc)

    # Schritt 2: Tool erstellen (immer erlaubt)
    composition_hint = ctx.composer.suggest_composition(desc)
    result = ctx.toolchain.create_tool(name, desc, tool_input["code"])

    if result.startswith("FEHLER"):
        return result  # Bau fehlgeschlagen, kein Evaluate noetig

    # Schritt 3: Evaluate — Neues Tool vs Benchmark vergleichen
    if challenge_info and challenge_info.get("has_benchmark"):
        benchmark = challenge_info["benchmark"]
        evaluation = ctx.curator.evaluate(name, benchmark["name"], ctx.toolchain)
        result += (
            f"\n\n--- EVOLUTION-REPORT ---\n"
            f"Benchmark: {benchmark['name']} ({benchmark['uses']}x bewaehrt)\n"
            f"Ergebnis: {evaluation['verdict'].upper()}\n"
            f"Lern-Signal: {evaluation['learning']}\n"
            f"Empfehlung: {evaluation['recommendation']}"
        )
    elif challenge_info:
        result += f"\n{challenge_info['challenge_text']}"

    if composition_hint:
        result += f"\n{composition_hint}"

    # Tool-Lifecycle: Version-Sprawl pruefen
    if ctx.tool_meta_patterns and not result.startswith("FEHLER"):
        try:
            ctx.tool_meta_patterns.check_version_sprawl(
                name, ctx.toolchain.registry.get("tools", {})
            )
        except Exception:
            pass

    return result


def handle_use_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Bestehendes Tool ausfuehren."""
    name = tool_input["name"]
    result = ctx.toolchain.use_tool(
        name,
        **(tool_input.get("arguments") or {}),
    )

    # Tool-Lifecycle: Failure-Loop pruefen
    if ctx.tool_meta_patterns:
        try:
            is_error = isinstance(result, str) and "FEHLER" in result
            ctx.tool_meta_patterns.check_failure_loop(name, is_error)
        except Exception:
            pass

    return result


def handle_generate_tool(ctx: ToolContext, tool_input: dict) -> str:
    """Tool per Foundry generieren mit Evolution-Challenge und Evaluation."""
    try:
        name = tool_input.get("name", "")
        desc = tool_input.get("description", "")
        if not name or not desc:
            return "FEHLER: name und description erforderlich."

        # Schritt 1: Challenge — Benchmark finden (blockiert NICHT)
        challenge_info = None
        if ctx.curator:
            challenge_info = ctx.curator.challenge(name, desc)

        # Composition-Hint isoliert abfragen (kann fehlschlagen)
        try:
            composition_hint = ctx.composer.suggest_composition(desc)
        except Exception:
            composition_hint = None

        # Schritt 2: Tool generieren (immer erlaubt)
        result = ctx.foundry.generate_tool(name, desc, ctx.toolchain)

        if isinstance(result, str) and result.startswith("FEHLER"):
            return result

        # Schritt 3: Evaluate — Neues Tool vs Benchmark vergleichen
        if challenge_info and challenge_info.get("has_benchmark") and isinstance(result, str):
            benchmark = challenge_info["benchmark"]
            evaluation = ctx.curator.evaluate(name, benchmark["name"], ctx.toolchain)
            result += (
                f"\n\n--- EVOLUTION-REPORT ---\n"
                f"Benchmark: {benchmark['name']} ({benchmark['uses']}x bewaehrt)\n"
                f"Ergebnis: {evaluation['verdict'].upper()}\n"
                f"Lern-Signal: {evaluation['learning']}\n"
                f"Empfehlung: {evaluation['recommendation']}"
            )
        elif challenge_info and isinstance(result, str):
            result += f"\n{challenge_info['challenge_text']}"

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
