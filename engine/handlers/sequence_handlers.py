"""
Handler fuer Sequenz-Steuerung:
complete_task, finish_sequence, write_sequence_plan, update_sequence_plan.
"""

from .context import ToolContext


def handle_complete_task(ctx: ToolContext, tool_input: dict) -> str:
    """Task aus der Queue abschliessen."""
    return ctx.task_queue.complete_task(tool_input.get("result", ""))


def handle_finish_sequence(ctx: ToolContext, tool_input: dict) -> str:
    """Sequenz beenden — delegiert an consciousness.py Callback."""
    return ctx.handle_finish_sequence(tool_input)


def handle_write_sequence_plan(ctx: ToolContext, tool_input: dict) -> str:
    """Sequenz-Plan schreiben."""
    return ctx.seq_intel.save_plan(tool_input)


def handle_update_sequence_plan(ctx: ToolContext, tool_input: dict) -> str:
    """Sequenz-Plan aktualisieren."""
    result = ctx.seq_intel.update_plan(tool_input)
    ctx.seq_intel.on_plan_updated()
    return result
