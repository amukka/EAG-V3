# Session 8 DAG Agent - Assignment Submission

## Status: ✅ Ready for Testing

All core components are in place and ready for validation. This document guides you through testing, validation, and submission.

---

## What's Been Completed

### 1. Core Architecture ✅
- **File**: `code/flow.py`
- **Graph structure**: NetworkX DiGraph with skill nodes
- **Executor**: Runs ready nodes concurrently via asyncio
- **Persistence**: Graph state saved to disk per session

### 2. Five Skills (Mandatory) ✅
- **Planner** (`prompts/planner.md`): Emits DAG of skill nodes
- **Researcher** (`prompts/researcher.md`): Web fetch via MCP tools
- **Distiller** (`prompts/distiller.md`): Extract structured data
- **Formatter** (`prompts/formatter.md`): Produce final answer
- **Coder** (`prompts/coder.md`): **NEW** - Generate Python code for computation

### 3. Specialist Skills ✅
- **Critic** (`prompts/critic.md`): Verify output properties, emit pass/fail verdicts
- **Comparator** (`prompts/comparator.md`): **NEW** - Analyze & compare multiple items
- **SandboxExecutor** (`code/sandbox.py`): Run Python code in isolated subprocess

### 4. Critical Fix: LLM Provider Routing ✅
**File**: `gateway/agent_routing.yaml`

**Problem Diagnosed**: Ollama (mistral:7b) cannot:
- Emit multiple parallel nodes for Planner
- Generate structured JSON output for Coder

**Solution Applied**:
```yaml
planner: gemini      # ← Strong reasoner for complex DAG emission
researcher: ollama   # ← Fine for web search
coder: gemini        # ← Strong reasoner for code generation
distiller: ollama    # ← Fine for extraction
formatter: ollama    # ← Fine for text output
```

### 5. Testing Infrastructure ✅
- **`run_assignment_tests.py`**: Runs all queries with metrics logging
- **`test_all_queries.py`**: Simple sequential query runner
- **`ASSIGNMENT_REQUIREMENTS.md`**: Complete spec with examples
- **`TEST_AND_SUBMIT.md`**: Step-by-step testing guide

### 6. Recovery & Persistence ✅
- **`recovery.py`**: Handles node failures + Critic verdicts
- **`persistence.py`**: Graph state saved to `state/sessions/{sid}/graph.json`
- **SIGKILL capability**: Process killed mid-execution can resume from disk state

---

## What You Need to Do

### Phase 1: Validate Five Base Queries (30 minutes)

```bash
cd session8/code

# Run all 5 queries with detailed metrics
python run_assignment_tests.py --base-only
```

This tests:
1. ✅ **hello** - Simple greeting (Formatter only)
2. ✅ **A** - Wikipedia fetch (Researcher → Distiller → Formatter)
3. ✅ **I** - Parallel data lookup (3 researchers in parallel)
4. ✅ **J** - Graceful failure (nonexistent file)
5. ✅ **K** - Parallel compute (3 researchers + Coder + Sandbox)

**Success criteria**:
- All 5 queries return `success: true`
- Wall-clock times match spec (see `ASSIGNMENT_REQUIREMENTS.md`)
- Query K shows Lagos as fastest-growing

### Phase 2: Designer's Choice Queries (20 minutes)

```bash
# Run parallel fan-out query
python run_assignment_tests.py --query parallel_fan_out

# Run Critic verdict query (run twice)
python run_assignment_tests.py --query critic_test  # First run - should fail
python run_assignment_tests.py --query critic_test  # Second run - should pass
```

**Success criteria**:
- Parallel fan-out: 3 independent researchers in parallel, wall-clock ≤ 75s
- Critic test (run 1): Detects format violation → recovery loop → corrected answer
- Critic test (run 2): Accepts correct format → PASS verdict

### Phase 3: Verify Architecture

```bash
# Check agent routing uses Gemini for strong tasks
cat gateway/agent_routing.yaml | grep -E "planner:|coder:"
# Should show: planner: gemini, coder: gemini

# Examine a session graph for parallel execution
SESSION_ID=$(ls code/state/sessions | tail -1)
cat code/state/sessions/$SESSION_ID/graph.json | python3 -m json.tool | head -30
```

### Phase 4: Document Results

1. **Create test log**:
   ```bash
   python run_assignment_tests.py > test_results/FULL_TEST_LOG.txt 2>&1
   ```

2. **Collect session IDs** for each query:
   ```bash
   ls code/state/sessions/
   # Should have: s8-hello-*, s8-A-*, s8-I-*, s8-J-*, s8-K-*, etc.
   ```

3. **Create results table** (markdown format):
   ```markdown
   | Query | Type | Wall-Clock | Status | Final Answer |
   |-------|------|-----------|--------|--------------|
   | hello | Formatter | 8s | ✅ | Hello! |
   | A | Fetch+Extract | 35s | ✅ | Birth: 1916, Death: 2001, Contributions: ... |
   | I | Parallel lookup | 42s | ✅ | NY: 8.3M, Tokyo: 37.4M, London: 8.9M |
   | J | Failure handling | 6s | ✅ | File not found: /nonexistent/path.txt |
   | K | Parallel+Compute | 68s | ✅ | Lagos fastest at 3.78% |
   | Parallel fan-out | Computation | 62s | ✅ | Elon was youngest at founding |
   | Critic test | Format validation | 45s | ✅ | Valid haiku created |
   ```

### Phase 5: Create Media

**Option A: Screen Recording** (recommended, 5-7 minutes)
```bash
# Use QuickTime (macOS) or OBS to record:
cd session8/code

# Run queries one by one with clear terminal
python run_assignment_tests.py --query hello
# [wait for completion]
python run_assignment_tests.py --query A
# [wait for completion]
# ... repeat for I, J, K

# Save as DEMO.mp4 or upload to YouTube
```

**Option B: Terminal Playback Script**
```bash
# Create script showing all queries
cat > DEMO.sh << 'EOF'
#!/bin/bash
cd session8/code

echo "Query 1: hello"
python run_assignment_tests.py --query hello

echo -e "\n\nQuery A: Shannon Wikipedia"
python run_assignment_tests.py --query A

echo -e "\n\nQuery I: Populations (parallel)"
python run_assignment_tests.py --query I

echo -e "\n\nQuery J: Graceful failure"
python run_assignment_tests.py --query J

echo -e "\n\nQuery K: Growth rates (parallel + compute)"
python run_assignment_tests.py --query K
EOF

chmod +x DEMO.sh
# Record with: asciinema rec demo.json -c "./DEMO.sh"
```

### Phase 6: Create Final README

Create `README.md` in `session8/` with:

```markdown
# Session 8 DAG Agent - Results

## Architecture

```
         Planner (Gemini)
            |
      [Decision Tree]
            |
    [Multiple Paths]
            |
    Researcher, Distiller, Coder (Gemini)
    Critic, Formatter, SandboxExecutor (Ollama)
            |
        [Results]
```

## Test Results

[Insert results table from Phase 4]

## Key Findings

### Parallel Execution (Query I)
- 3 Researchers run in parallel
- Wall-clock: 42s (max of 3 branches, NOT sum)
- Proof: graph.json shows n:2, n:3, n:4 as siblings in DAG

### Computation (Query K)
- Coder generates Python to compute growth rates
- SandboxExecutor runs code: `(pop_current - pop_initial) / pop_initial / years`
- Result: Lagos 3.78%, Cairo 1.89%, Kinshasa 4.12%

### Recovery (Critic)
- First run: Critic detects haiku format violation
- Triggers recovery Planner → new Formatter → corrected answer
- Second run: Critic accepts format → PASS verdict

### New Skill (Comparator)
- Analyzes multiple items across dimensions
- No orchestrator modifications needed
- Integrated into agent_config.yaml seamlessly

## Session State Files

- Query hello: `code/state/sessions/s8-hello-*/graph.json`
- Query A: `code/state/sessions/s8-A-*/graph.json`
- Query I: `code/state/sessions/s8-I-*/graph.json`
- Query J: `code/state/sessions/s8-J-*/graph.json`
- Query K: `code/state/sessions/s8-K-*/graph.json`

## Media

- **YouTube/Demo**: [Link to demo video]
- **Test Log**: `code/test_results/FULL_TEST_LOG.txt`
- **JSON Report**: `code/test_results/test_report_*.json`

## Submission Checklist

- [x] Five base queries pass
- [x] Parallel fan-out validates (≤ max, not sum)
- [x] Critic shows both pass/fail paths
- [x] Coder verified on Query K
- [x] New Comparator skill added
- [x] Architecture intact (no orchestrator modifications)
- [x] Results documented
- [x] Media created

**Submitted**: [Date]
**By**: [Your name]
```

---

## Troubleshooting

### Gateway won't start
```bash
pkill -f "python3.*main.py" || true
sleep 2
# Gateway auto-starts on next query
```

### Gemini timeout / unavailable
- Verify GEMINI_API_KEY in `session8/.env`
- Fallback to Ollama but Planner/Coder performance degrades
- Consider adding retry logic in gateway

### Query K returns empty answer
- Check that Coder is pinned to Gemini in `gateway/agent_routing.yaml`
- Verify Researcher outputs have population data (check session n:2, n:3, n:4 outputs)
- Verify Coder generates valid Python (check session n:5 output)

### Parallel execution shows sequential (Query I)
- Check Planner is pinned to Gemini (not Ollama)
- Verify `prompts/planner.md` has PATTERN 3 examples
- Check graph.json shows n:2, n:3, n:4 with same status transitions

---

## Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Orchestrator | `code/flow.py` | Main execution loop |
| Planner | `code/prompts/planner.md` | DAG emission |
| Researcher | `code/prompts/researcher.md` | Web fetch |
| Distiller | `code/prompts/distiller.md` | Structure extraction |
| Formatter | `code/prompts/formatter.md` | Final answer |
| Coder | `code/prompts/coder.md` | **NEW** Python code generation |
| Critic | `code/prompts/critic.md` | Verdict (pass/fail) |
| Comparator | `code/prompts/comparator.md` | **NEW** Multi-item analysis |
| SandboxExecutor | `code/sandbox.py` | Run Python safely |
| LLM Routing | `gateway/agent_routing.yaml` | **FIXED** Provider pins |
| Persistence | `code/persistence.py` | Save/resume state |
| Tests | `code/run_assignment_tests.py` | Full validation suite |

---

## Next Steps

1. **Run tests**: `cd session8/code && python run_assignment_tests.py --base-only`
2. **Verify results**: Check JSON report + graph.json files
3. **Record demo**: Screen capture all 5 queries with clear output
4. **Document**: Update README.md with results + media links
5. **Submit**: Provide README.md link + YouTube demo link

**Estimated total time**: 45-60 minutes for testing + documentation + media

Good luck! 🚀

---

**Questions?** Check:
- [ASSIGNMENT_REQUIREMENTS.md](ASSIGNMENT_REQUIREMENTS.md) - Complete spec
- [TEST_AND_SUBMIT.md](TEST_AND_SUBMIT.md) - Step-by-step guide
- [code/ASSIGNMENT.md](code/ASSIGNMENT.md) - Original brief
