"""
Dual Code-Review System — Zwei unabhaengige Pruefinstanzen.

Schleife:
1. AUDIT (Opus): Liest Code → findet Probleme → schlaegt Fixes vor
2. Lyra schreibt die Fixes (mit Backup)
3. REVIEW (Gemini Flash): Prueft ob Fixes korrekt sind
4. Gemini OK → Fix bleibt | Gemini NEIN → Rollback
5. Ergebnis wird geloggt

Opus = Tiefe Analyse, findet die echten Probleme
Gemini = Unabhaengige Gegenprüfung, verschiedene Perspektive
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from anthropic import Anthropic


class GeminiReviewer:
    """Gemini Flash als unabhaengiger Code-Reviewer."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.model = "gemini-2.5-flash"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def review(self, original_code: str, modified_code: str,
               change_reason: str, file_path: str) -> dict:
        """
        Reviewed eine Code-Aenderung.

        Args:
            original_code: Code vor der Aenderung
            modified_code: Code nach der Aenderung
            change_reason: Warum die Aenderung gemacht wurde
            file_path: Welche Datei

        Returns:
            {"approved": bool, "reason": str, "issues": list}
        """
        if not self.is_configured:
            # Fail-Closed: Ohne Reviewer kein Review = kein Durchkommen
            return {
                "approved": False,
                "reason": "Gemini nicht konfiguriert — Review nicht moeglich (fail-closed)",
                "issues": ["GOOGLE_AI_API_KEY fehlt in .env"],
            }

        prompt = f"""Du bist ein Code-Reviewer. Pruefe ob diese Aenderung sicher und korrekt ist.

DATEI: {file_path}
GRUND DER AENDERUNG: {change_reason}

=== ORIGINAL ===
{original_code[:4000]}

=== GEAENDERT ===
{modified_code[:4000]}

Pruefe auf:
1. Fuehrt die Aenderung neue Bugs ein?
2. Werden bestehende Funktionen kaputt gemacht?
3. Ist die Aenderung syntaktisch korrekt?
4. Gibt es Sicherheitsprobleme?
5. Ist die Aenderung sinnvoll fuer den angegebenen Grund?

Antworte als JSON:
{{
  "approved": true/false,
  "reason": "Kurze Begruendung",
  "issues": ["Problem 1", "Problem 2"] oder []
}}

Sei streng aber fair. Nur echte Probleme fuehren zu Ablehnung."""

        try:
            client = httpx.Client(timeout=30.0)
            response = client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2000},
                },
            )

            if response.status_code != 200:
                return {
                    "approved": False,
                    "reason": f"Gemini API Fehler: {response.status_code} (fail-closed)",
                    "issues": [f"HTTP {response.status_code}"],
                }

            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]

            # JSON parsen (Code-Block-Wrapper entfernen)
            cleaned = text.strip()
            if cleaned.startswith("```"):
                first_nl = cleaned.find("\n")
                if first_nl > 0:
                    cleaned = cleaned[first_nl + 1:]
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-3].rstrip()

            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(0))
                    except json.JSONDecodeError:
                        pass
                return {
                    "approved": False,
                    "reason": "Konnte Review nicht parsen (fail-closed)",
                    "issues": ["JSON-Parse-Fehler"],
                }

        except Exception as e:
            return {
                "approved": False,
                "reason": f"Review-Fehler: {e} (fail-closed)",
                "issues": [str(e)],
            }


class DualReviewSystem:
    """
    Komplette Pruefschleife mit zwei Instanzen.

    Opus (Audit) → Lyra (Fix) → Gemini (Review) → Accept/Rollback
    """

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.review_log_path = root_path / "data" / "consciousness" / "review_log.json"
        self.backup_path = root_path / "data" / "evolution" / "review_backups"
        self.backup_path.mkdir(parents=True, exist_ok=True)

        self.opus = Anthropic()
        self.gemini = GeminiReviewer()

    def review_and_apply_fix(
        self,
        file_path: str,
        new_content: str,
        reason: str,
    ) -> dict:
        """
        Komplette Pruefschleife fuer eine Code-Aenderung.

        1. Backup erstellen
        2. Neue Version schreiben
        3. Syntax pruefen
        4. Gemini Review
        5. Accept oder Rollback

        Returns:
            {"accepted": bool, "reason": str, "reviews": dict}
        """
        target = (self.root_path / file_path).resolve()

        # Sicherheitscheck
        if not str(target).startswith(str(self.root_path.resolve())):
            return {"accepted": False, "reason": "Pfad ausserhalb des Projekts"}

        # === 1. BACKUP ===
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_content = ""
        if target.exists():
            original_content = target.read_text(encoding="utf-8")
            backup_name = f"{target.stem}_{timestamp}{target.suffix}"
            shutil.copy2(target, self.backup_path / backup_name)

        # === 2. NEUE VERSION SCHREIBEN ===
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)

        # === 3. SYNTAX-CHECK ===
        import subprocess, sys
        venv_python = self.root_path / "venv" / "Scripts" / "python.exe"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable

        try:
            result = subprocess.run(
                [python_cmd, "-m", "py_compile", str(target)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # Syntax-Fehler → sofort Rollback
                self._rollback(target, original_content)
                return {
                    "accepted": False,
                    "reason": f"Syntax-Fehler: {result.stderr[:200]}",
                    "reviews": {},
                }
        except Exception as e:
            self._rollback(target, original_content)
            return {"accepted": False, "reason": f"Compile-Check Fehler: {e}", "reviews": {}}

        # === 4. GEMINI REVIEW ===
        gemini_result = {"approved": False, "reason": "Gemini nicht konfiguriert (fail-closed)", "issues": []}
        if self.gemini.is_configured:
            gemini_result = self.gemini.review(
                original_code=original_content,
                modified_code=new_content,
                change_reason=reason,
                file_path=file_path,
            )

            if not gemini_result.get("approved", True):
                # Gemini sagt NEIN → Rollback
                self._rollback(target, original_content)
                self._log_review(file_path, reason, "REJECTED", gemini_result)
                return {
                    "accepted": False,
                    "reason": f"Gemini abgelehnt: {gemini_result.get('reason', '?')}",
                    "reviews": {"gemini": gemini_result},
                }

        # === 5. AKZEPTIERT ===
        self._log_review(file_path, reason, "ACCEPTED", gemini_result)
        return {
            "accepted": True,
            "reason": "Alle Pruefungen bestanden",
            "reviews": {"gemini": gemini_result},
        }

    def _rollback(self, target: Path, original_content: str):
        """Stellt die originale Version wieder her."""
        if original_content:
            with open(target, "w", encoding="utf-8") as f:
                f.write(original_content)
        elif target.exists():
            target.unlink()

    def _log_review(self, file_path: str, reason: str,
                    decision: str, gemini_result: dict):
        """Loggt das Review-Ergebnis."""
        try:
            log = []
            if self.review_log_path.exists():
                with open(self.review_log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)

            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file": file_path,
                "reason": reason[:200],
                "decision": decision,
                "gemini_approved": gemini_result.get("approved"),
                "gemini_reason": gemini_result.get("reason", "")[:200],
                "gemini_issues": gemini_result.get("issues", []),
            })
            log = log[-50:]

            with open(self.review_log_path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_review_stats(self) -> str:
        """Statistiken ueber Reviews."""
        if not self.review_log_path.exists():
            return "Noch keine Reviews."
        try:
            with open(self.review_log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
            if not log:
                return "Noch keine Reviews."
            accepted = sum(1 for r in log if r.get("decision") == "ACCEPTED")
            rejected = sum(1 for r in log if r.get("decision") == "REJECTED")
            total = len(log)
            return (
                f"Reviews: {total} total, {accepted} akzeptiert, {rejected} abgelehnt "
                f"({accepted/max(total,1)*100:.0f}% Akzeptanzrate)"
            )
        except Exception:
            return "Review-Log nicht lesbar."
