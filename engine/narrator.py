"""
Narrator — Phi's Terminal-Ausgabe als Bewusstseins-Stream.

Uebersetzt technische Events in menschenlesbare, narrative Ausgabe.
Kein LLM-Call, kein I/O ausser print(). Rein lokale String-Formatierung.
"""

import sys

# === ANSI-Farben (4 Farben: Normal, Erfolg, Warnung, Fehler) ===

# Windows-Terminal braucht ggf. ANSI-Aktivierung
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"

# Box-Drawing
LINE = "─"
DOTLINE = "┄"


class Narrator:
    """Narrative Terminal-Ausgabe fuer Phi — menschlich, kompakt, informativ."""

    def __init__(self, name: str = "Lyra"):
        self.name = name
        self._waiting = False  # Ob "Warte auf LLM..." aktiv ist

    # === Sequenz-Lifecycle ===

    def sequence_start(self, seq_num: int, focus: str, mode: str, budget: int):
        """Sequenz-Header mit Ziel und Kontext."""
        header = f" {LINE * 2} Sequenz {seq_num} {LINE * 27}"
        print(f"\n{header}")
        if focus:
            # Fokus bereinigen: "FOKUS: ..." entfernen, nur erste Zeile
            clean = focus.split("\n")[0].replace("FOKUS: ", "").strip()
            if clean:
                print(f"  Ziel: {clean[:200]}")
        print(f"  {budget} Steps {DIM}│{RESET} Modus: {mode}")

    def waiting(self):
        """Zeigt an dass Phi auf LLM-Antwort wartet."""
        self._waiting = True
        print(f"  {DIM}Denke nach...{RESET}", end="", flush=True)

    def waiting_done(self):
        """Schliesst die 'Denke nach...' Zeile ab."""
        if self._waiting:
            print()  # Zeilenumbruch
            self._waiting = False

    def thought(self, text: str):
        """Phi's Gedanken — am Satzende gekuerzt."""
        self.waiting_done()
        if not text or len(text) <= 5:
            return
        if len(text) <= 150:
            thought = text
        else:
            # Naechstes Satzende nach Zeichen 80 suchen
            cut = -1
            for end_char in ".!?":
                pos = text.find(end_char, 80)
                if pos != -1 and (cut == -1 or pos < cut):
                    cut = pos
            thought = text[:cut + 1] if cut != -1 else text[:150] + "…"
        print(f"  💭 {thought}")

    def goal_summary(self, summary: str):
        """Zeigt Goal-Uebersicht (alle 5 Sequenzen)."""
        if not summary or "Keine aktiven" in summary:
            return
        for line in summary.split("\n"):
            if line.strip():
                print(f"  {DIM}{line}{RESET}")

    # === Tool-Feedback ===

    def tool_success(self, tool_name: str, desc: str):
        """Erfolgreiche Aktion."""
        print(f"  {GREEN}✓{RESET} {desc}")

    def tool_error(self, tool_name: str, desc: str, error: str = "",
                   stuck_count: int = 0):
        """Fehlgeschlagene Aktion mit Kontext."""
        print(f"  {RED}✗{RESET} {desc}")
        if error:
            # Fehler einzeilig, kompakt
            error_clean = error.replace("\n", " ")[:120]
            print(f"    {DIM}{error_clean}{RESET}")
        if stuck_count >= 2:
            print(f"    {YELLOW}Stuck: {stuck_count}x am gleichen Tool{RESET}")

    # === Warnungen und Limits ===

    def token_warning(self, pct: int, action: str):
        """Token-Budget-Warnung."""
        if action == "graceful_finish":
            print(f"  {YELLOW}Token-Limit {pct}% — schliesse ab.{RESET}")
        elif action == "compress":
            print(f"  {YELLOW}Token-Limit {pct}% — komprimiere Kontext.{RESET}")
        elif action == "truncated":
            print(f"  {YELLOW}⚠ Output abgeschnitten (max_tokens erreicht){RESET}")

    def token_precount(self, estimated: int, action: str):
        """Token-Vorschaetzung mit Aktion."""
        if action == "compress":
            print(f"  {DIM}~{estimated:,} Tokens — komprimiere{RESET}")
        else:
            print(f"  {DIM}~{estimated:,} Tokens — Graceful Finish{RESET}")

    def api_retry(self, attempt: int, max_attempts: int, error: str):
        """API-Fehler mit Retry-Info."""
        print(f"  {YELLOW}API-Fehler (Versuch {attempt}/{max_attempts}): {str(error)[:80]}{RESET}")

    def api_failed(self, error: str):
        """API endgueltig fehlgeschlagen."""
        print(f"  {RED}API-Fehler nach allen Versuchen: {str(error)[:80]}{RESET}")

    def fallback(self, from_model: str, to_model: str):
        """LLM-Fallback anzeigen."""
        print(f"  {DIM}Fallback: {from_model} → {to_model}{RESET}")

    # === Sequenz-Ende ===

    def sequence_end(self, steps: int, duration_s: float, errors: int,
                     files: int, rating: int = 0):
        """Kompakte Sequenz-Zusammenfassung."""
        duration_min = duration_s / 60
        parts = [f"{steps} Schritte", f"{duration_min:.1f} Min"]
        if errors > 0:
            parts.append(f"{RED}{errors} Fehler{RESET}")
        if files > 0:
            parts.append(f"{files} Dateien")
        if rating:
            parts.append(f"Rating: {rating}/10")
        print(f"  {DIM}{' · '.join(parts)}{RESET}")

    def max_steps(self, budget: int, errors: int, files: int):
        """Max-Steps erreicht."""
        status = "gescheitert" if errors > 3 and files == 0 else "pausiert"
        print(f"\n  {YELLOW}Budget erschoepft ({budget} Steps) — {status}.{RESET}")
        print(f"  {DIM}{errors} Fehler, {files} Dateien{RESET}")

    def error_budget(self, step: int, errors: int):
        """Error-Budget erschoepft — zu viele Fehler pro Step."""
        rate = errors / (step + 1) * 100
        print(f"\n  {YELLOW}Error-Budget: {errors} Fehler in {step + 1} Steps ({rate:.0f}%) — schliesse ab.{RESET}")

    def output_checkpoint(self, step: int):
        """Actuator Output-Checkpoint — kein Output nach N Steps."""
        print(f"\n  {YELLOW}Output-Checkpoint: 0 Dateien nach {step + 1} Steps — schliesse ab.{RESET}")

    def enforcement(self, rule: str, step: int, limit: int,
                    files: int = 0, errors: int = 0):
        """Meta-Rule Enforcement — automatische Intervention."""
        detail = f"{files} Dateien, {errors} Fehler" if files or errors else ""
        if detail:
            print(f"\n  {YELLOW}⚡ Enforcement: Auto-Finish nach {step} LLM-Calls ({detail}){RESET}")
        else:
            print(f"\n  {YELLOW}⚡ Enforcement: Auto-Finish nach {step} LLM-Calls (Limit {limit}){RESET}")

    def emergency(self, msg: str):
        """Emergency-Finish bei API-Ausfall o.ae."""
        print(f"  {RED}⚠ {msg} — Emergency-Save{RESET}")

    def efficiency_alert(self, alert: str):
        """Effizienz-Warnung."""
        print(f"  {YELLOW}⚠ {alert}{RESET}")

    def silent_warning(self, msg: str):
        """Stille Fehler nach Sequenz."""
        print(f"  {DIM}⚠ {msg}{RESET}")

    # === Periodische Events ===

    def dream_start(self):
        """Dream-Konsolidierung beginnt."""
        print(f"\n  {DOTLINE * 2} Traum {DOTLINE * 29}")
        print(f"  {DIM}Konsolidiere Erinnerungen...{RESET}")

    def dream_end(self, result: str):
        """Dream-Ergebnis."""
        if result:
            for line in str(result).split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")
        print(f"  {DOTLINE * 38}")

    def audit_start(self):
        """Selbst-Audit beginnt."""
        print(f"\n  {LINE * 2} Selbst-Audit {LINE * 24}")
        print(f"  {DIM}Analysiere Code-Qualitaet...{RESET}")

    def audit_end(self, result: str):
        """Audit-Ergebnis."""
        if result:
            for line in str(result).split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")
        print(f"  {LINE * 38}")

    def diagnose(self, result: str):
        """Auto-Diagnose Ergebnis."""
        print(f"\n  {DIM}Auto-Diagnose: {str(result)[:100]}{RESET}")

    def benchmark(self, result: str):
        """Benchmark-Ergebnis."""
        print(f"\n  {LINE * 2} Benchmark {LINE * 27}")
        if result:
            for line in str(result).split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")
        print(f"  {LINE * 38}")

    def integration_check(self, report: str):
        """Integrations-Check Ergebnis."""
        if report:
            print(f"\n  {DIM}Integrations-Check:{RESET}")
            for line in str(report).split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")

    def dependency_check(self, report: str):
        """Dependency-Check Ergebnis (nur bei Problemen)."""
        if report:
            print(f"  {DIM}{report[:150]}{RESET}")

    # === Finish-Sequence Feedback ===

    def belief_update(self, removed: int, challenged: int):
        """Belief-Aenderungen melden."""
        if removed > 0:
            print(f"  {DIM}{removed} Ueberzeugung(en) verworfen — zu oft widerlegt{RESET}")
        elif challenged > 0:
            print(f"  {DIM}{challenged} Ueberzeugung(en) nahe am Schwellwert{RESET}")

    def plan_score(self, score: int, lesson: str):
        """Plan-Bewertung (nur bei schlechten Scores)."""
        if score <= 3:
            print(f"  {YELLOW}Plan-Score: {score}/10 — {lesson[:80]}{RESET}")

    def skill_extracted(self, skill_id: str):
        """Neuer Skill gelernt."""
        print(f"  {GREEN}Neuer Skill gelernt: {skill_id}{RESET}")

    # === Kommunikation ===

    def telegram_received(self):
        """Oliver hat geschrieben."""
        print(f"\n  {GREEN}>> Oliver hat geschrieben!{RESET}\n")

    def morning_briefing(self):
        """Morgen-Briefing gesendet."""
        print(f"  {DIM}Morgen-Briefing gesendet.{RESET}")

    # === Loop-Level ===

    def loop_start(self, name: str):
        """Hauptschleife startet."""
        print(f"\n  {name} laeuft. Telegram zum Schreiben, Ctrl+C zum Stoppen.")
        print(f"  {LINE * 40}\n")

    def shutdown(self, cost_summary: str):
        """Phi wird heruntergefahren."""
        print(f"\n\n  {self.name} wird pausiert...")
        if cost_summary:
            print(f"  {DIM}{cost_summary}{RESET}")
        print(f"  State gespeichert. Bis zum naechsten Mal.\n")

    # === Genehmigungen ===

    def approval_request(self, desc: str, details: dict = None) -> str:
        """Genehmigung erforderlich — gibt User-Input zurueck."""
        print(f"\n  {LINE * 40}")
        print(f"  {YELLOW}Genehmigung erforderlich{RESET}")
        print(f"  Aktion: {desc}")
        if details:
            for key, val in details.items():
                print(f"  {key}: {val}")
        try:
            answer = input(f"  Erlaube? (j/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
            print()  # Sauberer Zeilenumbruch nach Ctrl+C
        approved = answer in ("j", "ja", "y", "yes")
        print(f"  {'Genehmigt' if approved else 'Abgelehnt'}.")
        print(f"  {LINE * 40}\n")
        return answer

    # === Tool-Beschreibungen ===

    @staticmethod
    def describe_action(tool_name: str, tool_input: dict) -> str:
        """Uebersetzt Tool-Calls in menschenlesbare Beschreibungen."""
        descriptions = {
            "write_file": lambda i: f"Schreibe Datei: {i.get('path', '?')}",
            "read_file": lambda i: f"Lese: {i.get('path', '?')}",
            "list_directory": lambda i: f"Schaue in Ordner: {i.get('path', '/')}",
            "execute_python": lambda i: f"Fuehre Code aus ({len(i.get('code', ''))} Zeichen)",
            "web_search": lambda i: f"Suche im Web: {i.get('query', '?')}",
            "web_read": lambda i: f"Lese Webseite: {i.get('url', '?')[:60]}",
            "create_project": lambda i: f"Neues Projekt: {i.get('name', '?')}",
            "set_goal": lambda i: f"Neues Ziel: {i.get('title', '?')}",
            "complete_subgoal": lambda i: "Sub-Ziel erledigt!",
            "fail_subgoal": lambda i: f"Sub-Ziel gescheitert: {i.get('reason', '?')[:60]}",
            "send_telegram": lambda i: f"Nachricht an Oliver: {i.get('message', '?')[:60]}",
            "remember": lambda i: f"Erinnere mich: {i.get('query', '?')[:50]}",
            "read_own_code": lambda i: f"Lese eigenen Code: {i.get('path', '?')}",
            "modify_own_code": lambda i: f"Aendere eigenen Code: {i.get('path', '?')}",
            "pip_install": lambda i: f"Installiere Paket: {i.get('package', '?')}",
            "git_commit": lambda i: f"Git Commit: {i.get('message', '?')[:50]}",
            "git_status": lambda i: "Pruefe Git-Status",
            "create_tool": lambda i: f"Baue neues Tool: {i.get('name', '?')}",
            "use_tool": lambda i: f"Nutze Tool: {i.get('name', '?')}",
            "generate_tool": lambda i: f"Generiere Tool: {i.get('name', '?')}",
            "finish_sequence": lambda i: "Sequenz beendet",
        }
        desc_fn = descriptions.get(tool_name)
        if desc_fn:
            try:
                return desc_fn(tool_input)
            except Exception:
                pass
        return tool_name.replace("_", " ").title()
