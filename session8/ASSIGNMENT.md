# Session 8 Assignment: DAG-Based Agent with Coder Skill

Build a complete DAG-based agent and prove the architecture is intact through five base queries, three custom design patterns, one new skill, and a video demo.

---

## Part 1: Five Base Queries (MANDATORY)

These queries MUST pass with the exact iteration counts and wall-clock bounds specified.

### Query 1: Hello
**Input:** `hello`  
**Expected:** Simple greeting (1 sentence)  
**Nodes:** planner → formatter (2 nodes)  
**Wall-clock:** < 5s  

**Validation:**
```bash
cd session8/code && uv run python flow.py "hello"
```
Expected final_answer: greeting

---

### Query 2: Claude Shannon (A)
**Input:** `Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.`  

**Expected output:** 
- Birth date
- Death date  
- Three key contributions (e.g., information entropy, channel capacity, bit concept)

**Execution pattern:**
- planner → researcher → distiller → formatter
- researcher fetches URL
- distiller extracts structured fields
- formatter synthesizes answer

**Wall-clock:** < 15s  

**Validation:**
```bash
cd session8/code && uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
```

---

### Query 3: City Populations (I)
**Input:** `Tell me the current population of New York, Tokyo, and London`

**Expected output:** Three distinct population figures with sources

**Execution pattern:**
- planner → [researcher, researcher, researcher] (parallel fan-out) → formatter
- Three independent researcher nodes for three cities
- Orchestrator runs all three in parallel (asyncio.gather)
- Wall-clock should be ~= time for one researcher, NOT 3x

**Wall-clock:** < 15s  

**Validation:**
- Run the query and verify execution log shows three nodes running concurrently
- Check `state/sessions/<sid>/graph.json` to see parallel node structure
- Confirm wall-clock is max(branch times), not sum

```bash
cd session8/code && uv run python flow.py "Tell me the current population of New York, Tokyo, and London"
```

---

### Query 4: Nonexistent Path (J)
**Input:** `Read /nonexistent/path.txt and tell me what's in it.`

**Expected:** Graceful failure — agent admits file doesn't exist rather than hallucinating

**Execution pattern:**
- planner detects impossible task
- emits appropriate skill node
- skill fails gracefully
- recovery classifier routes as upstream_failure
- planner re-routes to formatter with honest answer

**Wall-clock:** < 10s  

**Validation:**
```bash
cd session8/code && uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."
```
Expected final_answer should explicitly state file not found (not invented content)

---

### Query 5: Growth Rate Analysis (K)
**Input:** `For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest`

**Expected output:**
- Current population for each city
- Growth rate for each city
- Which is fastest (with justification)

**Execution pattern:**
- planner → [researcher(Lagos), researcher(Cairo), researcher(Kinshasa)] (parallel)
- Each researcher gathers population data
- coder generates Python to compute growth rates and rank them
- coder → sandbox_executor (automatic internal successor)
- formatter synthesizes final answer

**Wall-clock:** < 20s  

**Validation:**
```bash
cd session8/code && uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"
```
Expected final_answer should show computations (not just text extraction)

---

## Part 2: Custom Query Patterns (DESIGN + IMPLEMENT)

### Pattern A: Parallel Fan-Out (Minimum 3 independent sub-tasks)

**Requirement:** The Planner must emit 3+ sibling nodes with the same structure (e.g., researcher, researcher, researcher). The orchestrator must run them in parallel. Verify that:
- Wall-clock time ≈ max(subtask times), NOT sum
- Graph JSON shows all three nodes at same depth
- Execution log shows all three running before any successor

**Example query:**
```
Compare the populations of Tokyo, Mumbai, Shanghai, and Mexico City.
```

**Acceptance:**
- `flow.py` logs show three researcher nodes running concurrently
- Session graph confirms parallel structure
- Wall-clock ≤ 20s (not 60s for three sequential fetches)

**Validation Code:**
```bash
cd session8/code
uv run python flow.py "Compare the populations of Tokyo, Mumbai, Shanghai, and Mexico City."
# Check logs for concurrent execution
uv run python replay.py <sid> | grep -E "running|complete"
```

---

### Pattern B: Critic Verdict (Pass and Fail)

**Requirement:** Design a query where the Critic's verdict meaningfully gates downstream behavior. The same query must:
1. **Pass on first run:** Critic verdict=pass, node succeeds
2. **Fail on second run:** Critic verdict=fail, triggers recovery planner

**How it works:**
- Planner emits a writing/content-generation node (distiller, researcher, or custom skill)
- Orchestrator auto-inserts Critic between node and successor
- Critic evaluates the node's output against a constraint
- Verdict=pass: successor runs as planned
- Verdict=fail: recovery planner re-plans the failed branch

**Example query (with two invocations):**
```bash
# Invocation 1: Agent produces response; Critic passes it
uv run python flow.py "Write a haiku about artificial intelligence. It must be exactly 5-7-5 syllables."

# Invocation 2: Agent tries; Critic fails; recovery planner re-routes
# (or manually construct a query where Critic deterministically fails)
```

**Acceptance Criteria:**
- First run: final_answer is produced, Critic node shows verdict=pass
- Recovery mechanism: Critic fails → recovery planner added → new node generated → passes formatter
- Session logs clearly show Critic node and recovery path

**Validation Code:**
```bash
cd session8/code

# First invocation (passes)
uv run python flow.py "Write a haiku about AI. Must be exactly 5-7-5 syllables."
# Inspect graph.json — Critic node with verdict=pass

# Verify the recovery system is armed
cd ../tests
uv run pytest test_recovery.py -v
```

---

### Pattern C: Coder Computational Query

**Requirement:** Demonstrate Coder emitting Python code that solves a problem the Formatter cannot reliably produce from text alone.

**Acceptable problems:**
- Computing statistics (average, percentile, variance) from multiple data points
- Ranking or sorting based on derived metrics
- Parsing and aggregating structured data
- Mathematical computation (growth rates, compound interest, etc.)

**Example query:**
```
What is the average and median population of these 5 cities: (list 5 cities with populations from previous queries).
Show step-by-step: sum, count, mean, then sorted list and median.
```

**Execution pattern:**
1. Planner emits researcher (or retriever) to gather raw data
2. Planner emits coder node
3. Coder generates Python code that:
   - Reads the population data from INPUTS
   - Computes sum, count, mean, median
   - Prints results to stdout
4. Orchestrator auto-inserts sandbox_executor (internal_successors)
5. SandboxExecutor runs the code, captures stdout/stderr/exit_code
6. Formatter synthesizes final answer from sandbox output

**Acceptance Criteria:**
- `coder.py` emits valid JSON with "code" and "rationale" fields
- Emitted code is syntactically valid Python
- Code executes cleanly (exit_code 0, no errors)
- stdout contains computed results
- formatter's final_answer includes the computation results (not invented)

**Validation Code:**
```bash
cd session8/code

# Test a computational query
uv run python flow.py "Given populations: New York (8M), Tokyo (13.9M), Shanghai (24.2M), Delhi (16.7M), São Paulo (11.4M) — calculate and show the mean and median population. Sort them."

# Inspect the session
uv run python replay.py <sid> | grep -A 50 "coder"
# Verify: coder.output.code contains Python, sandbox_executor.output has stdout
```

---

## Part 3: New Skill Implementation (1 required)

### Requirement
Add one skill to `agent_config.yaml` that the existing catalogue does NOT cover.

**Options:**
- **Analyzer** — statistical analysis of structured data (like coder but LLM-driven)
- **Translator** — language translation (already partially in yaml; fill prompt and tools)
- **Validator** — fact-checking or consistency verification
- **Aggregator** — combines results from multiple sources with deduplication
- **Outlier** — identifies anomalies in datasets
- **ComparativeAnalyzer** — compares and contrasts multiple items

### Implementation Steps

1. **Edit `agent_config.yaml`:**
   ```yaml
   <skill_name>:
     prompt: prompts/<skill_name>.md
     tools_allowed: [...]  # if any; empty list for text-only
     temperature: 0.X
     max_tokens: YYYY
     description: One-line summary
   ```

2. **Create `prompts/<skill_name>.md`:**
   - Follow the pattern of existing prompts (researcher.md, formatter.md)
   - Specify inputs, procedure, output schema (JSON, no markdown fences)
   - NO Python classes — just a skill definition + prompt

3. **Write one query that exercises it:**
   - The query's Planner output must include your new skill
   - Verify the skill runs, produces valid JSON, and integrates with downstream nodes

4. **Verification:**
   - The orchestrator must NOT need modification
   - If you find yourself editing `flow.py` or `skills.py`, reconsider the design
   - New skills are yaml entries + prompts only

### Example: Analyzer Skill

**agent_config.yaml entry:**
```yaml
analyzer:
  prompt: prompts/analyzer.md
  tools_allowed: []
  temperature: 0.3
  max_tokens: 1500
  description: Analyzes patterns, trends, and statistical properties in structured data.
```

**Query to exercise it:**
```
Analyze the population trends for Rome, Berlin, Madrid, and Paris over the 
last 10 years. Identify which is growing, shrinking, or stable.
```

**Expected DAG:**
- planner → [researcher(Rome), researcher(Berlin), researcher(Madrid), researcher(Paris)] → analyzer → formatter

---

## Part 4: Submission Requirements

### 4.1 YouTube Demo
**Record a video demonstrating Parts 1–5 (the five base queries).**

The demo should show:
1. Terminal window running `cd session8/code && uv run python flow.py "..."`
2. Clear output for each query (hello, Shannon, populations, nonexistent, growth rates)
3. Final answers are correct and not hallucinated
4. Wall-clock times are reasonable (not hanging)

**Minimum length:** 3 minutes  
**Maximum length:** 10 minutes  
**Format:** MP4 or WebM, publicly accessible URL or embedded in README

---

### 4.2 README.md with Logs

Create or update `session8/RESULTS.md` showing:

**For each of the 5 base queries:**
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
FINAL: Hello! I'm an AI assistant ready to help you.
════════════════════════════════════════════════════════════════════════════════
\`\`\`

**Validation:** ✅ Greeting produced in < 5s
```

Repeat for all five queries. Include:
- Exact command run
- Actual final_answer from the run
- Wall-clock timing
- ✅ or ❌ validation status

**File:** `session8/RESULTS.md` (or similar, linked from main README)

---

## Part 5: Architectural Rules (Carry-over from Session 7)

These rules are NON-NEGOTIABLE. Violations cause the build to fail.

1. **Planner emits the graph; Executor runs it**
   - No hard-coded skill names in Python code
   - Graph structure is 100% determined by Planner's JSON output

2. **Skills are yaml entries + prompts**
   - No Python classes per skill (except internal tools like gateway wrappers)
   - Adding a new skill = yaml entry + prompt file
   - Touching the Executor for anything except a new generic mechanism is a bug

3. **Critic sits between a flagged producer and its successor**
   - Skills marked `critic: true` automatically get Critic nodes inserted
   - Critic verdict=pass continues; verdict=fail triggers recovery
   - Recovery classifier continues to pass all unit tests

4. **Tools are perception; Planner is decision**
   - Planner names skills, never tools
   - Tool-blindness contract: Planner cannot see the tool catalogue
   - Memory works because orchestrator delivers hits, not because FAISS is on disk

---

## Acceptance Tests

Run these before submission:

```bash
cd session8/code

# 1. Unit tests pass
uv run pytest tests/ -v

# 2. Five base queries complete
uv run python flow.py "hello"
uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
uv run python flow.py "Tell me the current population of New York, Tokyo, and London"
uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."
uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"

# 3. Parallel execution visible
uv run python replay.py <sid-from-query-3> | grep "ready_nodes\|running\|complete"

# 4. Coder emits code
uv run python flow.py "Given populations: New York (8M), Tokyo (13.9M) — compute the average."
uv run python replay.py <sid> | grep -A 10 "coder"

# 5. New skill wired and exercised
uv run python flow.py "<your new skill query>"
```

If all pass and the demo runs without errors, you're done.

---

## FAQ

**Q: Can I use external libraries in Coder's Python code?**  
A: No. Standard library only. Coder must be portable and sandbox-safe.

**Q: What if the Planner emits invalid skill names?**  
A: The orchestrator will error with a validation_error, which the classifier will skip (not replan). Fix the Planner prompt.

**Q: Do I need to modify `flow.py` to add a new skill?**  
A: No. New skills are yaml + prompt only. If you're editing `flow.py`, you've misunderstood the architecture.

**Q: How do I know if Critic actually failed?**  
A: Check the session graph: look for a Critic node with `"verdict": "fail"` in its output, followed by a recovery Planner node.

**Q: What's the difference between `tools_allowed: []` and not including it?**  
A: Empty list means the skill is text-only. If the key is missing, it defaults to empty list. Both are equivalent.

---

## Submission Checklist

- [ ] `prompts/coder.md` filled in with complete prompt
- [ ] Five base queries (hello, A, I, J, K) all pass
- [ ] Parallel fan-out query designed and tested
- [ ] Critic verdict query passes and fails appropriately
- [ ] Coder computational query runs and produces results
- [ ] New skill added to `agent_config.yaml` with prompt file
- [ ] New skill exercised with a query
- [ ] YouTube demo recorded (5 base queries visible)
- [ ] README.md or RESULTS.md with logs for 5 base queries
- [ ] All unit tests pass: `uv run pytest tests/ -v`
- [ ] Architectural rules verified (no Python per skill, no executor modifications)

---

**Version:** Session 8 Round-3 Review  
**Last Updated:** 2026-05-31
