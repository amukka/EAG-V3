"""
Decision role — picks the next action for one bounded goal.

Optimized for local Ollama models like:
- qwen2.5:7b
- llama3.1:8b

Smaller prompt.
Lower token usage.
Reduced looping.
More stable structured JSON generation.
"""

from __future__ import annotations

import json

import gateway
from schemas import DecisionOutput, Goal, MemoryItem


# ──────────────────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are the Decision role in a cognitive agent.

You receive:
- CURRENT GOAL
- MEMORY HITS
- RUN HISTORY
- optional ATTACHED ARTIFACT
- AVAILABLE TOOLS

Your job:
- Either answer the goal directly
- Or call exactly ONE tool

RULES:
- Never output both answer and tool_call
- Never output both as null

- If the answer already exists in:
  - MEMORY HITS
  - RUN HISTORY
  - ATTACHED ARTIFACT

  then answer directly.

- Never repeat the same fetch_url call twice.

- If ATTACHED ARTIFACT exists:
  use it before calling tools.

- Keep answers concise and factual.

- tool_call arguments must match schema exactly.

IMPORTANT:
- Use fetch_url for URLs
- Never call read_file on artifact ids
- Prefer existing artifacts over new fetches

- If RUN HISTORY already contains:
    fetch_url(url=X)

  do NOT fetch X again.

- If artifact content is enough:
  answer directly.

- Return ONLY valid JSON.
"""


# ──────────────────────────────────────────────────────────────────────────────
# Decision Role
# ──────────────────────────────────────────────────────────────────────────────

class Decision:
    def next_step(
        self,
        goal: Goal,
        hits: list[MemoryItem],
        attached: list[tuple[str, bytes]],
        history: list[dict],
        tools: list[dict],
    ) -> DecisionOutput:

        # ── Memory hits ──────────────────────────────────────────────────────

        hits_text = (
            "\n".join(
                f"- {h.descriptor} (kind={h.kind})"
                for h in hits
            )
            or "(none)"
        )

        # ── Shorter history for local models ────────────────────────────────

        short_history = history[-5:] if history else []

        history_text = (
            json.dumps(short_history, indent=2)
            if short_history
            else "[]"
        )

        # ── Tool list ───────────────────────────────────────────────────────

        tools_text = json.dumps(tools, indent=2)

        # ── Attached artifact ───────────────────────────────────────────────

        artifact_section = ""

        if attached:
            art_id, art_bytes = attached[0]

            content = art_bytes.decode(
                "utf-8",
                errors="replace",
            )

            # limit context size
            if len(content) > 8_000:
                content = (
                    content[:8_000]
                    + f"\n...[truncated — total {len(art_bytes):,} bytes]"
                )

            artifact_section = (
                f"\nATTACHED ARTIFACT ({art_id}):\n"
                f"{content}\n"
            )

        # ── Final user prompt ───────────────────────────────────────────────

        user_msg = (
            f"CURRENT GOAL:\n{goal.text}\n\n"
            f"MEMORY HITS:\n{hits_text}\n\n"
            f"RUN HISTORY:\n{history_text}\n"
            f"{artifact_section}\n"
            f"AVAILABLE TOOLS:\n{tools_text}"
        )

        # ── Structured LLM call ─────────────────────────────────────────────

        return gateway.chat_structured(
            messages=[
                {
                    "role": "user",
                    "content": user_msg,
                }
            ],
            schema=DecisionOutput,
            system=_SYSTEM,
            auto_route="decision",
            temperature=0.2,
            max_tokens=512,
            retries=2,
        )