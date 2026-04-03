"""
Message-Compression — Token-Window-Management fuer LLM-Konversationen.

Komprimiert alte Tool-Results adaptiv um Token zu sparen.
Extrahiert aus consciousness.py (God-Class Refactoring Phase 2).
"""

# Schreib-Tools: Ergebnis kann sicher auf Einzeiler komprimiert werden
SAFE_TO_COMPRESS = frozenset({
    "write_file", "send_telegram", "list_directory",
    "create_project", "create_tool", "pip_install",
    "git_commit", "set_goal", "complete_subgoal",
    "finish_sequence", "modify_own_code", "generate_tool",
})

# Lese-Tools: Behalten vollen Inhalt in den letzten N, werden
# danach auf Zusammenfassung gekuerzt (nicht geloescht)
READ_TOOLS = frozenset({
    "read_file", "read_own_code", "execute_python",
    "web_search", "web_read", "use_tool",
})


def find_tool_name_for_id(messages: list, user_idx: int, tool_use_id: str) -> str:
    """Findet den Tool-Namen fuer eine tool_use_id in der vorherigen Assistant-Message."""
    if user_idx < 1:
        return ""
    prev = messages[user_idx - 1]
    if prev.get("role") != "assistant":
        return ""
    for block in prev.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("id") == tool_use_id:
            return block.get("name", "")
    return ""


def estimate_tokens(system_prompt: str, messages: list, tools: list) -> int:
    """Schaetzt Token-Verbrauch VOR dem API-Call (ca. 4 Zeichen pro Token).

    Keine externe Abhaengigkeit (kein tiktoken). Genauigkeit: +/-15%,
    reicht fuer Budget-Entscheidungen vor dem Call.
    """
    char_count = len(system_prompt)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            char_count += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    char_count += len(block.get("content", ""))
                    char_count += len(str(block.get("input", "")))
                elif hasattr(block, "text"):
                    char_count += len(block.text or "")
    for tool in tools:
        char_count += len(str(tool))
    return char_count // 4


def compress_old_messages(messages: list, keep_recent: int = 5) -> None:
    """
    Komprimiert alte Tool-Results um Token zu sparen (in-place).

    Adaptive Strategie: Je aelter ein Eintrag, desto staerker komprimiert.
    - SAFE_TO_COMPRESS Tools (Schreib-Aktionen): Immer auf Einzeiler
    - READ_TOOLS (Lese-Aktionen): Adaptiv — neuere behalten mehr Kontext
    - Unbekannte Tools: NICHT komprimieren (sicheres Default)
    """
    if len(messages) <= keep_recent * 2 + 1:
        return

    compress_until = len(messages) - keep_recent * 2

    for i in range(1, compress_until):
        msg = messages[i]
        if msg["role"] != "user":
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            continue

        # Adaptive Limit: Aeltere Messages werden staerker gekuerzt
        # Position 1 (aelteste) → 300 Zeichen, Position nahe keep_recent → 800
        age_ratio = i / max(compress_until, 1)  # 0.0 (aelteste) bis 1.0
        read_limit = int(300 + 500 * age_ratio)  # 300-800 Zeichen

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue

            original = block.get("content", "")
            if len(original) <= 150:
                continue  # Schon komprimiert oder kurz

            tool_name = find_tool_name_for_id(
                messages, i, block.get("tool_use_id", ""),
            )

            if tool_name in SAFE_TO_COMPRESS:
                # Schreib-Tools: Auf Einzeiler komprimieren
                # ABER: Quality-Warnungen beibehalten
                if "QUALITAETS-WARNUNG" in original:
                    warning_start = original.index("QUALITAETS-WARNUNG")
                    block["content"] = f"[OK mit Warnung] {original[warning_start:][:200]}"
                else:
                    first_line = original.split("\n")[0][:80]
                    block["content"] = f"[OK] {first_line}"

            elif tool_name in READ_TOOLS:
                # Lese-Tools: Adaptiv kuerzen (aelter = kuertzer)
                if len(original) > read_limit:
                    # JSON-sicher: Am letzten Newline vor dem Limit schneiden
                    cut = original[:read_limit]
                    last_nl = cut.rfind("\n")
                    if last_nl > read_limit // 2:
                        cut = cut[:last_nl]
                    block["content"] = cut + f"\n[...gekuerzt auf {len(cut)} von {len(original)} Zeichen]"

            elif len(original) > 1500:
                # Fallback: Nur sehr grosse unbekannte Blocks kuerzen (Newline-safe)
                cut = original[:800]
                last_nl = cut.rfind("\n")
                if last_nl > 400:
                    cut = cut[:last_nl]
                block["content"] = cut + "\n[...gekuerzt]"
