"""
Handler fuer System-Operationen:
pip_install, git_commit, git_status, self_diagnose.
"""

from .context import ToolContext


def handle_pip_install(ctx: ToolContext, tool_input: dict) -> str:
    """Python-Paket installieren mit Duplikat-Check."""
    pkg = tool_input["package"]

    if pkg.lower() in ctx._installed_packages:
        return f"Bereits installiert: {pkg}"

    result = ctx.pip.install(pkg)
    if "already satisfied" in result.lower() or "installiert" in result.lower():
        ctx._installed_packages.add(pkg.lower())
        ctx.save_all()
    elif not result.startswith("FEHLER"):
        ctx._installed_packages.add(pkg.lower())
        ctx.save_all()

    return result


def handle_git_commit(ctx: ToolContext, tool_input: dict) -> str:
    """Git-Commit erstellen."""
    return ctx.git.commit(tool_input["message"])


def handle_git_status(ctx: ToolContext, tool_input: dict) -> str:
    """Git-Status abfragen."""
    return ctx.git.status()


def handle_self_diagnose(ctx: ToolContext, tool_input: dict) -> str:
    """Selbstdiagnose: Integration, Dependencies, stille Fehler."""
    parts = []

    integ = ctx.integration_tester.get_report()
    parts.append(integ)

    dep = ctx.dependency_analyzer.analyze()
    parts.append(dep["report"])

    silent = ctx.silent_failure_detector.get_recent_warnings()
    if silent:
        parts.append(silent)
    else:
        parts.append("Keine stillen Fehler erkannt.")

    return "\n\n".join(parts)
