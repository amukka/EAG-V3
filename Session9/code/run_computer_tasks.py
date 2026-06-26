"""Session 10 runner: drive the three Computer-Use tasks and print evidence.

Usage:
    uv run python run_computer_tasks.py            # run all three
    uv run python run_computer_tasks.py calc       # one task: calc|vscode|sketch
    uv run python run_computer_tasks.py --check     # preflight only (no run)

Preconditions (macOS):
    1. cua-driver installed and on ~/.local/bin
       /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh)"
    2. cua-driver permissions grant      # Accessibility + Screen Recording
    3. llm_gatewayV9 serving on :8109     # only needed for the sketch (vision) task

This is the assignment's evidence harness: every task records its cua-driver
trajectory (metadata.record=True) and this runner writes a per-task replay
block plus a machine-readable summary under state/sessions/<sid>/computer/.
flow.py is never touched — the skill is invoked exactly as the orchestrator
would invoke it, through ComputerSkill.run(NodeSpec).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from computer.cua import CuaDriver, CuaError
from computer.skill import ComputerSkill
from computer.tasks import ALL_TASKS, TASK_REGISTRY
from schemas import AgentResult, NodeSpec

ROOT = Path(__file__).parent


# ── preflight ───────────────────────────────────────────────────────────────
def preflight() -> bool:
    ok = True
    try:
        cua = CuaDriver()
        print(f"  cua-driver binary   {cua.bin}")
    except CuaError as e:
        print(f"  cua-driver binary   MISSING — {e}")
        return False
    running = cua.status()
    print(f"  daemon running      {running}  (will auto-start if not)")
    print("  gateway (:8109)     required only for the sketch/vision task")
    print("  permissions         run `cua-driver permissions grant` if the "
          "first scan returns element_count=0")
    return ok


# ── replay-style block (mirrors replay.py's per-node output) ─────────────────
def print_block(name: str, task: dict, result: AgentResult, elapsed: float) -> None:
    out = result.output or {}
    bar = "─" * 70
    print(f"\n{bar}\ntask        {name}")
    print(f"  goal        {task.get('goal', '')[:200]}")
    print(f"  app         {out.get('app')}  ({out.get('bundle_id')})")
    print(f"  success     {result.success}")
    print(f"  path        {out.get('path')}        ← cascade layer that ran")
    print(f"  turns       {out.get('turns')}")
    print(f"  verified    {out.get('verified')}")
    print(f"  elapsed     {elapsed:.1f}s")
    if result.error_code:
        print(f"  error_code  {result.error_code}")
    if result.error:
        print(f"  error       {result.error[:240]}")
    actions = out.get("actions") or []
    if actions:
        print("  actions:")
        for a in actions[:12]:
            if "turn" in a:
                th = (a.get("thinking") or "").replace("\n", " ")[:80]
                print(f"    turn {a['turn']}: {a.get('outcome')}  «{th}»")
            else:
                print(f"    step {a.get('step')}: {a.get('action')} → {a.get('outcome')}")
    if out.get("trajectory_dir"):
        print(f"  trajectory  {out['trajectory_dir']}")


async def run_one(name: str, task: dict, session_id: str) -> dict:
    skill = ComputerSkill(
        artifacts_root=str(ROOT / "state" / "sessions" / session_id / "computer"),
        session=session_id,
    )
    node = NodeSpec(skill="computer", inputs=["USER_QUERY"], metadata=task)
    t0 = time.time()
    try:
        result = await skill.run(node)
    except Exception as e:                                       # noqa: BLE001
        print(f"\ntask {name}: UNHANDLED {type(e).__name__}: {e}")
        return {"task": name, "success": False, "error": f"{type(e).__name__}: {e}"}
    elapsed = time.time() - t0
    print_block(name, task, result, elapsed)
    return {
        "task": name, "success": result.success,
        "path": (result.output or {}).get("path"),
        "turns": (result.output or {}).get("turns"),
        "verified": (result.output or {}).get("verified"),
        "error_code": result.error_code, "elapsed_s": round(elapsed, 2),
        "trajectory_dir": (result.output or {}).get("trajectory_dir"),
    }


async def main() -> int:
    args = [a for a in sys.argv[1:]]
    print("Session 10 — Computer-Use tasks\npreflight:")
    if not preflight():
        return 2
    if "--check" in args:
        return 0
    args = [a for a in args if not a.startswith("--")]

    if args:
        unknown = [a for a in args if a not in TASK_REGISTRY]
        if unknown:
            print(f"unknown task(s): {unknown}. choose from {list(TASK_REGISTRY)}")
            return 2
        selected = {k: TASK_REGISTRY[k] for k in args}
    else:
        selected = ALL_TASKS

    session_id = f"s10_computer_{int(time.time())}"
    print(f"\nsession {session_id}")
    summary = []
    for name, task in selected.items():
        summary.append(await run_one(name, task, session_id))

    out_dir = ROOT / "state" / "sessions" / session_id / "computer"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{'═' * 70}\nsummary written to {out_dir / 'summary.json'}")
    for s in summary:
        flag = "✓" if s.get("success") else "✗"
        print(f"  {flag} {s['task']:8} path={s.get('path')}  "
              f"verified={s.get('verified')}  {s.get('error_code') or ''}")
    # constraint check from the assignment
    paths = {s.get("path") for s in summary if s.get("success")}
    if len(selected) == len(ALL_TASKS):
        print("\nconstraint check:")
        print(f"  ≥1 vision         {'✓' if 'vision' in paths else '✗ (sketch task)'}")
        print(f"  ≥1 page/CDP path  see vscode task (path=deterministic via page tool)")
        print(f"  ≥1 zero-vision    {'✓' if {'deterministic','a11y','extract'} & paths else '✗'}")
    return 0 if all(s.get("success") for s in summary) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
