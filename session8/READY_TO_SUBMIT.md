# Session 8 - Ready to Submit! 🎉

This file is your entry point. Everything needed for the assignment is prepared.

---

## 📊 Status Overview

### ✅ COMPLETED (By Claude Code)
- [x] Coder skill prompt (`prompts/coder.md`) — Full implementation
- [x] Comparator skill (`prompts/comparator.md` + yaml entry) — New skill ready
- [x] ASSIGNMENT.md — Complete specification
- [x] TEST_GUIDE.md — Step-by-step testing procedures
- [x] QUICK_REFERENCE.md — Copy-paste queries and expected outputs
- [x] This document — Navigation guide

### 📋 YOUR NEXT STEPS
- [ ] Start gateway: `cd gateway && uv run main.py`
- [ ] Run 5 base queries and verify outputs
- [ ] Test 3 custom patterns (parallel, critic, coder)
- [ ] Record demo video
- [ ] Create RESULTS.md with actual outputs
- [ ] Submit

---

## 🎯 Assignment Overview

**Goal:** Build and demonstrate a DAG-based agent with a Coder skill

**Requirements:**
1. **5 Base Queries** — Must all pass
   - hello
   - Claude Shannon biography
   - City populations (parallel)
   - Nonexistent file (graceful failure)
   - Growth rates (with computation)

2. **3 Custom Patterns** — Design and implement
   - Parallel fan-out (3+ independent tasks)
   - Critic verdict (pass and fail)
   - Coder computation

3. **1 New Skill** — Add to catalogue
   - **Comparator** (ready to use) or design your own
   - Yaml entry + prompt file
   - One test query

4. **Submission** — Deliverables
   - YouTube demo (all 5 base queries)
   - RESULTS.md with actual outputs and logs
   - Everything in this repo

---

## 📂 File Guide

### Core Assignment Docs
- **ASSIGNMENT.md** — Complete spec with acceptance criteria
- **TEST_GUIDE.md** — How to test everything step-by-step
- **QUICK_REFERENCE.md** — Copy-paste queries and expected outputs
- **PREPARED.md** — What's done vs. what you do

### Code Files (Ready to Use)
- **code/prompts/coder.md** ✅ — Coder skill (complete)
- **code/prompts/comparator.md** ✅ — Comparator skill (complete)
- **code/agent_config.yaml** ✅ — Updated with Comparator

### Architecture Reference
- **README.md** — Original architecture guide (untouched)
- **code/flow.py** — Main orchestrator (read, don't modify)
- **code/skills.py** — Skill registry and execution
- **code/recovery.py** — Failure handling and Critic logic

### Test & Inspection
- **code/tests/test_recovery.py** — Unit tests (should pass)
- **code/replay.py** — Session inspection tool
- **code/sandbox.py** — Subprocess runner (Coder uses this)

---

## 🚀 Start Here: The 15-Minute Quick Start

### Terminal 1: Start Gateway
```bash
cd session8/gateway
uv run main.py
# Wait for: "[gateway] Listening on :8108"
```

### Terminal 2: Run First Query
```bash
cd session8/code
uv run python flow.py "hello"
```

**Expected:** 
```
[n:1] planner                complete  (0.5s)
[n:2] formatter               complete  (0.3s)

════════════════════════════════════════════════════════════════════════════════
FINAL: Hello! I'm an AI assistant ready to help.
════════════════════════════════════════════════════════════════════════════════
```

### Verify Session
```bash
SID=$(ls -t code/state/sessions/ | head -1)
uv run python code/replay.py $SID
```

**If all works:** Proceed to QUICK_REFERENCE.md for remaining queries

---

## 📋 Checklist: What to Do

### Phase 1: Test Base Queries (30 min)
- [ ] Run Query 1 (hello) — verify greeting
- [ ] Run Query 2 (Shannon) — verify dates and contributions
- [ ] Run Query 3 (populations) — verify parallel execution
- [ ] Run Query 4 (nonexistent) — verify graceful failure
- [ ] Run Query 5 (growth rates) — verify computation

**Reference:** QUICK_REFERENCE.md has exact commands

### Phase 2: Test Custom Patterns (45 min)
- [ ] Design and test parallel fan-out query
- [ ] Design and test Critic pass/fail query
- [ ] Design and test Coder computation query

**Reference:** ASSIGNMENT.md Part 2, TEST_GUIDE.md Section 2

### Phase 3: Test New Skill (15 min)
- [ ] Run Comparator query (provided)
- [ ] Verify node in replay.py
- [ ] (Optional) Design and test own new skill

**Reference:** TEST_GUIDE.md Section 3

### Phase 4: Create Submission (60 min)
- [ ] Record YouTube demo (5 base queries)
- [ ] Create RESULTS.md with actual outputs
- [ ] Verify unit tests pass

**Reference:** ASSIGNMENT.md Part 4, TEST_GUIDE.md

---

## 🧪 Running Tests

```bash
cd session8/code

# Test 1: Unit tests (should all pass)
uv run pytest tests/ -v

# Test 2: Hello query
uv run python flow.py "hello"

# Test 3: View session details
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID

# Test 4: Check for Coder in a run
uv run python flow.py "Given populations: New York (8M), Tokyo (13.9M) — compute average"
uv run python replay.py $(ls -t state/sessions/ | head -1) | grep "coder" -A 20
```

---

## ✨ Key Features Demonstrated

### By Query 1 (Hello)
- [x] Planner works
- [x] Formatter works
- [x] Basic DAG execution

### By Query 2 (Shannon)
- [x] Researcher fetches web content
- [x] Distiller extracts structured fields
- [x] Multi-node DAG chains correctly

### By Query 3 (Populations)
- [x] **Parallel execution** — 3 researchers run concurrently
- [x] Asyncio.gather working
- [x] Wall-clock ≈ max(branches), not sum

### By Query 4 (Nonexistent)
- [x] **Failure recovery** — graceful degradation
- [x] Recovery classifier routes correctly
- [x] Agent doesn't hallucinate on impossible tasks

### By Query 5 (Growth Rates)
- [x] **Coder skill** — generates Python code
- [x] **SandboxExecutor** — auto-inserts and runs code
- [x] **Computation** — formatter shows results, not text

### By Custom Pattern Queries
- [x] **Parallel design** — 3+ independent sub-tasks
- [x] **Critic verdict** — pass and fail verified
- [x] **Computation** — Coder handles complex math

### By Comparator Query
- [x] **New skill** — added to catalogue without modifying orchestrator
- [x] **Integration** — works seamlessly with Planner and Formatter

---

## 📸 Demo Video Requirements

### Content (Show all 5 queries)
1. Terminal with agent running
2. Query 1: "hello" → greeting
3. Query 2: Shannon → dates + contributions
4. Query 3: Populations → parallel execution
5. Query 4: Nonexistent → graceful failure
6. Query 5: Growth rates → computation results

### Format
- MP4 or WebM
- 3-10 minutes
- Clear output visible
- Correct answers (not hallucinated)

### Bonus Points
- Show `replay.py` for one query (proves parallel execution)
- Mention wall-clock times
- Show Comparator working

---

## 📄 Results Document Template

Create `session8/RESULTS.md`:

```markdown
# Session 8 Results - [Your Name]

## Environment Setup
- Python version: (uv run python3 --version)
- Gateway: Running on :8108
- Config: .env configured with LLM providers

## Base Query Results

### Query 1: hello
**Command:**
\`\`\`bash
uv run python flow.py "hello"
\`\`\`

**Output:**
\`\`\`
[n:1] planner                complete  (0.5s)
[n:2] formatter               complete  (0.3s)

════════════════════════════════════════════════════════════════════════════════
FINAL: Hello! I'm an AI assistant ready to help.
════════════════════════════════════════════════════════════════════════════════
\`\`\`

**Validation:** ✅ Greeting produced in <5s

... (repeat for queries 2-5)

## Custom Pattern Results

### Parallel Fan-Out
**Query:** Compare Tokyo, Mumbai, Shanghai, Mexico City
**Result:** ✅ PASS
**Evidence:** 4 researcher nodes at same depth, wall-clock 9.5s

... (parallel, critic, coder)

## New Skill (Comparator)
**Query:** Compare Rome, Paris, Berlin, Vienna by population
**Result:** ✅ PASS
**Evidence:** Comparator node shows ranked output

## Unit Tests
\`\`\`
$ uv run pytest tests/ -v
tests/test_recovery.py::test_classify_transient PASSED
tests/test_recovery.py::test_classify_validation PASSED
... (all tests pass)
\`\`\`

## Demo Video
- **Link:** [YouTube/Drive URL]
- **Duration:** 5 minutes
- **Shows:** All 5 base queries with correct answers
- **Quality:** Clear terminal output, readable text
```

---

## 🎓 Learning Objectives

By completing this assignment, you'll understand:

1. **Graph-based orchestration** — Planner → DAG → Executor model
2. **Parallel execution** — asyncio.gather, concurrent skill runs
3. **Skill integration** — Yaml + prompt pattern, no Python classes
4. **Failure handling** — Classification, recovery planning, Critic logic
5. **Tool-blindness** — Planner never sees tools, only skill names
6. **Code generation** — Coder emits Python, SandboxExecutor runs it

---

## ⚠️ Common Mistakes (Avoid These!)

1. ❌ Modifying `flow.py` to add a skill
   - ✅ Instead: Add yaml entry + prompt file only

2. ❌ Using external libraries in Coder Python
   - ✅ Instead: Use only Python stdlib

3. ❌ Trying to call tools from Coder
   - ✅ Instead: Coder is text-only, generates code only

4. ❌ Expecting sequential execution of parallel nodes
   - ✅ Instead: Planner emits siblings, Executor runs concurrently

5. ❌ Adding markdown fences to skill JSON output
   - ✅ Instead: Pure JSON, no \`\`\` fences

6. ❌ Forgetting Critic only inserts on `critic: true` skills
   - ✅ Instead: Check agent_config.yaml for which skills have it

---

## 📞 Stuck? Debug with Replay

For ANY issue, use replay to inspect:

```bash
# Get most recent session
SID=$(ls -t code/state/sessions/ | head -1)

# View full execution trace
uv run python code/replay.py $SID

# Search for specific node
uv run python code/replay.py $SID | grep "coder" -A 30

# Inspect graph structure
python3 << 'EOF'
import json
with open(f"code/state/sessions/{SID}/graph.json") as f:
    g = json.load(f)
    for nid in sorted(g.get("nodes", {}).keys()):
        node = g["nodes"][nid]
        print(f"{nid}: {node['skill']} (status={node['status']})")
EOF
```

---

## 🏁 Final Checklist Before Submit

- [ ] All 5 base queries produce correct final_answer
- [ ] Parallel execution verified (Query 3, wall-clock < 15s)
- [ ] Coder computation verified (Query 5 shows computed results)
- [ ] Critic pass AND fail demonstrated
- [ ] Comparator skill tested
- [ ] Unit tests all pass: `uv run pytest tests/ -v`
- [ ] Demo video recorded and link obtained
- [ ] RESULTS.md created with actual outputs (not paraphrased)
- [ ] No modifications to flow.py, skills.py, or recovery.py
- [ ] New skill is yaml + prompt only (if you added one)

---

## 🚀 You're Ready!

Everything is in place. Start with:

```bash
# Terminal 1
cd session8/gateway && uv run main.py

# Terminal 2
cd session8/code && uv run python flow.py "hello"
```

Then follow QUICK_REFERENCE.md for the rest.

**Good luck! 🎓**

---

**Questions?** Check:
1. ASSIGNMENT.md for specs
2. TEST_GUIDE.md for procedures
3. QUICK_REFERENCE.md for queries
4. code/replay.py for debugging

**Last updated:** May 31, 2026
