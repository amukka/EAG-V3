"""
Decision role — picks the next action for one bounded goal.

Returns either:
  • DecisionOutput.answer    — a final answer string (goal is resolved)
  • DecisionOutput.tool_call — a single MCP tool call to gather more info

Decision never sees other goals. It sees only the current goal, memory hits,
run history, and (if Perception requested it) an attached artifact.
Routes through auto_route="decision"; the gateway picks a worker by token tier.
"""
from __future__ import annotations

import json

import gateway
from schemas import DecisionOutput, Goal, MemoryItem

_SYSTEM = """\
You are the Decision role in a cognitive agent.

Before choosing, reason step-by-step:
  1. What information does the CURRENT GOAL require?
  2. Is an ATTACHED ARTIFACT present? If yes, read it fully before anything else.
  3. Is the needed information already in MEMORY HITS, ATTACHED ARTIFACT, or RUN HISTORY?
  4. If yes → answer directly (reasoning type: synthesis or lookup).
     If no  → identify which single tool fills the gap (reasoning type: planning).
  5. If a tool was already called for this goal and returned results, do not call it again
     unless the result was clearly truncated or an error occurred.

MEMORY RULE: If MEMORY HITS contain a USER-STATED FACT or INDEXED DOCUMENT CHUNK that
directly answers the CURRENT GOAL, output it as the ANSWER — no tool call needed.
- For personal questions (birthday, preferences, names): use USER-STATED FACTS. The "stated:"
  line shows the user's exact words — trust that over any tool outcome.
- For document/paper questions: use INDEXED DOCUMENT CHUNKS.
Example: goal="When is mom's birthday?", user-stated fact="My mom's birthday is 15 May 2026"
→ ANSWER: "Mom's birthday is 15 May 2026." Do NOT answer from tool outcome dates.

Then choose exactly ONE of:
  A) Provide a FINAL ANSWER — set "answer" to your answer, set "tool_call" to null.
  B) Make ONE TOOL CALL    — set "answer" to null, set "tool_call" to the call.

RULES:
- Never set both answer and tool_call. Never set both to null.
- Prefer answering directly if MEMORY HITS or RUN HISTORY already contain
  the needed information — do not call a tool you already called for this goal.
- tool_call.arguments must match the tool's parameter schema exactly.
- NEVER call read_file with an artifact ID (art:N). Artifacts are automatically
  injected into your prompt by the system under ATTACHED ARTIFACT. If you need
  artifact content, wait — it will appear in the next iteration via attachment.
- read_file is only for files inside the sandbox directory, not artifact handles.
- For 'remember', 'save', 'set reminder' goals: call create_file with a descriptive
  filename. If create_file fails because the file already exists, call update_file
  with the same path instead — never retry create_file on the same path.
- Before calling fetch_url, scan RUN HISTORY for previous fetch_url calls.
  If the URL is already in history, choose a DIFFERENT URL from the search results.
  Never fetch the same URL twice.
- For synthesis/list/compare goals: answer from whatever is in ATTACHED ARTIFACT
  and RUN HISTORY. Do not say "I need more data" — produce the best answer from
  what is available. One good source is enough to produce a numbered list.
- LOW CONFIDENCE EXCEPTION: If the ATTACHED ARTIFACT contains a note with
  "LOW CONFIDENCE" or "similarity score" below 0.50, the retrieved chunks are
  off-topic. Do NOT synthesise a fake connection. Instead answer:
  "The indexed papers do not cover <topic>. The closest match is <paper> which
  discusses <what it actually covers>, but this is not the same as <topic>."
  Never pretend unrelated content answers the question.
- Keep answers specific: include dates, numbers, names, and exact facts.
- Match answer length to the goal: a list goal needs a list, a date goal needs a date,
  a summary goal needs a paragraph. Never give a one-line answer to a multi-part goal.
- For recommendation/selection goals (e.g. "which activity is best given the weather"):
  always include in your answer: (1) the full list of candidates from RUN HISTORY,
  (2) the weather or criterion, (3) your recommendation with reasoning.
  Do NOT assume the reader already knows the candidate list.
- If an ATTACHED ARTIFACT is present, read it carefully — it contains the
  raw content needed to answer the goal.

SELF-CHECK before emitting output:
- Exactly one of answer / tool_call is non-null? ✓
- If tool_call: do the argument keys match the tool's parameter schema? ✓
- If answer: does it directly and completely address the goal text? ✓

KNOWN RELIABLE ENDPOINTS (prefer fetch_url over web_search for these):
- Current weather / forecast for any city → fetch_url("https://wttr.in/{City}?format=j1")
  Returns JSON with temperature, condition, and 3-day forecast. Example: fetch_url("https://wttr.in/Tokyo?format=j1")
- Python asyncio documentation → fetch_url("https://docs.python.org/3/library/asyncio.html")
- Python asyncio tutorial (Real Python) → fetch_url("https://realpython.com/async-io-python/")
- Wikipedia article for any topic → fetch_url("https://en.wikipedia.org/wiki/{Topic}")

WEB SEARCH FAILURE RULE (CRITICAL):
- If web_search returns empty results (content=[] or result=[]) even ONCE, do NOT call web_search again.
- Instead, immediately switch to fetch_url with a known reliable URL relevant to the goal.
- Never call web_search more than once if it returned empty. Retrying the same empty search wastes iterations.

FALLBACKS:
- If you are uncertain which tool to call, call web_search with the goal text as the query.
- If web_search fails (empty), switch to fetch_url with a known documentation or reference URL.
- If the artifact content is truncated and insufficient, call fetch_url again for the same URL.
- If no tool can help and you cannot answer with confidence, set answer to your best estimate
  and prefix it with "Based on available information: ".\

KNOWLEDGE BASE & INDEXING RULES:
- INGESTING: When the goal asks to make content SEARCHABLE (phrasings like 'index', 'ingest',
  'add to knowledge base', 'load to memory'), call index_document or index_paper_md.
  read_file only returns bytes once; index_document makes them permanently searchable.
- QUERYING: When the goal is to answer a question and MEMORY HITS already contain fact items
  whose descriptors begin with [sandbox: or [art: (these are previously-indexed chunks),
  call search_knowledge against the question rather than re-fetching the URL or re-reading
  the file.
- SYNTHESISING: The chunk text for indexed hits is shown inline under the hit's descriptor
  (chunk_preview: ...). When synthesising, do NOT just describe what each chunk says.
  Instead: (1) identify the conceptual question being asked, (2) for each chunk explain HOW
  it relates to that concept even when the exact words are absent — draw the bridge explicitly,
  (3) attribute each claim to its source paper. Example: if asked about "credit assignment"
  and a chunk discusses "reward shaping", state that reward shaping is the mechanism by which
  DPO assigns credit to model outputs. Never say "the paper discusses X" — say "paper X
  handles [concept] by doing Y because Z."
- CONTRIBUTIONS / KEY IDEAS: When the goal asks for "N key contributions" or "main ideas"
  and the content does NOT have an explicit numbered list, YOU MUST infer and enumerate them
  from the architecture, results, and motivation described in the chunks. Do NOT say "the
  information does not contain" — instead read the chunks, identify the N most novel/important
  aspects, and list them as numbered points with a one-sentence explanation each.
  Example: if chunks describe a new attention-only architecture that is faster and achieves
  SOTA, the three contributions are: (1) the attention-only design, (2) the parallelization
  benefit, (3) the SOTA results — even if those exact words never appear together.
"""


class Decision:
    def next_step(
        self,
        goal: Goal,
        hits: list[MemoryItem],
        attached: list[tuple[str, bytes]],
        history: list[dict],
        tools: list[dict],
    ) -> DecisionOutput:
        def _render_hit(h) -> str:
            line = f"  - [{h.source}] {h.descriptor}"
            # Show value.raw for user-stated facts so dates are never lost to truncation
            raw = (h.value or {}).get("raw", "")
            if raw and h.source == "user_query" and str(raw) not in h.descriptor:
                line += f"\n    stated: {str(raw)[:200]}"
            return line

        fact_hits = [h for h in hits if h.kind in ("fact", "preference")]
        other_hits = [h for h in hits if h.kind not in ("fact", "preference")]

        # User-stated facts first, then indexed document chunks — both labelled by source
        user_facts = [h for h in fact_hits if h.source == "user_query"]
        doc_chunks = [h for h in fact_hits if h.source.startswith("sandbox:") or h.source.startswith("art:")]
        other_facts = [h for h in fact_hits if h not in user_facts and h not in doc_chunks]

        sections = []
        if user_facts:
            sections.append(
                "USER-STATED FACTS — answer personal questions directly from these:\n"
                + "\n".join(_render_hit(h) for h in user_facts)
            )
        if doc_chunks:
            sections.append(
                "INDEXED DOCUMENT CHUNKS — use for questions about papers/documents:\n"
                + "\n".join(_render_hit(h) for h in doc_chunks)
            )
        if other_facts:
            sections.append(
                "Other facts:\n"
                + "\n".join(_render_hit(h) for h in other_facts)
            )
        if other_hits:
            sections.append(
                "Tool outcomes (context only):\n"
                + "\n".join(f"  - {h.descriptor}" for h in other_hits)
            )
        hits_text = "\n\n".join(sections) if sections else "  (none)"
        history_text = json.dumps(history, indent=2) if history else "[]"
        tools_text = json.dumps(tools, indent=2)

        artifact_section = ""
        if attached:
            art_id, art_bytes = attached[0]
            content = art_bytes.decode("utf-8", errors="replace")
            if len(content) > 20_000:
                content = content[:20_000] + f"\n...[truncated — total {len(art_bytes):,} bytes]"
            artifact_section = f"\nATTACHED ARTIFACT ({art_id}):\n{content}\n"

        user_msg = (
            f"CURRENT GOAL: {goal.text}\n\n"
            f"MEMORY HITS:\n{hits_text}\n\n"
            f"RUN HISTORY (recent):\n{history_text}\n"
            f"{artifact_section}"
            f"\nAVAILABLE TOOLS:\n{tools_text}"
        )

        return gateway.chat_structured(
            messages=[{"role": "user", "content": user_msg}],
            schema=DecisionOutput,
            system=_SYSTEM,
            provider="g",
            temperature=0.3,
            max_tokens=1024,
        )