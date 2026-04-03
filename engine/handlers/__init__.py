"""
Tool-Handler-Paket — Domain-spezifische Handler fuer die ToolRegistry.

Jeder Handler ist eine pure Funktion: (ctx: ToolContext, tool_input: dict) -> str
Die Registration passiert ueber register_all_handlers().
"""

from .context import ToolContext

from .file_handlers import handle_write_file, handle_read_file, handle_list_directory
from .code_handlers import handle_execute_python, handle_read_own_code, handle_modify_own_code
from .web_handlers import handle_web_search, handle_web_read, handle_send_telegram
from .goal_handlers import handle_set_goal, handle_complete_subgoal
from .project_handlers import (
    handle_create_project, handle_verify_project,
    handle_run_project_tests, handle_complete_project,
)
from .memory_handlers import handle_remember, handle_update_memory, handle_delete_memory
from .tool_handlers import handle_create_tool, handle_use_tool, handle_generate_tool, handle_combine_tools
from .system_handlers import handle_pip_install, handle_git_commit, handle_git_status, handle_self_diagnose
from .sequence_handlers import (
    handle_complete_task, handle_finish_sequence,
    handle_write_sequence_plan, handle_update_sequence_plan,
)


# Mapping: Tool-Name → Handler-Funktion
HANDLER_MAP: dict[str, callable] = {
    # Datei-Operationen
    "write_file": handle_write_file,
    "read_file": handle_read_file,
    "list_directory": handle_list_directory,

    # Code
    "execute_python": handle_execute_python,
    "read_own_code": handle_read_own_code,
    "modify_own_code": handle_modify_own_code,

    # Web
    "web_search": handle_web_search,
    "web_read": handle_web_read,
    "send_telegram": handle_send_telegram,

    # Ziele
    "set_goal": handle_set_goal,
    "complete_subgoal": handle_complete_subgoal,

    # Projekte
    "create_project": handle_create_project,
    "verify_project": handle_verify_project,
    "run_project_tests": handle_run_project_tests,
    "complete_project": handle_complete_project,

    # Memory
    "remember": handle_remember,
    "update_memory": handle_update_memory,
    "delete_memory": handle_delete_memory,

    # Tool-Management
    "create_tool": handle_create_tool,
    "use_tool": handle_use_tool,
    "generate_tool": handle_generate_tool,
    "combine_tools": handle_combine_tools,

    # System
    "pip_install": handle_pip_install,
    "git_commit": handle_git_commit,
    "git_status": handle_git_status,
    "self_diagnose": handle_self_diagnose,

    # Sequenz-Steuerung
    "complete_task": handle_complete_task,
    "finish_sequence": handle_finish_sequence,
    "write_sequence_plan": handle_write_sequence_plan,
    "update_sequence_plan": handle_update_sequence_plan,
}


def register_all_handlers(registry, ctx: ToolContext) -> None:
    """Registriert alle Tool-Handler in der ToolRegistry.

    Jeder Handler wird als Closure gewrappt, damit der ToolContext
    automatisch injiziert wird. Die Registry ruft handler(tool_input),
    wir machen daraus handler_fn(ctx, tool_input).

    Args:
        registry: ToolRegistry-Instanz (Tools muessen bereits registriert sein)
        ctx: ToolContext mit allen Dependencies
    """
    for tool_name, handler_fn in HANDLER_MAP.items():
        if registry.has_tool(tool_name):
            # Closure: ctx wird gecaptured, registry bekommt (tool_input) -> str
            registry.set_handler(
                tool_name,
                lambda inp, fn=handler_fn: fn(ctx, inp),
            )

    # Validierung: Warnen wenn Tools ohne Handler registriert sind
    import logging
    logger = logging.getLogger(__name__)
    for name in registry.get_tool_names():
        if name not in HANDLER_MAP:
            logger.warning(f"Tool '{name}' hat keinen Handler im handlers-Paket")
