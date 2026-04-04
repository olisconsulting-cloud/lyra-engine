"""
Multi-LLM Router — Waehlt das optimale Modell je nach Aufgabe.

Aufstellung:
- Kimi K2.5 (NVIDIA): Haupt-Arbeit (80%) — Tool-Use, Code, Telegram ($0)
- Claude Sonnet 4.6: Code-Review + letzter Fallback — nativer Tool-Use
- Claude Opus 4.6: Audit, Result-Validation — Tiefenanalyse
- GPT-4.1-mini (OpenAI): Dream, Goal-Planning, Fallback-Stufe 2
- DeepSeek V3.2: Fallback-Stufe 1 (~35x guenstiger als Sonnet)

Fallback-Kette: NVIDIA → DeepSeek → GPT-4.1-mini → Sonnet 4.6

TASK_MODEL_MAP ist die EINZIGE Stelle fuer Modell-Zuordnung.
Alle Module importieren von hier — keine hardcodierten Modell-IDs.

Kosten: ~$5-8/Tag statt $50-100 mit Opus-only
"""

import copy
import json
import logging
import os
import re
import threading
import time
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
        "max_output_tokens": 16384,
        "use_for": "Haupt-Arbeit, Tool-Use, Coding, Telegram, Code-Review",
    },
    "claude_opus": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "input_cost": 5.00,
        "output_cost": 25.00,
        "max_output_tokens": 16384,
        "use_for": "Kritische Selbstverbesserung, Audit",
    },
    "claude_sonnet": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "max_output_tokens": 16384,
        "use_for": "Code-Review — praezises Diff-Verstaendnis, nativer Tool-Use",
    },
    "deepseek_v3": {
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "input_cost": 0.28,
        "output_cost": 0.42,
        "max_output_tokens": 8192,
        "use_for": "Tool-Foundry, Fallback",
    },
    "gemini_flash": {
        "provider": "google",
        "model_id": "gemini-2.5-flash",
        "input_cost": 0.10,
        "output_cost": 0.40,
        "max_output_tokens": 65536,
        "use_for": "Nicht in Fallback-Kette — nur fuer explizite Gemini-Tasks",
    },
    "gpt4_1_mini": {
        "provider": "openai",
        "model_id": "gpt-4.1-mini",
        "input_cost": 0.40,
        "output_cost": 1.60,
        "max_output_tokens": 16384,
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
    "fallback": "deepseek_v3",             # DeepSeek V3 — Fallback Stufe 1 (Kette: DeepSeek → GPT-4.1-mini → Sonnet)
}


# Fallback-Kette: Wenn Primary ausfaellt, diese Reihenfolge versuchen
FALLBACK_CHAIN = ["deepseek_v3", "gpt4_1_mini", "claude_sonnet"]


class ProviderHealth:
    """
    State-Machine pro Provider: healthy → cooldown → dead.

    Zeitbasiert statt sequenzbasiert — unabhaengig von Phi-Laufzeit.
    Exponentieller Backoff: 30s → 60s → 120s → 240s → 480s (max).
    """

    # Zustaende
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    DEAD = "dead"

    # Konfiguration
    BASE_COOLDOWN = 30.0        # 30s erster Cooldown
    MAX_COOLDOWN = 480.0        # 8 Minuten Maximum
    DEAD_THRESHOLD = 5          # Nach 5 konsekutiven Failures → dead
    PROBE_AFTER_COOLDOWN = True # Nach Cooldown erst kleinen Request testen

    def __init__(self, provider: str):
        self.provider = provider
        self.state = self.HEALTHY
        self.consecutive_failures = 0
        self.cooldown_until = 0.0  # time.monotonic() Timestamp
        self.last_error_type = ""  # "timeout", "rate_limit", "auth", "server"
        self.total_failures = 0
        self.total_successes = 0

    def record_success(self):
        """Provider hat erfolgreich geantwortet."""
        self.consecutive_failures = 0
        self.state = self.HEALTHY
        self.cooldown_until = 0.0
        self.last_error_type = ""
        self.total_successes += 1

    def record_failure(self, status_code: int = 0, error_type: str = "unknown"):
        """Provider hat versagt — State + Cooldown aktualisieren."""
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_error_type = error_type

        # Auth-Fehler → sofort dead (Retry sinnlos)
        if status_code == 401 or status_code == 403:
            self.state = self.DEAD
            logger.warning("Provider %s: Auth-Fehler %d → DEAD", self.provider, status_code)
            return

        # Genug Failures → dead
        if self.consecutive_failures >= self.DEAD_THRESHOLD:
            self.state = self.DEAD
            logger.warning(
                "Provider %s: %d konsekutive Failures → DEAD",
                self.provider, self.consecutive_failures,
            )
            return

        # Exponentieller Backoff: 30s, 60s, 120s, 240s, 480s
        backoff = min(
            self.BASE_COOLDOWN * (2 ** (self.consecutive_failures - 1)),
            self.MAX_COOLDOWN,
        )
        # Rate-Limit → laengerer Cooldown (API braucht mehr Zeit)
        if status_code == 429:
            backoff *= 2

        self.cooldown_until = time.monotonic() + backoff
        self.state = self.COOLDOWN
        logger.info(
            "Provider %s: Failure %d → COOLDOWN %.0fs (Fehler: %s)",
            self.provider, self.consecutive_failures, backoff, error_type,
        )

    def is_available(self) -> bool:
        """Ist der Provider jetzt verfuegbar?"""
        if self.state == self.HEALTHY:
            return True
        if self.state == self.DEAD:
            return False
        # COOLDOWN: Abgelaufen?
        if self.state == self.COOLDOWN and time.monotonic() >= self.cooldown_until:
            # Cooldown abgelaufen → probieren (bleibt COOLDOWN bis Erfolg)
            return True
        return False

    def success_rate(self) -> float:
        """Erfolgsquote (0.0-1.0). Nuetzlich fuer Monitoring."""
        total = self.total_successes + self.total_failures
        if total == 0:
            return 1.0
        return self.total_successes / total

    def to_dict(self) -> dict:
        """Fuer State-Persistence."""
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "last_error_type": self.last_error_type,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
        }

    @classmethod
    def from_dict(cls, provider: str, data: dict) -> "ProviderHealth":
        """Aus gespeichertem State wiederherstellen."""
        health = cls(provider)
        health.consecutive_failures = data.get("consecutive_failures", 0)
        health.last_error_type = data.get("last_error_type", "")
        health.total_failures = data.get("total_failures", 0)
        health.total_successes = data.get("total_successes", 0)
        # State: Dead bleibt dead, Cooldown wird zu healthy (Neustart = frischer Versuch)
        saved_state = data.get("state", cls.HEALTHY)
        health.state = cls.DEAD if saved_state == cls.DEAD else cls.HEALTHY
        return health


def _classify_error(error: Exception, status_code: int = 0) -> str:
    """Klassifiziert Fehler fuer differenziertes Cooldown-Verhalten."""
    if status_code == 429:
        return "rate_limit"
    if status_code in (401, 403):
        return "auth"
    if status_code >= 500:
        return "server"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    if isinstance(error, (httpx.ConnectError, ConnectionError, OSError)):
        return "connection"
    return "unknown"


class LLMRouter:
    """
    Routet Anfragen an das optimale Modell mit Provider-Health-Tracking.

    Anthropic: Tool-Use ueber native API (Sonnet, Opus)
    OpenAI: REST API (GPT-4.1-mini)
    NVIDIA: OpenAI-kompatible REST API (Kimi K2.5)
    Google: Tool-Use ueber REST API (Gemini Flash)
    DeepSeek: OpenAI-kompatible REST API (Fallback)

    Provider-Health: Automatisches Cooldown + Fallback bei Ausfaellen.
    """

    def __init__(self):
        self.anthropic = Anthropic()
        self.google_key = os.getenv("GOOGLE_AI_API_KEY", "").strip()
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        # Getrennte Pools: Primary-Timeout blockiert nicht den Fallback-Pool
        _timeout = httpx.Timeout(
            connect=10.0,   # Verbindung aufbauen: 10s reicht
            read=45.0,      # Antwort abwarten: 45s (war 90s — zu lang fuer tote Provider)
            write=15.0,     # Request senden: 15s
            pool=10.0,      # Connection-Pool: 10s
        )
        self.http_primary = httpx.Client(timeout=_timeout)   # NVIDIA/Kimi
        self.http_fallback = httpx.Client(timeout=_timeout)  # DeepSeek, OpenAI (Sonnet nutzt eigenen Anthropic-Client)
        self._http_owned = True  # Marker fuer Cleanup

        # Provider-Health-Tracking
        providers = {m["provider"] for m in MODELS.values()}
        self.provider_health: dict[str, ProviderHealth] = {
            p: ProviderHealth(p) for p in providers
        }

        # Kosten-Tracking (thread-safe)
        self._cost_lock = threading.Lock()
        self.session_costs = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        self.model_usage = {}  # {model: {calls, input_tokens, output_tokens, cost}}

    def close(self):
        """Schliesst beide HTTP-Clients sauber."""
        if self._http_owned:
            for client in (self.http_primary, self.http_fallback):
                try:
                    if client:
                        client.close()
                except Exception:
                    pass
            self._http_owned = False

    def __del__(self):
        self.close()

    def get_model_for_task(self, task: str) -> str:
        """Gibt den Modell-Key fuer eine Aufgabe zurueck."""
        return TASK_MODEL_MAP.get(task, "kimi_k25")

    def _clamp_max_tokens(self, model_key: str, max_tokens: int) -> int:
        """Clampt max_tokens gegen das API-Limit des Modells."""
        limit = MODELS.get(model_key, {}).get("max_output_tokens", 16384)
        if max_tokens > limit:
            logger.debug("max_tokens %d → %d (Limit %s)", max_tokens, limit, model_key)
        return min(max_tokens, limit)

    # === Zentraler Call mit Fallback + Health-Tracking ===

    def call(
        self, task: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """
        Zentraler Entry-Point: Task → Modell → Provider → Call mit Health-Tracking.

        1. Waehlt Modell fuer Task via TASK_MODEL_MAP
        2. Prueft Provider-Health (Cooldown/Dead → Fallback)
        3. Ruft Provider auf, trackt Erfolg/Fehler
        4. Bei Failure: Fallback-Kette mit Health-Tracking

        Returns:
            {"content": list, "stop_reason": str, "usage": dict, "model": str}
        """
        model_key = self.get_model_for_task(task)
        provider = MODELS.get(model_key, {}).get("provider", "")
        health = self.provider_health.get(provider)

        # Provider im Cooldown oder Dead? → Direkt Fallback
        if health and not health.is_available():
            logger.info(
                "Provider %s nicht verfuegbar (%s) → Fallback-Kette",
                provider, health.state,
            )
            return self._fallback_call(
                system, messages, tools, max_tokens,
                skip_provider=provider, original_task=task,
            )

        # Primaerer Call
        try:
            result = self._dispatch_call(model_key, system, messages, tools, max_tokens)
            if health:
                health.record_success()
            return result
        except Exception as primary_error:
            # Fehler klassifizieren + Health aktualisieren
            status_code = self._extract_status_code(primary_error)
            error_type = _classify_error(primary_error, status_code)
            if health:
                health.record_failure(status_code, error_type)

            logger.warning(
                "Provider %s fehlgeschlagen (%s, HTTP %d) → Fallback-Kette",
                provider, error_type, status_code,
            )

            # Fallback-Kette versuchen
            try:
                return self._fallback_call(
                    system, messages, tools, max_tokens,
                    skip_provider=provider, original_task=task,
                )
            except Exception:
                raise primary_error  # Originalen Fehler werfen wenn alles scheitert

    def _dispatch_call(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list], max_tokens: int,
    ) -> dict:
        """Ruft den richtigen Provider fuer ein Modell auf (ohne Fallback)."""
        provider = MODELS.get(model_key, {}).get("provider", "")
        if provider == "anthropic":
            return self.call_anthropic(model_key, system, messages, tools, max_tokens)
        elif provider == "nvidia":
            return self.call_nvidia(model_key, system, messages, tools, max_tokens)
        elif provider == "deepseek":
            return self.call_deepseek(model_key, system, messages, tools, max_tokens)
        elif provider == "openai":
            return self.call_openai(model_key, system, messages, tools, max_tokens)
        elif provider == "google":
            return self.call_gemini(model_key, system, messages, tools, max_tokens)
        else:
            raise ValueError(f"Unbekannter Provider: {provider}")

    def _fallback_call(
        self, system: str, messages: list, tools: Optional[list],
        max_tokens: int, skip_provider: str, original_task: str,
    ) -> dict:
        """Versucht Fallback-Kette mit Health-Tracking pro Provider."""
        for fb_key in FALLBACK_CHAIN:
            fb_provider = MODELS.get(fb_key, {}).get("provider", "")
            if fb_provider == skip_provider:
                continue

            fb_health = self.provider_health.get(fb_provider)
            if fb_health and not fb_health.is_available():
                logger.debug("Fallback %s uebersprungen (nicht verfuegbar)", fb_key)
                continue

            try:
                result = self._dispatch_call(fb_key, system, messages, tools, max_tokens)
                if fb_health:
                    fb_health.record_success()
                logger.info("Fallback %s erfolgreich (Task: %s)", fb_key, original_task)
                return result
            except Exception as fb_error:
                status_code = self._extract_status_code(fb_error)
                error_type = _classify_error(fb_error, status_code)
                if fb_health:
                    fb_health.record_failure(status_code, error_type)
                logger.warning("Fallback %s fehlgeschlagen: %s", fb_key, fb_error)
                continue

        raise ValueError(f"Alle Provider fehlgeschlagen (Primary: {skip_provider})")

    @staticmethod
    def _extract_status_code(error: Exception) -> int:
        """Extrahiert HTTP-Status-Code aus Fehlermeldung (wenn vorhanden)."""
        msg = str(error)
        # Pattern: "API Fehler 429: ..." oder "Rate-Limit 429"
        match = re.search(r'\b([45]\d{2})\b', msg)
        return int(match.group(1)) if match else 0

    # === Provider-Health Persistence ===

    def get_health_state(self) -> dict:
        """Health-State fuer Persistence (consciousness.py speichert in state.json)."""
        return {p: h.to_dict() for p, h in self.provider_health.items()}

    def load_health_state(self, data: dict):
        """Health-State aus gespeichertem State laden."""
        for provider, health_data in data.items():
            if provider in self.provider_health:
                self.provider_health[provider] = ProviderHealth.from_dict(provider, health_data)

    def get_health_summary(self) -> str:
        """Kompakte Health-Uebersicht fuer Logging/Narrator."""
        parts = []
        for provider, health in sorted(self.provider_health.items()):
            icon = {"healthy": "+", "cooldown": "~", "dead": "X"}[health.state]
            rate = f"{health.success_rate():.0%}"
            parts.append(f"[{icon}] {provider}: {rate}")
        return " | ".join(parts)

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
        max_tokens = self._clamp_max_tokens(model_key, max_tokens)

        # System-Prompt als cacheable Content-Block (spart Tokens bei wiederholten Calls)
        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
        }
        if tools:
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
        max_tokens = self._clamp_max_tokens(model_key, max_tokens)

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

        # API Call mit Retry

        resp = None
        for attempt in range(2):
            try:
                resp = self.http_fallback.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
                    params={"key": self.google_key},
                    json=body,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("Gemini Timeout (Versuch %d/2): %s", attempt + 1, e)
                if attempt < 1:
                    time.sleep(2)
                    continue
                raise ValueError("Gemini API Timeout nach 2 Versuchen") from e
            break

        if resp is None:
            raise ValueError("Gemini API: Kein Response erhalten")
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
        max_tokens = self._clamp_max_tokens(model_key, max_tokens)

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


        resp = None
        for attempt in range(2):
            try:
                resp = self.http_fallback.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.deepseek_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("DeepSeek Timeout (Versuch %d/2): %s", attempt + 1, e)
                if attempt < 1:
                    time.sleep(2)
                    continue
                raise ValueError("DeepSeek API Timeout nach 2 Versuchen") from e
            break

        if resp is None:
            raise ValueError("DeepSeek API: Kein Response erhalten")
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
        max_tokens = self._clamp_max_tokens(model_key, max_tokens)
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

        # Ein Versuch reicht — Circuit Breaker uebernimmt bei Failure

        resp = None
        try:
            resp = self.http_primary.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.nvidia_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("NVIDIA Timeout: %s", e)
            raise ValueError("NVIDIA API Timeout") from e

        if resp.status_code == 429:
            logger.warning("NVIDIA Rate-Limit 429")
            # Ein Retry bei 429 (Rate-Limit ist oft kurzlebig)
            time.sleep(2)
            try:
                resp = self.http_primary.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.nvidia_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                raise ValueError("NVIDIA API Timeout nach 429-Retry") from e
            if resp.status_code == 429:
                raise ValueError("NVIDIA API Rate-Limit 429 nach Retry")
        if resp.status_code != 200:
            raise ValueError(f"NVIDIA API Fehler {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        return self._openai_to_anthropic_response(data, model_key)

    # === OpenAI (GPT-4.1 / GPT-4.1-mini) ===

    def call_openai(
        self, model_key: str, system: str, messages: list,
        tools: Optional[list] = None, max_tokens: int = 16000,
    ) -> dict:
        """Ruft OpenAI API auf — GPT-4.1-mini fuer Dream/Goal-Planning."""
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY nicht konfiguriert")

        model_id = MODELS[model_key]["model_id"]
        max_tokens = self._clamp_max_tokens(model_key, max_tokens)
        oai_messages = self._anthropic_to_openai_messages(system, messages)

        body = {
            "model": model_id,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }

        if tools:
            oai_tools = self._anthropic_to_openai_tools(tools)
            if oai_tools:
                body["tools"] = oai_tools

        resp = None
        for attempt in range(2):
            try:
                resp = self.http_fallback.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("OpenAI Timeout (Versuch %d/2): %s", attempt + 1, e)
                if attempt < 1:
                    time.sleep(2)
                    continue
                raise ValueError("OpenAI API Timeout nach 2 Versuchen") from e
            break

        if resp is None:
            raise ValueError("OpenAI API: Kein Response erhalten")
        if resp.status_code != 200:
            raise ValueError(f"OpenAI API Fehler {resp.status_code}: {resp.text[:200]}")

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
                decl["parameters"] = self._fix_gemini_schema(schema)
            declarations.append(decl)

        return [{"function_declarations": declarations}]

    def _fix_gemini_schema(self, schema: dict) -> dict:
        """Bereinigt JSON-Schema fuer Gemini: array-Properties brauchen explizites items-Feld."""
        schema = copy.deepcopy(schema)

        def fix_properties(props: dict):
            for key, prop in props.items():
                if prop.get("type") == "array" and "items" not in prop:
                    prop["items"] = {"type": "string"}
                # Rekursiv: nested Objects mit eigenen Properties
                if prop.get("type") == "object" and "properties" in prop:
                    fix_properties(prop["properties"])
                # items koennen auch Objects mit Properties sein
                if "items" in prop and isinstance(prop["items"], dict):
                    if prop["items"].get("type") == "object" and "properties" in prop["items"]:
                        fix_properties(prop["items"]["properties"])

        if "properties" in schema:
            fix_properties(schema["properties"])
        return schema

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
