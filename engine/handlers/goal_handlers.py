"""
Handler fuer Ziel-Management: set_goal, complete_subgoal.
"""

import logging
import re
from datetime import datetime, timezone

from .context import ToolContext
from .. import config
from ..config import safe_json_write

logger = logging.getLogger(__name__)


def handle_set_goal(ctx: ToolContext, tool_input: dict) -> str:
    """Neues Ziel setzen mit optionaler Opus-Planung."""
    title = tool_input["title"]
    description = tool_input.get("description", "")
    sub_goals = tool_input.get("sub_goals")

    # Duplikat-Check zuerst — vor teurem Opus-Call
    similar = ctx.goal_stack._find_similar_goal(title)
    if not similar:
        if not sub_goals or len(sub_goals) < 2:
            opus_sub_goals = ctx.opus_goal_planning(title, description)
            if opus_sub_goals:
                sub_goals = opus_sub_goals

    result = ctx.goal_stack.create_goal(title, description, sub_goals)
    # Neues Goal → alten Checkpoint loeschen (sonst falscher Resume-Kontext)
    ctx.seq_intel.clear_checkpoint()
    return result


def handle_complete_subgoal(ctx: ToolContext, tool_input: dict) -> str:
    """Sub-Ziel abschliessen mit Report-Generierung bei Ziel-Erreichung."""
    result = ctx.goal_stack.complete_subgoal(
        tool_input["goal_index"],
        tool_input["subgoal_index"],
        tool_input.get("result", ""),
    )

    # Auto-Erkennung: Ziel komplett → Report + Lehrprojekt-Check
    if "ZIEL ERREICHT" in result:
        try:
            completed = ctx.goal_stack.goals.get("completed", [])
            if completed:
                goal = completed[-1]
                goal_title = goal.get("title", "Ergebnis")

                # Sub-Goal-Ergebnisse sammeln
                sections = []
                for sg in goal.get("sub_goals", []):
                    if sg.get("result"):
                        sections.append(f"## {sg['title']}\n{sg['result']}")

                # Projekt-Dateien einbeziehen
                safe_name = re.sub(r"[^a-z0-9-]", "", goal_title.lower().replace(" ", "-"))[:40]
                project_dir = config.DATA_PATH / "projects"
                for md_file in sorted(project_dir.rglob("*.md")):
                    if md_file.name in ("README.md", "PLAN.md", "PROGRESS.md"):
                        continue
                    try:
                        content = md_file.read_text(encoding="utf-8")[:2000]
                        rel = md_file.relative_to(project_dir)
                        sections.append(f"## Datei: {rel}\n{content}")
                    except (OSError, UnicodeDecodeError):
                        continue

                if sections:
                    report = f"# Ergebnis: {goal_title}\n\n"
                    report += "\n\n".join(sections)
                    report += f"\n\n---\nErstellt: {datetime.now(timezone.utc).isoformat()}\n"
                    report_path = project_dir / f"REPORT_{safe_name}.md"
                    report_path.write_text(report, encoding="utf-8")
                    result += f" | Report: REPORT_{safe_name}.md"
                    if ctx.communication.telegram_active:
                        ctx.communication.send_message(
                            f"ZIEL ERREICHT: {goal_title}\n\n{report[:3500]}",
                            channel="telegram",
                        )
        except (OSError, KeyError) as e:
            logger.warning(f" Goal-Completion Report fehlgeschlagen: {e}")

        # Lehrprojekt-Check
        goals = ctx.goal_stack._load()
        for g in goals.get("completed", []):
            if "lehrprojekt" in g.get("title", "").lower():
                project_name = g.get("title", "").replace("Lehrprojekt: ", "")
                learn_result = ctx.learning.complete_learning_project(
                    project_name, ctx.skills
                )
                result += f" | {learn_result}"
                break

    return result
