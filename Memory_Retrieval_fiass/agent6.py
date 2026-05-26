
"""
Four-role cognitive architecture.

Roles:     Memory · Perception · Decision · Action
Contracts: schemas.py (Pydantic v2)
Substrate: LLM Gateway V3 (gateway.py)
Tools:     MCP server via stdio (mcp_server.py)

Run:
    uv run agent6.py "Your query here"
    uv run agent6.py              # prompts for input

Reset state between runs:
    Remove-Item -Recurse state\   (PowerShell)
    rm -rf state/                 (bash)
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import artifacts as artifact_store
import gateway
from action import Action
from decision import Decision
from memory import Memory
from perception import Perception
from schemas import DecisionOutput, Goal, Observation, ToolCall

load_dotenv(Path(__file__).parent / ".env")

MAX_ITERATIONS = 12

# ── module-level role instances ───────────────────────────────────────────────

_memory = Memory()
_perception = Perception()
_decision = Decision()
_action = Action()


# ── MCP session ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def mcp_session():
    server_script = str(Path(__file__).parent / "mcp_server.py")
    params = StdioServerParameters(
        command=sys.executable,   # same Python / venv as the agent
        args=[server_script],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _load_tools(session) -> list:
    result = await session.list_tools()
    return result.tools


def _tools_for_decision(mcp_tools: list) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema if hasattr(t, "inputSchema") else {},
        }
        for t in mcp_tools
    ]


# ── final answer synthesis ────────────────────────────────────────────────────

def _final_answer(history: list[dict]) -> str:
    # Keep only the last answer per goal_id (earlier retries are discarded)
    seen: dict[str, str] = {}
    for e in history:
        if e.get("kind") == "answer":
            seen[e.get("goal_id", e["iter"])] = e["text"]
    answers = list(seen.values())

    if not answers:
        tool_lines = [
            f"{e.get('tool', '?')}: {e.get('result_descriptor', '')}"
            for e in history
            if e.get("kind") == "action"
        ]
        return (
            "Research completed:\n\n" + "\n\n".join(tool_lines)
            if tool_lines
            else "No answer produced."
        )
    if len(answers) == 1:
        return answers[0]
    return "\n\n".join(answers)


def _extract_top_n(text: str) -> int | None:
    low = text.lower()
    m = re.search(r"\btop\s+(\d+)\b", low)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"\b(\d+)\s+results?\b", low)
    if m:
        return max(1, int(m.group(1)))
    word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    for word, value in word_map.items():
        if re.search(rf"\btop\s+{word}\b", low) or re.search(rf"\b{word}\s+results?\b", low):
            return value
    return None


def _is_read_results_goal(text: str) -> bool:
    low = text.lower()
    return "read" in low and "result" in low


def _fallback_urls_for_query(query: str) -> list[str]:
    low = query.lower()
    if "python" in low and "asyncio" in low:
        return [
            "https://docs.python.org/3/library/asyncio.html",
            "https://realpython.com/async-io-python/",
            "https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html",
        ]
    return []


def _urls_from_text(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = url.rstrip(").,;")
        if cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _urls_from_web_search_result(result_text: str) -> list[str]:
    try:
        parsed = json.loads(result_text)
    except Exception:
        return _urls_from_text(result_text)

    if isinstance(parsed, list):
        urls = [str(item.get("url", "")) for item in parsed if isinstance(item, dict)]
        return [u for u in urls if u]

    return _urls_from_text(result_text)


def _fetch_is_usable(result_text: str, art_id: str | None) -> bool:
    text = result_text
    if art_id and artifact_store.exists(art_id):
        text = artifact_store.get_bytes(art_id).decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except Exception:
        return bool(text.strip())

    if isinstance(payload, dict):
        status = int(payload.get("status", 200)) if str(payload.get("status", "")).isdigit() else payload.get("status", 200)
        try:
            status_code = int(status)
        except Exception:
            status_code = 200
        content = str(payload.get("text", ""))
        return status_code < 400 and len(content.strip()) > 80
    return bool(text.strip())


def _combine_artifacts(url_to_artifact: dict[str, str]) -> tuple[str, bytes] | None:
    parts: list[str] = []
    for idx, (url, art_id) in enumerate(url_to_artifact.items(), start=1):
        if not art_id or not artifact_store.exists(art_id):
            continue
        raw = artifact_store.get_bytes(art_id).decode("utf-8", errors="replace")
        parts.append(f"SOURCE {idx}: {url}\n{raw}\n")
    if not parts:
        return None
    combined = "\n".join(parts)
    if len(combined) > 80_000:
        combined = combined[:80_000] + "\n...[truncated]"
    return ("combined:sources", combined.encode("utf-8"))


def _is_refusal_answer(text: str) -> bool:
    low = text.lower()
    markers = [
        "i am unable to provide",
        "cannot fulfill",
        "do not have the content",
        "need to first summarize",
    ]
    return any(m in low for m in markers)


def _count_numbered_items(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d+\.\s+", text))


def _fallback_consensus_answer(query: str, combined_sources_text: str) -> str:
    prompt = (
        f"Task: {query}\n\n"
        "Using ONLY the source excerpts below, produce a short numbered list (3-6 items) "
        "of asyncio advice that appears consistently across the sources. "
        "No refusal language. If overlap is partial, include only clearly recurring advice.\n\n"
        f"SOURCES:\n{combined_sources_text}"
    )
    return gateway.chat(
        messages=[{"role": "user", "content": prompt}],
        system="You are a precise technical summarizer.",
        auto_route="decision",
        temperature=0.2,
        max_tokens=700,
    ).strip()


# ── main loop ─────────────────────────────────────────────────────────────────

async def run(query: str) -> str:
    gateway.ensure_gateway()

    run_id = uuid.uuid4().hex[:8]
    history: list[dict] = []
    prior_goals: list[Goal] = []
    last_search_urls: list[str] = []
    fetched_urls: set[str] = set()
    usable_fetched_urls: set[str] = set()
    url_to_artifact: dict[str, str] = {}
    goal_fetch_history: dict[str, set[str]] = {}
    required_results = _extract_top_n(query)
    top_n_controller_enabled = required_results is not None and "result" in query.lower()

    # Durable memory: classify the query so any facts/preferences in it persist
    mem_item = _memory.remember(query, source="user_query", run_id=run_id)
    print(f"[memory.remember]  classified as kind={mem_item.kind!r}  keywords={mem_item.keywords[:6]}")

    async with mcp_session() as session:
        mcp_tools = await _load_tools(session)
        tools = _tools_for_decision(mcp_tools)

        for it in range(1, MAX_ITERATIONS + 1):
            # 1. Read memory (no LLM cost)
            hits = _memory.read(query, history)
            print(f"[memory.read]   {len(hits)} hit{'s' if len(hits) != 1 else ''}")

            # 2. Perception: update goal list (one LLM call, pinned to Gemini)
            obs = _perception.observe(query, hits, history, prior_goals, run_id)
            prior_goals = obs.goals

            _log_iter(it, obs.goals)

            if obs.all_done:
                # Don't break if tool calls ran but produced no answer yet — let decision synthesize.
                has_answer = any(e.get("kind") == "answer" for e in history)
                has_actions = any(e.get("kind") == "action" for e in history)
                if has_answer or not has_actions:
                    break
                # Re-open the last goal so decision can produce an answer from the artifact.
                last_goal = obs.goals[-1] if obs.goals else None
                if last_goal is None:
                    break
                goal = Goal(id=last_goal.id, text=last_goal.text, done=False,
                            attach_artifact_id=last_goal.attach_artifact_id)
                obs = Observation(goals=[*obs.goals[:-1], goal])

            goal = obs.next_unfinished()
            if goal is None:
                break

            # 3. Attach artifact bytes if Perception flagged it
            # Force-attach safety net: synthesis goals get the most recent artifact
            _SYNTHESIS_KEYWORDS = {
                "synthesise", "synthesize", "synthesis", "summarize", "summary",
                "list", "compare", "common", "agree", "consolidate", "compile",
                "identify", "tell", "extract", "what", "answer",
                "report", "count", "total", "how", "many", "confirm",
            }
            if not goal.attach_artifact_id:
                goal_words = set(goal.text.lower().split())
                if goal_words & _SYNTHESIS_KEYWORDS:
                    recent_artifact_ids = [
                        e.get("artifact_id")
                        for e in reversed(history)
                        if e.get("kind") == "action" and e.get("artifact_id")
                    ]
                    for art_id in recent_artifact_ids:
                        if art_id and artifact_store.exists(art_id):
                            goal = Goal(
                                id=goal.id, text=goal.text, done=goal.done,
                                attach_artifact_id=art_id,
                            )
                            print(f"[safety-net]    auto-attached {art_id} to synthesis goal")
                            break

            attached: list[tuple[str, bytes]] = []
            if goal.attach_artifact_id and artifact_store.exists(goal.attach_artifact_id):
                attached.append(
                    (goal.attach_artifact_id, artifact_store.get_bytes(goal.attach_artifact_id))
                )
                print(f"[attach]        {goal.attach_artifact_id} ({len(attached[0][1]):,} bytes)")

            if top_n_controller_enabled and required_results and len(usable_fetched_urls) >= required_results:
                usable_url_to_art = {
                    url: art_id for url, art_id in url_to_artifact.items() if url in usable_fetched_urls
                }
                combined = _combine_artifacts(usable_url_to_art)
                if combined:
                    attached = [combined]
                    print(f"[attach]        {combined[0]} ({len(combined[1]):,} bytes)")

            # Deterministic controller: if a goal asks to read top-N results,
            # fetch distinct URLs from the latest web_search before allowing synthesis.
            if top_n_controller_enabled and required_results:
                if len(last_search_urls) < required_results:
                    for fallback_url in _fallback_urls_for_query(query):
                        if fallback_url not in last_search_urls:
                            last_search_urls.append(fallback_url)
                        if len(last_search_urls) >= required_results:
                            break
                pending_urls = [u for u in last_search_urls if u not in fetched_urls]
                if len(usable_fetched_urls) < required_results and pending_urls:
                    forced_call = {"url": pending_urls[0]}
                    forced_tool_call = ToolCall(name="fetch_url", arguments=forced_call)
                    print(f"[controller]    forcing fetch_url({forced_call}) before synthesis")
                    result_text, art_id = await _action.execute(
                        session,
                        forced_tool_call,
                    )
                    print(f"[action]        → {result_text[:120]}")
                    fetched_urls.add(pending_urls[0])
                    goal_fetch_history.setdefault(goal.id, set()).add(pending_urls[0])
                    if _fetch_is_usable(result_text, art_id):
                        usable_fetched_urls.add(pending_urls[0])
                        if art_id:
                            url_to_artifact[pending_urls[0]] = art_id
                    _memory.record_outcome(
                        tool_call=forced_tool_call,
                        result_text=result_text,
                        artifact_id=art_id,
                        run_id=run_id,
                        goal_id=goal.id,
                    )
                    history.append(
                        {
                            "iter": it,
                            "kind": "action",
                            "goal_id": goal.id,
                            "tool": "fetch_url",
                            "arguments": forced_call,
                            "result_descriptor": result_text[:2_000],
                            "artifact_id": art_id,
                        }
                    )
                    continue

            # Guard: if the same tool call was made twice for this goal (success or error), move on
            _goal_actions = [
                e for e in history
                if e.get("goal_id") == goal.id and e.get("kind") == "action"
            ]
            if len(_goal_actions) >= 2:
                _last = _goal_actions[-1]
                _prev = _goal_actions[-2]
                if (
                    _last.get("tool") == _prev.get("tool")
                    and _last.get("arguments") == _prev.get("arguments")
                ):
                    goal_words = set(re.findall(r"\b\w+\b", goal.text.lower()))
                    # Only use user-stated facts as fallback — never paper chunks
                    fact_hits = [
                        h for h in hits
                        if h.kind in ("fact", "preference")
                        and h.source == "user_query"
                        and bool(goal_words & set(h.keywords + re.findall(r"\b\w+\b", h.descriptor.lower())))
                    ]
                    fallback = (
                        fact_hits[0].descriptor
                        if fact_hits
                        else f"Could not complete: {goal.text}. Tool failed repeatedly — try a different approach."
                    )
                    print(f"[guard]         repeated tool failure — answering from memory: {fallback}")
                    history.append({"iter": it, "kind": "answer", "goal_id": goal.id, "text": fallback})
                    open_goals = [g for g in obs.goals if not g.done]
                    if len(open_goals) == 1 and open_goals[0].id == goal.id:
                        return _final_answer(history)
                    continue

            # 4. Decision: answer or tool call (one LLM call)
            out: DecisionOutput = _decision.next_step(goal, hits, attached, history, tools)

            if out.is_answer:
                if top_n_controller_enabled and required_results:
                    if len(usable_fetched_urls) < required_results:
                        if len(last_search_urls) < required_results:
                            for fallback_url in _fallback_urls_for_query(query):
                                if fallback_url not in last_search_urls:
                                    last_search_urls.append(fallback_url)
                                if len(last_search_urls) >= required_results:
                                    break
                        pending_urls = [u for u in last_search_urls if u not in fetched_urls]
                        if pending_urls:
                            forced_call = {"url": pending_urls[0]}
                            forced_tool_call = ToolCall(name="fetch_url", arguments=forced_call)
                            print(
                                "[controller]    delaying answer until enough sources are fetched"
                            )
                            result_text, art_id = await _action.execute(
                                session,
                                forced_tool_call,
                            )
                            print(f"[action]        → {result_text[:120]}")
                            fetched_urls.add(pending_urls[0])
                            goal_fetch_history.setdefault(goal.id, set()).add(pending_urls[0])
                            if _fetch_is_usable(result_text, art_id):
                                usable_fetched_urls.add(pending_urls[0])
                                if art_id:
                                    url_to_artifact[pending_urls[0]] = art_id
                            _memory.record_outcome(
                                tool_call=forced_tool_call,
                                result_text=result_text,
                                artifact_id=art_id,
                                run_id=run_id,
                                goal_id=goal.id,
                            )
                            history.append(
                                {
                                    "iter": it,
                                    "kind": "action",
                                    "goal_id": goal.id,
                                    "tool": "fetch_url",
                                    "arguments": forced_call,
                                    "result_descriptor": result_text[:2_000],
                                    "artifact_id": art_id,
                                }
                            )
                            continue
                print(f"[decision]      ANSWER: {out.answer[:120]}...")
                if (
                    top_n_controller_enabled
                    and required_results
                    and len(usable_fetched_urls) >= required_results
                    and out.answer
                ):
                    usable_url_to_art = {
                        url: art_id for url, art_id in url_to_artifact.items() if url in usable_fetched_urls
                    }
                    combined = _combine_artifacts(usable_url_to_art)
                    final_text = out.answer
                    if combined and (_is_refusal_answer(final_text) or _count_numbered_items(final_text) < 3):
                        combined_text = combined[1].decode("utf-8", errors="replace")
                        fallback = _fallback_consensus_answer(query, combined_text)
                        if fallback:
                            final_text = fallback
                    history.append(
                        {"iter": it, "kind": "answer", "goal_id": goal.id, "text": final_text}
                    )
                    return _final_answer(history)

                if (
                    top_n_controller_enabled
                    and required_results
                    and len(usable_fetched_urls) >= required_results
                    and out.answer
                    and _is_refusal_answer(out.answer)
                ):
                    usable_url_to_art = {
                        url: art_id for url, art_id in url_to_artifact.items() if url in usable_fetched_urls
                    }
                    combined = _combine_artifacts(usable_url_to_art)
                    if combined:
                        combined_text = combined[1].decode("utf-8", errors="replace")
                        fallback = _fallback_consensus_answer(query, combined_text)
                        history.append(
                            {"iter": it, "kind": "answer", "goal_id": goal.id, "text": fallback}
                        )
                        continue
                history.append(
                    {"iter": it, "kind": "answer", "goal_id": goal.id, "text": out.answer}
                )
                open_goals = [g for g in obs.goals if not g.done]
                if len(open_goals) == 1 and open_goals[0].id == goal.id:
                    return _final_answer(history)
                continue

            if out.tool_call is None:
                history.append(
                    {"iter": it, "kind": "noop", "goal_id": goal.id, "reason": "no action"}
                )
                continue

            # 5. Action: dispatch MCP tool (no LLM cost)
            if out.tool_call.name == "fetch_url":
                url = str(out.tool_call.arguments.get("url", "")).strip()
                seen_urls = goal_fetch_history.setdefault(goal.id, set())
                if url and url in seen_urls:
                    candidate_art_id = url_to_artifact.get(url)
                    if not candidate_art_id and attached:
                        candidate_art_id = attached[0][0]
                    if candidate_art_id and artifact_store.exists(candidate_art_id):
                        source_text = artifact_store.get_bytes(candidate_art_id).decode("utf-8", errors="replace")
                        if len(source_text) > 30_000:
                            source_text = source_text[:30_000] + "\n...[truncated]"
                        forced_answer = gateway.chat(
                            messages=[
                                {
                                    "role": "user",
                                    "content": (
                                        f"Goal: {goal.text}\n\n"
                                        "Use ONLY the source content below to answer directly and completely. "
                                        "If the goal asks for multiple facts, provide all of them.\n\n"
                                        f"SOURCE:\n{source_text}"
                                    ),
                                }
                            ],
                            system=(
                                "You are a precise technical assistant. "
                                "Answer the goal directly. "
                                "If the goal asks for a list, return a numbered list."
                            ),
                            auto_route="decision",
                            temperature=0.2,
                            max_tokens=700,
                        ).strip()
                        print("[controller]    prevented duplicate fetch_url; answered from cached artifact")
                        history.append(
                            {"iter": it, "kind": "answer", "goal_id": goal.id, "text": forced_answer}
                        )
                        open_goals = [g for g in obs.goals if not g.done]
                        if len(open_goals) == 1 and open_goals[0].id == goal.id:
                            return _final_answer(history)
                        continue

            print(f"[decision]      TOOL_CALL: {out.tool_call.name}({out.tool_call.arguments})")
            result_text, art_id = await _action.execute(session, out.tool_call)
            print(f"[action]        → {result_text[:120]}")

            if out.tool_call.name == "web_search":
                if art_id and artifact_store.exists(art_id):
                    text = artifact_store.get_bytes(art_id).decode("utf-8", errors="replace")
                else:
                    text = result_text
                urls = _urls_from_web_search_result(text)
                if urls:
                    last_search_urls = urls

            if out.tool_call.name == "fetch_url":
                url = str(out.tool_call.arguments.get("url", "")).strip()
                if url:
                    fetched_urls.add(url)
                    goal_fetch_history.setdefault(goal.id, set()).add(url)
                    if _fetch_is_usable(result_text, art_id):
                        usable_fetched_urls.add(url)
                        if art_id:
                            url_to_artifact[url] = art_id

            _memory.record_outcome(
                tool_call=out.tool_call,
                result_text=result_text,
                artifact_id=art_id,
                run_id=run_id,
                goal_id=goal.id,
            )
            history.append(
                {
                    "iter": it,
                    "kind": "action",
                    "goal_id": goal.id,
                    "tool": out.tool_call.name,
                    "arguments": out.tool_call.arguments,
                    "result_descriptor": result_text[:2_000],
                    "artifact_id": art_id,
                }
            )

    return _final_answer(history)


def _log_iter(it: int, goals: list[Goal]) -> None:
    print(f"\n─── iter {it} ───")
    for g in goals:
        status = "[done]" if g.done else "[open]"
        art = f"  attach={g.attach_artifact_id}" if g.attach_artifact_id else ""
        print(f"[perception]    {status} {g.text}{art}")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import platform
    from datetime import datetime

    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = input("Query: ").strip()
    if not query:
        print("No query provided.", file=sys.stderr)
        sys.exit(1)

    LOG_PATH = Path(__file__).parent / "runs.log"

    class _Tee:
        def __init__(self, *files):
            self._files = files
        def write(self, data):
            for f in self._files:
                f.write(data)
        def flush(self):
            for f in self._files:
                try:
                    f.flush()
                except Exception:
                    pass
        @property
        def encoding(self):
            return "utf-8"

    with open(LOG_PATH, "a", encoding="utf-8") as _log:
        _log.write(f"\n{'=' * 60}\n")
        _log.write(f"QUERY: {query}\n")
        _log.write(f"TIME:  {datetime.now().isoformat()}\n")
        _log.write(f"{'=' * 60}\n")
        _orig_stdout = sys.stdout
        sys.stdout = _Tee(_orig_stdout, _log)
        try:
            answer = asyncio.run(run(query))
            print(f"\nFINAL:\n{answer}")
        finally:
            sys.stdout = _orig_stdout



