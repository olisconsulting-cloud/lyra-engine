"""
Security-Gateway — Zentraler Schutz fuer alle Datei- und Code-Operationen.

Alle Schreibzugriffe und Code-Ausfuehrungen gehen durch diese Stelle.
Kein Weg daran vorbei — egal ob write_file, modify_own_code oder execute_python.

3 Schichten:
1. Pfad-Schutz: Protected files, Pfad-Normalisierung, Scope-Check
2. AST-Analyse: Soft-Warnings + Hard-Blocks fuer gefaehrliche Patterns
3. Review-Routing: Engine-Code → Dual-Review, Projekt-Code → direkt
"""

import ast
import os
from pathlib import Path
from typing import Optional


# === GESCHUETZTE DATEIEN UND PFADE ===

# Duerfen NIEMALS ueberschrieben werden (egal durch welchen Pfad)
PROTECTED_FILES = {
    ".env",
    ".env.local",
    "genesis.json",
}

# Engine-Dateien: Aenderungen NUR durch Dual-Review
ENGINE_PATHS = {
    "engine/",
    "run.py",
    "interact.py",
    "setup.py",
}

# === AST BLOCKLIST ===

# HARD BLOCK: Werden immer blockiert — destruktive Operationen
HARD_BLOCKED_PATTERNS = {
    # Dateisystem-Zerstoerung
    "shutil.rmtree": "Loescht ganze Verzeichnisbaeume — extrem gefaehrlich",
    "os.rmdir": "Loescht Verzeichnisse",
    "os.removedirs": "Loescht Verzeichnisbaeume rekursiv",
    # Beliebige Systembefehle
    "os.system": "Fuehrt Shell-Befehle aus — Sicherheitsrisiko",
    "os.popen": "Fuehrt Shell-Befehle aus",
    "os.exec": "Ersetzt den laufenden Prozess",
    "os.execv": "Ersetzt den laufenden Prozess",
    "os.execve": "Ersetzt den laufenden Prozess",
    # Netzwerk-Oeffnung
    "socket.listen": "Oeffnet einen Netzwerk-Port — nicht erlaubt",
    "socket.bind": "Bindet einen Netzwerk-Port",
}

# SOFT WARNING: Warnung ausgeben, aber nicht blockieren
SOFT_WARNING_PATTERNS = {
    "eval": "eval() ist unsicher — nutze json.loads() oder ast.literal_eval()",
    "exec": "exec() fuehrt beliebigen Code aus — nutze spezifischere Alternativen",
    "__import__": "__import__() ist unueblich — nutze regulaere imports",
    "compile": "compile() + exec ist ein Umweg um exec — wirklich noetig?",
    "getattr(__builtins__": "Zugriff auf __builtins__ ist verdaechtig",
    "subprocess.run": "subprocess.run — stelle sicher dass shell=False ist",
    "subprocess.call": "subprocess.call — nutze subprocess.run stattdessen",
    "subprocess.Popen": "subprocess.Popen — stelle sicher dass shell=False ist",
}


class SecurityGateway:
    """Zentraler Sicherheits-Gateway fuer alle Operationen."""

    def __init__(self, root_path: Path, data_path: Path):
        self.root_path = root_path.resolve()
        self.data_path = data_path.resolve()

    # === PFAD-SCHUTZ ===

    def check_write_permission(self, relative_path: str) -> dict:
        """
        Prueft ob ein Schreibzugriff erlaubt ist.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "requires_review": bool,  # Muss durch Dual-Review
                "warnings": list[str],
            }
        """
        # Pfad normalisieren (gegen Path-Traversal)
        target = (self.data_path / relative_path).resolve()

        # 1. Muss innerhalb von data/ oder root/ liegen
        in_data = target.is_relative_to(self.data_path)
        in_root = target.is_relative_to(self.root_path)

        if not (in_data or in_root):
            return {
                "allowed": False,
                "reason": f"Pfad ausserhalb des Projekts: {relative_path}",
                "requires_review": False,
                "warnings": [],
            }

        # 2. Protected files
        if target.name in PROTECTED_FILES:
            return {
                "allowed": False,
                "reason": f"Geschuetzte Datei: {target.name}",
                "requires_review": False,
                "warnings": [],
            }

        # 3. Engine-Pfade → Dual-Review erforderlich
        requires_review = False
        for engine_path in ENGINE_PATHS:
            # Pruefe ob relative_path ein Engine-Pfad ist
            if relative_path.startswith(engine_path) or relative_path == engine_path.rstrip("/"):
                requires_review = True
                break

        # Auch Pfade die engine/ direkt referenzieren (z.B. von root)
        try:
            rel_to_root = target.relative_to(self.root_path)
            rel_str = str(rel_to_root).replace("\\", "/")
            for engine_path in ENGINE_PATHS:
                if rel_str.startswith(engine_path) or rel_str == engine_path.rstrip("/"):
                    requires_review = True
                    break
        except ValueError:
            pass

        return {
            "allowed": True,
            "reason": "OK",
            "requires_review": requires_review,
            "warnings": [],
        }

    # === AST-ANALYSE ===

    def analyze_code(self, code: str) -> dict:
        """
        Analysiert Python-Code auf gefaehrliche Patterns.

        Returns:
            {
                "safe": bool,          # False nur bei Hard-Blocks
                "hard_blocks": list,   # Blockierte Patterns (Code wird NICHT ausgefuehrt)
                "warnings": list,      # Soft-Warnings (Code WIRD ausgefuehrt, aber mit Warnung)
            }
        """
        hard_blocks = []
        warnings = []

        # 1. Textbasierte Suche (schnell, faengt offensichtliche Patterns)
        code_lower = code.lower()
        for pattern, reason in HARD_BLOCKED_PATTERNS.items():
            if pattern.lower() in code_lower:
                hard_blocks.append(f"BLOCKIERT: {pattern} — {reason}")

        for pattern, reason in SOFT_WARNING_PATTERNS.items():
            if pattern.lower() in code_lower:
                warnings.append(f"WARNUNG: {pattern} — {reason}")

        # 2. AST-basierte Analyse (tiefer, faengt auch verschleierte Patterns)
        try:
            tree = ast.parse(code)
            ast_issues = self._analyze_ast(tree)
            hard_blocks.extend(ast_issues.get("hard", []))
            warnings.extend(ast_issues.get("soft", []))
        except SyntaxError:
            # Syntax-Fehler werden vom py_compile gefangen
            pass

        # 3. shell=True Check (besonders wichtig)
        if "shell=true" in code_lower or "shell = true" in code_lower:
            hard_blocks.append("BLOCKIERT: shell=True — Shell-Injection-Risiko")

        return {
            "safe": len(hard_blocks) == 0,
            "hard_blocks": hard_blocks,
            "warnings": warnings,
        }

    def _analyze_ast(self, tree: ast.AST) -> dict:
        """AST-basierte Tiefenanalyse."""
        hard = []
        soft = []

        for node in ast.walk(tree):
            # os.remove / os.unlink auf Nicht-Projekt-Pfade
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)

                if func_name in ("os.remove", "os.unlink", "pathlib.Path.unlink"):
                    # Pruefen ob Argument ein sicherer Pfad ist
                    # Konservativ: Warnung, nicht Block
                    soft.append(f"WARNUNG: {func_name}() — Datei-Loeschung, Pfad pruefen")

                elif func_name in ("shutil.rmtree", "os.rmdir", "os.removedirs"):
                    hard.append(f"BLOCKIERT: {func_name}() — Verzeichnis-Loeschung")

                elif func_name in ("os.system", "os.popen"):
                    hard.append(f"BLOCKIERT: {func_name}() — Shell-Ausfuehrung")

            # Import von verdaechtigen Modulen
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("ctypes", "multiprocessing"):
                        soft.append(f"WARNUNG: import {alias.name} — ungewoehnlich")

        return {"hard": hard, "soft": soft}

    def _get_call_name(self, node: ast.Call) -> str:
        """Extrahiert den Funktionsnamen aus einem Call-Node."""
        if isinstance(node.func, ast.Attribute):
            # z.B. os.remove
            if isinstance(node.func.value, ast.Name):
                return f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func.value, ast.Attribute):
                # z.B. pathlib.Path.unlink
                if isinstance(node.func.value.value, ast.Name):
                    return f"{node.func.value.value.id}.{node.func.value.attr}.{node.func.attr}"
        elif isinstance(node.func, ast.Name):
            return node.func.id
        return ""

    # === COMBINED CHECK ===

    def check_code_execution(self, code: str) -> dict:
        """
        Prueft ob Code ausgefuehrt werden darf.

        Returns:
            {"allowed": bool, "hard_blocks": list, "warnings": list}
        """
        analysis = self.analyze_code(code)
        return {
            "allowed": analysis["safe"],
            "hard_blocks": analysis["hard_blocks"],
            "warnings": analysis["warnings"],
        }
