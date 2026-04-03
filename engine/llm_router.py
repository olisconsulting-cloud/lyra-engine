"""
Multi-LLM Router — Waehlt das optimale Modell je nach Aufgabe.

Aufstellung:
- Kimi K2.5 (NVIDIA): Haupt-Arbeit (80%) — Tool-Use, Code, Telegram ($0)
- Claude Sonnet 4.6: Code-Review — praezises Diff-Verstaendnis, nativer Tool-Use
- Claude Opus 4.6: Audit, Result-Validation — Tiefenanalyse (hier lohnt sich Opus)
- GPT-4.1-mini (OpenAI): Dream, Goal-Planning — 89% guenstiger als Sonnet, JSON-Garantie
- DeepSeek V3.2: Fallback (~35x guenstiger als Claude Sonnet)

TASK_MODEL_MAP ist die EINZIGE Stelle fuer Modell-Zuordnung.
Alle Module importieren von hier — keine hardcodierten Modell-IDs.

Kosten: ~$5-8/Tag statt $50-100 mit Opus-only
"""

import json
import logging
import os
import re
import threading
from typing import Optional

logger = logging.getLogger(__name__)

import httpx
from anthropic import Anthropic


# === Modell-Konfiguration ===

MODELS = {
    "kimi_k25": {
        "provider": "nvidia",
        "model_id": "moonshotai/kimi-k2-instruct",
        "input_cost": 0.0,  # Kostenlos ueber NVIDIA API
        "output_cost": 0.0,
        "use_for": "Haupt-Arbeit, Tool-Use, Coding, Telegram, Code-Review",
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
        "use_for": "Schnelle Zusammenfassungen, Graceful-Finish, leichte Analyse",
    },
    "deepseek_v3": {
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "input_cost": 0.28,
        "output_cost": 0.42,
        "use_for": "Dream, Tool-Foundry, Fallback",
    },
    "gemini_flash": {
        "provider": "google",
        "model_id": "gemini-2.0-flash",
        "input_cost": 0.10,
        "output_cost": 0.40,
        "use_for": "Zweiter Fallback wenn DeepSeek versagt",
    },
    "gpt4_1_mini": {
        "provider": "openai",
        "model_id": "gpt-4.1-mini",
        "input_cost": 0.40,
        "output_cost": 1.60,
        "use_for": "Dream, Goal-Planning — guenstig mit JSON-Garantie",
    },
}

# Welches Modell fuer welche Aufgabe — EINZIGE Stelle fuer Modell-Zuordnung
TASK_MODEL_MAP = {
    "main_work": "kimi_k25",              # Kimi K2.5 — Hauptarbeit, Tool-Use, Coding ($0)
    "code_review": "claude_sonnet",        # Sonnet 4.6 — Code-Review (vorher Opus — 80% guenstiger, gleiche Qualitaet fuer Diffs)
    "audit_primary": "claude_opus",        # Opus 4.6 — Tiefenanalyse (hier lohnt sich Opus)
    "audit_secondary": "kimi_k25",         # Kimi — Gegenpruefung ($0)
    "telegram_reply": "kimi_k25",          # Kimi — Sofort-Antwort ($0)
    "dream": "gpt4_1_mini",                # GPT-4.1-mini — Memory-Konsolidierung (89% guenstiger als Sonnet, JSON-Garantie)
    "tool_generation": "kimi_k25",         # Kimi — Coding ist Kimis Staerke ($0)
    "goal_planning": "gpt4_1_mini",        # GPT-4.1-mini — Goal-Zerlegung (89% guenstiger als Sonnet, Structured Outputs)
    "result_validation": "claude_opus",    # Opus 4.6 — Ergebnis-Pruefung (kritisch, hier keine Abstriche)
    "graceful_finish": "kimi_k25",          # Kimi K2.5 — Sequenz-Zusammenfassungen bei Auto-Finish ($0, vorher Sonnet)
    "fallback": "deepseek_v3",             # DeepSeek V3 — Fallback wenn Kimi versagt
}


class LLMRouter:
    """
    Routet Anfragen an das optimale Modell.

    Anthropic: Tool-Use ueber native API
    Google: Tool-Use ueber REST API
    DeepSeek: OpenAI-kompatible REST API
    """

    def __init__(self):
        self.anthropic = Anthropic()
        self.google_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.http = httpx.Client(timeout=30.0)  # 30s statt 120s — Kimi antwortet in 3-10s
        self._http_owned = True  # Marker fuer Cleanup

        # Kosten-Tracking (thread-safe)
        self._cost_lock = threading.Lock()
        self.session_costs = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        self.model_usage = {}  # {model: {calls, input_tokens, output_tokens, cost}}

    def close(self):
        """Schliesst den HTTP-Client sauber."""
        if self._http_owned:
            try:
                if self.http:
                    self.http.close()
            except Exception:
                pass
            finally:
                self._http_owned = False

    def __del__(self):
        self.close()

    def get_model_for_task(self, task: str) -> str:
        """Gibt den Modell-Key fuer eine Aufgabe zurueck."""
        return TASK_MODEL_MAP.get(task, "kimi_k25")

    # === Anthropic (Claude) ===

    def call_anthropic(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """
        Ruft Claude auf mit Prompt-Caching fuer System + Tools.

        Returns:
            {"content": list, "stop_reason": str, "usage": dict, "model": str}
        """
        model_id = MODELS[model_key]["model_id"]

        # System-Prompt als cacheable Content-Block (spart Tokens bei wiederholten Calls)
        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tools:
            import copy
            cached_tools = copy.deepcopy(tools)
            cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["tools"] = cached_tools

        response = self.anthropic.messages.create(**kwargs)

        # Kosten tracken (mit Cache-Awareness)
        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self._track_cost(model_key, usage.input_tokens, usage.output_tokens)

        return {
            "content": response.content,
            "stop_reason": response.stop_reason,
            "usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
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

    # === DeepSeek (OpenAI-kompatibel) ===

    def call_deepseek(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 8192,
    ) -> dict:
        """
        Ruft DeepSeek V3.2 auf — OpenAI-kompatible API.

        Returns: Gleiches Format wie call_anthropic fuer Kompatibilitaet.
        """
        if not self.deepseek_key:
            raise ValueError("DEEPSEEK_API_KEY nicht konfiguriert")

        model_id = MODELS[model_key]["model_id"]

        # DeepSeek erlaubt max 8192 Tokens
        max_tokens = min(max_tokens, 8192)

        # Anthropic Messages → OpenAI Messages konvertieren
        oai_messages = self._anthropic_to_openai_messages(system, messages)

        body = {
            "model": model_id,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }

        # Tools konvertieren (Anthropic → OpenAI Format)
        if tools:
            oai_tools = self._anthropic_to_openai_tools(tools)
            if oai_tools:
                body["tools"] = oai_tools

        resp = self.http.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {self.deepseek_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )

        if resp.status_code != 200:
            raise ValueError(f"DeepSeek API Fehler {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        return self._openai_to_anthropic_response(data, model_key)

    # === NVIDIA (Kimi K2.5 — OpenAI-kompatibel) ===

    def call_nvidia(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """Ruft Kimi K2.5 ueber NVIDIA API auf — OpenAI-kompatibel."""
        if not self.nvidia_key:
            raise ValueError("NVIDIA_API_KEY nicht konfiguriert")

        model_id = MODELS[model_key]["model_id"]
        oai_messages = self._anthropic_to_openai_messages(system, messages)

        body = {
            "model": model_id,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "temperature": 0.6,  # Konsistente Tool-Calls, aber kreativ genug
            "top_p": 0.9,
        }

        if tools:
            oai_tools = self._anthropic_to_openai_tools(tools)
            if oai_tools:
                body["tools"] = oai_tools

        # Retry mit Backoff (429 Rate-Limit + Timeout)
        import time as _time
        last_error = None
        resp = None
        for attempt in range(3):
            try:
                resp = self.http.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.nvidia_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except httpx.TimeoutException as e:
                last_error = e
                logger.warning("NVIDIA Timeout (Versuch %d/3): %s", attempt + 1, e)
                if attempt < 2:
                    _time.sleep(2 ** attempt)
                    continue
                raise ValueError(f"NVIDIA API Timeout nach 3 Versuchen") from e

            if resp.status_code == 429:
                logger.warning("NVIDIA Rate-Limit 429 (Versuch %d/3)", attempt + 1)
                if attempt < 2:
                    _time.sleep(2 ** attempt)
                    continue
                # 3. Versuch auch 429 → break und unten als Fehler behandeln
            break

        if resp is None:
            raise ValueError("NVIDIA API: Kein Response erhalten")
        if resp.status_code != 200:
            raise ValueError(f"NVIDIA API Fehler {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        return self._openai_to_anthropic_response(data, model_key)

    def _anthropic_to_openai_messages(self, system: str, messages: list) -> list:
        """Konvertiert Anthropic Messages zu OpenAI Messages."""
        oai_msgs = []

        if system:
            oai_msgs.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                oai_msgs.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Einfache Text-Extraktion — Tool-Use wird separat behandelt
                text_parts = []
                tool_calls = []
                tool_results = []

                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            })
                        elif block.get("type") == "tool_result":
                            tool_results.append(block)
                    elif hasattr(block, "text"):
                        text_parts.append(block.text)
                    elif hasattr(block, "type") and block.type == "tool_use":
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input if isinstance(block.input, dict) else {}),
                            },
                        })

                if tool_calls:
                    msg_data = {"role": "assistant"}
                    if text_parts:
                        msg_data["content"] = "\n".join(text_parts)
                    msg_data["tool_calls"] = tool_calls
                    oai_msgs.append(msg_data)
                elif tool_results:
                    for tr in tool_results:
                        oai_msgs.append({
                            "role": "tool",
                            "tool_call_id": tr.get("tool_use_id", ""),
                            "content": str(tr.get("content", "")),
                        })
                elif text_parts:
                    oai_msgs.append({"role": role, "content": "\n".join(text_parts)})

        return oai_msgs

    def _anthropic_to_openai_tools(self, tools: list) -> list:
        """Konvertiert Anthropic Tool-Definitionen zu OpenAI Function-Format."""
        oai_tools = []
        for tool in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return oai_tools

    def _openai_to_anthropic_response(self, data: dict, model_key: str) -> dict:
        """Konvertiert OpenAI Response zu Anthropic-kompatiblem Format."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = []
        has_tool_use = False
        tool_counter = 0

        # Text-Content
        if message.get("content"):
            content.append(type("TextBlock", (), {
                "type": "text", "text": message["content"],
                "model_dump": lambda self=None, t=message["content"]: {"type": "text", "text": t},
            })())

        # Tool-Calls
        for tc in message.get("tool_calls", []):
            has_tool_use = True
            func = tc.get("function", {})
            tool_id = tc.get("id", f"toolu_deepseek_{tool_counter}")
            tool_counter += 1

            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                logger.warning(
                    "LLM-Router: Unvollstaendiges Tool-JSON fuer %s: %s",
                    func.get("name", "?"), func.get("arguments", "")[:200],
                )
                args = {"_parse_error": True}

            content.append(type("ToolUseBlock", (), {
                "type": "tool_use",
                "id": tool_id,
                "name": func.get("name", ""),
                "input": args,
                "model_dump": lambda self=None, tid=tool_id, n=func.get("name",""), inp=args: {
                    "type": "tool_use", "id": tid, "name": n, "input": inp
                },
            })())

        if not content:
            fallback_text = "Ich konnte keine Antwort generieren. Ich versuche es anders."
            content.append(type("TextBlock", (), {
                "type": "text", "text": fallback_text,
                "model_dump": lambda self=None, t=fallback_text: {"type": "text", "text": t},
            })())

        # Usage
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        self._track_cost(model_key, input_tokens, output_tokens)

        # finish_reason korrekt auswerten — length hat Vorrang (abgeschnittene Tool-Calls sind gefaehrlich)
        openai_finish = choice.get("finish_reason") or "stop"
        if openai_finish == "length":
            stop_reason = "length"
        elif has_tool_use:
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"

        return {
            "content": content,
            "stop_reason": stop_reason,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "model": MODELS[model_key]["model_id"],
        }

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

        # Gemini finish_reason — MAX_TOKENS hat Vorrang (abgeschnittene Tool-Calls sind gefaehrlich)
        gemini_finish = (candidates[0].get("finishReason") or "STOP").upper()
        if gemini_finish == "MAX_TOKENS":
            stop_reason = "length"
        elif has_tool_use:
            stop_reason = "tool_use"
        else:
            stop_reason = "end_turn"

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
