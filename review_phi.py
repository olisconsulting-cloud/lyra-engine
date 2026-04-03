"""
review_phi.py — Pre-Flight-Check fuer die Lyra/Phi Engine.

Prueft Syntax, Imports, Tool-Integritaet, State, Goals, Token-Budget,
LLM-Router, Working Memory, Git-Status und Projekt-Duplikate.

Aufruf: python review_phi.py
Oder:   /review-phi im Claude Code Chat
"""

import json
import os
import py_compile
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Farben fuer Terminal-Output (Windows-kompatibel)
try:
    os.system("")  # Aktiviert ANSI auf Windows
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
except Exception:
    GREEN = YELLOW = RED = CYAN = RESET = BOLD = ""

ROOT = Path(__file__).parent
ENGINE = ROOT / "engine"
DATA = ROOT / "data"


def _safe_json_load(path: Path) -> dict | None:
    """Laedt JSON-Datei sicher. Gibt None bei Fehler zurueck."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return None


def run():
    """Fuehrt alle Pre-Flight-Checks aus."""
    results = []  # Lokal statt global — kein Akkumulieren bei Mehrfach-Aufruf

    def check(status: str, label: str, detail: str = ""):
        results.append((status, label, detail))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{BOLD}REVIEW-PHI: Pre-Flight-Check{RESET}  ({now})")
    print("=" * 40)

    # === 1. SYNTAX ===
    engine_files = sorted(ENGINE.glob("*.py"))
    syntax_ok = 0
    syntax_fail = []
    for f in engine_files:
        try:
            py_compile.compile(str(f), doraise=True)
            syntax_ok += 1
        except py_compile.PyCompileError as e:
            syntax_fail.append(f"{f.name}: {e}")
    if syntax_fail:
        check("FAIL", f"Syntax ({syntax_ok}/{len(engine_files)} Dateien)",
              "\n".join(syntax_fail))
    else:
        check("PASS", f"Syntax ({syntax_ok}/{len(engine_files)} Dateien)")

    # === 2. IMPORTS ===
    sys.path.insert(0, str(ROOT))
    try:
        from engine.consciousness import ConsciousnessEngine, TOOLS, TOOL_TIERS, select_tools
        from engine.tool_registry import ToolRegistry
        from engine.actions import ActionEngine
        from engine.goal_stack import GoalStack
        from engine.config import normalize_name_words, STOP_WORDS
        from engine.llm_router import TASK_MODEL_MAP, MODELS
        check("PASS", "Imports")
    except Exception as e:
        check("FAIL", "Imports", str(e))
        return _print_results(results)  # Ohne Imports koennen weitere Checks nicht laufen

    # === 3. TOOL-INTEGRITAET ===
    from engine.consciousness import _get_compact_tools
    tools_set = {t["name"] for t in TOOLS}
    tiers_set = set(TOOL_TIERS.keys())
    missing = tools_set - tiers_set
    extra = tiers_set - tools_set
    core_tools = select_tools({1})
    has_finish = "finish_sequence" in {t["name"] for t in core_tools}
    compact = _get_compact_tools()
    req_ok = all(
        set(f.get("input_schema", {}).get("required", []))
        == set(next(c for c in compact if c["name"] == f["name"])
               .get("input_schema", {}).get("required", []))
        for f in TOOLS
    )
    problems = []
    if missing:
        problems.append(f"In TOOLS aber nicht in TIERS: {missing}")
    if extra:
        problems.append(f"In TIERS aber nicht in TOOLS: {extra}")
    if not has_finish:
        problems.append("finish_sequence fehlt in Tier 1!")
    if not req_ok:
        problems.append("Required-Felder Mismatch zwischen voll und kompakt")
    if problems:
        check("FAIL", f"Tool-Integritaet ({len(TOOLS)} Tools, {len(TOOL_TIERS)} Tiers)",
              "; ".join(problems))
    else:
        check("PASS", f"Tool-Integritaet ({len(TOOLS)} Tools, {len(TOOL_TIERS)} Tiers)")

    # === 4. TOKEN-SIMULATION ===
    def tok(tools):
        return len(json.dumps(tools, ensure_ascii=False)) // 4
    old_total = tok(TOOLS) * 25
    new_total = tok(select_tools({1, 2, 3, 4, 5}, compact=False))
    for _ in range(24):
        new_total += tok(select_tools({1, 2}, compact=True))
    saved = old_total - new_total
    pct = saved * 100 // old_total if old_total else 0
    check("INFO", f"Tokens: {old_total // 1000}k -> {new_total // 1000}k ({pct}% gespart)")

    # === 5. STATE ===
    state_path = DATA / "consciousness" / "state.json"
    state = _safe_json_load(state_path)
    if state is None:
        check("FAIL", "State", "state.json fehlt oder korrupt")
    else:
        seq = state.get("sequences_total", "?")
        spin = state.get("spin_tracker", {})
        spin_count = len(spin)
        if spin_count > 5:
            check("WARN", f"State ({seq} Sequenzen, Spin-Tracker: {spin_count})",
                  f"Spin-Tracker hat {spin_count} Eintraege — moeglicherweise Loops")
        else:
            check("PASS", f"State ({seq} Sequenzen, Spin-Tracker: {spin_count})")

    # === 6. GOALS ===
    goals_path = DATA / "consciousness" / "goals.json"
    goals = _safe_json_load(goals_path)
    if goals is None:
        check("FAIL", "Goals", "goals.json fehlt oder korrupt")
    else:
        active = goals.get("active", [])
        if not active:
            check("WARN", "Goals (0 aktiv)", "Keine aktiven Goals — Phi braucht ein Ziel")
        else:
            total_done = 0
            total_sgs = 0
            total_ip = 0
            goal_problems = []
            for i, goal in enumerate(active):
                sgs = goal.get("sub_goals", [])
                done = sum(1 for sg in sgs if sg["status"] == "done")
                ip = sum(1 for sg in sgs if sg["status"] == "in_progress")
                total_done += done
                total_sgs += len(sgs)
                total_ip += ip
                if ip > 1:
                    goal_problems.append(f"Goal {i}: {ip} Sub-Goals gleichzeitig in_progress")
            if goal_problems:
                check("WARN", f"Goals ({len(active)} aktiv, {total_done}/{total_sgs} erledigt)",
                      "; ".join(goal_problems))
            else:
                check("PASS", f"Goals ({len(active)} aktiv, {total_done}/{total_sgs} erledigt)")

    # === 7. WORKING MEMORY ===
    wm_path = DATA / "consciousness" / "working_memory.md"
    if wm_path.exists():
        wm = wm_path.read_text(encoding="utf-8")
        wm_problems = []
        if len(wm) < 50:
            wm_problems.append(f"Nur {len(wm)} Zeichen — zu wenig Kontext")
        if "Aktueller Fokus" not in wm:
            wm_problems.append("Sektion 'Aktueller Fokus' fehlt")
        if wm_problems:
            check("WARN", "Working Memory", "; ".join(wm_problems))
        else:
            check("PASS", "Working Memory")
    else:
        check("WARN", "Working Memory", "Datei fehlt — Phi startet ohne Kontext")

    # === 8. LLM-ROUTER ===
    main_model = TASK_MODEL_MAP.get("main_work", "?")
    if main_model == "claude_opus":
        check("WARN", f"LLM-Router (main_work = {main_model})",
              "Opus als Hauptmodell — teuer! Nur fuer Debugging nutzen")
    else:
        check("PASS", f"LLM-Router (main_work = {main_model})")

    # === 9. GIT ===
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        uncommitted = len([l for l in status.stdout.strip().split("\n") if l.strip()])
        ahead = subprocess.run(
            ["git", "rev-list", "--count", "origin/master..HEAD"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        ahead_count = int(ahead.stdout.strip()) if ahead.returncode == 0 else 0
        parts = []
        if uncommitted:
            parts.append(f"{uncommitted} uncommitted")
        if ahead_count:
            parts.append(f"{ahead_count} ahead")
        if not parts:
            parts.append("clean, synced")
        if uncommitted:
            check("WARN", f"Git ({', '.join(parts)})")
        else:
            check("INFO", f"Git ({', '.join(parts)})")
    except Exception:
        check("INFO", "Git (nicht verfuegbar)")

    # === 10. PROJEKTE ===
    projects_path = DATA / "projects"
    if projects_path.exists():
        projects = sorted([d.name for d in projects_path.iterdir() if d.is_dir()])
        # Duplikat-Check via normalize_name_words (zentrale Logik)
        duplicates = []
        for i, p1 in enumerate(projects):
            w1 = normalize_name_words(p1)
            for p2 in projects[i + 1:]:
                w2 = normalize_name_words(p2)
                if w1 and w2:
                    overlap = len(w1 & w2) / len(w1 | w2)
                    if overlap >= 0.5:
                        duplicates.append(f"{p1} <-> {p2}")
        if duplicates:
            check("WARN", f"Projekte ({len(projects)} vorhanden)",
                  f"Moegliche Duplikate: {'; '.join(duplicates)}")
        else:
            check("INFO", f"Projekte ({len(projects)} vorhanden)")
    else:
        check("INFO", "Projekte (keine)")

    # === API-KEYS ===
    env_path = ROOT / ".env"
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        missing_keys = []
        for key in ["ANTHROPIC_API_KEY", "NVIDIA_API_KEY"]:
            if key not in env_content or f'{key}=""' in env_content or f"{key}=''" in env_content:
                missing_keys.append(key)
        if missing_keys:
            check("WARN", f"API-Keys", f"Fehlend/leer: {', '.join(missing_keys)}")
        else:
            check("PASS", "API-Keys")
    else:
        check("FAIL", "API-Keys", ".env Datei fehlt!")

    # === 11. NEUE MODULE (Gehirn-Session) ===
    new_modules = {
        "sequence_planner": "Sequenz-Planung",
        "checkpoint": "Checkpoint-System",
        "meta_rules": "Meta-Regeln",
        "skill_library": "Skill-Library",
        "proactive_learner": "Proaktives Lernen",
    }
    missing_modules = []
    for mod, label in new_modules.items():
        mod_path = ENGINE / f"{mod}.py"
        if not mod_path.exists():
            missing_modules.append(label)
    if missing_modules:
        check("WARN", f"Lern-Module ({len(new_modules) - len(missing_modules)}/{len(new_modules)})",
              f"Fehlend: {', '.join(missing_modules)}")
    else:
        check("PASS", f"Lern-Module ({len(new_modules)}/{len(new_modules)})")

    # === 12. BELIEFS-KONSISTENZ ===
    beliefs_path = DATA / "consciousness" / "beliefs.json"
    beliefs = _safe_json_load(beliefs_path)
    if beliefs:
        formed = beliefs.get("formed_from_experience", [])
        dict_beliefs = [b for b in formed if isinstance(b, dict)]
        if dict_beliefs:
            check("WARN", f"Beliefs ({len(formed)} Eintraege)",
                  f"{len(dict_beliefs)} sind Dicts statt Strings — Format-Bug! "
                  "Bitte bereinigen: Dicts zu Strings konvertieren.")
        else:
            check("PASS", f"Beliefs ({len(formed)} Eintraege)")
    elif beliefs_path.exists():
        check("WARN", "Beliefs", "beliefs.json ist leer oder korrupt")

    # === 13. LOOP-DETECTION ===
    seq_mem_path = DATA / "consciousness" / "sequence_memory.json"
    seq_mem = _safe_json_load(seq_mem_path)
    if seq_mem:
        entries = seq_mem.get("entries", [])
        if len(entries) >= 3:
            last_3 = [e.get("summary", "")[:80] for e in entries[-3:]]
            # Pruefen ob die letzten 3 Summaries fast identisch sind
            if len(set(last_3)) == 1:
                check("WARN", "Loop-Detection",
                      f"Letzte 3 Sequenzen identisch: '{last_3[0][:60]}'")
            else:
                check("PASS", "Loop-Detection")

    # === 14. SKILL-LIBRARY + PLAN-HISTORY ===
    skill_index = _safe_json_load(DATA / "skill_library" / "index.json")
    plan_history = _safe_json_load(DATA / "consciousness" / "plan_history.json")
    skill_count = len(skill_index.get("skills", [])) if skill_index else 0
    plan_count = len(plan_history.get("plans", [])) if plan_history else 0
    check("INFO", f"Skill-Library: {skill_count} Skills, Plan-History: {plan_count} Plaene")

    # === VENV ===
    venv_python = ROOT / "venv" / "Scripts" / "python.exe"  # Windows
    venv_python_unix = ROOT / "venv" / "bin" / "python"     # Linux/Mac
    if venv_python.exists() or venv_python_unix.exists():
        check("PASS", "Virtual Environment")
    else:
        check("WARN", "Virtual Environment", "venv nicht gefunden")

    return _print_results(results)


def _print_results(results: list) -> int:
    """Gibt die Ergebnis-Tabelle aus. Gibt Exit-Code zurueck (0=OK, 1=FAIL)."""
    print()
    has_fail = False
    for status, label, detail in results:
        if status == "PASS":
            icon = f"{GREEN}PASS{RESET}"
        elif status == "FAIL":
            icon = f"{RED}FAIL{RESET}"
            has_fail = True
        elif status == "WARN":
            icon = f"{YELLOW}WARN{RESET}"
        else:
            icon = f"{CYAN}INFO{RESET}"
        print(f"  [{icon}] {label}")
        if detail:
            print(f"         {detail}")

    print()
    if has_fail:
        print(f"  {RED}{BOLD}ERGEBNIS: PROBLEME GEFUNDEN{RESET}")
        print(f"  Behebe die FAIL-Eintraege bevor Phi gestartet wird.")
        return 1
    else:
        print(f"  {GREEN}{BOLD}ERGEBNIS: STARTBEREIT{RESET}")
        print(f"  Phi kann gestartet werden: python run_live.py")
        return 0


if __name__ == "__main__":
    sys.exit(run())
