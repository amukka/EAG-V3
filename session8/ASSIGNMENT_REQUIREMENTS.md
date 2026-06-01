# Session 8 DAG Agent - Complete Assignment Requirements

## 1. Five Base Queries (Mandatory)

### Query 1 (hello) - Simple greeting
```
hello
```
- **Expected**: Formatter produces answer directly
- **Wall-clock**: ~5-10 seconds
- **Validation**: Graph shows only Planner → Formatter

### Query A - Web fetch + structure extraction
```
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory.
```
- **Expected**: Researcher fetches URL → Distiller extracts dates + 3 contributions
- **Wall-clock**: ~30-40 seconds
- **Validation**: Graph shows Planner → Researcher → Distiller → Formatter

### Query I - Parallel data lookup (3 cities)
```
Tell me the current population of New York, Tokyo, and London
```
- **Expected**: Planner emits 3 parallel Researcher nodes
- **Wall-clock**: ~max(researcher_1, researcher_2, researcher_3) ≈ 30-45 seconds (NOT sum)
- **Validation**: Graph shows n:planner → {n:r1, n:r2, n:r3} in parallel → n:formatter

### Query J - Graceful failure handling
```
Read /nonexistent/path.txt and tell me what's in it.
```
- **Expected**: Formatter handles file-not-found gracefully
- **Wall-clock**: ~5-10 seconds
- **Validation**: Graph completes without crashing; final answer explains the error

### Query K - Parallel fetch + computation (growth rates)
```
For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest
```
- **Expected**: 
  - Planner emits 3 parallel Researchers (one per city)
  - Coder computes growth rates from populations
  - SandboxExecutor runs the Python code
- **Wall-clock**: ~60-90 seconds
- **Validation**: 
  - Graph shows 3 parallel researchers + coder + sandbox
  - Final answer names the fastest-growing city with percentage

---

## 2. Parallel Fan-Out Query (Designer's Choice)

**Design a query with ≥3 independent sub-tasks**

### Recommended: "Compare tech CEOs"
```
Find the founding year, current age, and net worth of Elon Musk, Bill Gates, and Steve Ballmer. Which one was youngest when their company was founded?
```

**Architecture**:
- Planner emits 3 parallel Researchers (one per CEO)
- Coder computes: (founding_year - birth_year) for each → comparison
- Wall-clock validation: max(r1, r2, r3) + coder_time ≈ 50-70s (NOT 3× researcher time)

**Validation criteria**:
- [ ] Graph shows exactly 3 Researcher nodes in parallel (not sequential)
- [ ] Wall-clock ≤ 75 seconds
- [ ] Final answer correctly identifies youngest-at-founding

---

## 3. Critic Query (Designer's Choice with Pass + Fail)

**Design a query where Critic can verify an output property**

### Recommended: "5-7-5 Haiku validation"
```
Write a haiku about climate change. The haiku must have exactly 5 syllables in line 1, 7 in line 2, and 5 in line 3.
```

**Architecture - RUN 1 (Fail path)**:
- Planner → Formatter (writes haiku)
- Formatter output → Critic (checks syllable counts)
- Critic detects violation → emits recovery Planner → new Formatter
- Repeat until Critic passes

**Architecture - RUN 2 (Pass path)**:
- Same flow but Critic accepts syllable pattern
- Graph ends with Critic verdict: "PASS"

**Validation criteria**:
- [ ] First run shows Critic fail + recovery loop
- [ ] Second run shows Critic pass
- [ ] Final answer is a valid haiku with correct syllable counts

---

## 4. Coder Skill Verification

**File**: `prompts/coder.md`

**Current status**: ✓ Rewritten with JSON schema
```json
{
  "code": "<python source>",
  "rationale": "<one-liner>"
}
```

**Verification via Query K**:
- Researcher outputs: city name + population data
- Coder must:
  1. Parse researcher outputs
  2. Compute growth rates (population change / time period)
  3. Compare rates
  4. Output formatted result
- SandboxExecutor runs code successfully
- Final answer: "Lagos is growing fastest at 3.78%"

---

## 5. New Skill Addition

**Current plan**: Add `comparator` skill

**File edits needed**:
- [ ] `agent_config.yaml`: Add comparator entry
- [ ] `prompts/comparator.md`: Write new prompt
- [ ] No changes to orchestrator (Executor, flow.py, recovery.py)

**Design**: 
```yaml
comparator:
  prompt_file: prompts/comparator.md
  critic: false
  internal_successors: []
```

**Prompt function**: Given multiple items and dimensions, produce structured comparison

**Test query**:
```
Compare Apple, Microsoft, and Google across: founded year, market cap, employee count. Which was founded first?
```

---

## 6. YouTube Demo

**Requirements**:
- Show terminal running each of the 5 base queries (hello, A, I, J, K)
- Caption: Query number + description
- Show final answer clearly
- Total runtime: ~5-7 minutes

**Filename**: `DEMO.mp4` or YouTube link in README

---

## 7. README.md Results Log

**Required sections**:
1. Architecture diagram (DAG structure)
2. Query results table:
   ```
   | Query | Type | Wall-clock | Status | Final Answer |
   |-------|------|-----------|--------|--------------|
   | hello | Formatter | 8s | ✅ | ... |
   | A | Fetch+Extract | 35s | ✅ | ... |
   | I | Parallel lookup | 42s | ✅ | ... |
   | J | Failure handling | 6s | ✅ | ... |
   | K | Parallel+Compute | 68s | ✅ | ... |
   ```
3. Parallel fan-out test results
4. Critic pass/fail test results
5. Coder execution log
6. New skill test results

---

## Delivery Checklist

- [ ] All 5 base queries pass with correct wall-clock bounds
- [ ] Parallel fan-out query shows wall-clock ≤ max, not sum
- [ ] Critic shows both pass and fail paths working
- [ ] Coder.md verified on Query K
- [ ] New skill added to agent_config.yaml + prompt written
- [ ] YouTube demo shows all 5 base queries + final answers
- [ ] README.md with results logs for all parts

**Submission proof**:
- README.md link
- YouTube demo link
- Graph state files: `state/sessions/s8-**/graph.json` (one per query)
