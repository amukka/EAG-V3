"""Session 10 assignment: the three Computer-Use tasks.

Each task is a metadata dict the Computer-Use skill consumes (the same dict the
Planner would put on a NodeSpec). They are chosen to satisfy the assignment's
three constraints between them (session10.txt §14):

    constraint                         satisfied by
    ─────────────────────────────────  ───────────────────────────────
    at least one task uses vision      TASK_3_SKETCH  (Layer 3)
    at least one uses the page path     TASK_2_VSCODE  (Electron CDP)
    at least one with zero vision       TASK_1_CALC    (Layer 2a)

Bundle ids / selectors are environment-specific. session10.txt is explicit
that "the code samples are shapes of code you will write" — tune the selectors
in TASK_2 to your installed VS Code version, and the click target in TASK_3 to
your display. The cascade architecture is the constant; the targets are not.
"""
from __future__ import annotations

from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"
_SKETCH_URL = f"file://{_ASSETS / 'sketch_canvas.html'}"


# ── Task 1: Calculator — Layer 2a deterministic, ZERO vision ────────────────
# Pure keystroke sequence: no scan, no LLM in the loop. macOS Calculator maps
# digits and operators to literal keys; `=` is Return. verify_query confirms
# the result shows in the AX display readout after the sequence runs.
TASK_1_CALC: dict = {
    "goal": "Compute 7 × 8 in Calculator and confirm the result is 56.",
    "app": "Calculator",
    "bundle_id": "com.apple.calculator",
    "force_path": "deterministic",
    "record": True,
    # Verify against the display's AXStaticText value (not a raw substring —
    # "56" also appears as menu element-index [56]). verify_display tells the
    # skill to check static-text values only.
    "verify_display": "56",
    "sequence": [
        # press_key only takes letters/digits/named keys — operators are not
        # valid key names, so multiply goes through shift+8 (the '*' char) and
        # equals through Return. Pure Layer 2a: no scan, no LLM.
        {"type": "key", "value": "7"},
        {"type": "hotkey", "keys": ["shift", "8"]},   # × (asterisk = shift+8)
        {"type": "key", "value": "8"},
        {"type": "key", "value": "return"},           # =
        {"type": "wait", "seconds": 0.3},
    ],
}


# ── Task 2: VS Code — Electron page (CDP) path ──────────────────────────────
# Launching with electron_debugging_port unlocks the page tool: cua-driver
# drives VS Code's DOM via Chrome DevTools Protocol instead of the opaque
# AXWebArea. The sequence opens a new untitled editor and types into it, then
# reads the editor text back as verification.
#
# NOTE: VS Code's DOM class names are stable across recent versions but not
# guaranteed — `cua-driver call page '{"pid":<pid>,"action":"eval",
# "script":"document.querySelector(\".monaco-editor\")!==null"}'` is the
# quickest way to confirm a selector before a run.
TASK_2_VSCODE: dict = {
    "goal": "In VS Code, confirm the workbench DOM is live over CDP, read the "
            "window title and open-editor tabs, and click the Explorer icon.",
    "app": "Visual Studio Code",
    "bundle_id": "com.microsoft.VSCode",
    "electron_debugging_port": 9222,
    # IMPORTANT: the debug port only attaches on a FRESH launch. VS Code's
    # single-instance lock makes creates_new_application_instance return pid=-1
    # (verified on 0.6.8), so this task must run when VS Code is NOT already
    # running — i.e. NOT from the VS Code Claude extension. Run it from a
    # Terminal Claude session (or quit VS Code first). If VS Code is already up
    # the skill stops with a clear precondition_blocked message rather than
    # silently driving a port-less instance.
    "record": True,
    # cua-driver 0.6.8 page actions: query_dom / execute_javascript /
    # click_element / get_text. These are read-mostly + one visible click, so
    # they exercise the CDP path without editing the user's files. Selectors
    # are stable across recent VS Code builds; confirm with
    #   cua-driver call page '{"pid":<pid>,"action":"query_dom","css_selector":".monaco-workbench"}'
    "page_actions": [
        {"action": "query_dom", "css_selector": ".monaco-workbench"},
        {"action": "execute_javascript",
         "javascript": "Array.from(document.querySelectorAll("
                       "'.tabs-container .tab .label-name')).map(e=>e.textContent)"},
        {"action": "click_element", "selector": ".activitybar .actions-container a"},
    ],
    "verify_js": "document.title",
}


# ── Task 3: Sketch (canvas-only) — Layer 3 vision ───────────────────────────
# The window is a single <canvas>; its swatches are painted pixels with no AX
# nodes. Opened in Chrome app mode the AX tree is empty, so the cascade
# escalates to vision. force_path pins vision so the run is deterministic about
# which layer it exercises (the documented escape hatch for "caller already
# knows vision is required"). The vision model finds the red swatch by colour
# and clicks it; the page title changes to "Sketch — red" on success.
TASK_3_SKETCH: dict = {
    "goal": "Click the red colour swatch in the palette on the left edge of "
            "the window. Do not guess — only click if you can clearly see a "
            "red square.",
    "app": "Google Chrome",
    # Launched in app mode so the window is just the canvas (see runner).
    "chrome_app_url": _SKETCH_URL,
    "force_path": "vision",
    "record": True,
}


# ── Task 2 (preferred Electron target): Slack — page (CDP) path ─────────────
# Slack is a stock Electron app that HONORS --remote-debugging-port (unlike VS
# Code/Cursor v24.15, which reject it by design). The skill detects pid=-1 from
# launch_app and resolves the real pid via list_apps, then drives the DOM with
# the page tool over CDP. Read-oriented + title read-back so it works whether or
# not you're signed in to a workspace; extend with click_element/typing once
# you confirm the CDP backend supports them on your build.
#
# Run with VS Code NOT involved:  uv run python run_computer_tasks.py slack
TASK_2_SLACK: dict = {
    "goal": "In Slack, confirm the DOM is live over CDP, read the document "
            "title and the visible text, and count the interactive elements.",
    "app": "Slack",
    "bundle_id": "com.tinyspeck.slackmacgap",
    "electron_debugging_port": 9222,
    "record": True,
    "page_actions": [
        {"action": "query_dom", "css_selector": "body"},
        {"action": "get_text"},
        {"action": "execute_javascript",
         "javascript": "document.querySelectorAll('button,a,[role=button]').length"},
    ],
    "verify_js": "document.title",
}


# The three tasks that satisfy the assignment constraints (≥1 vision via
# sketch, ≥1 Electron page path via slack, ≥1 zero-vision via calc). This is
# what `run_computer_tasks.py` runs by default and constraint-checks.
ALL_TASKS = {
    "calc":   TASK_1_CALC,
    "slack":  TASK_2_SLACK,
    "sketch": TASK_3_SKETCH,
}

# Selectable by name but not part of the default run — kept as a documented
# example of the CDP-blocked VS Code path (VS Code v24.15 rejects the debug
# port). Run with: run_computer_tasks.py vscode
EXTRA_TASKS = {
    "vscode": TASK_2_VSCODE,
}

TASK_REGISTRY = {**ALL_TASKS, **EXTRA_TASKS}
