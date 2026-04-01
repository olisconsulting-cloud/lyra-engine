"""
Selbst-Diagnose — Findet was ein normaler Audit nicht findet.

3 Faehigkeiten:

1. INTEGRATIONS-TESTS
   Prueft ob Pipelines end-to-end funktionieren.
   Nicht "ist der Code korrekt?" sondern "funktioniert das System?"
   Beispiel: "Wenn Audit Findings findet → werden Goals erstellt?"

2. CROSS-FILE DEPENDENCY-ANALYSE
   Findet Funktionen die definiert aber nie aufgerufen werden.
   Findet Imports die fehlen oder veraltet sind.
   Beispiel: "LearningEngine.start_learning_project() wird nirgendwo aufgerufen"

3. STILLE-FEHLER-ERKENNUNG
   Prueft nach jeder Sequenz: Haben die Systeme die haetten laufen
   sollen auch wirklich gelaufen? Erkennt "es passiert nichts" als Fehler.
"""

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class IntegrationTester:
    """
    Prueft ob die Kern-Pipelines end-to-end funktionieren.

    Keine Code-Analyse — sondern DATEN-Analyse:
    Wenn System X gelaufen sein sollte, gibt es dann Daten die das beweisen?
    """

    def __init__(self, data_path: Path, root_path: Path):
        self.data_path = data_path
        self.root_path = root_path

    def run_all_checks(self) -> dict:
        """
        Fuehrt alle Integrations-Checks durch.

        Returns:
            {"passed": int, "failed": int, "results": list[dict]}
        """
        checks = [
            self._check_audit_to_goals_pipeline(),
            self._check_skill_tracking_active(),
            self._check_memory_growing(),
            self._check_strategy_learning(),
            self._check_tools_registered(),
            self._check_dream_running(),
            self._check_benchmark_running(),
            self._check_sequence_memory_saved(),
        ]

        passed = sum(1 for c in checks if c["passed"])
        failed = len(checks) - passed

        return {
            "passed": passed,
            "failed": failed,
            "total": len(checks),
            "results": checks,
        }

    def get_report(self) -> str:
        """Menschenlesbarer Report."""
        result = self.run_all_checks()
        lines = [
            f"INTEGRATIONS-CHECK: {result['passed']}/{result['total']} bestanden"
        ]
        for check in result["results"]:
            icon = "OK" if check["passed"] else "FAIL"
            lines.append(f"  [{icon}] {check['name']}: {check['detail']}")
        return "\n".join(lines)

    def _check_audit_to_goals_pipeline(self) -> dict:
        """Prueft: Wenn es Audit-Findings gibt, gibt es auch Goals dafuer?"""
        audit_log = self.data_path / "consciousness" / "audit_log.json"
        goals_file = self.data_path / "consciousness" / "goals.json"

        has_findings = False
        has_audit_goals = False

        if audit_log.exists():
            try:
                with open(audit_log, "r", encoding="utf-8") as f:
                    log = json.load(f)
                if log:
                    last = log[-1]
                    has_findings = last.get("critical", 0) > 0 or last.get("findings_count", 0) > 2
            except Exception:
                pass

        if goals_file.exists():
            try:
                with open(goals_file, "r", encoding="utf-8") as f:
                    goals = json.load(f)
                for g in goals.get("active", []) + goals.get("completed", []):
                    if "audit" in g.get("title", "").lower() or "optimierung" in g.get("title", "").lower():
                        has_audit_goals = True
            except Exception:
                pass

        if not has_findings:
            return {"name": "Audit→Goals", "passed": True, "detail": "Keine kritischen Findings (Pipeline nicht getestet)"}
        elif has_audit_goals:
            return {"name": "Audit→Goals", "passed": True, "detail": "Findings vorhanden UND Goals erstellt"}
        else:
            return {"name": "Audit→Goals", "passed": False, "detail": "Findings vorhanden aber KEINE Goals daraus erstellt"}

    def _check_skill_tracking_active(self) -> dict:
        """Prueft: Werden Skills ueberhaupt getrackt?"""
        skills_file = self.data_path / "consciousness" / "skills.json"
        if not skills_file.exists():
            return {"name": "Skill-Tracking", "passed": False, "detail": "skills.json existiert nicht"}
        try:
            with open(skills_file, "r", encoding="utf-8") as f:
                skills = json.load(f)
            total = sum(s.get("successes", 0) + s.get("failures", 0) for s in skills.values())
            if total == 0:
                return {"name": "Skill-Tracking", "passed": False, "detail": "Keine Skills getrackt (0 Events)"}
            return {"name": "Skill-Tracking", "passed": True, "detail": f"{len(skills)} Skills, {total} Events"}
        except Exception:
            return {"name": "Skill-Tracking", "passed": False, "detail": "skills.json nicht lesbar"}

    def _check_memory_growing(self) -> dict:
        """Prueft: Wachsen Erinnerungen oder stagnieren sie?"""
        index = self.data_path / "memory" / "index.json"
        if not index.exists():
            return {"name": "Memory", "passed": False, "detail": "Kein Memory-Index"}
        try:
            with open(index, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = len(data.get("experiences", []))
            if count == 0:
                return {"name": "Memory", "passed": False, "detail": "Keine Erfahrungen gespeichert"}
            return {"name": "Memory", "passed": True, "detail": f"{count} Erfahrungen"}
        except Exception:
            return {"name": "Memory", "passed": False, "detail": "Memory-Index nicht lesbar"}

    def _check_strategy_learning(self) -> dict:
        """Prueft: Hat das System Strategien gelernt?"""
        strat_file = self.data_path / "consciousness" / "strategies.json"
        if not strat_file.exists():
            return {"name": "Strategien", "passed": True, "detail": "Noch keine Fehler → keine Strategien noetig"}
        try:
            with open(strat_file, "r", encoding="utf-8") as f:
                rules = json.load(f)
            return {"name": "Strategien", "passed": True, "detail": f"{len(rules)} Regeln gelernt"}
        except Exception:
            return {"name": "Strategien", "passed": False, "detail": "Strategien-Datei nicht lesbar"}

    def _check_tools_registered(self) -> dict:
        """Prueft: Sind Tools registriert und nutzbar?"""
        registry = self.data_path / "tools" / "registry.json"
        if not registry.exists():
            return {"name": "Tools", "passed": True, "detail": "Noch keine Tools (OK fuer Anfang)"}
        try:
            with open(registry, "r", encoding="utf-8") as f:
                data = json.load(f)
            tools = data.get("tools", {})
            # Pruefen ob Tool-Dateien existieren
            missing = []
            for name, info in tools.items():
                filepath = self.data_path / "tools" / info.get("file", "")
                if not filepath.exists():
                    missing.append(name)
            if missing:
                return {"name": "Tools", "passed": False, "detail": f"Registriert aber Dateien fehlen: {missing}"}
            return {"name": "Tools", "passed": True, "detail": f"{len(tools)} Tools registriert"}
        except Exception:
            return {"name": "Tools", "passed": False, "detail": "Registry nicht lesbar"}

    def _check_dream_running(self) -> dict:
        """Prueft: Laueft die Dream-Konsolidierung?"""
        dream_log = self.data_path / "consciousness" / "dream_log.json"
        state_file = self.data_path / "consciousness" / "state.json"

        sequences = 0
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                sequences = state.get("sequences_total", 0)
            except Exception:
                pass

        if sequences < 10:
            return {"name": "Dream", "passed": True, "detail": f"Nur {sequences} Sequenzen — Dream noch nicht faellig"}

        if not dream_log.exists():
            return {"name": "Dream", "passed": False, "detail": f"{sequences} Sequenzen aber Dream nie gelaufen"}

        try:
            with open(dream_log, "r", encoding="utf-8") as f:
                log = json.load(f)
            return {"name": "Dream", "passed": bool(log), "detail": f"{len(log)} Dream-Laeufe"}
        except Exception:
            return {"name": "Dream", "passed": False, "detail": "Dream-Log nicht lesbar"}

    def _check_benchmark_running(self) -> dict:
        """Prueft: Werden Benchmarks durchgefuehrt?"""
        bench_file = self.data_path / "consciousness" / "benchmarks.json"
        state_file = self.data_path / "consciousness" / "state.json"

        sequences = 0
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    sequences = json.load(f).get("sequences_total", 0)
            except Exception:
                pass

        if sequences < 20:
            return {"name": "Benchmarks", "passed": True, "detail": f"Nur {sequences} Sequenzen — Benchmark noch nicht faellig"}

        if not bench_file.exists():
            return {"name": "Benchmarks", "passed": False, "detail": f"{sequences} Sequenzen aber nie benchmarked"}

        try:
            with open(bench_file, "r", encoding="utf-8") as f:
                results = json.load(f)
            return {"name": "Benchmarks", "passed": bool(results), "detail": f"{len(results)} Benchmark-Ergebnisse"}
        except Exception:
            return {"name": "Benchmarks", "passed": False, "detail": "Benchmark-Datei nicht lesbar"}

    def _check_sequence_memory_saved(self) -> dict:
        """Prueft: Wird Sequenz-Memory gespeichert?"""
        mem_file = self.data_path / "consciousness" / "sequence_memory.json"
        if not mem_file.exists():
            return {"name": "Sequenz-Memory", "passed": False, "detail": "Keine Sequenz-Memory gespeichert"}
        try:
            with open(mem_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = len(data.get("entries", []))
            return {"name": "Sequenz-Memory", "passed": entries > 0, "detail": f"{entries} Eintraege"}
        except Exception:
            return {"name": "Sequenz-Memory", "passed": False, "detail": "Nicht lesbar"}


class DependencyAnalyzer:
    """
    Cross-File Dependency-Analyse.

    Findet:
    - Funktionen die definiert aber nie aufgerufen werden
    - Klassen die importiert aber nie instanziiert werden
    - Potenzielle tote Code-Pfade
    """

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.engine_path = root_path / "engine"

    def analyze(self) -> dict:
        """
        Analysiert alle Engine-Dateien auf Cross-File-Dependencies.

        Returns:
            {"orphaned_functions": list, "missing_calls": list, "report": str}
        """
        # Alle Python-Dateien im engine/ Ordner sammeln
        all_code = {}
        for py_file in sorted(self.engine_path.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            try:
                all_code[py_file.name] = py_file.read_text(encoding="utf-8")
            except Exception:
                pass

        # Schritt 1: Alle definierten Funktionen/Methoden sammeln
        all_definitions = {}  # {name: file}
        for filename, code in all_code.items():
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        if not node.name.startswith("_"):  # Nur public
                            all_definitions[node.name] = filename
            except SyntaxError:
                pass

        # Schritt 2: Alle Funktionsaufrufe sammeln (ueber alle Dateien)
        all_calls = set()
        combined_code = "\n".join(all_code.values())
        for name in all_definitions:
            # Suche nach name( oder .name(
            pattern = rf"(?:\.|\b){re.escape(name)}\s*\("
            if re.search(pattern, combined_code):
                all_calls.add(name)

        # Schritt 3: Verwaiste Funktionen finden
        orphaned = []
        for name, filename in all_definitions.items():
            if name not in all_calls:
                # Ausnahmen: Methoden die durch Tool-Dispatching aufgerufen werden
                # oder durch die API-Definition referenziert werden
                if name in ("run", "search", "store", "record", "get_trend",
                            "get_summary", "describe", "should_audit",
                            "should_dream", "should_benchmark", "is_configured"):
                    continue
                orphaned.append({"function": name, "file": filename})

        report_lines = [f"DEPENDENCY-ANALYSE: {len(all_definitions)} public Funktionen, {len(orphaned)} potenziell verwaist"]
        for o in orphaned[:10]:
            report_lines.append(f"  [?] {o['file']}::{o['function']}() — wird nirgendwo aufgerufen")

        return {
            "total_functions": len(all_definitions),
            "orphaned": orphaned,
            "report": "\n".join(report_lines),
        }


class SilentFailureDetector:
    """
    Erkennt Systeme die haetten laufen sollen aber nicht liefen.

    Prueft nach jeder Sequenz:
    - Sollte Dream gelaufen sein? → Hat es?
    - Sollte Audit gelaufen sein? → Hat es?
    - Sollte ein Benchmark gelaufen sein? → Hat es?
    - Wurden Skills getrackt? → Stimmt die Zahl?
    """

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.detector_log_path = data_path / "consciousness" / "silent_failures.json"

    def check_after_sequence(self, sequence_num: int, tool_calls: int) -> list[str]:
        """
        Prueft nach einer Sequenz ob alles gelaufen ist was haette laufen sollen.

        Returns:
            Liste von Warnungen (leer = alles OK)
        """
        warnings = []

        # 1. Wenn Tool-Calls > 0 aber keine Skills getrackt → Tracking kaputt
        if tool_calls > 0:
            skills_file = self.data_path / "consciousness" / "skills.json"
            if skills_file.exists():
                try:
                    with open(skills_file, "r", encoding="utf-8") as f:
                        skills = json.load(f)
                    total_events = sum(
                        s.get("successes", 0) + s.get("failures", 0)
                        for s in skills.values()
                    )
                    if total_events == 0 and tool_calls > 5:
                        warnings.append(
                            f"STILL: {tool_calls} Tool-Calls aber 0 Skill-Events — "
                            f"Skill-Tracking funktioniert nicht"
                        )
                except Exception:
                    pass

        # 2. Wenn Sequenz-Memory nicht waechst
        seq_mem = self.data_path / "consciousness" / "sequence_memory.json"
        if seq_mem.exists() and sequence_num > 3:
            try:
                with open(seq_mem, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries = len(data.get("entries", []))
                if entries < sequence_num * 0.3:  # Weniger als 30% der Sequenzen haben Memory
                    warnings.append(
                        f"STILL: Nur {entries} Memory-Eintraege fuer {sequence_num} Sequenzen — "
                        f"finish_sequence wird nicht richtig aufgerufen"
                    )
            except Exception:
                pass

        # 3. Wenn Efficiency nicht getrackt wird
        eff_file = self.data_path / "consciousness" / "efficiency.json"
        if eff_file.exists() and sequence_num > 5:
            try:
                with open(eff_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                seqs = len(data.get("sequences", []))
                if seqs < sequence_num * 0.5:
                    warnings.append(
                        f"STILL: Nur {seqs} Effizienz-Eintraege fuer {sequence_num} Sequenzen — "
                        f"Effizienz-Tracking hat Luecken"
                    )
            except Exception:
                pass

        # Loggen
        if warnings:
            self._log_warnings(warnings, sequence_num)

        return warnings

    def _log_warnings(self, warnings: list, sequence: int):
        try:
            log = []
            if self.detector_log_path.exists():
                with open(self.detector_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            log.append({
                "sequence": sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "warnings": warnings,
            })
            log = log[-30:]
            with open(self.detector_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_recent_warnings(self) -> str:
        """Letzte stille Fehler fuer den System-Prompt."""
        if not self.detector_log_path.exists():
            return ""
        try:
            with open(self.detector_log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
            if not log:
                return ""
            last = log[-1]
            warnings = last.get("warnings", [])
            if not warnings:
                return ""
            lines = ["STILLE FEHLER ERKANNT:"]
            for w in warnings:
                lines.append(f"  {w}")
            return "\n".join(lines)
        except Exception:
            return ""
