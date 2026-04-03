"""
Handler fuer Projekt-Management:
create_project, verify_project, run_project_tests, complete_project.
"""

import logging
from datetime import datetime, timezone

from .context import ToolContext
from .. import config
from ..config import safe_json_write, safe_json_read

logger = logging.getLogger(__name__)


def handle_create_project(ctx: ToolContext, tool_input: dict) -> str:
    """Neues Projekt erstellen."""
    return ctx.actions.create_project(
        tool_input["name"],
        tool_input.get("description", ""),
        tool_input.get("acceptance_criteria"),
        tool_input.get("phases"),
    )


def handle_verify_project(ctx: ToolContext, tool_input: dict) -> str:
    """Akzeptanzkriterien aus PLAN.md lesen und zur Pruefung zurueckgeben."""
    plan_path = config.DATA_PATH / "projects" / tool_input["project_name"] / "PLAN.md"
    if not plan_path.exists():
        return f"FEHLER: Kein PLAN.md in projects/{tool_input['project_name']}/"

    plan_content = plan_path.read_text(encoding="utf-8")

    criteria_lines = []
    in_criteria = False
    for line in plan_content.split("\n"):
        if line.startswith("##") and ("akzeptanzkriterien" in line.lower() or "acceptance" in line.lower()):
            in_criteria = True
            continue
        if in_criteria:
            if line.startswith("##"):
                break
            if line.strip().startswith("- ["):
                criteria_lines.append(line.strip())

    if not criteria_lines:
        return "Keine Akzeptanzkriterien in PLAN.md gefunden."

    result = f"AKZEPTANZKRITERIEN fuer {tool_input['project_name']}:\n"
    result += "\n".join(criteria_lines)
    result += "\n\nPruefe JEDES Kriterium. Ist es erfuellt? Wenn nicht: was fehlt?"
    return result


def handle_run_project_tests(ctx: ToolContext, tool_input: dict) -> str:
    """Projekt-Tests ausfuehren und Evidenz speichern."""
    project_name = tool_input["project_name"]
    tests_path = config.DATA_PATH / "projects" / project_name / "tests.py"
    if not tests_path.exists():
        return f"FEHLER: Keine tests.py in projects/{project_name}/. Erstelle zuerst Tests."

    test_output = ctx.actions.run_script(
        f"projects/{project_name}/tests.py", timeout=60,
    )

    # Evidenz speichern (maschinenlesbar)
    evidence_path = config.DATA_PATH / "projects" / project_name / ".test_evidence.json"
    all_passed = "ALL_TESTS_PASSED" in test_output
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": all_passed,
        "output": test_output[:2000],
        "sequence": ctx.sequences_total,
    }
    safe_json_write(evidence_path, evidence)

    # PROGRESS.md aktualisieren
    ctx.actions._update_progress(
        project_name,
        f"Tests: {'ALL PASS' if all_passed else 'FAILED'}",
        section="Test-Ergebnisse",
    )

    return test_output


def handle_complete_project(ctx: ToolContext, tool_input: dict) -> str:
    """Projekt abschliessen mit Evidence-Gate, Opus-Validierung und Cross-Review."""
    project_name = tool_input["project_name"]
    plan_path = config.DATA_PATH / "projects" / project_name / "PLAN.md"
    progress_path = config.DATA_PATH / "projects" / project_name / "PROGRESS.md"
    evidence_path = config.DATA_PATH / "projects" / project_name / ".test_evidence.json"

    if not plan_path.exists():
        return f"FEHLER: Kein PLAN.md in projects/{project_name}/"

    # === EVIDENCE-GATE ===
    evidence = safe_json_read(evidence_path, default=None)
    if evidence is None:
        return (
            f"FEHLER: Keine gueltige Test-Evidenz vorhanden.\n"
            f"Fuehre zuerst run_project_tests('{project_name}') aus."
        )

    evidence_seq = evidence.get("sequence", -1)
    if evidence_seq != ctx.sequences_total:
        return (
            f"FEHLER: Test-Evidenz ist veraltet (Sequenz {evidence_seq}, "
            f"aktuell {ctx.sequences_total}).\n"
            f"Fuehre run_project_tests('{project_name}') erneut aus."
        )

    if not evidence.get("passed"):
        return (
            f"FEHLER: Tests nicht bestanden. Projekt kann nicht abgeschlossen werden.\n"
            f"Letzter Test-Output:\n{evidence.get('output', '')[:500]}\n"
            f"Behebe die Fehler und fuehre run_project_tests erneut aus."
        )

    # Akzeptanzkriterien aus PLAN.md
    plan_content = plan_path.read_text(encoding="utf-8")
    required_criteria = []
    in_criteria = False
    for line in plan_content.split("\n"):
        if line.startswith("##") and ("akzeptanzkriterien" in line.lower() or "acceptance" in line.lower()):
            in_criteria = True
            continue
        if in_criteria:
            if line.startswith("##"):
                break
            if line.strip().startswith("- ["):
                criterion = line.strip()[6:].strip() if "] " in line else line.strip()[4:].strip()
                required_criteria.append(criterion)

    if not required_criteria:
        return "FEHLER: Keine Akzeptanzkriterien in PLAN.md gefunden."

    # Kriterien pruefen
    verified = tool_input.get("verified_criteria", [])
    missing = []
    for req in required_criteria:
        found = any(req.lower()[:30] in v.lower() for v in verified)
        if not found:
            missing.append(req)

    if missing:
        return (
            f"FEHLER: Projekt kann nicht abgeschlossen werden.\n"
            f"Fehlende Kriterien ({len(missing)}):\n" +
            "\n".join(f"  - [ ] {m}" for m in missing)
        )

    # === OPUS ERGEBNIS-VALIDIERUNG ===
    project_path = config.DATA_PATH / "projects" / project_name
    opus_validation = ctx.opus_result_validation(
        project_name, required_criteria, verified
    )
    if opus_validation and not opus_validation.get("approved", False):
        return (
            f"OPUS-VALIDIERUNG FEHLGESCHLAGEN:\n"
            f"{opus_validation.get('reason', 'Unbekannter Grund')}\n"
            f"Behebe die Probleme und versuche es erneut."
        )

    # === CROSS-MODEL-REVIEW bei Projekten mit 3+ Dateien ===
    code_files = [f for f in project_path.iterdir()
                  if f.suffix == ".py" and f.name != "tests.py"]
    if len(code_files) >= 3:
        review = ctx.cross_model_review(project_name, code_files)
        if review and not review.get("approved", False):
            return (
                f"FEHLER: Cross-Model-Review nicht bestanden.\n"
                f"Grund: {review.get('reason', '?')}\n"
                f"Issues: {'; '.join(review.get('issues', []))}\n"
                f"Behebe die Issues und versuche es erneut."
            )

    # Alles OK — Projekt abschliessen
    updated_plan = plan_content
    for criterion in required_criteria:
        updated_plan = updated_plan.replace(f"- [ ] {criterion}", f"- [x] {criterion}")
    plan_path.write_text(updated_plan, encoding="utf-8")

    # PROGRESS.md: Abschluss dokumentieren
    if progress_path.exists():
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        summary = tool_input.get("summary", "Abgeschlossen")
        review_note = f" | Cross-Review: OK" if len(code_files) >= 3 else ""
        progress_content = progress_path.read_text(encoding="utf-8")
        progress_content = progress_content.replace(
            "## Status: IN ARBEIT",
            f"## Status: FERTIG ({now})"
        )
        progress_content += (
            f"\n### Abschluss\n"
            f"- [{now}] {summary}\n"
            f"- Evidenz: Tests ALL_TESTS_PASSED ({evidence.get('timestamp', '?')}){review_note}\n"
        )
        progress_path.write_text(progress_content, encoding="utf-8")

    ctx.communication.write_journal(
        f"Projekt '{project_name}' ABGESCHLOSSEN (evidence-based): {tool_input.get('summary', '')}",
        ctx.sequences_total,
    )
    return f"Projekt '{project_name}' erfolgreich abgeschlossen! {len(required_criteria)} Kriterien erfuellt, Tests bestanden."
