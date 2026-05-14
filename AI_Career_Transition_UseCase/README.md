# Career AI Transition Agent

An AI agent that builds a personalized, week-by-week learning plan to transition from any current role into a target tech career.

Powered by **gemini-2.5-flash-lite** with:
- Native function calling
- MCP (Model Context Protocol)
- Structured multi-step reasoning
- Tool-based planning and verification
- Full observability tracing

---

# Features

- Native Gemini function calling (no JSON prompting)
- MCP-based dynamic tool discovery
- Structured multi-step reasoning with mandatory execution order
- SELF_CHECK verification after every tool call
- Parallel tool execution using `asyncio.TaskGroup`
- Streamlit UI with expandable tool traces
- Pydantic-validated tool inputs
- Dependency-aware learning schedule generation
- Feasibility checking and automatic replanning
- AgentTrace observability with latency + token tracking
- Gemini implicit cache visibility (`cached_content_token_count`)

---

# Architecture

```text
                ┌────────────────────┐
                │      User Input    │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │      Gemini        │
                │ Native Tool Calling│
                └─────────┬──────────┘
                          │ function_call
                          ▼
                ┌────────────────────┐
                │    MCP Server      │
                │  (mcp_server.py)   │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │      tools.py      │
                │ Pydantic Validation│
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │   _impl_* Logic    │
                │  Pure Business     │
                │      Logic         │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Function Response  │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │      Gemini        │
                │ SELF_CHECK + Plan  │
                └────────────────────┘
```

---

# How It Works

The agent follows a mandatory multi-step execution order.

Every step:
1. Explains reasoning
2. Calls a tool
3. Performs a SELF_CHECK
4. Continues only if the result is valid

---

## Execution Flow

```text
Step 1  show_reasoning
        Parse user input (Logical)

Step 2  skill_gap_analysis
        Identify missing skills

Step 3  show_reasoning
        Estimate hours per skill (Lookup)

Step 4  allocate_learning_hours
        Build dependency-aware learning schedule

Step 5  show_reasoning
        Calculate total hours vs available (Arithmetic)

Step 6  check_feasibility
        Check whether plan fits timeline

        ↓ feasible?

Step 7  verify
        Confirm arithmetic correctness

Step 8  Final text response
        Present week-by-week learning plan

        ↓ not feasible?

Step 7  fallback_reasoning
        Explain the shortfall

Step 8  replan_with_constraints
        Drop lowest-priority skills

Step 9  Final text response
        Present revised feasible plan
```

---

# SELF_CHECK Verification

After every tool result, Gemini must verify whether the result makes sense before proceeding.

Example:

```text
SELF_CHECK: yes — 330 hours needed and 390 available
(15 hrs/week × 26 weeks), so the plan is feasible.

SELF_CHECK: no — 520 hours needed but only 260 available,
shortfall of 260 hours, replanning required.
```

This forces the model to:
- inspect outputs
- sanity-check arithmetic
- detect infeasible plans
- explicitly reason about correctness

---

# Project Structure

```text
career_ai_transition/
├── main.py
├── mcp_server.py
├── app.py
├── tools.py
├── schemas.py
├── prompts.py
├── evaluator.py
├── pyproject.toml
└── .env
```

---

# File Responsibilities

| File | Responsibility |
|---|---|
| `main.py` | MCP client + Gemini agent loop + observability |
| `mcp_server.py` | Exposes tools as MCP tools over stdio |
| `app.py` | Streamlit UI for interactive execution traces |
| `tools.py` | Tool registry + business logic |
| `schemas.py` | Pydantic validation schemas |
| `prompts.py` | System prompt + reasoning rules |
| `evaluator.py` | Prompt evaluation helper |

---

# Tool Data Flow

```text
Gemini (function_call args)
        ↓
mcp_server.py
        ↓
call_tool(name, args)
        ↓
tools.py public function
        ↓
Pydantic model_validate(args)
        ↓
_impl_*() function
        ↓
json.dumps(result)
        ↓
Gemini function_response
        ↓
SELF_CHECK
```

---

# Available Tools

| Tool | Purpose |
|---|---|
| `show_reasoning` | Forces explicit reasoning before every action |
| `skill_gap_analysis` | Finds missing skills for target role |
| `allocate_learning_hours` | Creates dependency-aware learning schedule |
| `check_feasibility` | Determines whether timeline is realistic |
| `replan_with_constraints` | Drops low-priority skills to fit deadline |
| `verify` | Confirms arithmetic/logical correctness |
| `fallback_reasoning` | Handles failures or infeasible plans |

---

# Knowledge Base

## Supported Roles

- Data Scientist
- ML Engineer
- Data Analyst
- AI Researcher
- Business Analyst

---

## Skill Hours

| Skill | Hours |
|---|---|
| Python | 80 |
| SQL | 40 |
| Statistics | 60 |
| Machine Learning | 100 |
| Deep Learning | 120 |
| Data Visualization | 50 |
| Spark | 80 |
| NLP | 80 |
| Cloud (AWS/GCP) | 60 |

---

## Skill Dependencies

```text
Python
 ├── Machine Learning
 ├── Deep Learning
 ├── NLP
 └── Spark

Statistics
 └── Machine Learning

Machine Learning
 ├── Deep Learning
 ├── NLP
 └── Computer Vision

SQL
 └── Spark
```

The scheduler respects all dependencies automatically.

---

# Observability

The agent records every:
- LLM request
- Tool call
- Tool result
- Token count
- Cache hit
- Latency measurement

All execution metadata is captured using `AgentTrace`.

---

## Example Trace Summary

```text
══════════════════════════════════════════════════════════════
AGENT TRACE SUMMARY
──────────────────────────────────────────────────────────────
LLM calls   : 5
Tool calls  : 7
Tokens in   : 4821
Tokens out  : 1032
Cached      : 2910
Total ms    : 8421
──────────────────────────────────────────────────────────────
```

---

# Example Agent Trace

```text
[LOGICAL] Parsing user background and constraints

SELF_CHECK: yes — user input includes role,
timeline, target role, and weekly hours.

→ TOOL: skill_gap_analysis

Result:
{
  "missing_skills": [
    "Python",
    "Statistics",
    "Machine Learning"
  ]
}

SELF_CHECK: yes — identified skills match
Data Scientist requirements.

→ TOOL: allocate_learning_hours

Result:
{
  "total_hours": 240,
  "total_weeks": 16
}

SELF_CHECK: yes — dependencies respected,
Python scheduled before Machine Learning.
```

---

# Why MCP?

Using MCP (Model Context Protocol) decouples the agent from tool implementations.

Benefits:
- Dynamic runtime tool discovery
- No hardcoded schemas in the agent loop
- Easy addition/removal of tools
- Cleaner separation of orchestration and execution
- Interoperability with other MCP-compatible systems

The agent never hardcodes tool definitions —
it discovers them directly from the MCP server.

---

# Why Native Gemini Tool Calling?

The agent uses Gemini's native `FunctionDeclaration` mechanism instead of prompting the model to generate JSON.

Advantages:
- Structured schema enforcement
- Higher reliability
- Better argument validation
- Less hallucinated tool syntax
- Stronger execution consistency

Gemini receives actual typed tool schemas instead of text instructions.

---

# Why Pydantic Validation?

Gemini-generated tool arguments are external input and may be malformed.

Pydantic:
- validates types
- catches missing fields
- prevents invalid tool execution
- ensures clean inputs before business logic runs

Validation occurs before entering `_impl_*()` logic.

---

# Why `show_reasoning` Before Every Action?

The `show_reasoning` tool forces Gemini to:
- explicitly explain its reasoning
- classify the reasoning type
- think before acting

Reasoning types:
- Logical
- Arithmetic
- Lookup

This improves:
- transparency
- debuggability
- hallucination resistance
- trace readability

---

# Setup

## Requirements

- Python 3.11+
- uv package manager
- Gemini API key

---

## Installation

```bash
# Clone repository
git clone <your_repo_url>

cd career_ai_transition

# Copy environment file
cp .env.example .env
```

Edit `.env`:

```env
GEMINI_API_KEY=your_api_key_here
```

---

## Install Dependencies

```bash
uv sync
```

---

# Run the Terminal Agent

```bash
uv run main.py
```

This mode includes:
- interactive pauses
- reasoning traces
- tool traces
- observability summaries

---

# Run the Streamlit UI

```bash
streamlit run app.py
```

The UI displays:
- tool inputs
- tool outputs
- SELF_CHECK lines
- expandable execution cards

---

# Example Queries

## Example 1

```text
I am a Marketing Manager with skills in Excel,
PowerPoint, and project management.

I want to become a Data Scientist in 6 months.
I can study 15 hours per week.
```

---

## Example 2

```text
I am a nurse with skills in Excel
and basic data reporting.

I want to become an ML Engineer in 4 months.
I can study 10 hours per week.
```

---

# Key Design Decisions

## Dynamic Tool Discovery

Tools are defined once in `mcp_server.py`
and discovered dynamically at runtime.

The agent loop never hardcodes:
- tool names
- tool schemas
- parameter definitions

---

## Parallel Tool Execution

Tool calls are executed concurrently using:

```python
asyncio.TaskGroup
```

This allows Gemini to request multiple tools in parallel while maintaining synchronized result collection.

---

## Pure Logic Separation

`tools.py` separates:
- validation
- orchestration
- business logic

Architecture:

```text
Gemini Tool Function
        ↓
Pydantic Validation
        ↓
_impl_*() Logic
```

This makes logic:
- testable
- reusable
- deterministic

---

# Safety Notes

- Tool inputs are validated with Pydantic
- Tool outputs come from trusted internal logic
- MCP server runs locally over stdio
- `verify()` currently uses Python `eval()`
  and should be sandboxed in production

---

# Future Improvements

- RAG-based real job market skill retrieval
- Course recommendation engine
- Persistent memory across sessions
- Multi-agent planning + verification
- Cost-aware planning
- OpenTelemetry / LangSmith integration
- Real-time labor market APIs
- Adaptive skill-hour estimation
- Human approval checkpoints

---

# Tech Stack

- gemini-2.5-flash-lite
- MCP (Model Context Protocol)
- Streamlit
- Pydantic
- asyncio.TaskGroup
- Python 3.11
- uv package manager

---

# License

MIT License

