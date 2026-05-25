"""Perception: the agent's orchestrator.

Runs every loop iteration. Looks at the user's original query, the memory
hits, and the run history so far, and emits the current Observation —
which goals exist, which are done, and whether the next unfinished goal
needs raw bytes from a specific artifact.

Perception never reads artifact bytes. It sees handles + descriptors only.
When a goal needs bytes, Perception flips `send_artifact: true` and points
`artifact_index` at one of the artifacts listed in MEMORY HITS. The outer
loop resolves the index back to the artifact id and attaches the bytes.

ARCHITECTURAL CONSTRAINT: This module's SYSTEM prompt contains ZERO MCP
tool names. Perception speaks at the level of intent. Decision maps
intent to tools. The grep test must pass:
  grep -nE 'web_search|fetch_url|get_time|currency_convert|read_file|
  list_dir|create_file|update_file|edit_file|index_document|search_knowledge'
  perception.py → 0 matches inside the SYSTEM string.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from gateway import LLM, ensure_gateway
from schemas import Goal, MemoryItem, Observation, new_id


class _GoalDelta(BaseModel):
    """What the Perception LLM emits per goal. No `id` field — goals are
    identified by their position in the output list. The LLM cannot drift
    identity across iterations because there is no identity field to drift."""

    text: str = Field(max_length=240)
    done: bool = False
    send_artifact: bool = False
    artifact_index: int | None = None


class _PerceptionOutput(BaseModel):
    goals: list[_GoalDelta] = Field(default_factory=list, max_length=10)


SYSTEM = (
    "You are the Perception layer of a multi-layer reasoning agent.\n\n"
    "── YOUR ROLE ─────────────────────────────────────────────────────────\n"
    "Each iteration you receive:\n"
    "  • the user's original query\n"
    "  • the prior goal list (may be empty on the first iteration)\n"
    "  • current memory hits (descriptors only — never raw bytes)\n"
    "  • the run history so far (actions taken and answers given)\n\n"
    "Your output is the CURRENT goal list as JSON matching the schema.\n\n"
    "── STEP-BY-STEP REASONING PROCEDURE ─────────────────────────────────\n"
    "Think step-by-step before producing your output. For each iteration:\n\n"
    "Step 1 — UNDERSTAND: Re-read the user's query. Identify what type of\n"
    "  task this is: retrieval, computation, synthesis, comparison, lookup,\n"
    "  or a multi-part composition of these.\n\n"
    "Step 2 — ASSESS PRIOR STATE: If PRIOR GOALS exist, check each one\n"
    "  against RUN HISTORY. Has an action fulfilled it? Has an answer been\n"
    "  produced for it? Mark fulfilled goals as done.\n\n"
    "Step 3 — DECOMPOSE (first iteration only): If PRIOR GOALS is empty,\n"
    "  break the query into short imperative goals — one per distinct\n"
    "  sub-task. Apply these decomposition rules:\n"
    "  • If the query asks to read/fetch/process N items ('top 3 results',\n"
    "    'first 5 articles'), emit a SEPARATE goal for each item plus the\n"
    "    final synthesis goal — NOT a single umbrella goal.\n"
    "  • If the query asks to ingest N files so they can be searched later,\n"
    "    emit one goal per file expressing that its content should be made\n"
    "    searchable, plus a final report goal.\n"
    "  • If MEMORY HITS already contain `fact` items whose descriptors\n"
    "    start with `[sandbox:` or `[art:` (these mark previously-indexed\n"
    "    chunks of source documents), the next goal for any question about\n"
    "    that material is to QUERY THE EXISTING KNOWLEDGE BASE rather than\n"
    "    re-fetch or re-open the original sources. Pair that query goal\n"
    "    with a final synthesis/answer goal.\n"
    "  • Whenever the query is a question (not a pure action), the LAST\n"
    "    goal must be a synthesis/answer goal using verbs like: answer,\n"
    "    tell, summarise, compare, list, extract, identify, describe.\n\n"
    "Step 4 — VERIFY before emitting: Self-check your output:\n"
    "  ✓ Are all prior goals preserved in the same order?\n"
    "  ✓ Does each goal express WHAT must happen (intent), not HOW or\n"
    "    WHICH specific mechanism will do it?\n"
    "  ✓ Is the last goal a synthesis/answer goal when the query is a\n"
    "    question?\n"
    "  ✓ No duplicate goals?\n"
    "  ✓ If uncertain about decomposition, prefer more granular goals.\n\n"
    "── GOAL ORDERING RULES ──────────────────────────────────────────────\n"
    "Goals are identified by POSITION in the output array. Always return\n"
    "goals in the SAME ORDER as PRIOR GOALS. Do not reorder, do not drop\n"
    "a prior goal, do not add a goal in the middle.\n"
    "You MAY append new goals at the END when a discovery action on a\n"
    "prior turn (for example, listing the contents of a directory) reveals\n"
    "concrete items that were unknown at decomposition time. In that case\n"
    "keep all prior goals verbatim and append one new goal per concrete\n"
    "item, then re-append the original synthesis/report goal LAST so it\n"
    "stays the final step.\n\n"
    "── INTENT-LEVEL VOCABULARY ──────────────────────────────────────────\n"
    "You speak at the level of INTENT, not mechanism selection. Write each\n"
    "goal as a short imperative describing WHAT must happen, not WHICH\n"
    "specific mechanism will do it. The Decision layer is responsible for\n"
    "mapping intent to the appropriate mechanism; leave that choice to\n"
    "Decision entirely.\n\n"
    "Example intent verbs you may use: fetch, open, list, look up the\n"
    "time, convert currency, save a note, make this content searchable,\n"
    "query the existing knowledge base, extract, summarise, compare,\n"
    "synthesise, remember, search the web for, retrieve, find, check.\n"
    "Do NOT name specific mechanisms or tools.\n\n"
    "── REASONING TYPE TAGS ──────────────────────────────────────────────\n"
    "For each goal, mentally classify its type before writing it:\n"
    "  • RETRIEVAL — fetching external data, searching the web, reading\n"
    "  • COMPUTATION — time lookup, currency conversion, calculation\n"
    "  • INGESTION — making content searchable for later queries\n"
    "  • SYNTHESIS — summarising, comparing, extracting, answering\n"
    "  • PERSISTENCE — saving notes, creating reminders\n"
    "This classification helps you write precise, actionable goals.\n\n"
    "── ERROR HANDLING ───────────────────────────────────────────────────\n"
    "• If memory hits are empty and the query needs external data, emit a\n"
    "  fetch/search goal first.\n"
    "• If a prior action failed (history shows an error), do NOT re-emit\n"
    "  the same goal verbatim. Rephrase it or decompose it differently.\n"
    "• If uncertain about decomposition, prefer more granular goals over\n"
    "  fewer coarse ones — Decision can always collapse simple steps.\n\n"
    "── DONE MARKING RULES ──────────────────────────────────────────────\n"
    "Copy each prior goal's `text` verbatim into the same slot.\n"
    "Mark `done: true` the moment RUN HISTORY shows an action satisfying\n"
    "it. Once done, leave it done in every later iteration.\n\n"
    "── ARTIFACT ATTACHMENT ──────────────────────────────────────────────\n"
    "For the FIRST unfinished goal (lowest-index slot with done=false),\n"
    "set `send_artifact: true` whenever ANY of these apply:\n"
    "  - the goal text contains extract / summarise / list / synthesise /\n"
    "    analyse / evaluate / select / compare / pick / choose / decide;\n"
    "  - the goal needs information that lives inside a fetched page or\n"
    "    file rather than just in the short descriptor.\n"
    "In that case pick `artifact_index` = the `i` value (0, 1, 2, ...)\n"
    "of the most relevant MEMORY HITS entry (entries whose `i` is null\n"
    "are not artifacts and cannot be picked). When in doubt, attach the\n"
    "most recent artifact whose descriptor matches the goal topic.\n"
    "Only when the goal is purely fetch / search / compute / open / time\n"
    "should you leave `send_artifact: false` and `artifact_index: null`.\n\n"
    "── OUTPUT FORMAT ────────────────────────────────────────────────────\n"
    "Return ONLY the JSON object matching the schema. No prose, no\n"
    "explanation outside the JSON. The JSON must parse cleanly.\n\n"
    "── EXAMPLE ──────────────────────────────────────────────────────────\n"
    "Given:\n"
    '  MEMORY HITS: [{"i":0,"artifact_id":"art:aaa","descriptor":'
    '"page fetch result -> art:aaa"}]\n'
    '  PRIOR GOALS: [{"text":"Fetch the page","done":false,'
    '"send_artifact":false,"artifact_index":null},\n'
    '                {"text":"Extract X","done":false,'
    '"send_artifact":false,"artifact_index":null}]\n'
    "Return:\n"
    '  {"goals":[\n'
    '    {"text":"Fetch the page","done":true,'
    '"send_artifact":false,"artifact_index":null},\n'
    '    {"text":"Extract X","done":false,'
    '"send_artifact":true,"artifact_index":0}\n'
    "  ]}"
)


def _snapshot_history(history: list[dict]) -> list[dict]:
    out = []
    for h in history[-10:]:
        clipped = {}
        for k, v in h.items():
            if isinstance(v, str) and len(v) > 240:
                clipped[k] = v[:240] + "..."
            else:
                clipped[k] = v
        out.append(clipped)
    return out


def _snapshot_hits(hits: list[MemoryItem]) -> list[dict]:
    """Render the memory hits the LLM sees. Artifacts are indexed (i) so
    Perception can point at them by integer; non-artifact hits show i=null."""
    art_pos = 0
    out = []
    for h in hits[:12]:
        i = None
        if h.artifact_id:
            i = art_pos
            art_pos += 1
        entry: dict = {
            "i": i,
            "kind": h.kind,
            "descriptor": h.descriptor,
            "keywords": h.keywords,
            "artifact_id": h.artifact_id,
        }
        # Show chunk previews for fact items with chunk content
        val = h.value or {}
        chunk = val.get("chunk")
        if isinstance(chunk, str) and chunk.strip():
            entry["chunk_preview"] = chunk[:200].replace("\n", " ")
        raw = val.get("raw")
        if isinstance(raw, str) and raw.strip():
            entry["raw_preview"] = raw[:200].replace("\n", " ")
        out.append(entry)
    return out


def observe(
    query: str,
    hits: list[MemoryItem],
    history: list[dict],
    prior_goals: list[Goal],
    run_id: str,
) -> Observation:
    ensure_gateway()

    art_ids_in_order = [h.artifact_id for h in hits[:12] if h.artifact_id]

    prior_snapshot = [g.model_dump() for g in prior_goals] if prior_goals else []
    prompt = (
        f"USER QUERY:\n  {query}\n\n"
        f"PRIOR GOALS:\n{json.dumps(prior_snapshot, indent=2)}\n\n"
        f"MEMORY HITS (handles + descriptors only, no raw bytes; `i` is the\n"
        f"artifact_index to pass back when send_artifact is true):\n"
        f"{json.dumps(_snapshot_hits(hits), indent=2)}\n\n"
        f"RUN HISTORY (last 10 events):\n"
        f"{json.dumps(_snapshot_history(history), indent=2, default=str)}\n\n"
        f"Return the current goal list as JSON matching the schema."
    )

    schema = _PerceptionOutput.model_json_schema()
    reply = LLM().chat(
        prompt=prompt,
        system=SYSTEM,
        auto_route="perception",
        provider="o",
        response_format={
            "type": "json_schema",
            "schema": schema,
            "name": "PerceptionOutput",
            "strict": True,
        },
        temperature=1.0,
    )

    parsed = reply.get("parsed")
    if not parsed or not parsed.get("goals"):
        return Observation(goals=[Goal(id=new_id("g"), text=query)])

    # Synthesis-type goals require Decision to actually produce a
    # substantive answer; we won't let Perception declare them done on the
    # strength of a tool-call alone.
    SYNTHESIS_KW = (
        "evaluate", "select", "synthes", "compare", "decide", "recommend",
        "tell me which", "most appropriate", "analy", "pick", "choose",
        "summarise", "summarize", "answer", "identify", "find", "determine",
        "extract", "list", "report", "tell", "explain", "describe", "name",
    )

    # Goal-count invariant: never contract, never reorder. Prior goals keep
    # their slot and id; Perception may APPEND new goals after the prior
    # list when a discovery action reveals work that wasn't knowable on
    # iter 1. Deduplicate appended goals against prior texts.
    raw_goals = parsed["goals"]
    if prior_goals:
        prior_texts = {g.text.strip().lower() for g in prior_goals}
        deduped = list(raw_goals[:len(prior_goals)])
        for extra in raw_goals[len(prior_goals):]:
            t = (extra.get("text") or "").strip().lower()
            if not t or t in prior_texts:
                continue
            prior_texts.add(t)
            deduped.append(extra)
        raw_goals = deduped

    out_goals: list[Goal] = []
    for i, d in enumerate(raw_goals):
        delta = _GoalDelta.model_validate(d)
        attach: str | None = None
        if delta.send_artifact and delta.artifact_index is not None:
            if 0 <= delta.artifact_index < len(art_ids_in_order):
                attach = art_ids_in_order[delta.artifact_index]

        gid = prior_goals[i].id if i < len(prior_goals) else new_id("g")
        was_done = prior_goals[i].done if i < len(prior_goals) else False

        proposed_done = was_done or delta.done
        if proposed_done and not was_done:
            gtext_lc = delta.text.lower()
            if any(kw in gtext_lc for kw in SYNTHESIS_KW):
                has_answer = any(
                    h.get("kind") == "answer"
                    and h.get("goal_id") == gid
                    and len((h.get("text") or "")) > 60
                    for h in history
                )
                if not has_answer:
                    proposed_done = False

        out_goals.append(Goal(
            id=gid,
            text=delta.text,
            done=proposed_done,
            attach_artifact_id=attach,
        ))

    # Safety net: if the first unfinished goal needs raw bytes (its text
    # matches a synthesis keyword) AND we have artifacts in memory AND the
    # model forgot to set send_artifact, force-attach the most recent
    # artifact. The LLM at temp=1.0 is otherwise too unreliable about this.
    for g in out_goals:
        if g.done:
            continue
        if g.attach_artifact_id:
            break  # already attached, nothing to do
        if not art_ids_in_order:
            break  # no artifacts available yet
        if any(kw in g.text.lower() for kw in SYNTHESIS_KW):
            g.attach_artifact_id = art_ids_in_order[-1]
        break  # only act on the FIRST unfinished goal
    return Observation(goals=out_goals)
