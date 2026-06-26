"""Deterministic tests for the Computer-Use cascade routing.

These exercise ComputerSkill.run against a FakeCua that records every
cua-driver call and returns canned scans — no real binary, no daemon, no
gateway. The mechanism under test is the *cascade decision* (which layer runs
for which metadata, and how precondition failures surface), exactly the way
the Browser skill's layer routing is the testable contract rather than the
live OS behaviour.

The two LLM-driven layers (a11y / vision) are intentionally not exercised here
— they need the gateway and a live window. Layer 2a (deterministic), the
extract layer, the page path, and the precondition guard are all deterministic
and fully covered.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computer.cua import AXElement, CuaError, PreconditionError      # noqa: E402
from computer.skill import ComputerSkill                              # noqa: E402
from schemas import NodeSpec                                          # noqa: E402


class FakeCua:
    """Records calls; returns scans from a scripted queue."""

    def __init__(self, scan_markdown="- [element_index 19] AXStaticText \"56\"",
                 daemon_error=False, page_error=False):
        self.calls: list[tuple] = []
        self.scan_markdown = scan_markdown
        self.daemon_error = daemon_error
        self.page_error = page_error

    # lifecycle
    def ensure_daemon(self):
        if self.daemon_error:
            raise CuaError("daemon did not come up")
        self.calls.append(("ensure_daemon",))

    def set_agent_cursor(self, enabled=True): self.calls.append(("cursor", enabled))
    def start_recording(self, d): self.calls.append(("start_recording", d))
    def stop_recording(self): self.calls.append(("stop_recording",))

    # launch / focus
    def launch_app(self, **kw): self.calls.append(("launch_app", kw)); return {"pid": 4321}
    def activate(self, app, settle=1.0): self.calls.append(("activate", app))
    def first_window_id(self, pid, **kw): return 99
    def is_app_running(self, **kw): return None         # nothing pre-running in tests
    def kill_app(self, pid): self.calls.append(("kill_app", pid))

    # perception
    def scan(self, pid, wid, query=None, guard=True):
        self.calls.append(("scan", pid, wid, query))
        if not self.scan_markdown and guard:
            raise PreconditionError("empty AX tree")
        els = [AXElement(19, "AXStaticText", "56", self.scan_markdown)]
        return {"element_count": len(els), "tree_markdown": self.scan_markdown}, els

    # actions
    def press_key(self, pid, wid, key): self.calls.append(("press_key", key))
    def type_text(self, pid, wid, text): self.calls.append(("type_text", text))
    def hotkey(self, keys, pid=None): self.calls.append(("hotkey", tuple(keys)))
    def click(self, pid, wid, **kw): self.calls.append(("click", kw))
    def page(self, pid, action, **kw):
        if self.page_error:
            raise RuntimeError("selector not found")
        self.calls.append(("page", action, kw))
        return {"text": "// TODO line"}


def _run(task: dict, **fake_kw):
    fake = FakeCua(**fake_kw)
    skill = ComputerSkill(cua=fake)
    res = asyncio.run(skill.run(NodeSpec(skill="computer", metadata=task)))
    return res, fake


# ── Layer 2a: deterministic sequence (the Calculator task shape) ─────────────
def test_deterministic_sequence_routes_and_verifies():
    task = {
        "goal": "Compute 7 × 8 in Calculator and confirm the result is 56.",
        "app": "Calculator", "bundle_id": "com.apple.calculator",
        "force_path": "deterministic", "verify_query": "56",
        "sequence": [{"type": "key", "value": "7"}, {"type": "key", "value": "*"},
                     {"type": "key", "value": "8"}, {"type": "key", "value": "="}],
    }
    res, fake = _run(task)
    assert res.success
    assert res.output["path"] == "deterministic"
    assert res.output["verified"] is True            # "56" found in the verify scan
    assert res.output["turns"] == 4
    # no LLM, but the four keystrokes were pressed in order
    pressed = [c[1] for c in fake.calls if c[0] == "press_key"]
    assert pressed == ["7", "*", "8", "="]


def test_deterministic_verify_fails_when_result_absent():
    task = {
        "goal": "Compute something", "app": "Calculator",
        "bundle_id": "com.apple.calculator", "force_path": "deterministic",
        "verify_query": "56", "sequence": [{"type": "key", "value": "1"}],
    }
    res, _ = _run(task, scan_markdown="- [element_index 19] AXStaticText \"42\"")
    assert res.output["verified"] is False           # display showed 42, not 56


# ── precondition layer ───────────────────────────────────────────────────────
def test_precondition_blocked_when_daemon_down():
    task = {"goal": "do a thing", "app": "Calculator",
            "bundle_id": "com.apple.calculator", "force_path": "deterministic",
            "sequence": [{"type": "key", "value": "1"}]}
    res, _ = _run(task, daemon_error=True)
    assert res.success is False
    assert res.error_code == "precondition_blocked"


# ── Layer 1: extract (read goal) ─────────────────────────────────────────────
def test_extract_layer_reads_ax_text():
    task = {"goal": "read the value of the display", "app": "Calculator",
            "bundle_id": "com.apple.calculator"}
    res, _ = _run(task)
    assert res.success
    assert res.output["path"] == "extract"
    assert "56" in (res.output["content"] or "")


# ── Electron page path → surfaced as deterministic ───────────────────────────
def test_page_actions_route_through_cdp():
    task = {
        "goal": "open a new file and type", "app": "Visual Studio Code",
        "bundle_id": "com.microsoft.VSCode", "electron_debugging_port": 9222,
        "verify_selector": ".monaco-editor .view-lines",
        "page_actions": [{"action": "click", "selector": ".x"},
                         {"action": "type", "selector": ".y", "value": "hi"}],
    }
    res, fake = _run(task)
    assert res.success
    assert res.output["path"] == "deterministic"     # page path is a Layer-2 special case
    assert any(c[0] == "page" for c in fake.calls)
    # launch carried the electron debugging port
    launch = next(c for c in fake.calls if c[0] == "launch_app")
    assert launch[1].get("electron_debugging_port") == 9222


def test_page_action_failure_is_interaction_failed():
    task = {"goal": "open a new file", "app": "Visual Studio Code",
            "bundle_id": "com.microsoft.VSCode", "electron_debugging_port": 9222,
            "page_actions": [{"action": "click", "selector": ".missing"}]}
    res, _ = _run(task, page_error=True)
    assert res.success is False
    assert res.error_code == "interaction_failed"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} computer-cascade tests pass")
