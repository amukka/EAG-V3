The Computer-Use skill drives real desktop applications through cua-driver
(the OS accessibility + input bridge). Like the Browser skill it walks a
four-layer cascade from the cheapest path upward and chooses the layer
internally — you pass a `goal` and a target app, the skill decides how.

    Layer 1  extract        read text straight off the accessibility tree
    Layer 2a deterministic  fixed hotkey / keystroke or page-selector sequence
    Layer 2b a11y           AX-tree markdown + a cheap text LLM (the workhorse)
    Layer 3  vision         screenshot + vision LLM, click by coordinate

Above the cascade is the precondition layer: the cua-driver daemon must be
running, the app launched and activated, and the accessibility tree non-empty.

Inputs (all under `metadata`):
  goal                     (required) what to accomplish in the active window
  app                      friendly name for activation, e.g. "Calculator"
  bundle_id                launch target, e.g. "com.apple.calculator"
  force_path               'extract'|'deterministic'|'a11y'|'vision' to pin a layer
  sequence                 Layer 2a fixed action list (hotkey/key/type/click/wait)
  page_actions             Electron CDP path: list of {action, selector, value?}
  electron_debugging_port  launch flag that unlocks the page (CDP) path
  query / verify_query     AX scan pre-filter, and post-condition text to confirm
  record                   true → wrap the run in start/stop_recording (evidence)

Output: `ComputerOutput` with `path` (the layer that actually ran), `actions`
(the per-turn record the replay viewer walks), `content` (AX text or read-back),
`verified` (post-condition result — a click that returned success is NOT proof
the goal was met), and `trajectory_dir` (the cua-driver recording).

When the AX tree is empty because permissions were never granted, the skill
returns `error_code="precondition_blocked"` and no content — the desktop twin
of the Browser skill's gateway_blocked. When the tree is empty because the
surface has no AX nodes (a canvas or game), the cascade escalates to vision.
The Planner reads `error_code` to route recovery (re-grant prompt vs. retry).
