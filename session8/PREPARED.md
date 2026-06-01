# Session 8 Assignment - Preparation Complete ✅

This document summarizes what has been prepared for you and what you still need to do.

---

## ✅ COMPLETED: Core Implementation

### 1. Coder Skill Prompt (`prompts/coder.md`)
**Status:** COMPLETE and READY TO USE

The Coder prompt has been fully implemented with:
- Clear procedures for reading inputs and generating Python code
- Constraints (stdlib-only, subprocess-safe, properly formatted)
- Output schema (JSON with "code" and "rationale" fields)
- Examples of suitable problems (statistics, rankings, parsing, aggregation)
- Failure mode handling

The prompt is designed to emit Python code that solves computational problems the Formatter cannot do from text alone. The SandboxExecutor automatically receives the code and runs it in a subprocess sandbox.

**File:** `session8/code/prompts/coder.md`

---

### 2. New Skill: Comparator (`prompts/comparator.md`)
**Status:** COMPLETE and WIRED

A new "Comparator" skill has been added to the skill catalogue that:
- Analyzes and compares multiple items across dimensions
- Produces ranked, structured insights
- Is fully integrated into `agent_config.yaml`
- Follows the same pattern as other skills (prompt + yaml entry)
- Requires NO changes to the orchestrator

**Files:**
- `session8/code/agent_config.yaml` — Comparator entry added
- `session8/code/prompts/comparator.md` — Comparator prompt implemented

---

### 3. Complete Assignment Documentation

Three comprehensive guides have been created:

#### ASSIGNMENT.md (Full Specification)
**File:** `session8/ASSIGNMENT.md`

Contains:
- Detailed spec for all 5 base queries (hello, A, I, J, K)
- Example DAGs for each query
- Acceptance criteria for parallel fan-out
- Critic verdict pass/fail examples
- Coder computation requirements
- New skill implementation guide
- Submission checklist

#### TEST_GUIDE.md (Testing & Validation)
**File:** `session8/TEST_GUIDE.md`

Contains:
- Prerequisites and setup instructions
- Step-by-step test procedures for all 5 base queries
- Parallel execution verification
- Coder verification with log inspection
- Comparator skill testing guide
- Unit test instructions
- Session replay and inspection procedures
- Troubleshooting guide

#### README.md (Architecture Reference)
**File:** `session8/README.md` (existing, comprehensive)

Already contains:
- Architecture explanation
- Layout and directory structure
- Quickstart guide
- Concepts and how to think about the system
- What NOT to touch
- Provenance and version notes

---

## ✅ READY: Test Infrastructure

### Session State Persistence
The system automatically persists all runs to `code/state/sessions/<sid>/`:
- `session.json` — metadata
- `graph.json` — final graph structure
- `nodes/*.json` — per-node inputs, outputs, prompts, timing

### Replay Tool
Run `uv run python replay.py <sid>` to inspect any session:
- See all nodes, their skills, inputs, outputs
- Review exact prompts sent to the gateway
- Check execution timing and status
- Identify Critic verdicts and recovery paths

### Unit Tests
Existing tests cover:
- Failure classification (transient, validation, upstream)
- Recovery planning
- Critic verdicts
- Run: `uv run pytest tests/ -v`

---

## 📋 TODO: What You Need to Do

### Phase 1: Run & Verify Base Queries
**Time:** ~30 minutes + API call time

1. Start gateway: `cd session8/gateway && uv run main.py`
2. Run each base query from Terminal 2:
   ```bash
   cd session8/code
   uv run python flow.py "hello"
   uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
   uv run python flow.py "Tell me the current population of New York, Tokyo, and London"
   uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."
   uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"
   ```
3. Verify outputs match expectations in ASSIGNMENT.md, Part 1
4. Use `replay.py` to inspect graph structures and verify parallel execution

**Deliverable:** All 5 queries produce correct final answers

---

### Phase 2: Design Custom Query Patterns
**Time:** ~45 minutes

Implement and test three custom queries:

#### A. Parallel Fan-Out (3+ independent tasks)
- Design a query that requires 3+ parallel sub-tasks
- Example: "Compare populations of 5 cities"
- Verify with: `replay.py` shows nodes at same depth running concurrently
- Expected wall-clock: ~= time for one task, not sum

**Test command:**
```bash
uv run python flow.py "YOUR_PARALLEL_QUERY"
uv run python replay.py <sid> | grep "researcher"
```

#### B. Critic Verdict (Pass and Fail)
- Design a query with a strict format constraint
- Example: "Write haiku exactly 5-7-5 syllables"
- First run should pass
- Construct second run that fails and triggers recovery
- Verify in session: Critic node with verdict=pass, then fail case shows recovery planner

**Test command:**
```bash
uv run python flow.py "YOUR_CONSTRAINT_QUERY"
uv run python replay.py <sid> | grep "critic" -A 3
```

#### C. Coder Computational Query
- Design a query requiring computation (statistics, rankings, aggregation)
- Example: "Given 5 populations, compute mean and median, sort by size"
- Verify Coder emits valid Python code
- Verify SandboxExecutor runs it (exit_code 0)
- Verify Formatter shows computed results

**Test command:**
```bash
uv run python flow.py "YOUR_COMPUTATION_QUERY"
uv run python replay.py <sid> | grep "coder" -A 20
```

**Deliverable:** Three working queries showing each pattern, with log evidence

---

### Phase 3: Exercise New Skill (Comparator)
**Time:** ~15 minutes

The Comparator skill is already wired into `agent_config.yaml` and has its prompt ready.

Design and test one query that uses Comparator:

**Example query:**
```bash
uv run python flow.py "Compare the populations of Rome, Paris, Berlin, and Madrid. Which city has the largest population?"
```

Expected DAG:
- Planner → [researcher(Rome), researcher(Paris), researcher(Berlin), researcher(Madrid)] (parallel)
- Planner → Comparator
- Comparator → Formatter

**Verification:**
```bash
uv run python replay.py <sid> | grep "comparator" -B 5 -A 10
# Should show Comparator node with ranked output
```

**Deliverable:** One query showing Comparator in action with log evidence

---

### Phase 4: Create Submission Materials
**Time:** ~1 hour

#### A. YouTube Demo Video
**Requirements:**
- Show terminal running all 5 base queries
- Capture final answers for each query
- Show that answers are correct (not hallucinated)
- Minimum 3 min, maximum 10 min
- MP4 or WebM format

**Content to include:**
1. Setup: show `.env` is configured, gateway is running
2. Query 1: `uv run python flow.py "hello"` and result
3. Query 2: Shannon biography with dates and contributions
4. Query 3: City populations (verify parallel execution mentioned)
5. Query 4: Nonexistent file (show graceful failure)
6. Query 5: Growth rates (show computation happening)
7. Bonus: Show Comparator skill working

**Record with:**
```bash
# Terminal 1
cd session8/gateway && uv run main.py

# Terminal 2 (record this one)
cd session8/code
uv run python flow.py "hello"
# ... run other queries
```

#### B. Results Document
**File:** `session8/RESULTS.md` (create or update)

For each of the 5 base queries:
```markdown
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

**Wall-clock:** 0.8s  
**Nodes:** planner → formatter  
**Status:** ✅ PASS
```

Repeat for all 5 queries. Include actual console output, not paraphrased.

---

## 🧪 Validation Checklist

Before submitting, verify:

- [ ] **Five base queries all pass**
  ```bash
  cd session8/code
  uv run pytest tests/ -v  # Should pass
  ```

- [ ] **Parallel execution verified**
  - Test Query I (city populations)
  - `replay.py` shows 3 researcher nodes at same depth
  - Wall-clock < 15s (not 45s)

- [ ] **Coder works end-to-end**
  - Coder node emits valid JSON with "code" field
  - Code contains valid Python
  - SandboxExecutor runs it (exit_code 0)
  - Formatter incorporates results

- [ ] **Critic verdict tested**
  - One query where Critic verdict=pass
  - One query where Critic verdict=fail (triggers recovery)
  - Recovery mechanism works

- [ ] **Comparator skill tested**
  - One query exercises Comparator
  - Output shows ranked comparison
  - No changes to `flow.py` needed

- [ ] **Demo video created**
  - All 5 queries visible
  - Correct final answers shown
  - 3-10 minutes duration
  - Shareable link provided

- [ ] **RESULTS.md complete**
  - All 5 queries documented
  - Actual outputs shown (not paraphrased)
  - ✅ or ❌ status for each

---

## 🚀 Quick Start to Testing

```bash
# 1. Terminal 1: Start gateway
cd session8/gateway
uv run main.py

# 2. Terminal 2: Test base queries
cd session8/code

# Test 1: Hello
uv run python flow.py "hello"

# Test 2: Shannon
uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."

# Test 3: Populations (parallel)
uv run python flow.py "Tell me the current population of New York, Tokyo, and London"

# Test 4: Nonexistent (failure)
uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."

# Test 5: Growth rates (computation)
uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"

# Inspect any session
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID
```

---

## 📚 Key Documents Reference

| Document | Purpose | Location |
|----------|---------|----------|
| ASSIGNMENT.md | Full spec with acceptance criteria | `session8/ASSIGNMENT.md` |
| TEST_GUIDE.md | Step-by-step testing procedures | `session8/TEST_GUIDE.md` |
| README.md | Architecture & quickstart | `session8/README.md` |
| This file | What's prepared vs. what you do | `session8/PREPARED.md` |
| coder.md | Coder skill prompt | `session8/code/prompts/coder.md` |
| comparator.md | Comparator skill prompt | `session8/code/prompts/comparator.md` |
| agent_config.yaml | Skills catalogue (Comparator added) | `session8/code/agent_config.yaml` |

---

## ⚠️ Important Reminders

1. **Gateway must be running** for agent to work
2. **Coder prompt does not call tools** — it generates Python code
3. **SandboxExecutor auto-inserts** — no changes needed to flow.py
4. **No Python classes per skill** — only yaml + prompt
5. **Critic auto-inserts** on edges from `critic: true` skills
6. **Memory is session-wide** — every skill sees FAISS hits
7. **Parallel execution is automatic** — Planner emits siblings, Executor runs them via asyncio.gather

---

## Summary

✅ **Ready to run:** Coder skill, Comparator skill, full documentation, test guide  
📋 **Your tasks:** Run 5 base queries, test 3 custom patterns, record demo, create results doc  
🎯 **Success criteria:** All queries produce correct answers, demo shows it working, logs prove architecture

**Estimated total time:** 3-4 hours of testing, ~1 hour for demo video

Good luck! 🚀
