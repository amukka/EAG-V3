# Session 8 Test & Demo Guide

This guide shows how to test and demonstrate all assignment components.

## Prerequisites

```bash
# 1. Install dependencies
cd session8
cp .env.example .env
# Edit .env and add any API keys you have
# Minimum: OLLAMA_URL + at least one LLM provider

cd code && uv sync && cd ..
cd gateway && uv sync && cd ..

# 2. Start the gateway (Terminal 1)
cd session8/gateway
uv run main.py
# Should show: "[gateway] Listening on :8108"

# 3. Ready for agent tests (Terminal 2)
cd session8/code
```

---

## Part 1: Five Base Queries

Run each query in Terminal 2 and verify the output.

### Test 1.1: Hello

```bash
uv run python flow.py "hello"
```

**Expected output:**
- Two nodes: planner → formatter
- Final answer: greeting (e.g., "Hello! How can I help?")
- Wall-clock: < 5s

**Log inspection:**
```bash
ls -t state/sessions/ | head -1  # Get most recent session ID
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID
```

---

### Test 1.2: Claude Shannon (Query A)

```bash
uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
```

**Expected output:**
- researcher fetches Wikipedia
- distiller extracts birth, death, contributions
- formatter synthesizes answer
- Final answer includes: 1916-2001 (or similar), three contributions

**Log inspection:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep -E "researcher|distiller|formatter" -A 5
```

---

### Test 1.3: City Populations (Query I) - Parallel Fan-Out

```bash
uv run python flow.py "Tell me the current population of New York, Tokyo, and London"
```

**Expected output:**
- Three researcher nodes run in parallel
- All finish before formatter
- Final answer lists populations with sources
- Wall-clock ≈ time for one researcher (not 3x)

**Parallel execution verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep "status" | sort | uniq -c
# Should show multiple nodes with status "complete" at similar depths

# Check graph structure
python3 << 'EOF'
import json
with open(f"state/sessions/{SID}/graph.json") as f:
    g = json.load(f)
    nodes = g.get("nodes", {})
    researchers = [n for n in nodes.values() if n.get("skill") == "researcher"]
    print(f"Found {len(researchers)} researcher nodes (expected 3)")
    print("Researcher inputs:", [n.get("inputs") for n in researchers])
EOF
```

---

### Test 1.4: Nonexistent Path (Query J)

```bash
uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."
```

**Expected output:**
- Agent gracefully reports file not found
- Does NOT invent content
- Final answer explicitly states error

**Failure handling verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep -E "failed|error|recovery" -B 2 -A 2
# Should show recovery path or honest error message
```

---

### Test 1.5: Growth Rate Analysis (Query K)

```bash
uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"
```

**Expected output:**
- Three researcher nodes (parallel) fetch city data
- coder node generates Python to compute growth rates
- sandbox_executor runs the code
- formatter synthesizes: populations, growth rates, fastest growing city

**Coder verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep -A 20 "\"skill\": \"coder\""
# Should show coder.output.code contains Python code
# Should show sandbox_executor.output.exit_code == 0 and meaningful stdout
```

---

## Part 2: Pattern Tests

### Test 2.1: Parallel Fan-Out (3+ independent tasks)

```bash
uv run python flow.py "Compare the populations of Tokyo, Mumbai, Shanghai, and Mexico City. Which is largest?"
```

**Verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID

# Key checks:
# 1. Four researcher nodes at same depth
# 2. All run before formatter
# 3. Final answer compares all four correctly
# 4. Wall-clock < 20s (not 80s for sequential)
```

---

### Test 2.2: Critic Verdict (Pass and Fail)

**First run (should pass):**
```bash
uv run python flow.py "Write a haiku about artificial intelligence. It MUST be exactly 5-7-5 syllables."
```

**Verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep -A 5 "critic"
# Look for: "verdict": "pass"
```

**Second test (construct a fail scenario):**
Edit the query or constraints to verify Critic failure triggers recovery:
```bash
# If first run had 6-7-5 syllables instead of 5-7-5,
# Critic should fail and recovery planner should be invoked
uv run python flow.py "Write a haiku about AI that is exactly 3-5-7 syllables (unusual format)."
# Critic will likely fail due to impossibility, triggering recovery
```

---

### Test 2.3: Coder Computational Query

```bash
# Create a computational query
uv run python flow.py "Given these populations: New York (8.3 million), Tokyo (13.9 million), Shanghai (24.2 million), Delhi (16.7 million), São Paulo (11.4 million) — compute the average population and show the cities sorted by population (largest first)."
```

**Verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID

# Key checks:
# 1. Look for coder node with code field containing Python
# 2. Check sandbox_executor output:
#    - exit_code: 0
#    - stdout contains computed average and sorted list
#    - NO errors/stderr
# 3. formatter.final_answer includes the computed results
```

**Example Coder output:**
```json
{
  "code": "import json\npopulations = {'New York': 8.3, 'Tokyo': 13.9, ...}\nvalues = list(populations.values())\navg = sum(values) / len(values)\nprint(f'Average: {avg:.1f}M')\nsorted_cities = sorted(populations.items(), key=lambda x: x[1], reverse=True)\nfor city, pop in sorted_cities:\n    print(f'{city}: {pop}M')",
  "rationale": "Computes mean population and sorts cities"
}
```

---

## Part 3: New Skill Test

Add your new skill to `agent_config.yaml` and test with a query that exercises it.

### Example: Comparator Skill

**Edit agent_config.yaml:**
```yaml
comparator:
  prompt: prompts/comparator.md
  tools_allowed: []
  temperature: 0.3
  max_tokens: 1200
  description: Compares multiple items across dimensions and ranks them.
```

**Create prompts/comparator.md:**
```markdown
You are the Comparator skill. You receive structured data about multiple items
and produce a ranked comparison.

Procedure:
1. Read INPUTS containing data about N items
2. Identify comparison dimensions from USER_QUERY
3. Rank items by the specified dimension
4. Output a structured comparison

Output (JSON, no markdown):
{
  "comparisons": [{"item": "...", "rank": N, "score": X}],
  "rationale": "..."
}
```

**Test query:**
```bash
uv run python flow.py "Compare Rome, Paris, and Berlin. Which has the most historical monuments? Rank them."
```

**Verification:**
```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID | grep "comparator" -A 10
# Should show comparator node and its output
```

---

## Part 4: Unit Tests

```bash
cd session8/code

# Run existing unit tests
uv run pytest tests/ -v

# Expected: test_recovery.py tests pass
# These test the failure classification and recovery system
```

---

## Part 5: Session Replay & Inspection

For any session, use replay to see detailed execution:

```bash
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID

# This shows:
# - Graph structure (nodes, edges, skills)
# - Per-node inputs, outputs, prompts sent, timing
# - Critic verdicts
# - Recovery paths
```

**Key files in state/sessions/<SID>/:**
```
├── session.json        # Session metadata
├── graph.json          # Final graph structure
└── nodes/
    ├── n:1.json        # Node 1: planner
    ├── n:2.json        # Node 2: researcher
    └── ...
```

---

## Demo Script (for YouTube recording)

```bash
#!/bin/bash
# Run this to generate demo output

cd session8/code

echo "=== Query 1: hello ==="
uv run python flow.py "hello"

echo -e "\n=== Query 2: Claude Shannon ==="
uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."

echo -e "\n=== Query 3: City Populations ==="
uv run python flow.py "Tell me the current population of New York, Tokyo, and London"

echo -e "\n=== Query 4: Nonexistent Path ==="
uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."

echo -e "\n=== Query 5: Growth Rate Analysis ==="
uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"

echo -e "\n=== Done ==="
```

---

## Troubleshooting

| Issue | Debug |
|-------|-------|
| Gateway not starting | Check `.env` has at least one LLM key; check port 8108 not in use |
| "no code in upstream coder output" | Check coder.output.code field exists and is non-empty |
| Coder produces invalid JSON | Check the prompt is not adding markdown fences |
| Critic never runs | Verify distiller is upstream; check agent_config has `critic: true` on distiller |
| Parallel nodes run sequentially | Check Planner is emitting sibling nodes with independent inputs |
| Session not persisting | Check `state/sessions/` directory exists and is writable |

