"""
Kompetenz-Matrix + Selbst-Audit — Aktive Evolution.

1. KOMPETENZ-MATRIX
   Definiert welche Skills Lyra BRAUCHT (nicht nur welche sie zufaellig hat).
   Wenn ein Skill zu schwach ist → schlaegt konkrete Aktionen vor.
   "Training" = Tools bauen die den Skill abdecken + Strategien sammeln.

2. SELBST-AUDIT
   Periodisch liest Lyra ihren eigenen Code, findet Bugs/Luecken,
   und verbessert sich selbst. Echte Evolution, nicht simuliert.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from anthropic import Anthropic

from .config import safe_json_read, safe_json_write
from .llm_router import MODELS, TASK_MODEL_MAP


# === KOMPETENZ-MATRIX ===

# Ziel-Skills die Lyra braucht — mit Beschreibung und wie man sie "trainiert"
TARGET_SKILLS = {
    "python_coding": {
        "name": "Python-Entwicklung",
        "description": "Code schreiben, testen, debuggen, optimieren",
        "target_level": "expert",
        "training": "Komplexere Scripts bauen, Error-Handling verbessern, Tests schreiben",
        "tools_to_build": ["code_tester", "debug_helper"],
    },
    "web_research": {
        "name": "Web-Research",
        "description": "Internet durchsuchen, Informationen extrahieren und bewerten",
        "target_level": "advanced",
        "training": "Verschiedene Suchstrategien testen, Quellen vergleichen, Zusammenfassungen schreiben",
        "tools_to_build": ["research_summarizer", "source_evaluator"],
    },
    "tool_building": {
        "name": "Tool-Building",
        "description": "Wiederverwendbare Tools bauen die dauerhaft verfuegbar bleiben",
        "target_level": "expert",
        "training": "Tools fuer verschiedene Domaenen bauen, bestehende Tools verbessern",
        "tools_to_build": ["tool_tester", "tool_upgrader"],
    },
    "project_management": {
        "name": "Projekt-Management",
        "description": "Projekte planen, strukturieren, Meilensteine setzen, abschliessen",
        "target_level": "advanced",
        "training": "Projekte mit klaren Sub-Goals anlegen, Fortschritt tracken, abschliessen",
        "tools_to_build": ["project_planner"],
    },
    "self_improvement": {
        "name": "Selbstverbesserung",
        "description": "Eigenen Code lesen, verstehen, Fehler finden, optimieren",
        "target_level": "advanced",
        "training": "Eigene Engine-Module lesen und verbessern, Patterns erkennen",
        "tools_to_build": ["code_analyzer"],
    },
    "communication": {
        "name": "Kommunikation",
        "description": "Klar, direkt und hilfreich mit Oliver kommunizieren",
        "target_level": "advanced",
        "training": "Ergebnisse praesentieren, Fragen stellen, Updates geben",
        "tools_to_build": [],
    },
    "api_integration": {
        "name": "API-Integration",
        "description": "Externe APIs einbinden, Authentifizierung, Daten verarbeiten",
        "target_level": "advanced",
        "training": "APIs recherchieren, einbinden, Wrapper bauen",
        "tools_to_build": ["api_connector"],
    },
    "data_analysis": {
        "name": "Datenanalyse",
        "description": "Daten auswerten, Muster erkennen, Visualisierungen erstellen",
        "target_level": "intermediate",
        "training": "Daten laden, analysieren, Reports erstellen",
        "tools_to_build": ["data_analyzer", "report_generator"],
    },
    "architecture": {
        "name": "Architektur-Design",
        "description": "Systeme sauber strukturieren, Module trennen, Interfaces definieren",
        "target_level": "advanced",
        "training": "Eigene Codebase analysieren, Refactoring-Vorschlaege machen",
        "tools_to_build": ["architecture_reviewer"],
    },
    "testing": {
        "name": "Testing",
        "description": "Code testen bevor er deployed wird, Edge-Cases abfangen",
        "target_level": "intermediate",
        "training": "Tests fuer eigene Tools schreiben, Fehler provozieren",
        "tools_to_build": ["test_runner"],
    },
    "business_thinking": {
        "name": "Business-Denken",
        "description": "Monetarisierung, Kundennutzen, Marktanalyse, Mehrwert-Kreation",
        "target_level": "advanced",
        "training": "Markt recherchieren, Pricing kalkulieren, Verkaufsstrategien entwickeln",
        "tools_to_build": ["market_analyzer"],
    },
}

# Level-Hierarchie
LEVEL_ORDER = {"novice": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}


class CompetenceMatrix:
    """Verwaltet Lyras Ziel-Skills und schlaegt Training vor."""

    def __init__(self, skills_data: dict):
        """
        Args:
            skills_data: Aktueller Skill-Stand aus SkillTracker
        """
        self.skills = skills_data

    def get_gaps(self) -> list[dict]:
        """Findet Skills wo Lyra unter dem Ziel-Level liegt."""
        gaps = []
        for skill_id, target in TARGET_SKILLS.items():
            current_data = self.skills.get(skill_id, {})
            current_level = current_data.get("level", "novice")
            target_level = target["target_level"]

            current_rank = LEVEL_ORDER.get(current_level, 0)
            target_rank = LEVEL_ORDER.get(target_level, 0)

            if current_rank < target_rank:
                gaps.append({
                    "skill": skill_id,
                    "name": target["name"],
                    "current": current_level,
                    "target": target_level,
                    "gap": target_rank - current_rank,
                    "training": target["training"],
                    "tools_to_build": target["tools_to_build"],
                })

        # Nach groesstem Gap sortieren
        gaps.sort(key=lambda x: x["gap"], reverse=True)
        return gaps

    def get_training_suggestion(self) -> str:
        """Konkrete Trainings-Empfehlung fuer den naechsten Zyklus."""
        gaps = self.get_gaps()
        if not gaps:
            return "Alle Ziel-Skills erreicht!"

        # Groesste Luecke zuerst
        top_gap = gaps[0]
        suggestion = (
            f"TRAINING EMPFOHLEN: {top_gap['name']} "
            f"({top_gap['current']} → {top_gap['target']})\n"
            f"  Wie: {top_gap['training']}"
        )

        if top_gap["tools_to_build"]:
            tools = ", ".join(top_gap["tools_to_build"])
            suggestion += f"\n  Tools bauen: {tools}"

        return suggestion

    def get_overview(self) -> str:
        """Kompakte Uebersicht — nur Gaps und erreichte Skills, kein Volllisting."""
        gaps = []
        reached = []
        for skill_id, target in TARGET_SKILLS.items():
            current_data = self.skills.get(skill_id, {})
            current_level = current_data.get("level", "novice")
            target_level = target["target_level"]

            current_rank = LEVEL_ORDER.get(current_level, 0)
            target_rank = LEVEL_ORDER.get(target_level, 0)

            if current_rank >= target_rank:
                reached.append(skill_id)
            else:
                gaps.append(f"{skill_id}({current_level}→{target_level})")

        parts = []
        if gaps:
            parts.append(f"GAPS: {', '.join(gaps)}")
        if reached:
            parts.append(f"OK: {', '.join(reached)}")
        return " | ".join(parts) if parts else "Alle Skills erreicht"


# === SELBST-AUDIT ===

AUDIT_MODEL = MODELS[TASK_MODEL_MAP["audit_primary"]]["model_id"]

# Dateien die beim Audit geprueft werden
AUDIT_FILES = [
    "engine/consciousness.py",
    "engine/intelligence.py",
    "engine/actions.py",
    "engine/toolchain.py",
    "engine/extensions.py",
    "engine/web_access.py",
    "engine/dream.py",
    "engine/competence.py",
    "engine/self_modify.py",
    "engine/code_review.py",
    "engine/security.py",
    "engine/config.py",
]


class SelfAudit:
    """
    Dual-Audit — Opus UND Gemini pruefen BEIDE die gesamte Codebase.

    Ablauf:
    1. Code sammeln
    2. Opus Audit (parallel) — tiefe Analyse
    3. Gemini Audit (parallel) — unabhaengige zweite Meinung
    4. MERGE: Findings von beiden zusammenfuehren
       - Beide finden es → hohe Konfidenz
       - Nur einer → niedrigere Konfidenz
    5. Lyra sieht die gemergten Empfehlungen
    """

    AUDIT_PROMPT = """Du bist ein Code-Auditor fuer eine autonome KI-Engine.
Analysiere den Code auf:

1. BUGS: Echte Fehler die Crashes verursachen koennten
2. LUECKEN: Fehlende Error-Handler, unbehandelte Edge-Cases
3. INEFFIZIENZ: Code der vereinfacht werden koennte
4. ARCHITEKTUR: Strukturelle Probleme
5. SICHERHEIT: Potenzielle Sicherheitsprobleme

Antworte als JSON:
{
  "findings": [
    {
      "severity": "critical|high|medium|low",
      "category": "bug|gap|inefficiency|architecture|security",
      "file": "engine/xxx.py",
      "description": "Was das Problem ist",
      "suggestion": "Wie man es loest"
    }
  ],
  "overall_quality": 1-10,
  "summary": "Kurze Gesamteinschaetzung"
}

Sei STRENG aber FAIR. Finde echte Probleme, keine Stilfragen."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.audit_log_path = root_path / "data" / "consciousness" / "audit_log.json"
        self.opus_client = Anthropic()
        audit_key = TASK_MODEL_MAP["audit_secondary"]
        audit_config = MODELS[audit_key]
        self.secondary_provider = audit_config["provider"]
        self.secondary_model = audit_config["model_id"]
        if self.secondary_provider == "nvidia":
            self.secondary_key = os.getenv("NVIDIA_API_KEY", "").strip()
            self.secondary_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        elif self.secondary_provider == "google":
            self.secondary_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
            self.secondary_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.secondary_model}:generateContent"
        else:
            self.secondary_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            self.secondary_url = "https://api.deepseek.com/chat/completions"

    def should_audit(self, sequences_since_last: int) -> bool:
        return sequences_since_last >= 15

    def run_audit(self) -> str:
        """
        Dual-Audit: Opus + Gemini pruefen parallel, Ergebnisse werden gemerged.
        """
        code_context = self._gather_code()

        # Parallel ausfuehren
        opus_result = [None]
        gemini_result = [None]

        def run_opus():
            opus_result[0] = self._audit_opus(code_context)

        def run_gemini():
            gemini_result[0] = self._audit_gemini(code_context)

        t_opus = threading.Thread(target=run_opus)
        t_gemini = threading.Thread(target=run_gemini)
        t_opus.start()
        t_gemini.start()
        t_opus.join(timeout=45)
        t_gemini.join(timeout=45)

        opus = opus_result[0] or {"findings": [], "overall_quality": 0, "summary": "Opus Timeout"}
        gemini = gemini_result[0] or {"findings": [], "overall_quality": 0, "summary": "Gemini Timeout"}

        # MERGE: Findings zusammenfuehren
        merged = self._merge_findings(opus, gemini)

        # Loggen
        self._log_audit(merged)

        # Report
        findings = merged.get("findings", [])
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")
        confirmed = sum(1 for f in findings if f.get("confirmed_by_both"))

        report = (
            f"DUAL-AUDIT ABGESCHLOSSEN\n"
            f"  Opus: {opus.get('overall_quality', '?')}/10 | "
            f"Gemini: {gemini.get('overall_quality', '?')}/10\n"
            f"  Findings: {len(findings)} ({critical} kritisch, {high} hoch, "
            f"{confirmed} von beiden bestaetigt)\n"
            f"  Opus: {opus.get('summary', '')[:100]}\n"
            f"  Gemini: {gemini.get('summary', '')[:100]}\n"
        )

        for f in findings[:5]:
            confirmed_tag = " [BEIDE]" if f.get("confirmed_by_both") else ""
            report += (
                f"\n  [{f.get('severity', '?').upper()}]{confirmed_tag} {f.get('file', '?')}\n"
                f"    {f.get('description', '')[:150]}\n"
                f"    Fix: {f.get('suggestion', '')[:150]}"
            )

        return report

    def _audit_opus(self, code_context: str) -> dict:
        """Opus-Audit."""
        try:
            response = self.opus_client.messages.create(
                model=AUDIT_MODEL,
                max_tokens=4000,
                system=self.AUDIT_PROMPT,
                messages=[{"role": "user", "content": code_context}],
            )
            return self._parse_json(response.content[0].text)
        except Exception as e:
            return {"findings": [], "overall_quality": 0, "summary": f"Opus-Fehler: {e}"}

    def _audit_gemini(self, code_context: str) -> dict:
        """Zweites Modell Audit (Gemma/Kimi/DeepSeek via TASK_MODEL_MAP)."""
        if not self.secondary_key:
            return {"findings": [], "overall_quality": 0, "summary": "Secondary Auditor nicht konfiguriert"}

        try:
            prompt = f"{self.AUDIT_PROMPT}\n\n{code_context}"
            with httpx.Client(timeout=60.0) as client:
                if self.secondary_provider == "google":
                    response = client.post(
                        self.secondary_url,
                        params={"key": self.secondary_key},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": 4000}},
                    )
                else:
                    response = client.post(
                        self.secondary_url,
                        headers={"Authorization": f"Bearer {self.secondary_key}",
                                 "Content-Type": "application/json"},
                        json={"model": self.secondary_model,
                              "messages": [{"role": "user", "content": prompt}],
                              "max_tokens": 4000},
                    )
            if response.status_code != 200:
                return {"findings": [], "overall_quality": 0, "summary": f"Audit HTTP {response.status_code}"}

            if self.secondary_provider == "google":
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            else:
                text = response.json()["choices"][0]["message"]["content"]
            return self._parse_json(text)
        except Exception as e:
            return {"findings": [], "overall_quality": 0, "summary": f"Gemini-Fehler: {e}"}

    def _parse_json(self, text: str) -> dict:
        """Robust JSON-Parsing."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Code-Block entfernen
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
        return {"findings": [], "overall_quality": 0, "summary": "Parse-Fehler"}

    def _merge_findings(self, opus: dict, gemini: dict) -> dict:
        """Merged Findings von Opus und Gemini."""
        opus_findings = opus.get("findings", [])
        gemini_findings = gemini.get("findings", [])

        merged = []
        used_gemini = set()

        for of in opus_findings:
            of["source"] = "opus"
            of["confirmed_by_both"] = False

            # Suche passendes Gemini-Finding (gleiche Datei + aehnliches Problem)
            for i, gf in enumerate(gemini_findings):
                if i in used_gemini:
                    continue
                if (of.get("file") == gf.get("file") and
                    of.get("category") == gf.get("category")):
                    # Beide haben das gleiche Problem gefunden
                    of["confirmed_by_both"] = True
                    of["gemini_note"] = gf.get("description", "")[:100]
                    # Severity: Nimm das hoehere
                    sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                    if sev_order.get(gf.get("severity"), 0) > sev_order.get(of.get("severity"), 0):
                        of["severity"] = gf["severity"]
                    used_gemini.add(i)
                    break

            merged.append(of)

        # Gemini-only Findings hinzufuegen
        for i, gf in enumerate(gemini_findings):
            if i not in used_gemini:
                gf["source"] = "gemini"
                gf["confirmed_by_both"] = False
                merged.append(gf)

        # Nach Severity sortieren, confirmed_by_both zuerst
        sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        merged.sort(key=lambda x: (
            x.get("confirmed_by_both", False),
            sev_order.get(x.get("severity"), 0),
        ), reverse=True)

        # Durchschnitts-Qualitaet
        opus_q = opus.get("overall_quality", 0)
        gemini_q = gemini.get("overall_quality", 0)
        avg_quality = (opus_q + gemini_q) / 2 if gemini_q else opus_q

        return {
            "findings": merged,
            "overall_quality": round(avg_quality, 1),
            "summary": f"Opus ({opus_q}/10): {opus.get('summary', '')} | Gemini ({gemini_q}/10): {gemini.get('summary', '')}",
            "opus_quality": opus_q,
            "gemini_quality": gemini_q,
        }

    def _gather_code(self) -> str:
        """Sammelt alle zu pruefenden Code-Dateien."""
        parts = ["=== DUAL CODE-AUDIT ===\n"]
        for rel_path in AUDIT_FILES:
            filepath = self.root_path / rel_path
            if filepath.exists():
                try:
                    code = filepath.read_text(encoding="utf-8")
                    if len(code) > 3000:
                        code = code[:1500] + "\n\n... [GEKUERZT] ...\n\n" + code[-1500:]
                    parts.append(f"\n--- {rel_path} ---\n{code}")
                except Exception:
                    parts.append(f"\n--- {rel_path} --- (Lesefehler)")
        return "\n".join(parts)

    def _log_audit(self, result: dict):
        """Speichert Audit-Ergebnisse."""
        log = safe_json_read(self.audit_log_path, default=[])
        # Volle Findings speichern (nicht nur Counts) — fuer Goals-Pipeline
        findings = result.get("findings", [])
        log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "quality": result.get("overall_quality"),
            "opus_quality": result.get("opus_quality"),
            "gemini_quality": result.get("gemini_quality"),
            "findings_count": len(findings),
            "confirmed_by_both": sum(1 for f in findings if f.get("confirmed_by_both")),
            "critical": sum(1 for f in findings if f.get("severity") == "critical"),
            "summary": result.get("summary", "")[:300],
            "findings": [
                {"severity": f.get("severity"), "file": f.get("file"),
                 "description": f.get("description", "")[:150],
                 "suggestion": f.get("suggestion", "")[:150],
                 "confirmed_by_both": f.get("confirmed_by_both", False)}
                for f in findings[:8]
            ],
        })
        log = log[-20:]
        safe_json_write(self.audit_log_path, log)

    def create_goals_from_findings(self, findings: list, goal_stack) -> str:
        """
        Konvertiert Audit-Findings automatisch in Goals.

        Nur critical und high Findings werden zu Goals.
        Confirmed-by-both Findings bekommen hoechste Prioritaet.
        """
        goals_created = 0

        # Nur critical/high, confirmed_by_both zuerst
        actionable = [
            f for f in findings
            if f.get("severity") in ("critical", "high")
        ]
        actionable.sort(key=lambda x: (
            x.get("confirmed_by_both", False),
            x.get("severity") == "critical",
        ), reverse=True)

        if not actionable:
            return "Keine kritischen Findings — keine neuen Goals."

        # Ein Sammel-Goal mit Sub-Goals fuer alle Findings
        sub_goals = []
        for f in actionable[:5]:  # Max 5 Findings als Sub-Goals
            confirmed = " [BEIDE]" if f.get("confirmed_by_both") else ""
            sub_goals.append(
                f"[{f.get('severity', '?').upper()}]{confirmed} {f.get('file', '?')}: "
                f"{f.get('suggestion', f.get('description', ''))[:100]}"
            )

        goal_stack.create_goal(
            title="Selbst-Optimierung: Audit-Findings beheben",
            description=(
                f"Der Dual-Audit hat {len(actionable)} kritische/hohe Findings gefunden. "
                f"Diese muessen behoben werden um die Code-Qualitaet zu verbessern."
            ),
            sub_goals=sub_goals,
        )
        goals_created = 1

        return f"Goal erstellt: {len(sub_goals)} Findings als Sub-Goals"

    def get_last_audit(self) -> str:
        """Zusammenfassung des letzten Audits."""
        if not self.audit_log_path.exists():
            return "Noch kein Audit durchgefuehrt."
        try:
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                log = json.load(f)
            if not log:
                return "Noch kein Audit durchgefuehrt."
            last = log[-1]
            return (
                f"Letztes Audit: {last.get('quality', '?')}/10 "
                f"(Opus: {last.get('opus_quality', '?')}, Gemini: {last.get('gemini_quality', '?')}), "
                f"{last.get('findings_count', 0)} Findings, "
                f"{last.get('confirmed_by_both', 0)} von beiden bestaetigt"
            )
        except Exception:
            return "Audit-Log nicht lesbar."
