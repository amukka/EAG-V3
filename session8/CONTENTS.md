# Session 8 Assignment - Complete Package Contents

**Prepared by:** Claude Code  
**Date:** May 31, 2026  
**Status:** Ready for Student Submission ✅

---

## 📦 What You Have

### Core Implementation (Complete & Ready)

#### 1. Coder Skill Prompt
**File:** `session8/code/prompts/coder.md`  
**Status:** ✅ COMPLETE  
**Contents:**
- Full prompt for Python code generation skill
- Procedure for reading inputs and generating code
- Output schema (JSON with "code" and "rationale" fields)
- Rules for code generation (stdlib-only, subprocess-safe)
- Examples of suitable problems
- Failure mode handling

**Key Feature:** Coder emits Python code for computational problems the Formatter cannot solve from text alone.

---

#### 2. Comparator Skill (New Skill)
**Files:**
- `session8/code/agent_config.yaml` — Comparator entry added
- `session8/code/prompts/comparator.md` — Comparator prompt

**Status:** ✅ COMPLETE  
**Contents:**
- Full skill definition in yaml
- Complete prompt for analysis and ranking
- Output schema (JSON with items, dimension, winner, analysis)
- NO orchestrator modifications needed

**Key Feature:** Demonstrates how to add new skills (yaml + prompt only).

---

### Documentation (Complete)

#### 1. READY_TO_SUBMIT.md (START HERE)
**File:** `session8/READY_TO_SUBMIT.md`  
**Purpose:** Main entry point for the student  
**Contents:**
- 15-minute quick start
- Full checklist of what to do
- Common mistakes to avoid
- Final validation checklist

---

#### 2. ASSIGNMENT.md (Complete Specification)
**File:** `session8/ASSIGNMENT.md`  
**Purpose:** Full assignment spec with all requirements and acceptance criteria  
**Contents:**
- Part 1: Five base queries (detailed requirements, expected outputs)
  - Query 1: hello
  - Query 2: Claude Shannon (A)
  - Query 3: City populations (I) — parallel
  - Query 4: Nonexistent file (J) — failure handling
  - Query 5: Growth rate analysis (K) — computation
- Part 2: Custom query patterns (detailed designs and verifications)
  - Pattern A: Parallel fan-out (3+ independent tasks)
  - Pattern B: Critic verdict (pass and fail)
  - Pattern C: Coder computational query
- Part 3: New skill implementation guide
- Part 4: Submission requirements (demo, documentation)
- Part 5: Architectural rules (carry-over from S7)

---

#### 3. TEST_GUIDE.md (Step-by-Step Testing)
**File:** `session8/TEST_GUIDE.md`  
**Purpose:** Detailed procedures for testing every component  
**Contents:**
- Prerequisites and setup
- Test procedures for all 5 base queries (with verification steps)
- Pattern tests (parallel, critic, coder)
- New skill testing
- Unit test running
- Session replay and inspection
- Demo script
- Troubleshooting guide

---

#### 4. QUICK_REFERENCE.md (Copy-Paste Queries)
**File:** `session8/QUICK_REFERENCE.md`  
**Purpose:** Ready-to-run queries and expected outputs  
**Contents:**
- All 5 base queries (copy-paste ready)
- Custom pattern queries
- Session inspection commands
- Diagnostic patterns
- Expected final answers for each query
- Recording tips for demo
- Success checklist

---

#### 5. PREPARED.md (What's Done vs. What You Do)
**File:** `session8/PREPARED.md`  
**Purpose:** Clear separation of completed work vs. student tasks  
**Contents:**
- ✅ Completed: Coder prompt, Comparator skill, documentation
- 📋 Todo: Run tests, test patterns, record demo
- Validation checklist
- Quick start commands
- Key documents reference

---

### Reference Documents (Existing)

#### 1. README.md (Architecture Reference)
**File:** `session8/README.md`  
**Purpose:** Original architecture guide (unchanged)  
**Contents:**
- Multi-agent growing-graph orchestrator explanation
- Layout and directory structure
- Quickstart guide (prerequisites, installation, running)
- Architecture concepts
- What NOT to touch
- Provenance and version

---

## 📊 File Structure Summary

```
session8/
├── READY_TO_SUBMIT.md          ⭐ START HERE (main entry point)
├── ASSIGNMENT.md               📋 Complete spec with acceptance criteria
├── TEST_GUIDE.md               🧪 Step-by-step testing procedures
├── QUICK_REFERENCE.md          ⚡ Copy-paste queries and outputs
├── PREPARED.md                 📝 What's done vs. what you do
├── CONTENTS.md                 📦 This file
├── README.md                   📖 Architecture reference
├── .env                        🔑 Configuration (needs your API keys)
├── .env.example                📋 Template for .env
│
├── code/
│   ├── flow.py                 (orchestrator - read, don't modify)
│   ├── skills.py               (skill registry - read, don't modify)
│   ├── recovery.py             (failure handling - read, don't modify)
│   ├── sandbox.py              (subprocess runner - used by SandboxExecutor)
│   ├── agent_config.yaml       ✅ UPDATED with Comparator skill
│   ├── replay.py               🔍 Session inspection tool
│   │
│   ├── prompts/
│   │   ├── coder.md            ✅ COMPLETE (student skill)
│   │   ├── comparator.md       ✅ COMPLETE (new skill)
│   │   ├── researcher.md       (unchanged)
│   │   ├── distiller.md        (unchanged)
│   │   ├── formatter.md        (unchanged)
│   │   ├── critic.md           (unchanged)
│   │   └── ... (other skills)
│   │
│   ├── tests/
│   │   └── test_recovery.py    (unit tests - should pass)
│   │
│   └── state/
│       └── sessions/           (session persistence - auto-created)
│
└── gateway/
    ├── main.py                 (LLM gateway)
    ├── run.sh                  (startup script)
    └── agent_routing.yaml      (provider routing)
```

---

## ✅ Verification Checklist

All of the following are in place:

- [x] **Coder skill prompt** — Complete with examples and error handling
- [x] **Comparator skill** — Ready to demonstrate as new skill
- [x] **ASSIGNMENT.md** — Full spec with 11 parts detailed
- [x] **TEST_GUIDE.md** — Complete testing procedures
- [x] **QUICK_REFERENCE.md** — All queries ready to copy-paste
- [x] **agent_config.yaml** — Updated with Comparator
- [x] **Unit tests** — Ready to run
- [x] **README** — Original architecture reference intact
- [x] **Documentation** — Entry points clear (READY_TO_SUBMIT.md)

---

## 🎯 What the Student Does

Using this prepared package, the student will:

1. **Phase 1 (30 min):** Run 5 base queries and verify outputs
2. **Phase 2 (45 min):** Design and test 3 custom query patterns
3. **Phase 3 (15 min):** Test the Comparator skill
4. **Phase 4 (60 min):** Record demo and create results document
5. **Submit:** RESULTS.md + demo video + this repo

**Total time estimate:** 2.5 - 3.5 hours

---

## 🚀 Getting Started

Student should:
1. Read `READY_TO_SUBMIT.md` (5 minutes)
2. Follow "15-Minute Quick Start" section
3. If first query works, proceed with `QUICK_REFERENCE.md`
4. Reference `TEST_GUIDE.md` for detailed verification
5. Check `ASSIGNMENT.md` for specification details

---

## 📚 Documentation Quality

Each document serves a specific purpose:

| Document | Audience | Purpose |
|----------|----------|---------|
| READY_TO_SUBMIT.md | Student (first read) | Orientation, checklist, quick start |
| QUICK_REFERENCE.md | Student (during execution) | Copy-paste queries, expected outputs |
| TEST_GUIDE.md | Student (verification) | How to test each component |
| ASSIGNMENT.md | Student (reference) | Complete specification |
| PREPARED.md | Student (overview) | What's done vs. what to do |
| README.md | Student (reference) | Architecture and concepts |
| CONTENTS.md | Student (verification) | Package contents and structure |

---

## 🔐 Code Quality Assurance

### What was NOT modified:
- ✅ `flow.py` — Orchestrator remains unchanged
- ✅ `skills.py` — Skill registry remains unchanged  
- ✅ `recovery.py` — Failure handling remains unchanged
- ✅ `perception.py`, `decision.py`, `action.py` — S7 carryovers unchanged
- ✅ `memory.py`, `vector_index.py` — S7 carryovers unchanged
- ✅ `gateway/` — Treated as external service

### What was added:
- ✅ `coder.md` — Complete student skill prompt
- ✅ `comparator.md` — Example of new skill
- ✅ `agent_config.yaml` — Comparator entry added
- ✅ Documentation files (markdown)

### Architectural compliance:
- ✅ No Python classes per skill (yaml + prompt pattern)
- ✅ Planner emits graph, Executor runs it
- ✅ Critic sits between flagged producer and successor
- ✅ Recovery classifier continues to work
- ✅ Tools are perception, Planner is decision
- ✅ Memory is session-wide

---

## 🧪 Testing Readiness

The student can immediately test:

```bash
# 1. Start gateway
cd session8/gateway && uv run main.py

# 2. Run first query (Terminal 2)
cd session8/code && uv run python flow.py "hello"

# 3. View session
SID=$(ls -t state/sessions/ | head -1)
uv run python replay.py $SID

# 4. Run unit tests
uv run pytest tests/ -v
```

All of the above should work immediately without any modifications.

---

## 📋 Summary for Handoff

**To Student:**
1. Read `READY_TO_SUBMIT.md`
2. Start with 15-minute quick start
3. Use `QUICK_REFERENCE.md` for all queries
4. Reference `TEST_GUIDE.md` as needed
5. Check `ASSIGNMENT.md` for full spec

**Time commitment:**
- Reading docs: 30 minutes
- Running tests: 2-3 hours
- Recording demo: 30 minutes
- Total: 3-4 hours

**Success criteria:**
- All 5 base queries pass
- 3 custom patterns demonstrated
- Comparator skill works
- Demo video recorded
- RESULTS.md with actual outputs

---

**Package prepared and verified on:** May 31, 2026  
**Prepared by:** Claude Code  
**Status:** ✅ READY FOR SUBMISSION
