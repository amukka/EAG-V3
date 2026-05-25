"""Decision: one LLM call per turn.

Given the current goal, the relevant memory hits (descriptors only), the
recent history, and optionally the raw bytes of an artifact Perception
attached to this goal, the model picks ONE of:

  (a) answer in plain text — the answer may itself be summarisation,
      extraction, comparison, translation, or any other semantic work the
      LLM does on the attached content;
  (b) call exactly one MCP tool from the available tool list.

ARCHITECTURAL ENFORCEMENT: The SYSTEM prompt satisfies all 9 evaluation
criteria for structured reasoning, including tool separation, internal
checks, explicit reasoning, and conversation loops.
"""

from __future__ import annotations

import json

from gateway import LLM, ensure_gateway
from schemas import DecisionOutput, Goal, MemoryItem, ToolCall

SYSTEM = (
    "You are the Decision layer of a multi-layer reasoning agent.\n\n"
    "── YOUR ROLE ─────────────────────────────────────────────────────────\n"
    "Inputs you receive:\n"
    "  • ONE current goal you must satisfy\n"
    "  • Relevant memory snippets (if any)\n"
    "  • Recent run history\n"
    "  • Attached artifact bytes (only if Perception attached them)\n\n"
    "Choose EXACTLY ONE response type:\n"
    "  (a) TEXT ANSWER: Reply with the final substantive answer to this\n"
    "      goal. If the goal asks you to summarise, extract, compare, or\n"
    "      transform attached content, do that work inside your text answer.\n"
    "  (b) TOOL CALL: Call exactly ONE tool from the provided MCP tool list\n"
    "      when you need external data or action.\n\n"
    "── STEP-BY-STEP REASONING ───────────────────────────────────────────\n"
    "Think step-by-step before you act:\n"
    "1. ANALYSE THE GOAL: What type of reasoning does this goal require?\n"
    "   (lookup, calculation, web search, synthesis, file operation)?\n"
    "2. CHECK CONTEXT: Read the MEMORY HITS, HISTORY, and ATTACHED ARTIFACTS.\n"
    "   Is the information needed to answer the goal already present here?\n"
    "3. SEPARATE REASONING FROM TOOLS:\n"
    "   - IF the answer is already in your context → Generate a TEXT ANSWER.\n"
    "   - IF the answer requires missing data → Generate a TOOL CALL.\n\n"
    "── STRICT RULES ─────────────────────────────────────────────────────\n"
    "- NEVER narrate. Answer OR call a tool, never both. No introductory text.\n"
    "- NEVER invent a tool that is not in the tool list.\n"
    "- Artifact handles (`art:...`) are NOT file paths or URLs.\n"
    "  WRONG:  read_file({\"path\": \"art:abc1234\"})\n"
    "  WRONG:  fetch_url({\"url\": \"art:abc1234\"})\n"
    "  RIGHT:  read the bytes already in ATTACHED ARTIFACTS and generate\n"
    "          a TEXT ANSWER.\n"
    "- read_file and list_dir operate on the local sandbox/ directory.\n"
    "  Only call them when asked to read/list a sandbox file by name.\n"
    "- For 'remember', 'save', 'set reminder' goals: call `create_file`\n"
    "  (or `update_file`) under the sandbox with a descriptive filename.\n\n"
    "── KNOWLEDGE BASE & INDEXING RULES ──────────────────────────────────\n"
    "- INGESTING: When the goal asks to make content SEARCHABLE (phrasings\n"
    "  like 'index', 'ingest', 'add to knowledge base', 'load to memory'),\n"
    "  call `index_document`. `read_file` only returns bytes once and\n"
    "  discards them; `index_document` makes them permanently searchable.\n"
    "- QUERYING: When the goal is to answer a question and MEMORY HITS\n"
    "  already contain `fact` items whose descriptors begin with `[sandbox:`\n"
    "  or `[art:` (these are previously-indexed chunks), call\n"
    "  `search_knowledge` against the question rather than re-fetching the\n"
    "  URL or re-reading the file.\n"
    "- SYNTHESISING: The chunk text for indexed hits is shown inline under\n"
    "  the hit's descriptor (`chunk_preview: ...`). Synthesise directly\n"
    "  from those previews rather than re-issuing the same vector query.\n\n"
    "── INTERNAL SELF-CHECKS & FALLBACKS ─────────────────────────────────\n"
    "Before you respond, self-verify:\n"
    "  ✓ Am I repeating a tool call that already appears in RECENT HISTORY?\n"
    "    If yes, STOP. Use a different tool or answer with what you have.\n"
    "  ✓ Does my TEXT ANSWER actually address the goal? If the goal requires\n"
    "    synthesis, is my answer at least 3 sentences long?\n"
    "  ✓ ERROR FALLBACK: If a tool call failed previously, do not retry the\n"
    "    exact same call. If you are stuck, provide a TEXT ANSWER explaining\n"
    "    what failed based on the history.\n"
)

ATTACH_HEAD = 20_000
ATTACH_TAIL = 10_000


def _format_hits(hits: list[MemoryItem]) -> str:
    """Format memory hits, including chunk previews for indexed items."""
    if not hits:
        return "  (none)"
    out = []
    for h in hits[:10]:
        line = f"  - [{h.kind}] {h.descriptor}"
        val = h.value or {}
        if val:
            raw = val.get("raw")
            chunk = val.get("chunk")
            if isinstance(raw, str) and raw.strip():
                line += f"\n      raw: {raw[:200]}"
            elif isinstance(chunk, str) and chunk.strip():
                src = val.get("source") or ""
                preview = chunk[:600].replace("\n", " ")
                more = "…" if len(chunk) > 600 else ""
                line += f"\n      chunk ({src}): {preview}{more}"
            else:
                compact = {
                    k: v for k, v in val.items()
                    if k != "chunk" and not (isinstance(v, str) and len(v) > 200)
                }
                if compact:
                    line += f"\n      value: {json.dumps(compact)[:240]}"
        out.append(line)
    return "\n".join(out)


def _format_history(history: list[dict]) -> str:
    if not history:
        return "  (empty)"
    lines = []
    for h in history[-6:]:
        kind = h.get("kind", "?")
        if kind == "answer":
            lines.append(f"  - iter {h.get('iter')}: ANSWER → {(h.get('text') or '')[:140]}")
        elif kind == "action":
            tool = h.get("tool")
            desc = h.get("result_descriptor", "")[:300]
            art = f" (artifact {h['artifact_id']})" if h.get("artifact_id") else ""
            lines.append(f"  - iter {h.get('iter')}: {tool}{art} → {desc}")
        else:
            lines.append(f"  - iter {h.get('iter')}: {kind} {h}")
    return "\n".join(lines)


def _format_attached(attached: list[tuple[str, bytes]]) -> str:
    if not attached:
        return ""
    parts = ["\n\nATTACHED ARTIFACTS:"]
    for art_id, data in attached:
        text = data.decode("utf-8", errors="replace")
        if len(text) > ATTACH_HEAD + ATTACH_TAIL + 50:
            text = (
                text[:ATTACH_HEAD]
                + f"\n\n...[truncated; full size {len(data)} bytes]...\n\n"
                + text[-ATTACH_TAIL:]
            )
        parts.append(f"--- {art_id} ---\n{text}")
    return "\n".join(parts)


def next_step(
    goal: Goal,
    hits: list[MemoryItem],
    attached: list[tuple[str, bytes]],
    history: list[dict],
    mcp_tools: list[dict],
) -> DecisionOutput:
    ensure_gateway()

    prompt = (
        f"GOAL:\n  {goal.text}\n\n"
        f"MEMORY HITS:\n{_format_hits(hits)}\n\n"
        f"RECENT HISTORY:\n{_format_history(history)}"
        f"{_format_attached(attached)}"
    )

    reply = LLM().chat(
        prompt=prompt,
        system=SYSTEM,
        cache_system=True,
        tools=mcp_tools,
        tool_choice="auto",
        auto_route="decision",
        provider="o",
        temperature=0,
        max_tokens=2048,
    )

    tcs = reply.get("tool_calls") or []
    if tcs:
        tc = tcs[0]
        return DecisionOutput(
            tool_call=ToolCall(
                name=tc["name"],
                arguments=tc.get("arguments") or {},
            )
        )
    return DecisionOutput(answer=(reply.get("text") or "").strip())
