# Session 8 DAG Agent - Validation Checklist

**Date**: 2026-05-31  
**Status**: ✅ Ready for Final Validation

---

## Pre-Flight Checks

- [ ] Navigate to `session8/code/`
  ```bash
  cd /Users/srinivasmukka/SchoolOfAI/DAG/session8/code
  ```

- [ ] Verify GEMINI_API_KEY is set
  ```bash
  grep GEMINI_API_KEY ../.env | head -1
  # Should output: GEMINI_API_KEY=AIzaSy...
  ```

- [ ] Verify agent_routing.yaml has Gemini pins
  ```bash
  cat ../gateway/agent_routing.yaml | grep -E "planner:|coder:"
  # Should output: planner: gemini
  #               coder: gemini
  ```

- [ ] Kill any existing gateway
  ```bash
  pkill -f "python3.*main.py" || true
  sleep 2
  ```

---

## Phase 1: Test Five Base Queries

### Step 1a: Run all 5 queries
```bash
python run_assignment_tests.py --base-only
```

**Expected output**:
```
================================================================================
RUNNING: 5 BASE QUERIES
================================================================================

================================================================================
QUERY: hello - Simple greeting
================================================================================
...
✅ PASS - 8.2s wall-clock
Session: s8-c123abc...

================================================================================
QUERY: A - Web fetch + structure extraction
================================================================================
...
✅ PASS - 35.7s wall-clock
Session: s8-c456def...

... [Query I, J, K follow] ...

================================================================================
FINAL REPORT
================================================================================
Total queries: 5
Passed: 5
Failed: 0
Duration: 456.2s
Report: test_results/test_report_20260531_143015.json
```

- [ ] All 5 queries show ✅ PASS
- [ ] Wall-clock times reasonable (within 50% of expected)

### Step 1b: Examine results
```bash
# View JSON report
cat test_results/test_report_*.json | python3 -m json.tool

# Check specific query results
ls state/sessions/ | sort
```

- [ ] At least 5 session IDs created (one per query)
- [ ] Each session has `graph.json`
- [ ] Each graph has `nodes` array with skills

---

## Phase 2: Validate Parallel Execution

### Step 2a: Check Query I (populations - 3 parallel researchers)
```bash
# Get the Query I session ID
SESSION_I=$(ls state/sessions/ | grep -i "i_\|population" | head -1)

# View the graph
cat state/sessions/$SESSION_I/graph.json | python3 -m json.tool | head -50
```

**Expected**:
```json
{
  "nodes": [
    {"id": "n:1", "skill": "planner", "status": "complete"},
    {"id": "n:2", "skill": "researcher", "status": "complete"},
    {"id": "n:3", "skill": "researcher", "status": "complete"},
    {"id": "n:4", "skill": "researcher", "status": "complete"},
    {"id": "n:5", "skill": "formatter", "status": "complete"}
  ]
}
```

- [ ] Nodes n:2, n:3, n:4 are all `researcher` (3 parallel)
- [ ] All have same status transitions (run in parallel)

### Step 2b: Check wall-clock
```bash
# Extract elapsed times for each node
python3 << 'EOF'
import json
from pathlib import Path

SESSION_I = "$(ls state/sessions | grep -i 'i_\|population' | head -1)"
nodes_dir = Path(f"state/sessions/{SESSION_I}/nodes")

times = []
for f in sorted(nodes_dir.glob("n_*.json")):
    data = json.load(open(f))
    skill = data.get("node_id")
    elapsed = data.get("result", {}).get("elapsed_s", 0)
    times.append((skill, elapsed))
    print(f"{skill}: {elapsed:.1f}s")

# Calculate total (should be max, not sum)
r1, r2, r3 = times[1][1], times[2][1], times[3][1]
max_time = max(r1, r2, r3)
sum_time = sum([r1, r2, r3])
print(f"\nResearcher times: {r1:.1f}s, {r2:.1f}s, {r3:.1f}s")
print(f"Parallel (max): {max_time:.1f}s")
print(f"Sequential (sum): {sum_time:.1f}s")
print(f"Parallel efficiency: {max_time / sum_time * 100:.0f}%")

if max_time < sum_time * 0.8:
    print("✅ PARALLEL EXECUTION VERIFIED")
else:
    print("❌ EXECUTION APPEARS SEQUENTIAL")
EOF
```

- [ ] max_time significantly less than sum_time (≥ 60% efficiency)

---

## Phase 3: Validate Computation (Query K)

### Step 3a: Check Query K (growth rates)
```bash
SESSION_K=$(ls state/sessions | grep -i "k_\|growth\|lagos" | head -1)
cat state/sessions/$SESSION_K/graph.json | python3 -m json.tool | head -60
```

**Expected**:
```json
{
  "nodes": [
    {"id": "n:1", "skill": "planner"},
    {"id": "n:2", "skill": "researcher"},
    {"id": "n:3", "skill": "researcher"},
    {"id": "n:4", "skill": "researcher"},
    {"id": "n:5", "skill": "coder"},
    {"id": "n:6", "skill": "sandbox_executor"},
    {"id": "n:7", "skill": "formatter"}
  ]
}
```

- [ ] Has 3 parallel researchers (n:2, n:3, n:4)
- [ ] Has Coder node (n:5)
- [ ] Has SandboxExecutor node (n:6)
- [ ] Ends with Formatter (n:7)

### Step 3b: Check Coder output
```bash
# View Coder node output
cat state/sessions/$SESSION_K/nodes/n_005.json | python3 -m json.tool | grep -A20 '"output":'
```

**Expected**:
```json
"output": {
  "code": "import json\n...",
  "rationale": "Computes growth rates from population data"
}
```

- [ ] Coder output is NOT empty
- [ ] Has "code" and "rationale" fields

### Step 3c: Check final answer
```bash
# View Formatter output (final answer)
cat state/sessions/$SESSION_K/nodes/n_007.json | python3 -m json.tool | grep -A5 '"final_answer":'
```

**Expected**:
```
Lagos is growing fastest at approximately 3.78% annually
```

- [ ] Final answer identifies fastest-growing city
- [ ] Includes growth percentage

---

## Phase 4: Test Designer's Queries

### Step 4a: Run parallel fan-out query
```bash
python run_assignment_tests.py --query parallel_fan_out
```

Expected output: ✅ PASS - ~60-75s wall-clock

- [ ] Status: ✅ PASS
- [ ] Wall-clock ≤ 75s

### Step 4b: Run Critic test (first run - should fail)
```bash
python run_assignment_tests.py --query critic_test
```

Expected: Critic detects format violation → recovery → corrected answer

- [ ] Status: ✅ PASS (even though critic initially fails)
- [ ] Graph shows recovery: Critic failed → Planner recovery → new Formatter

### Step 4c: Run Critic test (second run - should pass)
```bash
python run_assignment_tests.py --query critic_test
```

Expected: Critic accepts format → PASS verdict

- [ ] Status: ✅ PASS
- [ ] Graph shows Critic verdict: "PASS"

---

## Phase 5: Verify Architecture Integrity

### Step 5a: Check no Executor modifications
```bash
# Count lines in flow.py, skills.py, recovery.py (should be same)
wc -l flow.py skills.py recovery.py persistence.py
```

Compare against previous session - should not have grown unexpectedly.

- [ ] No new orchestrator modifications beyond bug fixes

### Step 5b: Check skill additions are yaml only
```bash
# New Comparator skill should be in yaml only
grep "comparator:" agent_config.yaml
cat prompts/comparator.md | head -3
```

- [ ] Comparator in `agent_config.yaml`
- [ ] `prompts/comparator.md` exists
- [ ] No code changes to orchestrator

### Step 5c: Verify recovery system passes unit tests
```bash
# Check recovery tests (if they exist)
python -m pytest recovery_test.py -v 2>/dev/null || echo "No tests found"
```

- [ ] Tests pass (if they exist)

---

## Phase 6: Create Deliverables

### Step 6a: Collect session metadata
```bash
# Extract all session IDs with query labels
python3 << 'EOF'
from pathlib import Path
import json

sessions_dir = Path("state/sessions")
print("Session IDs (for README):")
for session_id in sorted(sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime):
    session_name = session_id.name
    graph_file = session_id / "graph.json"
    if graph_file.exists():
        with open(graph_file) as f:
            graph = json.load(f)
            node_count = len(graph.get("nodes", []))
        print(f"  {session_name}: {node_count} nodes")
EOF
```

- [ ] At least 7 session IDs collected (5 base + 2 designer's)

### Step 6b: Create test results table
```bash
# Extract metrics from JSON report
python3 << 'EOF'
import json
from pathlib import Path

# Find latest report
reports = sorted(Path("test_results").glob("test_report_*.json"), reverse=True)
if reports:
    with open(reports[0]) as f:
        report = json.load(f)
    
    print("| Query | Status | Wall-Clock |")
    print("|-------|--------|-----------|")
    for key, result in report.get("results", {}).items():
        status = "✅" if result.get("success") else "❌"
        elapsed = result.get("elapsed_seconds", 0)
        print(f"| {key} | {status} | {elapsed:.1f}s |")
EOF
```

- [ ] Table has all 7+ queries
- [ ] All show ✅ status
- [ ] Wall-clock times reasonable

### Step 6c: Create README.md
```bash
# Use template from SUBMIT_README.md
cp ../SUBMIT_README.md README_RESULTS.md
# Edit README_RESULTS.md to fill in actual results
```

- [ ] README.md created with:
  - [ ] Results table
  - [ ] Session IDs
  - [ ] Final answers for each query
  - [ ] Architecture diagram
  - [ ] Media links (YouTube, recordings)

### Step 6d: Create media
```bash
# Option 1: Terminal recording
asciinema rec demo.json -c "
python run_assignment_tests.py --query hello &&
python run_assignment_tests.py --query A &&
python run_assignment_tests.py --query I &&
python run_assignment_tests.py --query J &&
python run_assignment_tests.py --query K
"

# Option 2: Screen recording (use QuickTime or OBS)
# Save as DEMO.mp4
```

- [ ] Demo video created showing all 5 base queries
- [ ] Final answers clearly visible
- [ ] Duration: 5-7 minutes

---

## Final Submission Checklist

- [ ] ✅ Phase 1: All 5 base queries pass
- [ ] ✅ Phase 2: Parallel execution verified (wall-clock < sum)
- [ ] ✅ Phase 3: Computation verified (Coder + Sandbox)
- [ ] ✅ Phase 4: Designer's queries pass
- [ ] ✅ Phase 5: Architecture integrity confirmed
- [ ] ✅ Phase 6: Deliverables created

**Ready to submit**:
- [ ] README.md with results
- [ ] YouTube demo or recording
- [ ] Session JSON files (proof of execution)

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Gateway won't start | `pkill -f "main.py"; sleep 2` then retry |
| Gemini timeout | Check API key in `.env`, use fallback Ollama |
| Empty Coder output | Verify agent_routing.yaml has `coder: gemini` |
| Sequential execution | Verify agent_routing.yaml has `planner: gemini` |
| Test script errors | Check Python 3.10+ installed: `python --version` |

---

## Quick Commands

```bash
# Run all tests
python run_assignment_tests.py

# Run specific query
python run_assignment_tests.py --query hello
python run_assignment_tests.py --query K

# View latest session graph
cat state/sessions/$(ls state/sessions | tail -1)/graph.json | python3 -m json.tool

# View latest test report
cat test_results/$(ls test_results | tail -1)

# Check status of all sessions
for session in state/sessions/*/; do
    echo "$(basename $session): $(cat $session/graph.json | grep -c '"complete"') complete nodes"
done
```

---

**Time estimate**: 45-60 minutes total  
**Status**: ✅ Ready to proceed with Phase 1

Good luck! 🚀
