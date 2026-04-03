"""
Handler fuer Code-Ausfuehrung und Selbstmodifikation:
execute_python, read_own_code, modify_own_code.
"""

import logging
from pathlib import Path

from .context import ToolContext
from .. import config

logger = logging.getLogger(__name__)


def handle_execute_python(ctx: ToolContext, tool_input: dict) -> str:
    """Python-Code ausfuehren."""
    return ctx.actions.run_code(tool_input["code"])


def handle_read_own_code(ctx: ToolContext, tool_input: dict) -> str:
    """Eigenen Quellcode lesen."""
    return ctx.self_modify.read_source(tool_input["path"])


def handle_modify_own_code(ctx: ToolContext, tool_input: dict) -> str:
    """Eigenen Code aendern mit Dual-Review und Critic-Agent."""
    # Sicherheit: Max 3 modify_own_code pro Sequenz
    ctx.seq_intel.metrics.modify_count = getattr(
        ctx.seq_intel.metrics, "modify_count", 0
    )
    ctx.seq_intel.metrics.modify_count += 1
    if ctx.seq_intel.metrics.modify_count > 3:
        return (
            "FEHLER: Maximum 3 Code-Aenderungen pro Sequenz erreicht. "
            "Beende die Sequenz und mache in der naechsten weiter."
        )

    # Alten Code lesen fuer Critic-Vergleich
    try:
        raw_path = (config.ROOT_PATH / tool_input["path"]).resolve()
        old_code = raw_path.read_text(encoding="utf-8") if raw_path.exists() else ""
    except (OSError, KeyError, UnicodeDecodeError):
        old_code = ""

    # Dual-Review: Syntax + Opus pruefen
    review_result = ctx.code_review.review_and_apply_fix(
        file_path=tool_input["path"],
        new_content=tool_input["new_content"],
        reason=tool_input.get("reason", "Selbstverbesserung"),
    )
    if review_result["accepted"]:
        # Critic-Agent: Ist es BESSER als vorher?
        critic = ctx.critic.evaluate_change(
            tool_input["path"], old_code,
            tool_input["new_content"],
            tool_input.get("reason", ""),
        )
        raw_score = critic.get("score", 5)
        try:
            score = int(raw_score) if not isinstance(raw_score, (int, float)) else raw_score
        except (ValueError, TypeError):
            score = 5
        score = max(1, min(10, score))
        critic_note = f" | Critic: {score}/10"
        if critic.get("side_effects"):
            critic_note += f" | Seiteneffekte: {critic['side_effects'][:80]}"

        # CRITIC ENTSCHEIDET: Score < 4 = Rollback
        if isinstance(score, (int, float)) and score < 4:
            ctx.code_review._rollback(
                (config.ROOT_PATH / tool_input["path"]).resolve(),
                old_code,
            )
            return (
                f"ROLLBACK — Critic-Score zu niedrig ({score}/10): "
                f"{critic.get('side_effects', 'Verschlechterung')[:100]}"
            )

        ctx.communication.write_journal(
            f"Code geaendert (REVIEW OK{critic_note}): {tool_input['path']}\n"
            f"Grund: {tool_input.get('reason', '?')}",
            ctx.sequences_total,
        )
        return f"Code geaendert{critic_note}: {tool_input['path']}"
    else:
        return f"ROLLBACK — Review abgelehnt: {review_result['reason']}"
