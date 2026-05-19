# Session 6 — Four-Role Cognitive Agent

A cognitive agent built on four single-responsibility roles: **Memory · Perception · Decision · Action**.  
Every LLM call routes through a local LLM Gateway. Tools are served via the MCP protocol over stdio.

---

## Architecture


agent6.py            ← main loop (max 12 iterations)
  ├── memory.py      ← keyword search + LLM classification, persists to state/
  ├── perception.py  ← goal decomposition + completion tracking
  ├── decision.py    ← answer or tool call for one goal at a time
  ├── action.py      ← MCP tool dispatch, stores large results as artifacts
  ├── artifacts.py   ← artifact store  (IDs: art:1, art:2, …)
  ├── gateway.py     ← LLM gateway client — structured output + retry
  ├── schemas.py     ← all Pydantic v2 contracts
  ├── mcp_server.py  ← 9 MCP tools via stdio
  └── llm_gateway/
        server.py    ← FastAPI gateway server (port 8101)


### Role responsibilities

| Role | LLM calls | Job |
|------|-----------|-----|
| Memory | 1 per write | Classify free-form text into typed items; keyword search is free |
| Perception | 1 per iteration | Decompose query into goals; track done flags; attach artifacts |
| Decision | 1 per iteration | For one goal: answer directly or call one MCP tool |
| Action | 0 | Dispatch MCP tool; store large results as artifacts |

### MCP Tools (mcp_server.py)

| Tool | Description |
|------|-------------|
| web_search | Tavily (950/mo cap) → DuckDuckGo fallback |
| fetch_url | crawl4ai with Wikipedia REST / MediaWiki / DBpedia fallbacks |
| get_time | IANA timezone support |
| currency_convert | frankfurter.dev |
| read_file / list_dir / create_file / update_file / edit_file | Sandboxed under ./sandbox/ |

---

## Prerequisites

- Python 3.11+
- An LLM backend (choose one below)

---

## LLM Backend Setup

The gateway server (llm_gateway/server.py) is the only file that changes between backends.

### Option A — Groq (recommended: fast, free tier)

1. Get a free API key at https://console.groq.com
2. Set .env:


env
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile


> Other available models: qwen-qwq-32b, mixtral-8x7b-32768

### Option B — Ollama (local)

1. Install Ollama and pull the model:


powershell
ollama pull qwen2.5:latest


2. Set .env:


env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:latest


### Optional extras (any backend)


env
TAVILY_API_KEY=your_key_here    # web_search primary source (falls back to DuckDuckGo)
GATEWAY_PORT=8101               # default


---

## Install & Run

### 1. Install dependencies


powershell
uv sync


Or with pip:


powershell
pip install fastapi uvicorn httpx pydantic python-dotenv mcp fastmcp tavily-python duckduckgo-search crawl4ai anyio


### 2. Start the LLM Gateway


powershell
python llm_gateway\server.py


Leave this running in a separate terminal.

### 3. Run the agent


powershell
python agent6.py "Your query here"


---

## Reset state between runs


powershell
Remove-Item -Recurse -Force state\
mkdir state


> runs.log lives outside state/ and is never deleted — it persists across resets.

---

## Test Queries

### Query A — Wikipedia fetch + extraction


powershell
python agent6.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."


Expected: 3 iterations. Perception attaches the fetched artifact to the extraction goal so Decision reads the page without re-fetching.

---

### Query B — Weather-constrained planning


powershell
python agent6.py "Plan a weekend trip to Mumbai. Check the current weather first and suggest activities that suit the conditions."


Expected: 3–4 iterations. Decision calls fetch_url for weather, then synthesises a plan.

---

### Query C — Durable memory (two separate runs)

**Run 1** — store a preference:


powershell
python agent6.py "My preferred coding language is Python and I always want concise answers."


**Run 2** — recall it (do NOT reset state between runs):


powershell
python agent6.py "What is my preferred coding language and how should answers be formatted?"


Expected: Run 2 answers from memory with zero tool calls.

---

### Query D — Multi-source synthesis


powershell
python agent6.py "Search for the top three uses of Claude Shannon's information theory in modern technology and summarise the findings from at least two sources."


Expected: 4–5 iterations. Perception decomposes into search + synthesis goals; Decision calls web_search multiple times; final answer synthesises across sources.

---

## Prompt Design & PoP Validation

### Perception — _SYSTEM ([perception.py](perception.py))

**What it does:** Decomposes the user query into 1–4 bounded goals, updates done flags monotonically, and attaches an artifact to the first unfinished goal if needed.

**PoP Validation JSON:**


json
{
  "role": "Perception",
  "temperature": 1.0,
  "output_schema": "PerceptionOutput { goals: list[GoalDraft { text, done, artifact_index }] }",
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true,
  "overall_clarity": "Excellent structure. Obligations are ordered and labelled with reasoning types (planning, verification, lookup). SELF-CHECK block enforces output integrity. Hallucination defences (positional goal identity, integer artifact index) prevent LLM-fabricated handles."
}


**Hallucination defences:**
- Goals have no id in LLM output — the loop owns IDs by position
- artifact_index is an integer, never a raw art:N string — loop resolves it
- artifacts.exists() gate in the loop silently drops bad indices

---

### Decision — _SYSTEM ([decision.py](decision.py))

**What it does:** For one goal at a time — either answers directly from memory/artifacts or calls exactly one MCP tool. Never sees other goals.

**PoP Validation JSON:**


json
{
  "role": "Decision",
  "temperature": 0.7,
  "output_schema": "DecisionOutput { answer: str|null, tool_call: ToolCall|null }",
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true,
  "overall_clarity": "Strong invariant enforcement — exactly one of answer/tool_call is non-null. Memory-first rule prevents redundant tool calls. Known reliable endpoints list reduces web_search failures. Web search failure rule (switch to fetch_url after one empty result) prevents wasted iterations."
}


**Key invariants:**
- Exactly one of answer / tool_call is non-null — never both, never neither
- tool_call.arguments must match the tool's inputSchema exactly
- Never calls read_file with an artifact ID — artifacts are injected automatically

---

## Validate Prompts

Runs the Session 5 PoP evaluator against both prompts and exits 1 if any claimed criterion fails:


powershell
python validate_prompts.py


## Youtube Video Link:
https://www.youtube.com/watch?v=HJSyMvW1lQM