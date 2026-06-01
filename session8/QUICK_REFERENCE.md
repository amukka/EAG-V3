# Session 8 Quick Reference Guide

Copy-paste ready queries and expected patterns.

---

## Base Queries (Must Pass)

### Query 1: Hello
```bash
uv run python flow.py "hello"
```
**Expected:** Greeting in < 5s  
**Nodes:** planner → formatter  
**Pattern:** Simple direct answer

---

### Query 2: Claude Shannon
```bash
uv run python flow.py "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, death date, and three key contributions to information theory."
```
**Expected:** 
- Birth: ~1916
- Death: ~2001  
- Contributions: information entropy, channel capacity, bit
**Nodes:** planner → researcher → distiller → formatter  
**Pattern:** Web fetch → structured extraction

---

### Query 3: City Populations (Parallel)
```bash
uv run python flow.py "Tell me the current population of New York, Tokyo, and London"
```
**Expected:** Three populations with sources  
**Nodes:** planner → [researcher, researcher, researcher] → formatter  
**Pattern:** Parallel fan-out (3 sibling nodes, all run at once)  
**Wall-clock:** < 15s (proof: check `replay.py` shows concurrent execution)

---

### Query 4: Nonexistent File
```bash
uv run python flow.py "Read /nonexistent/path.txt and tell me what's in it."
```
**Expected:** "File not found" (NOT invented content)  
**Nodes:** planner → (failure) → recovery planner → formatter  
**Pattern:** Graceful failure & recovery

---

### Query 5: Growth Rates (Computation)
```bash
uv run python flow.py "For Lagos, Cairo, and Kinshasa, find current populations and growth rates and tell me which is growing fastest"
```
**Expected:**
- Population for each city
- Growth rate for each city  
- Which is fastest (e.g., "Cairo is growing fastest at X% per year")
**Nodes:** planner → [researcher, researcher, researcher] → coder → sandbox_executor → formatter  
**Pattern:** Parallel fetch → computation → answer synthesis

---

## Custom Pattern Queries

### Parallel Fan-Out (4 tasks)
```bash
uv run python flow.py "Compare the populations of Tokyo, Mumbai, Shanghai, and Mexico City. Which is largest?"
```
**Verify:** `replay.py <sid>` shows 4 researcher nodes at same depth running concurrently

---

### Critic Verdict (Pass case)
```bash
uv run python flow.py "Write a haiku about artificial intelligence. It must be exactly 5-7-5 syllables."
```
**Verify:** `replay.py <sid>` shows critic node with `"verdict": "pass"`

---

### Critic Verdict (Fail case - Forces Recovery)
```bash
uv run python flow.py "Write a haiku about programming that is exactly 3-5-7 syllables (reverse format)."
```
**Verify:** `replay.py <sid>` shows critic node with `"verdict": "fail"` followed by recovery planner

---

### Coder Computation
```bash
uv run python flow.py "Given these populations: New York (8.3M), Tokyo (13.9M), Shanghai (24.2M), Delhi (16.7M), São Paulo (11.4M) — calculate and show: 1) the average population, 2) the cities sorted by population (largest first), 3) the population range (max - min)"
```
**Verify:** 
- `replay.py <sid> | grep "coder" -A 20` shows code field with Python
- `replay.py <sid> | grep "sandbox_executor" -A 10` shows `exit_code: 0` and computed results in stdout

---

### Comparator (New Skill)
```bash
uv run python flow.py "Compare Rome, Paris, Berlin, and Vienna. Which city is largest by population?"
```
**Verify:** `replay.py <sid> | grep "comparator" -B 5 -A 10` shows Comparator node with ranked output

---

## Session Inspection Commands

```bash
# Get most recent session ID
SID=$(ls -t code/state/sessions/ | head -1)
echo $SID

# View full session trace
uv run python code/replay.py $SID

# View just nodes and their status
uv run python code/replay.py $SID | grep "skill"

# View specific node details
uv run python code/replay.py $SID | grep "researcher" -A 20

# View graph structure (JSON)
cat code/state/sessions/$SID/graph.json | python3 -m json.tool | head -50

# View specific node output
cat code/state/sessions/$SID/nodes/n:2.json | python3 -m json.tool
```

---

## Diagnostic Patterns

### Is Parallel Execution Happening?
```bash
SID=$(ls -t code/state/sessions/ | head -1)
python3 << 'EOF'
import json
with open(f"code/state/sessions/{SID}/graph.json") as f:
    g = json.load(f)
    for nid, node in g.get("nodes", {}).items():
        print(f"{nid}: {node['skill']} (status={node['status']})")
EOF
# Look for multiple researcher nodes at same depth with status "complete"
```

### Did Coder Run?
```bash
SID=$(ls -t code/state/sessions/ | head -1)
uv run python code/replay.py $SID | grep -A 30 '"skill": "coder"'
# Should show: "output": {"code": "...", "rationale": "..."}
```

### Did SandboxExecutor Run?
```bash
SID=$(ls -t code/state/sessions/ | head -1)
uv run python code/replay.py $SID | grep -A 20 '"skill": "sandbox_executor"'
# Should show: "output": {"exit_code": 0, "stdout": "...", ...}
```

### Did Critic Run?
```bash
SID=$(ls -t code/state/sessions/ | head -1)
uv run python code/replay.py $SID | grep -A 5 '"skill": "critic"'
# Should show: "output": {"verdict": "pass"} or {"verdict": "fail"}
```

### Did Recovery Happen?
```bash
SID=$(ls -t code/state/sessions/ | head -1)
uv run python code/replay.py $SID | grep -E "(failed|recovery)" -B 2 -A 2
```

---

## Wall-Clock Timing Verification

```bash
# For parallel queries, timing should be:
# wall-clock ≈ max(branch times) + overhead

# Example: 3 researchers each taking ~5s
# Sequential would be: 3 * 5 = 15s
# Parallel should be: ~5 + formatter = ~7-8s

# Check in replay output:
uv run python code/replay.py $SID | grep -E "n:[0-9].*researcher|complete"
# Look at elapsed_s times — they should overlap, not stack
```

---

## Expected Skill Integration

### Flow Pattern for Query 5 (Growth Rates)
```
planner
  ├── researcher(Lagos)
  ├── researcher(Cairo)
  ├── researcher(Kinshasa)
  
  ├── coder
  │   └── sandbox_executor (auto-inserted)
  │
  └── formatter
```

**Why this pattern?**
- Three researchers run in parallel (asyncio.gather)
- Coder generates Python to compute growth rates
- SandboxExecutor auto-inserts (internal_successors in yaml)
- Formatter combines all results into final answer

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| "no code in upstream coder output" | Coder's JSON must have "code" field, not empty |
| Coder node doesn't appear | Planner must emit it; check USER_QUERY needs computation |
| SandboxExecutor shows errors | Check Coder's Python syntax; it must be self-contained |
| Parallel nodes run sequentially | Check Planner emits siblings with independent inputs |
| Critic never inserts | Distiller must be upstream; agent_config must have `critic: true` |
| Gateway connection error | Check gateway is running: `cd gateway && uv run main.py` |

---

## Expected Final Answers

### Query 1: Hello
```
Hello! I'm an AI assistant ready to help. How can I assist you today?
```

### Query 2: Shannon
```
Claude Shannon (1916-2001) made three key contributions to information theory:
1. Information entropy - the mathematical measure of information content
2. Channel capacity - showing the maximum rate information can be transmitted
3. The bit - defining the binary unit as fundamental to information
```

### Query 3: Populations
```
The current populations are:
- New York: 8.3 million
- Tokyo: 13.9 million
- London: 9 million
```

### Query 4: Nonexistent File
```
The file /nonexistent/path.txt does not exist on this system. 
I cannot read or display its contents as it is not accessible.
```

### Query 5: Growth Rates
```
Current populations and growth rates:
- Lagos: ~15.2M, growing ~3.2% annually
- Cairo: ~20.9M, growing ~2.1% annually
- Kinshasa: ~13.5M, growing ~3.7% annually

Kinshasa is growing fastest at approximately 3.7% per year.
```

---

## Recording Demo

Use OBS or built-in tools:

```bash
# macOS: Use QuickTime Player
# Windows: Use OBS or Xbox Game Bar (Win+G)
# Linux: Use OBS or SimpleScreenRecorder

# Key: Show 
# 1. Terminal with queries running
# 2. Final answers for each query
# 3. Mention wall-clock times
# 4. Don't need to show replay.py (but you can)
```

**Edit video to:**
- Trim setup/boring parts
- Keep 3-10 minutes total
- Show queries 1-5 clearly
- Export as MP4 or WebM
- Upload and get shareable link

---

## Submission Template

Create `session8/RESULTS.md`:

```markdown
# Session 8 Results

## Query Results

### 1. Hello
Command: `uv run python flow.py "hello"`
Result: ✅ PASS
Final Answer: Hello! I'm an AI assistant...
Wall-clock: 0.8s

### 2. Claude Shannon
Command: `uv run python flow.py "Fetch https://..."`
Result: ✅ PASS
Final Answer: Claude Shannon (1916-2001)...
Wall-clock: 8.2s

... (repeat for all 5)

## Custom Patterns

### Parallel Fan-Out
Query: Compare Tokyo, Mumbai, Shanghai, Mexico City
Result: ✅ PASS
Evidence: 4 researcher nodes at same depth, wall-clock 9.5s

... (repeat for other patterns)

## Demo Video
YouTube/Drive link: https://...
Duration: 5 minutes
Shows: All 5 base queries with correct answers

## Unit Tests
\`\`\`
$ uv run pytest tests/ -v
tests/test_recovery.py::test_classify_transient PASSED
tests/test_recovery.py::test_classify_validation PASSED
... all pass
\`\`\`
```

---

## Success Checklist

Before declaring done:

- [ ] All 5 base queries produce final_answer
- [ ] Query 3 (populations) runs in <15s
- [ ] Query 4 (nonexistent) shows graceful failure
- [ ] Query 5 (growth rates) uses Coder for computation
- [ ] Parallel fan-out query verified with replay.py
- [ ] Critic pass and fail both demonstrated
- [ ] Comparator skill works in at least one query
- [ ] Demo video recorded and linked
- [ ] RESULTS.md has actual outputs (not paraphrased)
- [ ] All unit tests pass

Good luck! 🚀
