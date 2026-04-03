"""
Handler fuer Web-Operationen: web_search, web_read, send_telegram.
"""

from .context import ToolContext


def handle_web_search(ctx: ToolContext, tool_input: dict) -> str:
    """Web-Suche mit Cache-Pruefung."""
    query = tool_input["query"]

    # Web-Cache pruefen bevor echte Suche
    cached = ctx.proactive_learner.web_cache.get(query)
    if cached:
        results = cached.get("results", [])
        formatted = "\n".join(
            f"  {i+1}. {r}" if isinstance(r, str) else
            f"  {i+1}. {r.get('title', '')}: {r.get('snippet', '')}"
            for i, r in enumerate(results[:5])
        )
        return f"[CACHE] Ergebnisse fuer '{query[:50]}':\n{formatted}"

    result = ctx.web.search(query)

    # Ergebnis cachen fuer naechste Sequenz
    if result and "FEHLER" not in result:
        result_lines = [line.strip() for line in result.split("\n") if line.strip()][:5]
        ctx.proactive_learner.store_research_result(query, result_lines)

    return result


def handle_web_read(ctx: ToolContext, tool_input: dict) -> str:
    """Webseite lesen."""
    return ctx.web.read_page(tool_input["url"])


def handle_send_telegram(ctx: ToolContext, tool_input: dict) -> str:
    """Telegram-Nachricht senden."""
    msg = tool_input["message"]
    channel = "telegram" if ctx.communication.telegram_active else "outbox"
    ctx.communication.send_message(msg, channel=channel)
    return f"Nachricht gesendet ({channel}): {msg[:100]}..."
