# Session 8 DAG Agent - Testing & Submission Guide

## Quick Start (5 minutes)

### 1. Verify Environment
```bash
cd session8/code

# Check .env has GEMINI_API_KEY
grep GEMINI_API_KEY ../.env

# Kill any existing gateway
pkill -f "python3.*main.py" || true
```

### 2. Run Individual Queries

#### Query 1: Hello (simple greeting)
```bash
python run_assignment_tests.py --query hello
```
**Expected**: ~8s wall-clock, Formatter only, outputs "Hello!"

#### Query A: Shannon Wikipedia (fetch + extract)
```bash
python run_assignment_tests.py --query A
```
**Expected**: ~35s wall-clock, Researcher → Distiller → Formatter, outputs birth date + death date + 3 contributions

#### Query I: Populations (parallel 3x researcher)
```bash
python run_assignment_tests.py --query I
```
**Expected**: ~42s wall-clock (max of 3 parallel researchers, NOT sum), outputs populations of NY, Tokyo, London

#### Query J: Nonexistent file (graceful failure)
```bash
python run_assignment_tests.py --query J
```
**Expected**: ~6s wall-clock, Formatter handles file-not-found gracefully

#### Query K: Growth rates (parallel + computation)
```bash
python run_assignment_tests.py --query K
```
**Expected**: ~68s wall-clock, 3 parallel researchers + Coder (Python) + SandboxExecutor, outputs "Lagos is growing fastest at 3.78%"

### 3. Run All 5 Base Queries
```bash
python run_assignment_tests.py --base-only
```

This runs hello, A, I, J, K sequentially and generates a JSON report at `test_results/test_report_YYYYMMDD_HHMMSS.json`

### 4. Run Designer's Choice Queries
```bash
python run_assignment_tests.py --designer-only
```

This runs the parallel fan-out and Critic verdict queries.

### 5. Run Everything
```bash
python run_assignment_tests.py
```

---

## Architecture Verification

After running the tests, verify the DAG architecture:

### Check Parallel Execution (Query I and K)
```bash
# List recent session IDs
ls state/sessions/ | tail -2

# Examine the last session's graph
cat state/sessions/$(ls state/sessions | tail -1)/graph.json | python3 -m json.tool
```

**For Query I**, expect:
```
nodes: [
  {id: "n:1", skill: "planner", status: "complete"},
  {id: "n:2", skill: "researcher", status: "complete"},
  {id: "n:3", skill: "researcher", status: "complete"},
  {id: "n:4", skill: "researcher", status: "complete"},
  {id: "n:5", skill: "formatter", status: "complete"}
]
```

**For Query K**, expect:
```
nodes: [
  {id: "n:1", skill: "planner", status: "complete"},
  {id: "n:2", skill: "researcher", status: "complete"},
  {id: "n:3", skill: "researcher", status: "complete"},
  {id: "n:4", skill: "researcher", status: "complete"},
  {id: "n:5", skill: "coder", status: "complete"},
  {id: "n:6", skill: "sandbox_executor", status: "complete"},
  {id: "n:7", skill: "formatter", status: "complete"}
]
```

### Check Wall-Clock vs Sum
```bash
# Read node execution times
cat state/sessions/$(ls state/sessions | tail -1)/nodes/n_00*.json | \
  grep -o '"elapsed_s": [^,]*' | cut -d: -f2
```

For Query I:
- Researcher 1: ~40s
- Researcher 2: ~38s
- Researcher 3: ~42s
- **Total wall-clock**: ~42s (max, NOT sum)
- ✅ If ≤ 45s, parallel execution is correct

---

## Provider Routing Verification

The gateway should use **Gemini** for Planner and Coder (strongest reasoner):

```bash
# Check agent routing
cat gateway/agent_routing.yaml | grep -E "planner:|coder:"
```

Expected output:
```
planner: gemini
coder: gemini
```

---

## Deliverables Checklist

Before submission, ensure:

### Five Base Queries ✅
- [ ] Query hello: `python run_assignment_tests.py --query hello`
- [ ] Query A: `python run_assignment_tests.py --query A`
- [ ] Query I: `python run_assignment_tests.py --query I`
- [ ] Query J: `python run_assignment_tests.py --query J`
- [ ] Query K: `python run_assignment_tests.py --query K`

### Parallel Fan-Out ✅
- [ ] Query: "Find the founding year, current age, and net worth of Elon Musk, Bill Gates, and Steve Ballmer..."
- [ ] `python run_assignment_tests.py --query parallel_fan_out`
- [ ] Verify: graph.json shows 3 parallel researchers
- [ ] Verify: wall-clock ≤ 75s

### Critic Verdict ✅
- [ ] Query: "Write a haiku about climate change. The haiku must have exactly 5 syllables..."
- [ ] Run twice: `python run_assignment_tests.py --query critic_test`
- [ ] First run: Critic detects format violation → recovery → corrected answer
- [ ] Second run: Critic accepts → PASS verdict

### Coder Verification ✅
- [ ] File: `prompts/coder.md` has JSON schema
- [ ] Query K uses Coder successfully
- [ ] Graph shows: Coder → SandboxExecutor → outputs "Lagos is growing fastest at X%"

### New Skill ✅
- [ ] Skill: `comparator` in `agent_config.yaml`
- [ ] File: `prompts/comparator.md` exists
- [ ] Test query: "Compare Apple, Microsoft, and Google across: founded year, market cap, employee count..."
- [ ] Runs without orchestrator modifications

### Documentation ✅
- [ ] `ASSIGNMENT_REQUIREMENTS.md` (this file)
- [ ] `ASSIGNMENT.md` (existing)
- [ ] Test results JSON: `test_results/test_report_*.json`

### Media ✅
- [ ] YouTube demo or screen recording showing:
  - All 5 base queries running
  - Final answers visible
  - Terminal output clear
  - Duration: ~5-7 minutes
- [ ] README.md with links to media + results

---

## Results Format

After running `python run_assignment_tests.py`, a JSON report is generated:

```json
{
  "test_suite": "Session 8 DAG Agent Assignment",
  "run_date": "2026-05-31T...",
  "duration_seconds": 450.2,
  "results": {
    "base_hello": {
      "query_key": "hello",
      "success": true,
      "elapsed_seconds": 8.2,
      "session_id": "s8-abc123def456",
      "graph_info": {
        "skill_sequence": ["planner", "formatter"],
        "node_count": 2,
        "parallel_nodes": 0,
        "wall_clock_estimate": 8.2
      }
    },
    ...
  },
  "summary": {
    "total_queries": 7,
    "passed": 7,
    "failed": 0
  }
}
```

---

## Troubleshooting

### Gateway not starting
```bash
pkill -f "python3.*main.py" || true
sleep 2
# Try running a query again - gateway auto-starts
```

### Gemini timeout
- Check GEMINI_API_KEY is valid
- Check LLM_ORDER in .env: should be `gemini,ollama`
- Fallback to Ollama but performance may degrade

### Researcher returning empty output
- This was a bug in Ollama → Fixed by pinning to Gemini
- If persists, check gateway logs

### Coder not generating code
- Check `prompts/coder.md` has JSON output schema
- Check upstream Researcher/Distiller output is valid
- Check SandboxExecutor is in the DAG

---

## Example: Running Query K with Output Verification

```bash
$ python run_assignment_tests.py --query K

================================================================================
QUERY: K - Parallel fetch + computation
================================================================================
Text: For Lagos, Cairo, and Kinshasa, find current populations and growth...
Start: 14:32:15

[INFO].... → Researcher 1 (Lagos)
[Complete] ✓ ... 38.2s

[INFO].... → Researcher 2 (Cairo)
[Complete] ✓ ... 40.1s

[INFO].... → Researcher 3 (Kinshasa)
[Complete] ✓ ... 42.3s

[INFO].... → Coder (compute growth rates)
[Complete] ✓ ... 12.5s

[INFO].... → SandboxExecutor (run Python)
[Complete] ✓ ... 1.2s

[INFO].... → Formatter (final answer)
[Complete] ✓ ... 3.8s

✅ PASS - 68.2s wall-clock
Session: s8-k_test_20260531

## Final Answer:
Based on current population and growth data:
- Lagos: ~15.5M (growing at 3.78% annually)
- Cairo: ~21.3M (growing at 1.89% annually)
- Kinshasa: ~14.2M (growing at 4.12% annually)

**Lagos is the fastest-growing city in West Africa at approximately 3.78% annually.**
```

---

## Next Steps

1. Run all tests: `python run_assignment_tests.py`
2. Capture terminal output or screen recording
3. Collect JSON reports from `test_results/`
4. Create README.md with results + links
5. Upload YouTube demo
6. Submit assignment

Good luck! 🚀
