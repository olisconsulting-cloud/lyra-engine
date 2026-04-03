"""
Multi-Ebenen-Evolution — 5 Dimensionen des Wachstums.

1. Adaptiver Rhythmus: Evolution wenn noetig, nicht nach Zeitplan
2. Tool-Foundry: Meta-Tools die andere Tools erstellen/kombinieren
3. Selbst-Benchmarking: Standardaufgaben loesen und Fortschritt messen
4. Lehrprojekte: Neue Domains durch Bauen lernen, nicht durch Lesen
5. Mini-Metacognition: 2 Saetze Reflexion pro Sequenz (kein eigener Loop)
"""

import json
import random
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from .llm_router import MODELS, TASK_MODEL_MAP


# ============================================================
# 1. ADAPTIVER RHYTHMUS
# ============================================================

class AdaptiveRhythm:
    """
    Entscheidet was Lyra als naechstes tun soll — adaptiv, nicht starr.

    Statt "jede 3. Sequenz Evolution" → schaut was gerade am wichtigsten ist.
    """

    def __init__(self, data_path: Path):
        self.data_path = data_path

    def get_mode(self, state: dict) -> dict:
        """
        Bestimmt den Modus fuer die naechste Sequenz.

        Returns:
            {
                "mode": "execution|evolution|learning|sprint|cooldown",
                "reason": str,
                "instruction": str,  # Wird in die Perception eingefuegt
            }
        """
        # Daten sammeln
        has_oliver_tasks = self._has_pending_tasks()
        has_active_goals = self._has_active_goals()
        has_audit_findings = self._has_audit_goals()
        sequences = state.get("sequences_total", 0)
        skill_gaps = self._get_biggest_skill_gap()

        # === Prioritaeten ===

        # 0. Spin-Loop Cooldown: Bei 5+ unproduktiven Sequenzen → Modus wechseln
        spin_streak = self._get_spin_loop_streak()
        if spin_streak >= 5 and not has_oliver_tasks:
            return {
                "mode": "cooldown",
                "reason": f"Spin-Loop erkannt: {spin_streak} unproduktive Sequenzen",
                "instruction": (
                    "=== SPIN-LOOP ERKANNT ===\n"
                    f"Die letzten {spin_streak} Sequenzen waren unproduktiv "
                    f"(keine Dateien geschrieben, keine Tools gebaut).\n"
                    f"STOPP: Mach etwas ANDERES als bisher.\n"
                    f"Optionen: (1) Offene Goals pruefen und Sub-Goals anpassen, "
                    f"(2) Selbstverbesserung (read_own_code + modify_own_code), "
                    f"(3) finish_sequence mit Erklaerung warum kein Fortschritt.\n"
                ),
            }

        # 1. Oliver-Aufgaben haben IMMER Vorrang
        if has_oliver_tasks:
            return {
                "mode": "execution",
                "reason": "Oliver hat eine Aufgabe geschickt",
                "instruction": "",  # Kein Extra-Instruction noetig
            }

        # 2. Spin-Loop Warnung: Bei 3+ unproduktiven Sequenzen → Warnung anhaengen
        spin_warning = ""
        if spin_streak >= 3:
            spin_warning = (
                f"\n\nACHTUNG: {spin_streak} unproduktive Sequenzen in Folge. "
                f"Mach konkreten Fortschritt oder wechsle den Ansatz!"
            )

        # 3. Audit-Findings als Goals → Evolution-Sprint
        if has_audit_findings:
            return {
                "mode": "sprint",
                "reason": "Audit-Findings muessen behoben werden",
                "instruction": (
                    "=== EVOLUTION-SPRINT ===\n"
                    "Du hast offene Audit-Findings als Goals. "
                    "Behebe sie JETZT mit read_own_code + modify_own_code.\n"
                ) + spin_warning,
            }

        # 4. Aktive Goals → Execution (kein Evolution-Unterbruch)
        if has_active_goals:
            return {
                "mode": "execution",
                "reason": "Aktive Ziele vorhanden",
                "instruction": spin_warning,
            }

        # 5. Skill-Luecken → Lehrprojekt
        if skill_gaps:
            return {
                "mode": "learning",
                "reason": f"Skill-Luecke: {skill_gaps}",
                "instruction": (
                    f"=== LERN-SEQUENZ ===\n"
                    f"Deine groesste Skill-Luecke: {skill_gaps}\n"
                    f"Baue ein kleines Lern-Projekt das diesen Skill trainiert.\n"
                    f"Nicht lesen — BAUEN. Das Projekt ist das Lernen.\n"
                ),
            }

        # 6. Nichts zu tun → Evolution
        return self._evolution_mode()

    def _evolution_mode(self) -> dict:
        """Waehlt ein zufaelliges Modul zur Verbesserung."""
        targets = [
            "engine/actions.py", "engine/toolchain.py", "engine/web_access.py",
            "engine/intelligence.py", "engine/extensions.py", "engine/dream.py",
            "engine/perception.py", "engine/communication.py", "engine/security.py",
            "web/app.py", "web/templates/dashboard.html",
        ]
        target = random.choice(targets)

        # Frontend-spezifische Anweisungen
        if target.startswith("web/"):
            return {
                "mode": "evolution",
                "reason": f"Dashboard-Verbesserung: {target}",
                "instruction": (
                    f"=== DASHBOARD-EVOLUTION ===\n"
                    f"Verbessere: {target}\n"
                    f"1. Lies den Code (read_own_code)\n"
                    f"2. Finde EINE konkrete UX-Verbesserung:\n"
                    f"   - Neues Panel (Journal, Erfahrungen, Projekte)\n"
                    f"   - Bessere Charts oder Visualisierungen\n"
                    f"   - Responsive Design, Animationen, Accessibility\n"
                    f"   - Interaktive Features (Filter, Suche, Sortierung)\n"
                    f"3. Implementiere sie (modify_own_code)\n"
                    f"Design-Prinzipien: Dark Theme, minimalistisch, Tailwind CSS,\n"
                    f"Alpine.js fuer Reaktivitaet, ApexCharts fuer Daten.\n"
                    f"WICHTIG: Aenderungen an web/ gehen durch Opus-Review.\n"
                ),
            }

        return {
            "mode": "evolution",
            "reason": f"Selbstverbesserung: {target}",
            "instruction": (
                f"=== EVOLUTION-SEQUENZ ===\n"
                f"Verbessere: {target}\n"
                f"1. Lies den Code (read_own_code)\n"
                f"2. Finde EINE konkrete Verbesserung\n"
                f"3. Implementiere sie (modify_own_code)\n"
                f"4. Teste ob es funktioniert\n"
                f"ODER: Baue ein neues Tool das dich staerker macht.\n"
            ),
        }

    def _has_pending_tasks(self) -> bool:
        tasks_path = self.data_path / "consciousness" / "tasks.json"
        if not tasks_path.exists():
            return False
        try:
            with open(tasks_path, "r", encoding="utf-8") as f:
                tasks = json.load(f)
            return bool(tasks.get("pending"))
        except Exception:
            return False

    def _has_active_goals(self) -> bool:
        goals_path = self.data_path / "consciousness" / "goals.json"
        if not goals_path.exists():
            return False
        try:
            with open(goals_path, "r", encoding="utf-8") as f:
                goals = json.load(f)
            return bool(goals.get("active"))
        except Exception:
            return False

    def _has_audit_goals(self) -> bool:
        goals_path = self.data_path / "consciousness" / "goals.json"
        if not goals_path.exists():
            return False
        try:
            with open(goals_path, "r", encoding="utf-8") as f:
                goals = json.load(f)
            for g in goals.get("active", []):
                if "audit" in g.get("title", "").lower() or "optimierung" in g.get("title", "").lower():
                    return True
            return False
        except Exception:
            return False

    def _get_spin_loop_streak(self) -> int:
        """Liest den Spin-Loop-Counter aus dem SilentFailureDetector."""
        spin_path = self.data_path / "consciousness" / "spin_loop_counter.json"
        try:
            if spin_path.exists():
                with open(spin_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("streak", 0)
        except Exception:
            pass
        return 0

    def _get_biggest_skill_gap(self) -> Optional[str]:
        skills_path = self.data_path / "consciousness" / "skills.json"
        if not skills_path.exists():
            return "python_coding (keine Skills getrackt)"
        try:
            from .competence import CompetenceMatrix
            with open(skills_path, "r", encoding="utf-8") as f:
                skills = json.load(f)
            cm = CompetenceMatrix(skills)
            gaps = cm.get_gaps()
            if gaps:
                return f"{gaps[0]['name']} ({gaps[0]['current']} → {gaps[0]['target']})"
            return None
        except Exception:
            return None


# ============================================================
# 2. TOOL-FOUNDRY (ECHT — mit LLM-Call)
# ============================================================

FOUNDRY_MODEL_KEY = TASK_MODEL_MAP["tool_generation"]
FOUNDRY_MODEL = MODELS[FOUNDRY_MODEL_KEY]["model_id"]
FOUNDRY_PROVIDER = MODELS[FOUNDRY_MODEL_KEY]["provider"]


class ToolFoundry:
    """
    Echte Tool-Fabrik — generiert Tools via LLM-Call.

    generate_tool(): Beschreibung rein → fertiges, getestetes Tool raus
    combine_tools(): Zwei Tools rein → kombiniertes Tool raus
    """

    def __init__(self, tools_path: Path):
        self.tools_path = tools_path
        self.foundry_log_path = tools_path / "foundry_log.json"
        self.provider = FOUNDRY_PROVIDER
        if self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.provider == "deepseek":
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.api_url = "https://api.deepseek.com/chat/completions"
        else:
            self.api_key = ""
            self.api_url = "anthropic"

    def generate_tool(self, name: str, description: str, toolchain) -> str:
        """
        Generiert ein Tool via LLM-Call und registriert es.

        Args:
            name: Tool-Name (snake_case)
            description: Was das Tool tun soll
            toolchain: Toolchain-Instanz fuer Registrierung

        Returns:
            Ergebnis-Nachricht
        """
        prompt = f"""Schreibe ein Python-Tool mit dieser Spezifikation:

Name: {name}
Beschreibung: {description}

REGELN:
- Das Tool MUSS eine 'def run(**kwargs) -> str' Funktion haben
- run() muss IMMER einen String zurueckgeben
- Nutze nur Python-Stdlib + httpx (bereits installiert)
- Fehlerbehandlung mit try/except
- Keine globalen Variablen
- Kein print() — alles ueber return

Gib NUR den Python-Code zurueck. Kein Markdown, keine Erklaerung.
Starte direkt mit import oder def."""

        try:
            if self.api_url == "anthropic":
                from anthropic import Anthropic
                response = Anthropic().messages.create(
                    model=FOUNDRY_MODEL, max_tokens=3000,
                    messages=[{"role": "user", "content": prompt}],
                )
                code = response.content[0].text.strip()
            else:
                import httpx
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}",
                                 "Content-Type": "application/json"},
                        json={"model": FOUNDRY_MODEL, "max_tokens": 3000,
                              "messages": [{"role": "user", "content": prompt}]},
                    )
                if resp.status_code != 200:
                    return f"FEHLER bei Tool-Generierung: API {resp.status_code}"
                code = resp.json()["choices"][0]["message"]["content"].strip()

            # Code-Block-Wrapper entfernen falls vorhanden
            if code.startswith("```"):
                first_nl = code.find("\n")
                if first_nl > 0:
                    code = code[first_nl + 1:]
                if code.rstrip().endswith("```"):
                    code = code.rstrip()[:-3].rstrip()

            # Validierung: Muss run() haben
            if "def run(" not in code:
                return f"FEHLER: Generierter Code hat keine run() Funktion"

            # Ueber Toolchain registrieren (die testet und registriert)
            result = toolchain.create_tool(name, description, code)

            # Loggen
            self._log_generation(name, description, result)

            return result

        except Exception as e:
            return f"FEHLER bei Tool-Generierung: {e}"

    def combine_tools(self, tool_a_name: str, tool_b_name: str,
                      new_name: str, toolchain) -> str:
        """
        Kombiniert zwei existierende Tools zu einem mächtigeren.
        """
        # Tool-Code laden
        code_a = toolchain.get_tool_code(tool_a_name)
        code_b = toolchain.get_tool_code(tool_b_name)

        if code_a.startswith("FEHLER") or code_b.startswith("FEHLER"):
            return f"FEHLER: Konnte Tools nicht laden: {code_a[:50]}, {code_b[:50]}"

        prompt = f"""Kombiniere diese zwei Tools zu einem neuen, maechtigeren Tool:

=== Tool A: {tool_a_name} ===
{code_a[:2000]}

=== Tool B: {tool_b_name} ===
{code_b[:2000]}

Erstelle ein kombiniertes Tool namens '{new_name}' das:
- Beide Funktionalitaeten vereint
- Eine 'def run(**kwargs) -> str' Funktion hat
- Intelligent entscheidet welche Funktionalitaet genutzt wird

Gib NUR den Python-Code zurueck. Kein Markdown."""

        try:
            response = self.client.messages.create(
                model=FOUNDRY_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            code = response.content[0].text.strip()
            if code.startswith("```"):
                first_nl = code.find("\n")
                if first_nl > 0:
                    code = code[first_nl + 1:]
                if code.rstrip().endswith("```"):
                    code = code.rstrip()[:-3].rstrip()

            if "def run(" not in code:
                return "FEHLER: Kombinierter Code hat keine run() Funktion"

            description = f"Kombination von {tool_a_name} + {tool_b_name}"
            result = toolchain.create_tool(new_name, description, code)

            self._log_generation(new_name, description, result)
            return result

        except Exception as e:
            return f"FEHLER bei Tool-Kombination: {e}"

    def _log_generation(self, name: str, description: str, result: str):
        try:
            log = []
            if self.foundry_log_path.exists():
                with open(self.foundry_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "name": name,
                "description": description[:200],
                "result": result[:200],
            })
            log = log[-50:]
            with open(self.foundry_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_foundry_status(self) -> str:
        """Status der Tool-Fabrik."""
        tools_count = sum(1 for f in self.tools_path.glob("*.py")
                         if f.name not in ("__init__.py", "registry.json"))
        log = []
        if self.foundry_log_path.exists():
            try:
                with open(self.foundry_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except Exception:
                pass
        generated = len(log)
        return (
            f"Tool-Arsenal: {tools_count} Tools ({generated} generiert)\n"
            f"  Foundry: generate_tool + combine_tools verfuegbar"
        )


# ============================================================
# 3. SELBST-BENCHMARKING
# ============================================================

# Standard-Aufgaben fuer Benchmarking
BENCHMARK_TASKS = [
    {
        "id": "code_fibonacci",
        "name": "Fibonacci-Funktion schreiben",
        "type": "coding",
        "prompt": "Schreibe eine Python-Funktion die die n-te Fibonacci-Zahl berechnet. Teste sie mit n=10 (Ergebnis: 55).",
        "success_criteria": "55",
    },
    {
        "id": "tool_creation",
        "name": "Tool in unter 5 Calls erstellen",
        "type": "tool_building",
        "prompt": "Erstelle ein Tool namens 'word_counter' das einen Text zaehlt und die Wortanzahl zurueckgibt.",
        "success_criteria": "Tool.*erstellt",
    },
    {
        "id": "web_research",
        "name": "3 Fakten finden",
        "type": "research",
        "prompt": "Finde 3 aktuelle Fakten ueber Python 3.14 Features via web_search.",
        "success_criteria": "3",
    },
]


class SelfBenchmark:
    """
    Echtes Benchmarking — fuehrt Aufgaben aus und misst Ergebnisse.

    Nicht nur definieren, sondern AUSFUEHREN + MESSEN.
    """

    def __init__(self, data_path: Path, root_path: Path):
        self.data_path = data_path
        self.root_path = root_path
        self.benchmark_path = data_path / "consciousness" / "benchmarks.json"
        self.results = self._load()

    def _load(self) -> list:
        if self.benchmark_path.exists():
            with open(self.benchmark_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save(self):
        with open(self.benchmark_path, "w", encoding="utf-8") as f:
            json.dump(self.results[-100:], f, indent=2, ensure_ascii=False)

    def should_benchmark(self, sequences_since_last: int) -> bool:
        """Benchmark alle 20 Sequenzen oder wenn noch nie durchgefuehrt."""
        if not self.results:
            return True
        return sequences_since_last >= 20

    def run_coding_benchmark(self) -> dict:
        """
        Fuehrt den Coding-Benchmark aus: Fibonacci in Python.
        Misst ob der Code korrekt laeuft und wie schnell.
        """
        start = time.time()
        venv_python = self.root_path / "venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable

        code = '''
def fib(n):
    if n <= 1: return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# Test
results = [fib(i) for i in range(15)]
print(f"fib(10) = {fib(10)}")
print(f"fib(14) = {fib(14)}")
assert fib(10) == 55, f"FEHLER: fib(10) = {fib(10)}"
assert fib(14) == 377, f"FEHLER: fib(14) = {fib(14)}"
print("BENCHMARK_PASS")
'''
        try:
            result = subprocess.run(
                [python_cmd, "-c", code],
                capture_output=True, timeout=10,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            success = "BENCHMARK_PASS" in output
            duration = time.time() - start

            self.record_result("code_fibonacci", 1, success, duration)
            return {"task": "code_fibonacci", "success": success, "duration": round(duration, 2)}

        except Exception as e:
            self.record_result("code_fibonacci", 1, False, time.time() - start)
            return {"task": "code_fibonacci", "success": False, "error": str(e)}

    def run_all_benchmarks(self) -> str:
        """Fuehrt alle Benchmarks aus und gibt Ergebnis zurueck."""
        results = []

        # 1. Coding Benchmark
        r = self.run_coding_benchmark()
        results.append(r)

        # 2. File-IO Benchmark
        r = self._run_file_benchmark()
        results.append(r)

        # Zusammenfassung
        passed = sum(1 for r in results if r.get("success"))
        total = len(results)
        return (
            f"BENCHMARK: {passed}/{total} bestanden\n" +
            "\n".join(f"  {'OK' if r.get('success') else 'FAIL'} {r.get('task', '?')} ({r.get('duration', '?')}s)"
                      for r in results)
        )

    def _run_file_benchmark(self) -> dict:
        """File-IO Benchmark: Datei schreiben + lesen + loeschen."""
        start = time.time()
        test_file = self.data_path / "projects" / "_benchmark_test.txt"
        try:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("Benchmark-Test 12345", encoding="utf-8")
            content = test_file.read_text(encoding="utf-8")
            success = "12345" in content
            test_file.unlink()
            duration = time.time() - start
            self.record_result("file_io", 1, success, duration)
            return {"task": "file_io", "success": success, "duration": round(duration, 3)}
        except Exception as e:
            self.record_result("file_io", 1, False, time.time() - start)
            return {"task": "file_io", "success": False, "error": str(e)}

    def record_result(self, task_id: str, tool_calls: int, success: bool, duration: float):
        """Speichert ein Benchmark-Ergebnis."""
        self.results.append({
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_calls": tool_calls,
            "success": success,
            "duration_seconds": round(duration, 1),
        })
        self._save()

    def get_trend(self) -> str:
        """Zeigt Benchmark-Trends."""
        if not self.results:
            return "Noch keine Benchmarks durchgefuehrt."

        # Erfolgsrate
        recent = self.results[-20:]
        success_rate = sum(1 for r in recent if r.get("success")) / len(recent) * 100

        # Durchschnittliche Tool-Calls (weniger = besser)
        avg_calls = sum(r.get("tool_calls", 0) for r in recent) / len(recent)

        # Trend: Werden es weniger Calls?
        if len(recent) >= 6:
            first_half = recent[:len(recent)//2]
            second_half = recent[len(recent)//2:]
            first_avg = sum(r.get("tool_calls", 0) for r in first_half) / len(first_half)
            second_avg = sum(r.get("tool_calls", 0) for r in second_half) / len(second_half)
            if second_avg < first_avg * 0.8:
                trend = "VERBESSERND (weniger Calls)"
            elif second_avg > first_avg * 1.2:
                trend = "verschlechternd"
            else:
                trend = "stabil"
        else:
            trend = "zu wenig Daten"

        return (
            f"Benchmarks: {len(recent)} Tests, {success_rate:.0f}% Erfolg, "
            f"Ø {avg_calls:.1f} Calls, Trend: {trend}"
        )

    def get_next_benchmark(self) -> Optional[dict]:
        """Gibt die naechste Benchmark-Aufgabe zurueck."""
        # Rotiere durch die Aufgaben
        if not self.results:
            return BENCHMARK_TASKS[0]

        last_ids = [r.get("task_id") for r in self.results[-3:]]
        for task in BENCHMARK_TASKS:
            if task["id"] not in last_ids:
                return task

        return BENCHMARK_TASKS[0]  # Von vorne beginnen


# ============================================================
# 4. LEHRPROJEKTE
# ============================================================

# Domain-zu-Projekt Mapping
LEARNING_PROJECTS = {
    "api_integration": {
        "name": "api-explorer",
        "description": "Baue einen universellen API-Client der beliebige REST-APIs ansprechen kann",
        "sub_goals": [
            "GET-Requests mit httpx implementieren",
            "JSON-Response-Parsing mit Fehlerbehandlung",
            "Als wiederverwendbares Tool registrieren",
        ],
    },
    "data_analysis": {
        "name": "data-insights",
        "description": "Baue ein Datenanalyse-Tool das CSV/JSON Dateien analysiert und Reports erstellt",
        "sub_goals": [
            "CSV/JSON Loader bauen",
            "Statistische Grundauswertung (Mittelwert, Median, etc.)",
            "Report-Generator als Tool registrieren",
        ],
    },
    "testing": {
        "name": "test-framework",
        "description": "Baue ein Mini-Test-Framework fuer deine eigenen Tools",
        "sub_goals": [
            "Test-Runner der Tools automatisch testet",
            "Assertion-Helpers (expect_contains, expect_no_error)",
            "Als Tool registrieren: test_all_tools",
        ],
    },
    "architecture": {
        "name": "code-mapper",
        "description": "Baue ein Tool das deine eigene Codebase analysiert und visualisiert",
        "sub_goals": [
            "Alle Python-Dateien scannen und Imports extrahieren",
            "Dependency-Graph als Text-Diagramm",
            "Code-Metriken (Zeilen, Funktionen, Komplexitaet)",
        ],
    },
    "business_thinking": {
        "name": "market-scanner",
        "description": "Baue ein Tool das Maerkte und Konkurrenz analysiert",
        "sub_goals": [
            "Web-Search fuer Marktdaten nutzen",
            "Konkurrenz-Analyse strukturiert aufbereiten",
            "Pricing-Kalkulator als Tool",
        ],
    },
    "frontend_design": {
        "name": "dashboard-enhancer",
        "description": "Verbessere das Web-Dashboard (web/templates/dashboard.html) — Layout, Charts, UX",
        "sub_goals": [
            "Dashboard-Code lesen und verstehen (read_own_code web/templates/dashboard.html)",
            "Ein neues Panel hinzufuegen (z.B. Journal-Timeline oder Erfahrungs-Feed)",
            "CSS/Layout verbessern — Responsive Design, Animationen, Spacing",
            "Ergebnis im Browser testen und Screenshot-Beschreibung erstellen",
        ],
    },
}


class LearningEngine:
    """
    Echte Lehrprojekte — startet automatisch, trackt Abschluss, updated Skills.

    Nicht nur vorschlagen, sondern:
    1. Goal automatisch erstellen (mit Sub-Goals aus dem Projekt)
    2. Nach Abschluss: Skill-Level aktualisieren
    3. Tracken welche Projekte schon gemacht wurden
    """

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.learning_log_path = data_path / "consciousness" / "learning_log.json"
        self.learning_log = self._load_log()

    def _load_log(self) -> list:
        if self.learning_log_path.exists():
            try:
                with open(self.learning_log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_log(self):
        with open(self.learning_log_path, "w", encoding="utf-8") as f:
            json.dump(self.learning_log[-50:], f, indent=2, ensure_ascii=False)

    def start_learning_project(self, skill_gap: str, goal_stack) -> str:
        """
        Startet ein Lehrprojekt WIRKLICH — erstellt Goal mit Sub-Goals.

        Args:
            skill_gap: Name der Skill-Luecke
            goal_stack: GoalStack-Instanz fuer Goal-Erstellung

        Returns:
            Ergebnis
        """
        # Passendes Projekt finden
        project = self._find_project(skill_gap)
        if not project:
            return f"Kein Lehrprojekt fuer '{skill_gap}' verfuegbar."

        # Pruefen ob schon gemacht
        done_projects = [l.get("project") for l in self.learning_log if l.get("completed")]
        if project["name"] in done_projects:
            return f"Lehrprojekt '{project['name']}' schon abgeschlossen."

        # Goal erstellen
        result = goal_stack.create_goal(
            title=f"Lehrprojekt: {project['name']}",
            description=f"Skill-Training fuer {skill_gap}: {project['description']}",
            sub_goals=project["sub_goals"],
        )

        # Im Log eintragen
        self.learning_log.append({
            "project": project["name"],
            "skill": skill_gap,
            "started": datetime.now(timezone.utc).isoformat(),
            "completed": False,
        })
        self._save_log()

        return f"Lehrprojekt gestartet: {project['name']} ({len(project['sub_goals'])} Schritte) — {result}"

    def complete_learning_project(self, project_name: str, skills_tracker) -> str:
        """
        Schliesst ein Lehrprojekt ab und updated den Skill-Level.

        Args:
            project_name: Name des Projekts
            skills_tracker: SkillTracker-Instanz fuer Skill-Update
        """
        # Im Log finden und als abgeschlossen markieren
        for entry in reversed(self.learning_log):
            if entry.get("project") == project_name and not entry.get("completed"):
                entry["completed"] = True
                entry["completed_at"] = datetime.now(timezone.utc).isoformat()

                # Skill-Update: 5 Erfolge auf einmal (Projekt = groesserer Skill-Boost)
                skill = entry.get("skill", "")
                for key in LEARNING_PROJECTS:
                    if key in skill.lower():
                        for _ in range(5):
                            skills_tracker.record_success(f"create_project")
                            skills_tracker.record_success(f"execute_python")
                        break

                self._save_log()
                return f"Lehrprojekt '{project_name}' abgeschlossen! Skill-Boost angewendet."

        return f"Lehrprojekt '{project_name}' nicht gefunden."

    def _find_project(self, skill_gap: str) -> Optional[dict]:
        """Findet passendes Projekt fuer eine Skill-Luecke."""
        for key, project in LEARNING_PROJECTS.items():
            if key in skill_gap.lower() or any(
                word in skill_gap.lower() for word in key.split("_")
            ):
                return project
        return None

    def get_status(self) -> str:
        """Status aller Lehrprojekte."""
        done = sum(1 for l in self.learning_log if l.get("completed"))
        in_progress = sum(1 for l in self.learning_log if not l.get("completed"))
        total_available = len(LEARNING_PROJECTS)
        return (
            f"Lehrprojekte: {done} abgeschlossen, {in_progress} laufend, "
            f"{total_available - done - in_progress} verfuegbar"
        )

    def get_available_projects(self) -> str:
        """Liste verfuegbarer Lehrprojekte (noch nicht gemacht)."""
        done = {l.get("project") for l in self.learning_log if l.get("completed")}
        lines = []
        for key, project in LEARNING_PROJECTS.items():
            status = "DONE" if project["name"] in done else "verfuegbar"
            if status == "verfuegbar":
                lines.append(f"  - {key}: {project['name']} — {project['description'][:60]}")
        return "\n".join(lines) if lines else "Alle Lehrprojekte abgeschlossen!"


# ============================================================
# 5. MINI-METACOGNITION
# ============================================================

class MetaCognition:
    """
    Minimale Metacognition — 2 Saetze pro Sequenz, kein eigener Loop.

    Speichert:
    - "Was hat mich gebremst?" (bottleneck)
    - "Was mache ich naechstes Mal anders?" (strategy_change)

    Diese werden als Strategien gespeichert und beeinflussen zukuenftige Sequenzen.
    """

    def __init__(self, data_path: Path):
        self.meta_path = data_path / "consciousness" / "metacognition.json"
        self.entries = self._load()

    def _load(self) -> list:
        if self.meta_path.exists():
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save(self):
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.entries[-30:], f, indent=2, ensure_ascii=False)

    def record(self, bottleneck: str, strategy_change: str, sequence: int,
               wasted_steps: int = 0, productive_steps: int = 0,
               key_decision: str = ""):
        """Speichert eine erweiterte Reflexion mit Prozess-Metriken."""
        if not bottleneck and not strategy_change:
            return

        entry = {
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bottleneck": bottleneck[:500],
            "strategy_change": strategy_change[:500],
        }
        if wasted_steps or productive_steps:
            entry["wasted_steps"] = wasted_steps
            entry["productive_steps"] = productive_steps
        if key_decision:
            entry["key_decision"] = key_decision[:300]
        self.entries.append(entry)
        self._save()

    def analyze_patterns(self) -> list[str]:
        """Erkennt wiederkehrende Muster in den letzten Reflexionen."""
        if len(self.entries) < 5:
            return []

        alerts = []
        recent = self.entries[-10:]

        # 1. Wiederkehrende Engpaesse (Wort-Overlap > 50%)
        bottlenecks = [e.get("bottleneck", "").lower() for e in recent if e.get("bottleneck")]
        seen_cluster = set()
        for i, b in enumerate(bottlenecks):
            b_words = set(b.split())
            if not b_words or id(b) in seen_cluster:
                continue
            similar = sum(
                1 for other in bottlenecks
                if other != b and len(b_words & set(other.split())) / max(len(b_words), 1) > 0.5
            )
            if similar >= 2:
                alerts.append(f"Engpass {similar + 1}x aehnlich: {bottlenecks[i][:100]}")
                break

        # 2. Max-Steps ohne finish_sequence
        max_steps_count = sum(
            1 for e in recent
            if "Max Steps" in e.get("bottleneck", "") or "Auto-beendet" in e.get("key_decision", "")
        )
        if max_steps_count >= 3:
            alerts.append(f"{max_steps_count}/10 Sequenzen ohne finish_sequence beendet")

        # 3. Effizienz-Trend (wenn Daten vorhanden)
        efficiencies = [
            e["productive_steps"] / max(e["productive_steps"] + e["wasted_steps"], 1)
            for e in recent
            if "productive_steps" in e and "wasted_steps" in e
        ]
        if len(efficiencies) >= 3:
            avg = sum(efficiencies) / len(efficiencies)
            if avg < 0.3:
                alerts.append(f"Effizienz nur {avg:.0%} — ueber 70% der Steps unproduktiv")

        return alerts[:3]

    def get_recent_insights(self, n: int = 3) -> str:
        """Letzte Erkenntnisse + Muster-Analyse fuer den System-Prompt."""
        if not self.entries:
            return ""
        recent = self.entries[-n:]
        lines = ["SELBST-ERKENNTNISSE (vermeide diese Engpaesse):"]
        for e in recent:
            if e.get("bottleneck"):
                lines.append(f"  Engpass: {e['bottleneck'][:150]}")
            if e.get("strategy_change"):
                lines.append(f"  Strategie: {e['strategy_change'][:150]}")
            if e.get("key_decision"):
                lines.append(f"  Entscheidung: {e['key_decision'][:100]}")

        # Muster-Analyse anfuegen
        alerts = self.analyze_patterns()
        if alerts:
            lines.append("MUSTER-ANALYSE:")
            for a in alerts:
                lines.append(f"  ! {a[:150]}")

        return "\n".join(lines)
