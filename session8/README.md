# EAGV3 Session 8 — Student Scaffolding

Multi-agent growing-graph orchestrator built on the Session 7 cognitive
architecture. The graph itself is the agent loop: each node is a typed
skill (Planner, Researcher, Distiller, Critic, Formatter, …), edges
carry the predecessor's `AgentResult`, and the runtime executes ready
nodes in parallel via `asyncio.gather`.

Your assignment is to ship one missing skill (the **Coder**) so the
agent can write code, run it in a subprocess sandbox, and feed the
result back through the graph. Full spec in [ASSIGNMENT.md](ASSIGNMENT.md).

---

## Layout

```
S8SharedCode/
├── README.md          ← you are here
├── ASSIGNMENT.md      ← what you implement, how it gets graded
├── .env.example       ← copy to .env, fill in keys you have
├── .gitignore
│
├── code/              ← the agent. Run from here.
│   ├── flow.py        ← orchestrator (Graph + Executor + CLI). Read this first.
│   ├── skills.py      ← skill registry, prompt rendering, run_skill
│   ├── recovery.py    ← failure classification + critic-fail splice
│   ├── persistence.py ← session writes (graph.json + per-node JSON)
│   ├── mcp_runner.py  ← multi-turn tool-use loop wrapper
│   ├── sandbox.py     ← subprocess Python runner (usability boundary; NOT security)
│   ├── replay.py      ← stdin-driven trace viewer
│   ├── schemas.py     ← AgentResult, NodeSpec, NodeState, MemoryItem, …
│   ├── agent_config.yaml  ← skills catalogue (this is where you confirm Coder wiring)
│   ├── prompts/       ← one .md per skill. You edit coder.md.
│   ├── tests/         ← starts with test_recovery.py; you add yours.
│   ├── mcp_server.py  ← MCP tools: web_search, fetch_url, search_knowledge, …
│   ├── memory.py / vector_index.py / artifacts.py  ← S7 carryover (don't touch)
│   ├── perception.py / decision.py / action.py     ← S7 carryover (don't touch)
│   └── sandbox/papers/  ← five arxiv abstracts for indexed-corpus queries
│
└── gateway/           ← LLM Gateway V8 (FastAPI). Runs on :8108.
    ├── main.py
    ├── client.py      ← the SDK code/gateway.py imports from
    ├── providers.py / router.py / embedders.py / db.py / cache.py
    ├── agent_routing.yaml  ← agent → preferred provider mapping
    ├── pyproject.toml
    └── run.sh
```

---

## Quickstart

You need: Python 3.11+, [uv](https://docs.astral.sh/uv/), Ollama
(`brew install ollama` then `ollama pull nomic-embed-text`), and at least
one provider API key from `.env.example`.

```bash
# 1. Secrets
cp .env.example .env
$EDITOR .env                  # add the keys you have

# 2. Install
cd gateway && uv sync && cd ..
cd code    && uv sync && cd ..

# 3. Start the gateway (one terminal)
cd gateway && uv run main.py
# (or: ./run.sh)
# It boots on http://localhost:8108; /v1/routers should answer.

# 4. Run the agent (another terminal)
cd code
uv run python flow.py "hello"
```

A successful first run prints two node lines (planner, formatter) and a
greeting. Sessions land in `code/state/sessions/<sid>/`. Walk one with:

```bash
uv run python replay.py <sid>
```

---

## How to think about the architecture

The Planner reads the user query and emits a small DAG of skill nodes
to run. Each ready node fires through the gateway in parallel with its
ready siblings. When a skill's yaml entry has `internal_successors`,
the orchestrator appends those automatically — that's how **Coder →
SandboxExecutor** chains without the Planner having to ask for it.

Critic nodes get auto-inserted on edges out of skills tagged
`critic: true` in `agent_config.yaml` (currently Distiller). A
verdict=fail from a Critic splices a recovery Planner into the graph,
capped at one re-plan per branch.

Failure handling is in `recovery.py`. Transient gateway errors don't
re-plan (the gateway already retries); validation errors don't re-plan
(it's a prompt bug); upstream-failures do. `tests/test_recovery.py`
pins the classifier against the actual gateway error strings.

Read `flow.py`'s 300 lines top-to-bottom before you write a single
line of your Coder prompt. The orchestrator is small enough to fit in
your head.

---

## When things go wrong

| symptom | first place to look |
|---|---|
| `[gateway] launching … failed to start within 45s` | `cd gateway && uv run main.py` in another terminal; read its stderr. Probably a missing API key or port :8108 already taken. |
| `httpx.HTTPStatusError: '503 Service Unavailable'` | All worker providers in cooldown / unconfigured. Add another key to `.env` or wait a minute. |
| coder ran but `sandbox_executor` reports `no code in upstream coder output` | Your prompt isn't emitting the JSON shape the orchestrator expects. See ASSIGNMENT.md §"Output contract". |
| The final answer is short / wrong | Run `replay.py <sid>` and inspect what each node actually saw (the `prompt_sent` field captures the exact bytes sent to the gateway). |

---

## What NOT to touch

- `agent7_s7_carryover.py` (if present) — the Session 7 single-loop agent kept for reference. Out of scope.
- `perception.py`, `decision.py`, `action.py`, `memory.py`,
  `vector_index.py`, `artifacts.py`, `mcp_server.py` — carry over
  byte-identical from Session 7. The tool-blindness contract on
  Perception depends on these staying as-is.
- `gateway/` — treat as a service you call. If you find a real bug,
  open an issue; do not patch it inside your assignment.

---

## Provenance and version

This package is the Session 8 build that passes the round-3 review.
22 unit tests cover the failure-recovery + critic-splice mechanics.
Five validation queries (hello, S7 carryover Shannon, parallel fan-out
populations, graceful-fail nonexistent path, SIGKILL+resume) have been
verified end-to-end on the same code you have here.

If your `uv run python flow.py "hello"` produces a final answer, the
build runs cleanly on your machine. The next step is ASSIGNMENT.md.


## Youtube link:
https://youtu.be/lwlYoyb3NwE

## Traces:
srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it." 

══════════════════════════════════════════════════════════════════════════════
session s8-1626bd1f  ─  query: Read /nonexistent/path.txt and tell me what's in it.
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (15.9s)
[06/01/26 08:12:30] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 08:12:33] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 08:12:54] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 08:13:14] INFO     Processing request of type CallToolRequest                                server.py:727
[n:2] researcher         complete (98.2s)
[n:3] formatter          complete (8.4s)

══════════════════════════════════════════════════════════════════════════════
FINAL: I'm sorry, but the file /nonexistent/path.txt does not exist.
══════════════════════════════════════════════════════════════════════════════

srinivasmukka@Srinivass-Mac-mini code % clear
srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "hello"

══════════════════════════════════════════════════════════════════════════════
session s8-932436a8  ─  query: hello
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (16.8s)
[n:2] formatter          complete (4.4s)

══════════════════════════════════════════════════════════════════════════════
FINAL: Hello! It seems like you've just said hello.
══════════════════════════════════════════════════════════════════════════════

srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."

══════════════════════════════════════════════════════════════════════════════
session s8-400450ff  ─  query: Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (18.5s)
[n:2] researcher         complete (25.3s)
[n:3] distiller          complete (10.5s)
[n:4] formatter          complete (9.5s)

══════════════════════════════════════════════════════════════════════════════
FINAL: Claude Shannon was born on April 30, 1916, and he died on February 24, 2001. Three key contributions he made to information theory are: 
1. Mathematical Theory of Communication
2. Invention of Shannon's Information Theory
3. Concept of bit and binary digit.
══════════════════════════════════════════════════════════════════════════════

srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it." 

══════════════════════════════════════════════════════════════════════════════
session s8-efd5bc6c  ─  query: Read /nonexistent/path.txt and tell me what's in it.
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (16.2s)
[06/01/26 10:12:12] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:12:14] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 10:12:33] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:12:53] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:13:07] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:13:20] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:13:43] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:14:05] INFO     Processing request of type CallToolRequest                                server.py:727
[n:2] researcher         complete (127.1s)
[n:3] formatter          complete (5.6s)

══════════════════════════════════════════════════════════════════════════════
FINAL: I'm sorry, but the file /nonexistent/path.txt does not exist.
══════════════════════════════════════════════════════════════════════════════

srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "Research the current population of New York, Tokyo, and London and tell me which city has the highest population."

══════════════════════════════════════════════════════════════════════════════
session s8-e72b2b8f  ─  query: Research the current population of New York, Tokyo, and London and tell me which city has the highest population.
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (25.2s)
[06/01/26 10:16:32] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:16:33] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:16:35] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:16:36] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 10:16:38] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 10:16:39] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 10:17:03] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:17:33] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:17:47] INFO     Processing request of type CallToolRequest                                server.py:727
[n:2] researcher         complete (102.4s)
[n:3] researcher         complete (54.3s)
[n:4] researcher         complete (19.2s)
[n:5] distiller          complete (15.6s)
[n:6] distiller          complete (20.9s)
[n:7] distiller          complete (10.2s)
[n:8] coder              complete (33.0s)
[n:9] formatter          complete (5.7s)
[n:10] sandbox_executor   failed   (0.0s)  err=no code in upstream coder output
  ↪ recovery (upstream_failure): planner node n:11 queued for n:10
[n:11] planner            complete (21.5s)
[06/01/26 10:19:36] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:19:37] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:19:40] INFO     Processing request of type ListToolsRequest                               server.py:727
[06/01/26 10:19:41] INFO     Processing request of type ListToolsRequest                               server.py:727
[skills] researcher: 3 malformed NodeSpec(s) emitted.
  - successor={'url': 'https://www.google.com/search?q=current+population+of+tokyo', 'title': ''}  error=1 validation error for NodeSpec
skill
  Field required [type=missing, input_value={'url': 'https://www.goog...+of+tokyo', 'title': ''}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
  - successor={'url': 'https://www.google.com/search?q=current+population+of+new+york', 'title': ''}  error=1 validation error for NodeSpec
skill
  Field required [type=missing, input_value={'url': 'https://www.goog...+new+york', 'title': ''}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing
  - successor={'url': 'https://www.google.com/search?q=current+population+of+london', 'title': ''}  error=1 validation error for NodeSpec
skill
  Field required [type=missing, input_value={'url': 'https://www.goog...of+london', 'title': ''}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.13/v/missing


[06/01/26 10:20:36] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:21:00] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:21:09] INFO     Processing request of type CallToolRequest                                server.py:727

[06/01/26 10:21:23] INFO     Processing request of type CallToolRequest                                server.py:727

[06/01/26 10:21:46] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:22:08] INFO     Processing request of type CallToolRequest                                server.py:727
[n:12] researcher         complete (164.1s)
[n:13] researcher         failed   (28.6s)  err=researcher: 3 malformed NodeSpec(s) emitted.
  - successor={'url': 'https://www.
  ↪ n:13 failed (validation_error, skill=researcher): validation error (malformed NodeSpec); fix the prompt, not the run
[n:14] researcher         complete (49.5s)

══════════════════════════════════════════════════════════════════════════════
FINAL: The city with the highest current population among New York, Tokyo, and London is Tokyo.
══════════════════════════════════════════════════════════════════════════════

srinivasmukka@Srinivass-Mac-mini code % uv run python flow.py "Write a haiku about climate change. The haiku must have exactly 5 syllables in line 1, 7 in line 2, and 5 in line 3."

══════════════════════════════════════════════════════════════════════════════
session s8-2c59a24b  ─  query: Write a haiku about climate change. The haiku must have exactly 5 syllables in line 1, 7 in line 2, and 5 in line 3.
══════════════════════════════════════════════════════════════════════════════
[memory.read] 8 hit(s) visible to every skill this run
[n:1] planner            complete (17.5s)
[06/01/26 10:23:46] INFO     Processing request of type CallToolRequest                                server.py:727
[06/01/26 10:23:48] INFO     Processing request of type ListToolsRequest                               server.py:727
[n:2] researcher         complete (35.7s)
[n:3] distiller          complete (8.3s)
[n:4] formatter          complete (6.0s)

══════════════════════════════════════════════════════════════════════════════
FINAL: Earth warms, ice melts fast
Rising seas, storms take hold
Climate change, we must act
══════════════════════════════════════════════════════════════════════════════
