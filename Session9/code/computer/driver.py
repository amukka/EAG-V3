"""Computer-Use drivers — Layer 2b (a11y) and Layer 3 (vision).

The desktop twin of browser/driver.py. Same shape, different perception:

  - A11yDriver  reads the AX-tree markdown cua-driver returns and sends the
                element legend (text only) to V9 /v1/chat. Actions address
                elements by `element_index`. This is the workhorse layer.
  - VisionDriver captures a screenshot and sends it to V9 /v1/vision. Used
                only when AX is empty (canvas / game / opaque renderer);
                actions click by (x, y) pixel coordinate.

Both share the scan-act-verify loop from CUA_DRIVER_GUIDE §5 and its two
invariants:

  A. get_window_state once per turn before any element-indexed action — it
     builds the daemon's element_index cache.
  B. every scan replaces the previous index map; indices are turn-scoped.
     So we re-scan at the top of every turn and never reuse an index across
     turns.

Framework-free: cua-driver for the OS, the V9 gateway client (reused from the
Browser skill) for the LLM, Pillow only if the vision layer annotates. The
cua-driver calls are synchronous subprocess hops, wrapped in asyncio.to_thread
so an OS call and a gateway call never block each other.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from browser.client import V9Client

from .cua import AXElement, CuaDriver, PreconditionError


# ─── action vocabulary (shared) ──────────────────────────────────────────────
# A superset of the browser action schema, desktop-flavoured: element_index
# instead of mark for AX clicks, hotkey/press_key for the keyboard, click_xy
# for the vision layer's pixel clicks.
ACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["thinking", "actions"],
    "properties": {
        "thinking": {"type": "string", "description": "1–2 sentences of reasoning"},
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["click", "type", "key", "hotkey",
                                 "click_xy", "scroll", "wait", "done"],
                    },
                    "element_index": {"type": "integer"},
                    "value":  {"type": "string"},
                    "keys":   {"type": "array", "items": {"type": "string"}},
                    "x":      {"type": "integer"},
                    "y":      {"type": "integer"},
                    "direction": {"type": "string"},
                    "amount": {"type": "integer"},
                    "seconds": {"type": "number"},
                    "success": {"type": "boolean"},
                    "note":    {"type": "string"},
                },
            },
        },
    },
}


SYSTEM_PROMPT_A11Y = (
    "You are a desktop-driving agent. Each turn you receive a text legend of "
    "the active window's actionable accessibility elements, formatted as "
    "[element_index N] AXRole \"name\". There is no screenshot. Make progress "
    "toward the goal by emitting a short list of actions:\n"
    "  click(element_index)             — click that element\n"
    "  type(element_index, value)       — focus it and type `value`\n"
    "  key(value)                       — press one key like 'Return', 'Tab'\n"
    "  hotkey(keys=['cmd','s'])         — press a key combination\n"
    "  scroll(direction, amount?)       — direction in ['up','down','left','right']\n"
    "  wait(seconds)                    — let the UI settle\n"
    "  done(success, note)              — finish; success=true if goal met\n"
    "Choose the element whose name best matches the next step. You CANNOT see "
    "the screen — rely on names and roles.\n"
    "\nCRITICAL RULES (the AX tree reflows between turns; indices are "
    "turn-scoped tokens):\n"
    "  - Never bundle `done` with other actions. After a click/type, observe "
    "    next turn's legend to CONFIRM the state changed before declaring done.\n"
    "  - Any action that opens a menu, dialog, or popover MUST be the SINGLE "
    "    action that turn — the new elements only appear in the next scan. A "
    "    second action in the same turn would hit a stale element_index.\n"
    "  - At most 2 actions per turn. Most turns should be ONE action.\n"
    "Be terse in `thinking` — one or two sentences."
)

SYSTEM_PROMPT_VISION = (
    "You are a desktop-driving agent operating a window whose contents are NOT "
    "exposed through the accessibility tree (a canvas, game, or custom "
    "renderer). Each turn you receive a screenshot of the window. There are no "
    "element indices — you act by pixel coordinate. Available actions:\n"
    "  click_xy(x, y)        — click that window-local pixel coordinate\n"
    "  scroll(direction)     — direction in ['up','down','left','right']\n"
    "  wait(seconds)         — let the window settle\n"
    "  done(success, note)   — finish; success=true if the goal is met\n"
    "Coordinates are in the screenshot's CSS/point space with the window's "
    "top-left as (0, 0). Look carefully, name what you see in `thinking`, then "
    "give the single best click. Emit ONE action per turn unless the next is "
    "obvious. If the goal says not to guess and you cannot locate the target, "
    "return done(success=false)."
)


# ─── records ──────────────────────────────────────────────────────────────────
@dataclass
class StepRecord:
    turn: int
    thinking: str
    actions: list[dict]
    outcome: str
    provider: str
    model: str
    latency_ms: int
    tokens_in: int
    tokens_out: int


@dataclass
class DriverConfig:
    goal: str
    pid: int
    window_id: int
    app_name: str
    max_steps: int = 12
    max_failures: int = 3
    artifacts_dir: Optional[str] = None
    pause_between_steps: float = 0.5
    query: Optional[str] = None        # AX scan pre-filter (GUIDE §6.4)
    provider: Optional[str] = None
    model: Optional[str] = None


@dataclass
class DriverResult:
    success: bool
    note: str
    steps: list[StepRecord] = field(default_factory=list)
    final_markdown: str = ""
    precondition_blocked: bool = False


# ─── shared loop machinery ───────────────────────────────────────────────────
class BaseDriver:
    """Scan-act-verify loop. Subclasses provide SYSTEM_PROMPT, LAYER_NAME, and
    `_decide()` (which also owns whether the turn scans AX or screenshots)."""

    SYSTEM_PROMPT: str = ""
    LAYER_NAME: str = "base"

    def __init__(self, cua: CuaDriver, client: V9Client, config: DriverConfig):
        self.cua = cua
        self.client = client
        self.config = config
        self.steps: list[StepRecord] = []
        self.last_markdown: str = ""

    # ── perception helpers (run the blocking OS call off the event loop) ──────
    async def _scan(self) -> tuple[dict, list[AXElement]]:
        return await asyncio.to_thread(
            self.cua.scan, self.config.pid, self.config.window_id,
            self.config.query, True,
        )

    def _legend(self, elements: list[AXElement]) -> str:
        if not elements:
            return "(no actionable elements)"
        return "\n".join(f"  {e}" for e in elements)

    def _history_text(self) -> str:
        if not self.steps:
            return "(no actions yet)"
        lines = []
        for s in self.steps[-5:]:
            acts = ", ".join(
                f"{a.get('type')}({a.get('element_index', a.get('value', a.get('x', '')))})"
                for a in s.actions[:3]
            )
            lines.append(f"turn {s.turn}: {acts} → {s.outcome}")
        return "\n".join(lines)

    # ── action dispatch ───────────────────────────────────────────────────────
    async def _dispatch(self, action: dict) -> str:
        t = action.get("type", "")
        c, pid, wid = self.cua, self.config.pid, self.config.window_id
        try:
            if t == "click":
                await asyncio.to_thread(
                    c.click, pid, wid, element_index=int(action["element_index"]))
                return "ok"
            if t == "type":
                ei = int(action["element_index"])
                await asyncio.to_thread(c.click, pid, wid, element_index=ei)
                await asyncio.to_thread(c.type_text, pid, wid,
                                        str(action.get("value", "")))
                return "ok"
            if t == "key":
                await asyncio.to_thread(c.press_key, pid, wid,
                                        str(action.get("value", "Return")))
                return "ok"
            if t == "hotkey":
                await asyncio.to_thread(c.hotkey, list(action.get("keys", [])), pid)
                return "ok"
            if t == "click_xy":
                await asyncio.to_thread(c.click, pid, wid,
                                        x=int(action["x"]), y=int(action["y"]))
                return "ok"
            if t == "scroll":
                await asyncio.to_thread(
                    c.call, "scroll",
                    {"pid": pid, "window_id": wid,
                     "direction": action.get("direction", "down"),
                     "amount": int(action.get("amount", 5))})
                return "ok"
            if t == "wait":
                await asyncio.sleep(float(action.get("seconds", 0.5)))
                return "ok"
            if t == "done":
                return "ok"
        except KeyError as e:
            return f"error: action {t!r} missing field {e}"
        except Exception as e:                                  # noqa: BLE001
            return f"error: {type(e).__name__}: {e}"
        return f"error: unknown action {t!r}"

    async def _decide(self, state: dict, elements: list[AXElement], turn: int):
        """Returns (parsed_dict, GatewayResult). Subclass implements."""
        raise NotImplementedError

    async def step(self, turn: int) -> tuple[bool, bool, str]:
        state, elements = await self._scan()
        self.last_markdown = state.get("tree_markdown", "") or self.last_markdown
        parsed, result = await self._decide(state, elements, turn)

        if not parsed:
            self.steps.append(StepRecord(
                turn, "", [], f"error: no parsed output; raw={result.text[:120]!r}",
                result.provider, result.model, result.latency_ms,
                result.input_tokens, result.output_tokens))
            return False, False, "no parsed output"

        thinking = parsed.get("thinking", "")
        actions = parsed.get("actions") or []
        outcomes: list[str] = []
        done_seen = success_seen = False
        done_note = ""
        for a in actions:
            if a.get("type") == "done":
                done_seen = True
                success_seen = bool(a.get("success", False))
                done_note = a.get("note", "")
                outcomes.append(f"done({success_seen})")
                break
            outcome = await self._dispatch(a)
            outcomes.append(outcome)
            if outcome.startswith("error"):
                break
            await asyncio.sleep(self.config.pause_between_steps)

        self.steps.append(StepRecord(
            turn=turn, thinking=thinking, actions=actions,
            outcome=" | ".join(outcomes) or "ok",
            provider=result.provider, model=result.model,
            latency_ms=result.latency_ms,
            tokens_in=result.input_tokens, tokens_out=result.output_tokens))
        return done_seen, success_seen, done_note

    async def run(self) -> DriverResult:
        failures = 0
        try:
            for turn in range(1, self.config.max_steps + 1):
                done, success, note = await self.step(turn)
                if "error" in self.steps[-1].outcome:
                    failures += 1
                    if failures >= self.config.max_failures:
                        return DriverResult(False,
                                            f"giveup after {failures} consecutive failures",
                                            steps=self.steps,
                                            final_markdown=self.last_markdown)
                else:
                    failures = 0
                if done:
                    return DriverResult(success, note, steps=self.steps,
                                        final_markdown=self.last_markdown)
            return DriverResult(False, f"step cap reached ({self.config.max_steps})",
                                steps=self.steps, final_markdown=self.last_markdown)
        except PreconditionError as e:
            return DriverResult(False, str(e), steps=self.steps,
                                final_markdown=self.last_markdown,
                                precondition_blocked=True)


# ─── Layer 2b — a11y text ─────────────────────────────────────────────────────
class A11yDriver(BaseDriver):
    SYSTEM_PROMPT = SYSTEM_PROMPT_A11Y
    LAYER_NAME = "a11y"

    async def _decide(self, state, elements, turn):
        if self.config.artifacts_dir:
            d = Path(self.config.artifacts_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"turn_{turn:02d}_legend.txt").write_text(
                self._legend(elements), encoding="utf-8")

        prompt = (
            f"GOAL: {self.config.goal}\n\n"
            f"APP: {self.config.app_name}  (pid={self.config.pid})\n"
            f"ACTIONABLE ELEMENTS ({len(elements)}):\n{self._legend(elements)}\n\n"
            f"RECENT ACTIONS:\n{self._history_text()}\n\n"
            f"What is the next set of actions? Names and roles are your only "
            f"guide — no screenshot is available."
        )
        result = await self.client.chat(
            prompt, system=self.SYSTEM_PROMPT,
            schema=ACTION_SCHEMA, schema_name="AgentOutput", max_tokens=1024,
            provider=self.config.provider, model=self.config.model)
        return result.parsed, result


# ─── Layer 3 — vision ─────────────────────────────────────────────────────────
class VisionDriver(BaseDriver):
    SYSTEM_PROMPT = SYSTEM_PROMPT_VISION
    LAYER_NAME = "vision"

    async def _scan(self):
        # Vision does NOT depend on AX. Probe with guard=False so an empty tree
        # is fine, then capture the screenshot the model actually reasons over.
        state = await asyncio.to_thread(
            self.cua.get_window_state, self.config.pid, self.config.window_id,
            capture_mode="vision", query=None, screenshot_out_file=None, guard=False)
        return state, []

    async def _decide(self, state, elements, turn):
        from browser.client import V9Client  # noqa: F401  (type clarity)
        shot = None
        if self.config.artifacts_dir:
            d = Path(self.config.artifacts_dir)
            d.mkdir(parents=True, exist_ok=True)
            shot = str(d / f"turn_{turn:02d}_screen.png")
        else:
            import tempfile
            shot = str(Path(tempfile.gettempdir()) / f"cua_turn_{turn:02d}.png")
        await asyncio.to_thread(self.cua.screenshot, self.config.pid,
                                self.config.window_id, shot)
        data_url = _png_to_data_url(shot)

        prompt = (
            f"GOAL: {self.config.goal}\n\n"
            f"APP: {self.config.app_name}\n"
            f"RECENT ACTIONS:\n{self._history_text()}\n\n"
            f"The screenshot is the window's current state. What is the next "
            f"action? Click by pixel coordinate."
        )
        result = await self.client.vision(
            data_url, prompt, system=self.SYSTEM_PROMPT,
            schema=ACTION_SCHEMA, schema_name="AgentOutput", max_tokens=1024,
            provider=self.config.provider, model=self.config.model)
        return result.parsed, result


def _png_to_data_url(path: str) -> str:
    import base64
    raw = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
