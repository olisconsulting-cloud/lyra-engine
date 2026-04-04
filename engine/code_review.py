"""
Dual Code-Review System — Zwei unabhaengige Pruefinstanzen.

Schleife:
1. Primary-Modell schreibt Code (Haupt-Arbeit, aktuell Gemma 4 31B)
2. Lyra schreibt die Fixes (mit Backup)
3. REVIEW (Opus 4.6): Prueft ob Fixes korrekt sind (unabhaengiger Reviewer)
4. Opus OK → Fix bleibt | Opus NEIN → Rollback
5. Ergebnis wird geloggt

Primary = Haupt-Arbeit, schreibt den Code (via TASK_MODEL_MAP)
Opus = Unabhaengige Gegenpruefung, tiefste Analyse-Qualitaet
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx
from anthropic import Anthropic

from .config import safe_json_read, safe_json_write
from .llm_router import MODELS, TASK_MODEL_MAP


class CodeReviewer:
    """
    Code-Reviewer — nutzt Opus 4.6 als unabhaengigen Reviewer.

    Primary-Modell schreibt den Code, Opus prueft ihn — echtes Dual-Review
    mit zwei verschiedenen Modellen/Providern.
    """

    def __init__(self):
        model_key = TASK_MODEL_MAP["code_review"]
        model_config = MODELS[model_key]
        self.provider = model_config["provider"]
        self.model = model_config["model_id"]

        # Anthropic-Client fuer Opus
        if self.provider == "anthropic":
            self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        elif self.provider == "nvidia":
            self.api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        elif self.provider == "google":
            self.api_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        else:
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _build_diff(self, original: str, modified: str) -> str:
        """Erzeugt einen lesbaren Diff statt ganzen Code zu senden."""
        import difflib
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines, modified_lines,
            fromfile="original", tofile="modified",
            lineterm="",
        )
        diff_text = "".join(diff)
        # Wenn Diff zu lang, kuerzen aber nie abschneiden mitten in einer Zeile
        if len(diff_text) > 6000:
            lines = diff_text.split("\n")
            truncated = []
            total = 0
            for line in lines:
                if total + len(line) > 5500:
                    remaining = len(lines) - len(truncated)
                    truncated.append(f"\n... ({remaining} weitere Diff-Zeilen gekuerzt) ...")
                    break
                truncated.append(line)
                total += len(line) + 1  # +1 fuer den \n der beim join dazukommt
            diff_text = "\n".join(truncated)
        return diff_text

    def review(self, original_code: str, modified_code: str,
               change_reason: str, file_path: str) -> dict:
        """
        Reviewed eine Code-Aenderung via Opus 4.6.

        Sendet einen Diff statt ganzen Code — verhindert Truncation-Probleme.

        Returns:
            {"approved": bool, "reason": str, "issues": list}
        """
        if not self.is_configured:
            provider_name = self.provider.upper()
            key_name = {
                "anthropic": "ANTHROPIC_API_KEY",
                "nvidia": "NVIDIA_API_KEY",
                "google": "GOOGLE_AI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }.get(self.provider, "API_KEY")
            return {
                "approved": False,
                "reason": f"Reviewer nicht konfiguriert — {key_name} fehlt (fail-closed)",
                "issues": [f"{key_name} fehlt in .env"],
            }

        # Diff statt ganzen Code senden
        diff_text = self._build_diff(original_code, modified_code)

        # Vollstaendigen Code begrenzen — bei grossen Dateien nur Diff + Kontext
        if len(modified_code) > 12000:
            code_section = f"(Datei zu gross fuer vollstaendige Anzeige: {len(modified_code)} Zeichen)\n"
            code_section += f"Erste 4000 Zeichen:\n{modified_code[:4000]}\n...\n"
            code_section += f"Letzte 4000 Zeichen:\n{modified_code[-4000:]}"
        else:
            code_section = modified_code

        prompt = f"""Du bist ein strenger Code-Reviewer. Pruefe ob diese Aenderung sicher und korrekt ist.

DATEI: {file_path}
GRUND DER AENDERUNG: {change_reason}

=== DIFF (unified) — Das ist die primaere Review-Grundlage ===
{diff_text}

=== KONTEXT: Neuer Code ===
{code_section}

Pruefe auf:
1. Fuehrt die Aenderung neue Bugs ein?
2. Werden bestehende Funktionen kaputt gemacht?
3. Ist die Aenderung syntaktisch korrekt und VOLLSTAENDIG?
4. Gibt es Sicherheitsprobleme?
5. Ist die Aenderung sinnvoll fuer den angegebenen Grund?

Antworte AUSSCHLIESSLICH als JSON (kein Markdown, kein Text davor/danach):
{{
  "approved": true/false,
  "reason": "Kurze Begruendung",
  "issues": ["Problem 1", "Problem 2"]
}}

Sei streng aber fair. Nur echte Probleme fuehren zu Ablehnung.
Unvollstaendiger Code ist ein ECHTES Problem — lehne ab wenn Code abgeschnitten wirkt."""

        try:
            if self.provider == "anthropic":
                # Nativer Anthropic-Client — robuster als httpx
                client = Anthropic()
                response = client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text.strip()
            else:
                # OpenAI-kompatible API (NVIDIA, DeepSeek)
                base_urls = {
                    "nvidia": "https://integrate.api.nvidia.com/v1",
                    "deepseek": "https://api.deepseek.com",
                    "google": "https://generativelanguage.googleapis.com/v1beta",
                }
                base_url = base_urls.get(self.provider, "")

                if self.provider == "google":
                    with httpx.Client(timeout=30.0) as http:
                        resp = http.post(
                            f"{base_url}/models/{self.model}:generateContent",
                            params={"key": self.api_key},
                            json={
                                "contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": 2000},
                            },
                        )
                    if resp.status_code != 200:
                        return {"approved": False, "reason": f"API Fehler: {resp.status_code} (fail-closed)", "issues": [f"HTTP {resp.status_code}"]}
                    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    with httpx.Client(timeout=30.0) as http:
                        resp = http.post(
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                            json={"model": self.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000},
                        )
                    if resp.status_code != 200:
                        return {"approved": False, "reason": f"API Fehler: {resp.status_code} (fail-closed)", "issues": [f"HTTP {resp.status_code}"]}
                    text = resp.json()["choices"][0]["message"]["content"]

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
                    "issues": ["JSON-Parse-Fehler", f"Antwort: {cleaned[:200]}"],
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

    Primary (Code schreiben) → Backup → Syntax-Check → Opus (Review) → Accept/Rollback
    """

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.review_log_path = root_path / "data" / "consciousness" / "review_log.json"
        self.backup_path = root_path / "data" / "evolution" / "review_backups"
        self.backup_path.mkdir(parents=True, exist_ok=True)

        self.reviewer = CodeReviewer()

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
        4. Opus Review (fail-closed)
        5. Accept oder Rollback

        Returns:
            {"accepted": bool, "reason": str, "reviews": dict}
        """
        target = (self.root_path / file_path).resolve()

        # Sicherheitscheck
        if not target.is_relative_to(self.root_path.resolve()):
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

        # === 4. OPUS REVIEW (fail-closed: ohne Review kein Durchkommen) ===
        review_result = self.reviewer.review(
            original_code=original_content,
            modified_code=new_content,
            change_reason=reason,
            file_path=file_path,
        )

        if not review_result.get("approved", False):
            # Nicht approved (oder Key fehlt) → Rollback
            self._rollback(target, original_content)
            self._log_review(file_path, reason, "REJECTED", review_result)
            return {
                "accepted": False,
                "reason": f"Review abgelehnt: {review_result.get('reason', '?')}",
                "reviews": {"opus": review_result},
            }

        # === 5. AKZEPTIERT ===
        self._log_review(file_path, reason, "ACCEPTED", review_result)
        return {
            "accepted": True,
            "reason": "Alle Pruefungen bestanden",
            "reviews": {"opus": review_result},
        }

    def _rollback(self, target: Path, original_content: str):
        """Stellt die originale Version wieder her und validiert den Rollback."""
        if original_content:
            with open(target, "w", encoding="utf-8") as f:
                f.write(original_content)
            # Validierung: Lesen und vergleichen
            restored = target.read_text(encoding="utf-8")
            if restored != original_content:
                # Zweiter Versuch mit atomarem Schreiben
                import tempfile
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp_fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    f.write(original_content)
                Path(tmp_path).replace(target)
        elif target.exists():
            target.unlink()

    def _log_review(self, file_path: str, reason: str,
                    decision: str, review_result: dict):
        """Loggt das Review-Ergebnis."""
        try:
            log = safe_json_read(self.review_log_path, default=[])

            log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file": file_path,
                "reason": reason[:200],
                "decision": decision,
                "reviewer_approved": review_result.get("approved"),
                "reviewer_reason": review_result.get("reason", "")[:200],
                "reviewer_issues": review_result.get("issues", []),
            })
            log = log[-50:]

            safe_json_write(self.review_log_path, log)
        except Exception as e:
            # Fehler loggen statt still schlucken — safe_json_write
            # behandelt atomares Schreiben, aber uebergeordnete Fehler
            # (z.B. Berechtigungen) werden hier abgefangen
            import logging
            logging.getLogger(__name__).warning("Review-Log Schreibfehler: %s", e)

    def get_review_stats(self) -> str:
        """Statistiken ueber Reviews."""
        log = safe_json_read(self.review_log_path, default=[])
        if not log:
            return "Noch keine Reviews."
        accepted = sum(1 for r in log if r.get("decision") == "ACCEPTED")
        rejected = sum(1 for r in log if r.get("decision") == "REJECTED")
        total = len(log)
        return (
            f"Reviews: {total} total, {accepted} akzeptiert, {rejected} abgelehnt "
            f"({accepted/max(total,1)*100:.0f}% Akzeptanzrate)"
        )
