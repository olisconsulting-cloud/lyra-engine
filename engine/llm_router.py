"""
Multi-LLM Router — Waehlt das optimale Modell je nach Aufgabe.

Aufstellung:
- Gemini 3 Flash: Haupt-Arbeit (80%) — Tool-Use, Code, Projekte
- Claude Opus 4.6: Kritische Selbstverbesserung (Audit) — Batch API
- Gemini 2.5 Flash: Code-Review (guenstigster Check)
- Gemini 3 Flash: Audit-Gegenpruefung + Telegram-Antwort

Kosten: ~$4-9/Tag statt $50-100 mit Opus-only
"""

import json
import os
import re
import threading
from typing import Optional

import httpx
from anthropic import Anthropic


# === Modell-Konfiguration ===

MODELS = {
    "gemini_3_flash": {
        "provider": "google",
        "model_id": "gemini-2.5-flash",  # 2.5 Flash — stabil, Tool-Use funktioniert
        "input_cost": 0.15,
        "output_cost": 0.60,
        "use_for": "Haupt-Arbeit, Tool-Use, Coding, Telegram",
    },
    "gemini_25_flash": {
        "provider": "google",
        "model_id": "gemini-2.5-flash",
        "input_cost": 0.15,
        "output_cost": 0.60,
        "use_for": "Code-Review (guenstigster Check)",
    },
    "claude_opus": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "input_cost": 5.00,
        "output_cost": 25.00,
        "use_for": "Kritische Selbstverbesserung, Audit",
    },
    "claude_sonnet": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "use_for": "Fallback wenn Gemini nicht reicht",
    },
}

# Welches Modell fuer welche Aufgabe
TASK_MODEL_MAP = {
    "main_work": "gemini_3_flash",          # Agentic Loop, Tool-Use
    "code_review": "gemini_25_flash",        # Gemini als Reviewer
    "audit_primary": "claude_opus",          # Opus fuer Tiefenanalyse
    "audit_secondary": "gemini_3_flash",     # Gemini als Gegenpruefung
    "telegram_reply": "gemini_3_flash",      # Sofort-Antwort
    "dream": "gemini_3_flash",               # Memory-Konsolidierung
    "tool_generation": "gemini_3_flash",     # Tool-Foundry
    "fallback": "claude_sonnet",             # Wenn Gemini versagt
}


class LLMRouter:
    """
    Routet Anfragen an das optimale Modell.

    Anthropic: Tool-Use ueber native API
    Google: Tool-Use ueber REST API
    """

    def __init__(self):
        self.anthropic = Anthropic()
        self.google_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.http = httpx.Client(timeout=120.0)

        # Kosten-Tracking (thread-safe)
        self._cost_lock = threading.Lock()
        self.session_costs = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        self.model_usage = {}  # {model: {calls, input_tokens, output_tokens, cost}}

    def get_model_for_task(self, task: str) -> str:
        """Gibt den Modell-Key fuer eine Aufgabe zurueck."""
        return TASK_MODEL_MAP.get(task, "gemini_3_flash")

    # === Anthropic (Claude) ===

    def call_anthropic(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """
        Ruft Claude auf.

        Returns:
            {"content": list, "stop_reason": str, "usage": dict, "model": str}
        """
        model_id = MODELS[model_key]["model_id"]

        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self.anthropic.messages.create(**kwargs)

        # Kosten tracken
        self._track_cost(model_key, response.usage.input_tokens, response.usage.output_tokens)

        return {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
            "model": model_id,
        }

    # === Google (Gemini) ===

    def call_gemini(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """
        Ruft Gemini auf — konvertiert Anthropic-Format zu Google-Format.

        Returns: Gleiches Format wie call_anthropic fuer Kompatibilitaet.
        """
        if not self.google_key:
            raise ValueError("GOOGLE_AI_API_KEY nicht konfiguriert")

        model_id = MODELS[model_key]["model_id"]

        # Anthropic Messages → Gemini Contents konvertieren
        contents = self._anthropic_to_gemini_messages(messages)

        # Request bauen
        body = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        # System Instruction
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        # Tools konvertieren (Anthropic → Gemini Format)
        if tools:
            gemini_tools = self._anthropic_to_gemini_tools(tools)
            if gemini_tools:
                body["tools"] = gemini_tools

        # API Call
        resp = self.http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
            params={"key": self.google_key},
            json=body,
        )

        if resp.status_code != 200:
            raise ValueError(f"Gemini API Fehler {resp.status_code}: {resp.text[:200]}")

        data = resp.json()

        # Gemini Response → Anthropic-kompatibles Format konvertieren
        return self._gemini_to_anthropic_response(data, model_key)

    def _anthropic_to_gemini_messages(self, messages: list) -> list:
        """
        Konvertiert Anthropic Messages zu Gemini Contents.

        CRITICAL FIX:
        - tool_result braucht den TOOL-NAMEN (nicht die ID)
        - tool_result muss als eigene User-Message kommen
        - Wir tracken tool_use IDs → Namen fuer das Mapping
        """
        contents = []
        # Mapping: tool_use_id → tool_name (fuer Result-Zuordnung)
        id_to_name = {}

        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg["content"]

            if isinstance(content, str):
                contents.append({"role": role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                # Pruefen ob diese Message tool_results enthaelt
                has_tool_results = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                )

                if has_tool_results:
                    # Tool-Results als eigene User-Message mit functionResponse
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_id = block.get("tool_use_id", "")
                            # CRITICAL FIX: Tool-NAME statt ID verwenden
                            tool_name = id_to_name.get(tool_id, tool_id)
                            parts.append({
                                "functionResponse": {
                                    "name": tool_name,
                                    "response": {"content": str(block.get("content", ""))},
                                }
                            })
                    if parts:
                        contents.append({"role": "user", "parts": parts})
                else:
                    # Normale Message (Text + Tool-Calls)
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                if block.get("text", "").strip():
                                    parts.append({"text": block["text"]})
                            elif block.get("type") == "tool_use":
                                # ID → Name Mapping speichern
                                id_to_name[block.get("id", "")] = block.get("name", "")
                                parts.append({
                                    "functionCall": {
                                        "name": block["name"],
                                        "args": block.get("input", {}),
                                    }
                                })
                        elif hasattr(block, "text"):
                            if block.text.strip():
                                parts.append({"text": block.text})
                    if parts:
                        contents.append({"role": role, "parts": parts})

        return contents

    def _anthropic_to_gemini_tools(self, tools: list) -> list:
        """Konvertiert Anthropic Tool-Definitionen zu Gemini Function Declarations."""
        declarations = []
        for tool in tools:
            decl = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            schema = tool.get("input_schema", {})
            if schema.get("properties"):
                decl["parameters"] = schema
            declarations.append(decl)

        return [{"function_declarations": declarations}]

    def _gemini_to_anthropic_response(self, data: dict, model_key: str) -> dict:
        """Konvertiert Gemini Response zu Anthropic-kompatiblem Format."""
        candidates = data.get("candidates", [])
        if not candidates or not candidates[0].get("content", {}).get("parts"):
            # CRITICAL FIX #3: Leere Antwort → Fehler statt leere Sequenz
            # Erzeugt einen Text-Block der die Situation erklaert
            fallback_text = "Ich konnte keine Antwort generieren. Ich versuche es anders."
            return {
                "content": [type("TextBlock", (), {
                    "type": "text", "text": fallback_text,
                    "model_dump": lambda self=None, t=fallback_text: {"type": "text", "text": t},
                })()],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "model": model_key,
            }

        parts = candidates[0].get("content", {}).get("parts", [])

        # Content-Bloecke konvertieren
        content = []
        has_tool_use = False
        tool_counter = 0

        for part in parts:
            if part.get("thought"):
                continue  # Thinking-Parts ignorieren

            if "text" in part:
                content.append(type("TextBlock", (), {
                    "type": "text", "text": part["text"],
                    "model_dump": lambda self=None, t=part["text"]: {"type": "text", "text": t},
                })())
            elif "functionCall" in part:
                has_tool_use = True
                fc = part["functionCall"]
                tool_id = f"toolu_gemini_{tool_counter}"
                tool_counter += 1
                content.append(type("ToolUseBlock", (), {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": fc.get("name", ""),
                    "input": fc.get("args", {}),
                    "model_dump": lambda self=None, tid=tool_id, n=fc.get("name",""), inp=fc.get("args",{}): {
                        "type": "tool_use", "id": tid, "name": n, "input": inp
                    },
                })())

        # Usage aus Gemini extrahieren
        usage_meta = data.get("usageMetadata", {})
        input_tokens = usage_meta.get("promptTokenCount", 0)
        output_tokens = usage_meta.get("candidatesTokenCount", 0)

        self._track_cost(model_key, input_tokens, output_tokens)

        stop_reason = "tool_use" if has_tool_use else "end_turn"

        return {
            "content": content,
            "stop_reason": stop_reason,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "model": MODELS[model_key]["model_id"],
        }

    # === Kosten-Tracking ===

    def _track_cost(self, model_key: str, input_tokens: int, output_tokens: int):
        """Trackt Kosten pro Modell und gesamt (thread-safe)."""
        model = MODELS.get(model_key, {})
        cost = (input_tokens * model.get("input_cost", 0) +
                output_tokens * model.get("output_cost", 0)) / 1_000_000

        with self._cost_lock:
            self.session_costs["input_tokens"] += input_tokens
            self.session_costs["output_tokens"] += output_tokens
            self.session_costs["cost_usd"] += cost

            if model_key not in self.model_usage:
                self.model_usage[model_key] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}

            self.model_usage[model_key]["calls"] += 1
            self.model_usage[model_key]["input_tokens"] += input_tokens
            self.model_usage[model_key]["output_tokens"] += output_tokens
        self.model_usage[model_key]["cost"] += cost

    def get_cost_summary(self) -> str:
        """Session-Kosten-Uebersicht."""
        total = self.session_costs["cost_usd"]
        lines = [f"Session: ${total:.3f}"]
        for model_key, usage in sorted(self.model_usage.items(), key=lambda x: x[1]["cost"], reverse=True):
            lines.append(
                f"  {model_key}: {usage['calls']} Calls, ${usage['cost']:.3f}"
            )
        return "\n".join(lines)
