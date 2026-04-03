"""
Handler fuer Datei-Operationen: write_file, read_file, list_directory.
"""

from .context import ToolContext


def handle_write_file(ctx: ToolContext, tool_input: dict) -> str:
    """Datei schreiben mit Duplikat-Schutz und Markdown-Quality-Gate."""
    path = tool_input["path"]
    content = tool_input["content"]
    force = bool(tool_input.get("force", False))

    # force-Missbrauch tracken (max 3 pro Sequenz)
    if force:
        ctx._seq_force_used += 1
        if ctx._seq_force_used > 3:
            return (
                "FEHLER: force wurde diese Sequenz bereits 3x genutzt. "
                "Das deutet auf ein systematisches Problem hin. "
                "Pruefe ob du bestehende Dateien aktualisieren solltest."
            )

    # Quality Gate fuer Markdown-Dateien
    if path.endswith(".md") and len(content) > 200:
        issues = ctx.check_markdown_quality(content)
        if issues:
            result = ctx.actions.write_file(path, content, force=force)
            if result.startswith("FEHLER") or result.startswith("WARNUNG"):
                return result
            return f"{result}\nQUALITAETS-WARNUNG: {'; '.join(issues)}"

    return ctx.actions.write_file(path, content, force=force)


def handle_read_file(ctx: ToolContext, tool_input: dict) -> str:
    """Datei lesen."""
    return ctx.actions.read_file(tool_input["path"])


def handle_list_directory(ctx: ToolContext, tool_input: dict) -> str:
    """Verzeichnis auflisten."""
    return ctx.actions.list_directory(tool_input.get("path", ""))
