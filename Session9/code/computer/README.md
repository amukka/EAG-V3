# Session 10 — Computer-Use Skill

A Computer-Use skill that drives real macOS desktop applications through
[`cua-driver`](../CUA_DRIVER_GUIDE.md), wired into the Session 9 multi-agent
runtime exactly the way the Browser skill is. The orchestrator (`flow.py`) is
**not modified** — integration is one catalogue entry, one prompt file, one
dispatch branch, and one schema. The interesting work is the five layers above
the driver.

```
User goal
   │
   ▼
Planner ──▶ Computer skill ──▶ (cascade picks the cheapest correct layer)
                 │
   ┌─────────────┼───────────────┬────────────────┐
   ▼             ▼               ▼                ▼
 extract     deterministic     a11y            vision
 (AX text)   (hotkeys/page)    (AX + LLM)      (screenshot + VLM)
   │             │               │                │
   └─────────────┴───────────────┴────────────────┘
                 │
        precondition guard (TCC / activation / empty-tree)
                 │
              cua-driver daemon  (AX / input / screenshots)
```

## Why this mirrors the Browser skill

Session 9's Browser cascade transfers to the desktop wholesale (session10.txt
§6): same four layers, same "do the cheap thing first, escalate only on
failure" discipline, same `output.path` surfaced to the replay viewer. The
desktop differences are local to each layer:

| | Browser (S9) | Computer (S10) |
|---|---|---|
| Layer 1 extract | httpx + trafilatura | read text off the AX tree |
| Layer 2a deterministic | CSS selectors | hotkeys / keystrokes / `page` CDP selectors |
| Layer 2b a11y | DOM a11y snapshot + LLM | AX-tree markdown + LLM (`element_index`) |
| Layer 3 vision | set-of-marks + VLM | screenshot + VLM, click by `(x, y)` |
| precondition block | CAPTCHA / login → `gateway_blocked` | empty AX / no TCC → `precondition_blocked` |

## The five layers above cua-driver (what we built)

cua-driver does perception and action only. Everything else is this skill
(CUA_DRIVER_GUIDE §8):

1. **Goal decomposition** — the Planner maps a goal to an app + subgoal; the
   skill's metadata contract (`goal`, `app`, `bundle_id`, `sequence`, …) is the
   wire format.
2. **Perception interpretation** — `computer/cua.py::parse_elements` turns the
   AX markdown into a de-duped element list (first occurrence wins, GUIDE §6.3);
   the `query` pre-filter shrinks the legend (GUIDE §6.4).
3. **Action sequencing** — `computer/driver.py` runs the scan→act→verify loop,
   re-scanning every turn because `element_index` is a turn-scoped token
   (Invariants A & B, GUIDE §5).
4. **Error recovery** — empty AX tree raises `PreconditionError`; the skill maps
   genuine permission failures to `error_code="precondition_blocked"` and
   escalates an AX-empty *canvas* to vision instead.
5. **Vision fallback** — `VisionDriver` screenshots the window and clicks by
   coordinate when there are no AX nodes to address.

## Files

| File | Role |
|---|---|
| `computer/cua.py` | cua-driver subprocess client, daemon lifecycle, the empty-tree precondition guard, AX-markdown parser |
| `computer/driver.py` | scan-act-verify loop; `A11yDriver` (text LLM) and `VisionDriver` (vision LLM) |
| `computer/skill.py` | the four-layer cascade; `ComputerSkill.run(NodeSpec) → AgentResult` |
| `computer/tasks.py` | the three assignment tasks as metadata dicts |
| `computer/assets/sketch_canvas.html` | canvas-only vision target (no AX nodes) |
| `prompts/computer.md` | planner-facing skill description |
| `run_computer_tasks.py` | evidence harness: runs the tasks, prints replay blocks, records trajectories |
| `tests/test_computer_cascade.py` | deterministic cascade-routing tests (no binary/gateway needed) |

Wiring: `computer:` entry in `agent_config.yaml`, `ComputerOutput` +
`precondition_blocked` in `schemas.py`, one `if skill.name == "computer"`
branch in `skills.py`.

## The three tasks

| # | Task | Layer | Constraint satisfied |
|---|------|-------|----------------------|
| 1 | **Calculator** — compute 7 × 8, confirm 56 | `deterministic` (2a) | **zero vision** |
| 2 | **VS Code** — new file + type, via `page`/CDP | `deterministic` via `page` (2 special case) | **Electron page path** |
| 3 | **Sketch** — click the red swatch on a canvas | `vision` (3) | **uses vision** |

Together they satisfy all three assignment constraints (session10.txt §14):
≥1 vision, ≥1 Electron page path, ≥1 zero-vision.

### Task 1 — Calculator (Layer 2a, zero vision)
Pure keystroke sequence (`7 * 8 =`), no scan and no LLM in the loop. This is
the layer students skip because it is boring, and the layer that keeps the
assignment cheap. The post-condition scan confirms `56` shows in the AX display
readout — a click that "succeeded" is not proof the goal was met (GUIDE §12).

### Task 2 — VS Code (Electron `page`/CDP path)
VS Code is Chromium in disguise; to AX it is one opaque `AXWebArea` (GUIDE §7.2).
Launching with `electron_debugging_port: 9222` unlocks the `page` tool, which
drives the DOM by CSS selector. The selector sequence opens an untitled editor
and types a line, then reads it back. **VS Code DOM class names are version-
specific** — confirm a selector first with
`cua-driver call page '{"pid":<pid>,"action":"eval","script":"document.querySelector(\".monaco-editor\")!==null"}'`.

### Task 3 — Sketch canvas (Layer 3 vision)
`assets/sketch_canvas.html` paints three colour swatches as canvas pixels.
Opened in Chrome app mode (`--app=…`, no tab/URL bar) the window has a near-
empty AX tree, so the a11y layer finds nothing and the cascade escalates to
vision. `force_path: "vision"` pins the layer so the run deterministically
exercises Layer 3 (the documented escape hatch for "caller already knows
vision is required"). The VLM locates the red square by colour and returns a
click coordinate.

## Running

```bash
# 1. install cua-driver (sudo-free)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh)"

# 2. grant TCC (Accessibility + Screen Recording) — binds to com.trycua.driver
cua-driver permissions grant

# 3. (vision task only) start the V9 gateway on :8109

# 4. preflight, then run
uv run python run_computer_tasks.py --check
uv run python run_computer_tasks.py            # all three
uv run python run_computer_tasks.py calc       # one task

# tests need neither the binary nor the gateway
uv run python -m pytest tests/test_computer_cascade.py -q
```

Every run records its cua-driver trajectory (`metadata.record=True`) under
`state/sessions/<sid>/computer/.../trajectory/` and writes a `summary.json`.
The trajectory directory plus the YouTube demo are the submission's evidence
(session10.txt §11). The agent-cursor overlay is enabled per run so the demo
shows where the agent is acting.

## Failure modes encountered / guarded

All share the Session 7/9 "the success path and the failure path look identical
from the caller" shape — detection means inspecting the side effect.

- **Empty AX tree is silent** (GUIDE §6.6). `get_window_state` returns
  `element_count: 0` rather than raising. `cua.py` guards every AX scan and
  raises `PreconditionError`, which the skill maps to `precondition_blocked`
  with an actionable message (grant TCC / activate / Qt env / Electron port).
- **Background-launch stub tree** (GUIDE §6.1). `launch_app` does not steal
  focus, so the first scan sees only the menu bar. The skill activates via
  AppleScript and sleeps before scanning. `bring_to_front` is Windows-only.
- **Process-scoped element cache** (GUIDE §6.2). Indices only survive inside the
  daemon. `ensure_daemon` starts `cua-driver serve` before any indexed action.
- **Index reflow between turns** (Invariant B). The driver re-scans at the top
  of every turn and never reuses an index across turns; menu/dialog-opening
  actions are forced to be the only action in their turn.
- **Canvas vs. permission ambiguity.** An empty tree can mean "no grant" or "no
  AX nodes (canvas)". The cascade escalates AX-empty to vision; only if vision
  also cannot proceed is it reported as `precondition_blocked`.

## Live validation notes — cua-driver 0.6.8 vs. the guide

Running on the real driver surfaced several deltas from CUA_DRIVER_GUIDE.md
(which was written against an earlier/idealised build). Each was a silent
wrong-behaviour bug of the Session 7/9 shape — fixed and captured here:

- **AX element tag is `[N]`, not `[element_index N]`.** The parser accepts both.
- **Control labels come in two forms.** Menu items are quoted
  (`AXMenuItem "About This Mac"`); buttons/controls are parenthesised
  (`AXButton (7) [id=Seven ...]`). Reading only quotes left every button
  nameless and blinded the a11y layer. The parser now reads quote, paren, then
  `id=` as fallback.
- **A process owns several windows.** The system menu bar is a full-width, 30px,
  off-screen pseudo-window; returning it made `get_window_state` walk only the
  menu (the "204 elements, 0 buttons" symptom). `first_window_id` now scores by
  on-screen + area and skips menu-bar shapes.
- **`press_key` only accepts letters, digits, and named keys** (`return`, `tab`,
  …) — operators like `*`/`+`/`=` are invalid. Multiply goes through
  `hotkey(["shift","8"])`, equals through `return`.
- **The display wraps its value in bidi marks** (U+200E). Verification strips
  them and matches against `AXStaticText` *values* only — a raw substring
  search for `56` also hits the menu element index `[56]` (a false positive).
- **`page` actions are** `execute_javascript` / `get_text` / `query_dom` /
  `click_element` (+ `window_id` required) — not the `click`/`type`/`eval`
  the guide implied.
- **Electron CDP needs a fresh launch.** `creates_new_application_instance`
  returns `pid=-1` for VS Code (single-instance lock), so the **VS Code task
  must run when VS Code is not already running** — from a Terminal Claude
  session, not the VS Code extension. The skill raises `precondition_blocked`
  with guidance rather than driving a port-less instance. `list_windows`
  exposes `app_name`/`title` (not `app`/`owner`).

## Submission checklist (session10.txt §14)

- [x] Computer-Use skill drops into the S9 catalogue; `flow.py` unchanged
- [x] Five-layer architecture visible in code
- [x] Three tasks: ≥1 vision, ≥1 Electron page path, ≥1 zero-vision
- [x] Every run recorded with `start_recording`
- [ ] GitHub repo README (this file) + YouTube demo with agent-cursor overlay
- [ ] Run live on a machine with cua-driver installed + TCC granted

## Youtube Video
https://youtu.be/IzStqE_l0i0
