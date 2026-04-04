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
    # Mehrere Varianten erkennen (Phi schreibt Tests unterschiedlich)
    upper_output = test_output.upper()
    all_passed = (
        "ALL_TESTS_PASSED" in test_output
        or "ALL TESTS PASSED" in upper_output
        or ("\u2705" in test_output and "FAIL" not in upper_output)
    )
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
    # Toleriere Tests aus der vorherigen Sequenz (oft laeuft complete_project
    # eine Sequenz nach run_project_tests)
    if evidence_seq < ctx.sequences_total - 1:
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
        # Fuzzy-Matching: Erstes Drittel des Kriteriums ODER hohe Ueberlappung
        req_lower = req.lower()
        found = any(
            req_lower[:80] in v.lower()
            or v.lower() in req_lower
            for v in verified
        )
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

    # === INTEGRATION-GATE (Warnung, kein Block) ===
    # Pruefen ob der Projekt-Code tatsaechlich in der Engine verdrahtet ist
    # Isolierte Projekte in data/projects/ sind wertlos wenn sie nie genutzt werden
    integration_warning = _check_engine_integration(project_name)
    if integration_warning:
        logger.info("Integration-Gate fuer '%s': %s", project_name, integration_warning)

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
    result = f"Projekt '{project_name}' erfolgreich abgeschlossen! {len(required_criteria)} Kriterien erfuellt, Tests bestanden."
    if integration_warning:
        result += f"\n\nINTEGRATIONS-HINWEIS: {integration_warning}"
    return result


def _check_engine_integration(project_name: str) -> str:
    """Prueft ob Projekt-Code in der Engine referenziert wird.

    Isolierte Tools in data/projects/ die nie importiert oder
    genutzt werden sind toter Code. Gibt Warnung zurueck oder ''.
    """
    engine_path = config.ENGINE_PATH
    project_path = config.DATA_PATH / "projects" / project_name
    tools_path = config.DATA_PATH / "tools"

    if not engine_path.exists():
        return ""

    # Sammle relevante Dateinamen aus dem Projekt (ohne tests.py, PLAN.md etc.)
    code_files = []
    if project_path.exists():
        code_files = [
            f.stem for f in project_path.iterdir()
            if f.suffix == ".py" and f.name not in ("tests.py", "__init__.py")
        ]

    if not code_files:
        return ""

    # Normalisierter Projektname fuer Suche (z.B. "two-stage-perception" → "perception")
    search_terms = [project_name.replace("-", "_")]
    search_terms.extend(code_files)

    # In engine/ und tools/ nach Referenzen suchen
    found_in = []
    search_dirs = [engine_path]
    if tools_path.exists():
        search_dirs.append(tools_path)

    for search_dir in search_dirs:
        try:
            for py_file in search_dir.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    for term in search_terms:
                        if term in content:
                            found_in.append(py_file.name)
                            break
                except OSError:
                    continue
        except OSError:
            continue

    if found_in:
        return ""  # Code ist referenziert — alles gut

    return (
        f"Der Code in projects/{project_name}/ wird nirgends in engine/ oder tools/ "
        f"importiert oder referenziert. Damit das Projekt Wirkung hat, muss es in die "
        f"Engine integriert werden (z.B. als Tool registrieren oder in consciousness.py einbinden)."
    )
