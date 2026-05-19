# 🚀 Session 6 — Four-Role Cognitive Agent (LLM Gateway + MCP Tools)

A deterministic multi-agent system built around a four-role cognitive architecture:

🧠 Memory · 👁 Perception · 🎯 Decision · ⚙️ Action

Each role is independently prompted, typed, and validated using PoP (Plan-of-Process) constraints, Pydantic schemas, and an LLM Gateway V3.

---

# 📌 Architecture


agent6.py → Main orchestration loop
│
├── memory.py → Retrieval + classification + persistence (state/)
├── perception.py → Goal decomposition + completion tracking
├── decision.py → Tool vs answer routing (single-goal reasoning)
├── action.py → MCP tool execution + artifact storage
├── artifacts.py → Sequential artifact store (art:1, art:2…)
├── gateway.py → LLM Gateway V3 client (structured output + retry)
├── schemas.py → Pydantic v2 contracts (strict typing)
└── mcp_server.py → 9 MCP tools via stdio


---

# 🧠 Core Design Principles

- Multi-turn memory via persistent `state/`
- Strict goal decomposition (no over-splitting)
- Deterministic tool routing (Decision module)
- Artifact-based large context handling
- PoP validation at every role boundary
- No tool duplication (anti-loop guarantees)

---

# 🧰 MCP Tools (9 total)

- web_search
- fetch_url
- get_time
- currency_convert
- read_file
- list_dir
- create_file
- update_file
- edit_file

---

# ⚙️ Setup

## Requirements

- Python 3.11+
- uv package manager
- LLM Gateway V3 running on http://localhost:8101

---

## Install dependencies

```powershell
uv sync
Environment variables

Create .env:

LLM_GATEWAY_URL=http://localhost:8101
TAVILY_API_KEY=your_key_here   # optional fallback

▶️ Running the Agent
uv run agent6.py "Your query here"
💾 State & Persistence
state/ → runtime memory (resettable)
runs.log → persistent execution logs (NOT deleted on reset)
artifacts/ → large content storage
Reset state
Remove-Item -Recurse -Force state\
mkdir state

🧪 Evaluation Queries
📍 Query A — Wikipedia Extraction
uv run agent6.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions."

Expected:

3 iterations
Artifact attached
No duplicate fetch
🌦 Query B — Weather Planning
uv run agent6.py "Plan a weekend trip to Mumbai. Check weather first and suggest activities."

Expected:

web_search usage
context-aware itinerary
3–4 iterations
🧠 Query C — Memory Persistence
Run 1
uv run agent6.py "My preferred coding language is Python and I want concise answers."
Run 2
uv run agent6.py "What is my preferred coding language?"

Expected:

No tool call in Run 2
Memory retrieval works
🌐 Query D — Multi-source Synthesis
uv run agent6.py "Search top uses of Claude Shannon’s information theory in modern tech and summarize from at least two sources."

Expected:

Multiple web_search calls
Cross-source synthesis
4–5 iterations
🧠 Prompt Design (PoP System)
👁 Perception
{
  "role": "Perception",
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true
}
🎯 Decision
{
  "role": "Decision",
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "internal_self_checks": true,
  "reasoning_type_awareness": true,
  "fallbacks": true,
  "invariants": [
    "exactly one of answer/tool_call is non-null",
    "tool_call arguments match schema",
    "no repeated fetch_url calls"
  ]
}
🔒 System Guarantees
No repeated fetch_url calls
No mixed answer + tool outputs
No cross-goal contamination
Deterministic routing
Structured memory persistence
Multi-turn reasoning continuity
📊 System Properties
Property	Status
Deterministic execution	✅
Tool safety	✅
Multi-turn memory	✅
Artifact isolation	✅
PoP compliance	✅
MCP integration	✅
🎥 Demo

YouTube Demo Link: add here

🚀 Future Work
LangGraph orchestration
Redis memory backend
Formal PoP verifier
Tool ranking system
Streaming reasoning traces