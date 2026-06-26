"""Session 10: the Computer-Use skill — cascade wrapper over cua-driver.

The desktop twin of browser/skill.py. It translates the orchestrator's
NodeSpec contract into the typed ComputerOutput / AgentResult contract and
owns the four-layer cascade (CUA_DRIVER_GUIDE §6 / session10.txt §6):

    Layer 1  — extract        read text straight off the AX tree (no action)
    Layer 2a — deterministic  fixed hotkey/keystroke or page-selector sequence
                              (no LLM in the loop)
    Layer 2b — a11y           A11yDriver  (AX markdown + V9 /v1/chat)
    Layer 3  — vision         VisionDriver (screenshot + V9 /v1/vision)

Above all four sits the precondition layer (the desktop twin of Browser's
gateway block): the daemon must be running, the app launched + activated, and
the AX tree non-empty. When the precondition fails for a reason no later layer
can fix (missing TCC grant), the skill returns error_code='precondition_blocked'.
When the AX tree is empty because the surface simply has no AX nodes (canvas /
game), the cascade escalates to vision instead of failing.

Metadata contract (all under node.metadata):
    goal                 (required) natural-language goal for this window
    app                  friendly app name for AppleScript activation, e.g. "Calculator"
    bundle_id            launch target, e.g. "com.apple.calculator"
    force_path           'extract'|'deterministic'|'a11y'|'vision' — skip the cascade
    sequence             Layer 2a: list of {type, ...} actions run with no LLM
    page_actions         Electron path: list of {action, selector, value?} page-tool ops
    electron_debugging_port  launch flag that unlocks the CDP page path
    query                AX scan pre-filter (GUIDE §6.4) to shrink the legend
    verify_query         text to look for in the post-action scan (sets `verified`)
    record               when true, wrap the run in start/stop_recording
    provider / model     V9 routing pins for the judgment LLM

Integration is one dispatch branch in skills.py — flow.py never changes.
"""
from __future__ import annotations

import asyncio
import json as _json
import time
import urllib.request as _urlreq
from pathlib import Path
from typing import Optional

from browser.client import V9Client
from schemas import AgentResult, ComputerOutput, NodeSpec

from . import cdp
from .cua import CuaDriver, CuaError, PreconditionError
from .driver import A11yDriver, DriverConfig, DriverResult, VisionDriver


def _cdp_live(port: int) -> bool:
    """True if a Chrome/Electron CDP endpoint already answers on this port.
    Lets us attach to an app that's running WITH the debug flag instead of
    refusing it as a port-less live instance."""
    try:
        with _urlreq.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:                                           # noqa: BLE001
        return False


def _cdp_wait_page(port: int, timeout: float = 20.0) -> bool:
    """Block until ≥1 CDP target of type 'page' is registered, so a query_dom
    doesn't race the renderer's first paint (Slack takes several seconds to
    load its workspace). Returns True if a page appeared within `timeout`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with _urlreq.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as r:
                targets = _json.load(r)
            if any(t.get("type") == "page" for t in targets):
                return True
        except Exception:                                       # noqa: BLE001
            pass
        time.sleep(0.5)
    return False


# Goals that name a read, not an interaction, can be answered by Layer 1 alone.
_READ_VERBS = ("read", "what is", "what's", "extract", "contents of",
               "value of", "show me", "tell me")
_INTERACTIVE_VERBS = ("click", "type", "press", "compute", "draw", "open",
                      "create", "fill", "select", "send", "run", "toggle",
                      "filter", "sort", "navigate", "set")


class ComputerSkill:
    NAME = "computer"

    def __init__(self, *, gateway_url: str = "http://localhost:8109",
                 agent_tag: str = "computer",
                 a11y_provider_pin: str | None = "gemini",
                 vision_provider_pin: str | None = None,
                 artifacts_root: str | None = None,
                 max_steps_a11y: int = 12,
                 max_steps_vision: int = 8,
                 wall_clock_s: float = 180.0,
                 session: str | None = None,
                 cua: CuaDriver | None = None):
        self.gateway_url = gateway_url
        self.agent_tag = agent_tag
        self.a11y_provider_pin = a11y_provider_pin
        self.vision_provider_pin = vision_provider_pin
        self.artifacts_root = Path(artifacts_root) if artifacts_root else None
        self.max_steps_a11y = max_steps_a11y
        self.max_steps_vision = max_steps_vision
        self.wall_clock_s = wall_clock_s
        self.session = session
        # Injectable for tests (a fake CuaDriver) — defaults to the real one.
        self._cua = cua

    # ── public entry point ─────────────────────────────────────────────────
    async def run(self, node: NodeSpec) -> AgentResult:
        m = node.metadata or {}
        goal = m.get("goal") or "interact with the active window"
        app = m.get("app") or ""
        bundle_id = m.get("bundle_id")
        force_path = m.get("force_path")
        t0 = time.time()

        client = V9Client(base_url=self.gateway_url, agent=self.agent_tag,
                          session=self.session)
        cua = self._cua or CuaDriver(session=self.session)
        artifacts_dir = (str(self.artifacts_root / f"computer_{int(t0)}")
                         if self.artifacts_root else None)
        traj_dir = (str(Path(artifacts_dir) / "trajectory")
                    if artifacts_dir else None)

        # ── precondition: daemon + launch + activate + window ───────────────
        try:
            await asyncio.to_thread(cua.ensure_daemon)
            await asyncio.to_thread(cua.set_agent_cursor, True)
            if m.get("record") and traj_dir:
                await asyncio.to_thread(cua.start_recording, traj_dir)
            pid, window_id = await self._launch_and_focus(cua, m, app, bundle_id)
        except CuaError as e:
            await self._stop_recording(cua, m)
            return self._pack_error(goal, app, bundle_id, "precondition_blocked",
                                    f"precondition_blocked: {e}",
                                    elapsed=time.time() - t0)

        try:
            # ── Electron page path (CDP) — a Layer-2 special case ───────────
            page_actions = m.get("page_actions") or []
            if page_actions:
                res = await self._run_page_actions(cua, pid, window_id, goal,
                                                   app, bundle_id, page_actions, m)
                if res is not None:
                    return self._finish(res, time.time() - t0)

            # ── Layer 2a: deterministic hotkey/keystroke sequence ───────────
            sequence = m.get("sequence") or []
            if sequence and force_path in (None, "deterministic"):
                res = await self._run_sequence(cua, pid, window_id, goal, app,
                                               bundle_id, sequence, m)
                return self._finish(res, time.time() - t0)

            # ── Layer 1: extract (read straight off the AX tree) ────────────
            if force_path == "extract" or (force_path is None
                                           and self._is_read_goal(goal)):
                res = await self._run_extract(cua, pid, window_id, goal, app,
                                              bundle_id, m)
                if res is not None:
                    return self._finish(res, time.time() - t0)

            # ── Layer 2b: a11y ──────────────────────────────────────────────
            a11y_result: DriverResult | None = None
            if force_path != "vision":
                a11y_result = await self._drive(
                    A11yDriver, cua, client, pid, window_id, goal, app,
                    artifacts_dir, self.a11y_provider_pin, self.max_steps_a11y, m)
                if a11y_result.success:
                    res = self._pack_driver("a11y", goal, app, bundle_id,
                                            a11y_result, traj_dir)
                    return self._finish(res, time.time() - t0)
                # An empty AX tree that no permission fix helps → escalate to
                # vision (canvas/game). A genuine TCC failure surfaces below if
                # vision also can't proceed.

            # ── Layer 3: vision ─────────────────────────────────────────────
            vis_result = await self._drive(
                VisionDriver, cua, client, pid, window_id, goal, app,
                artifacts_dir, self.vision_provider_pin, self.max_steps_vision, m)
            if vis_result.success:
                res = self._pack_driver("vision", goal, app, bundle_id,
                                        vis_result, traj_dir)
                return self._finish(res, time.time() - t0)

            # ── nothing worked ──────────────────────────────────────────────
            if a11y_result is not None and a11y_result.precondition_blocked \
                    and vis_result.precondition_blocked:
                res = self._pack_error(goal, app, bundle_id, "precondition_blocked",
                                       a11y_result.note, traj_dir=traj_dir)
            else:
                last = vis_result.note or (a11y_result.note if a11y_result else "")
                res = self._pack_error(goal, app, bundle_id, "interaction_failed",
                                       f"all layers exhausted; last: {last}",
                                       traj_dir=traj_dir)
            return self._finish(res, time.time() - t0)
        finally:
            await self._stop_recording(cua, m)

    # ── precondition helpers ────────────────────────────────────────────────
    async def _launch_and_focus(self, cua: CuaDriver, m: dict, app: str,
                                bundle_id: Optional[str]) -> tuple[int, int]:
        """Launch the target, activate via AppleScript (GUIDE §6.1), and
        resolve the window id. Three launch shapes:
          - metadata.pid given         → caller already launched it
          - metadata.chrome_app_url    → Chrome app-mode (canvas vision target)
          - bundle_id / app            → launch_app (+ electron_debugging_port)"""
        pid = m.get("pid")
        window_id = m.get("window_id")
        chrome_url = m.get("chrome_app_url")
        port = m.get("electron_debugging_port")
        if pid is not None:
            pass
        elif chrome_url:
            # Chrome app-mode: launch chromeless, attach by window title, and
            # bring it forward so the vision screenshot captures a rendered window.
            cpid, cwid = await asyncio.to_thread(self._launch_chrome_app, cua, chrome_url)
            await asyncio.to_thread(cua.activate, "Google Chrome")
            return cpid, cwid
        else:
            if not (bundle_id or app):
                raise CuaError("need metadata.bundle_id or metadata.app to launch")
            # Electron debug port only takes effect on a FRESH launch. If the
            # app is already running we cannot enable CDP retroactively. Two
            # safe escapes: creates_new_application_instance (spawn a second,
            # isolated instance — preferred, never touches the user's window)
            # or relaunch_if_running (quit + relaunch). Without either we refuse
            # rather than silently driving a port-less instance.
            new_instance = m.get("creates_new_application_instance")
            running = None
            if port and not new_instance:
                running = await asyncio.to_thread(
                    cua.is_app_running, bundle_id=bundle_id, name=app or None)
            # A live instance that ALREADY exposes the CDP port (e.g. a prior
            # run launched it with the flag) is usable as-is — attach to it
            # rather than needlessly quitting the user's window. relaunch_if_
            # running still forces a fresh start when the caller wants one.
            reuse_running = bool(
                running and port and not m.get("relaunch_if_running")
                and await asyncio.to_thread(_cdp_live, port))
            if running and not reuse_running and not m.get("relaunch_if_running"):
                raise CuaError(
                    f"{app or bundle_id} is already running (pid={running}) "
                    f"without the electron_debugging_port. CDP cannot be "
                    f"enabled on a live instance — quit it fully (Cmd-Q) and "
                    f"re-run, or set metadata.relaunch_if_running=true to "
                    f"quit+relaunch it. (creates_new_application_instance does "
                    f"not help VS Code: its single-instance lock returns pid=-1.)")
            if running and m.get("relaunch_if_running"):
                await asyncio.to_thread(cua.kill_app, running)
                await asyncio.sleep(1.0)
            if reuse_running:
                pid = running
            else:
                resp = await asyncio.to_thread(
                    cua.launch_app, bundle_id=bundle_id, name=app or None,
                    electron_debugging_port=port,
                    creates_new_application_instance=bool(
                        m.get("creates_new_application_instance")))
                pid = resp.get("pid")
                # Some apps re-exec themselves on launch (VS Code, ToDesktop
                # apps), so LaunchServices hands back pid=-1. Resolve the real
                # pid from list_apps by bundle id once the app registers.
                if (pid is None or int(pid) <= 0) and bundle_id:
                    for _ in range(12):
                        await asyncio.sleep(0.5)
                        real = await asyncio.to_thread(
                            cua.is_app_running, bundle_id=bundle_id)
                        if real:
                            pid = real
                            break
                if pid is None or int(pid) <= 0:
                    raise CuaError(f"launch_app returned no usable pid: {resp}")
            # Don't let a page action race the renderer's first paint: wait for
            # a CDP 'page' target before returning (no-op if CDP isn't up yet).
            if port:
                await asyncio.to_thread(_cdp_wait_page, port, 20.0)
        if app:
            await asyncio.to_thread(cua.activate, app)
        if window_id is None:
            window_id = await asyncio.to_thread(cua.first_window_id, int(pid))
        return int(pid), int(window_id)

    @staticmethod
    def _launch_chrome_app(cua: CuaDriver, url: str) -> tuple[int, int]:
        """Open `url` in a chromeless Chrome app window (no tab/URL bar) so the
        canvas is the whole window and the AX tree is near-empty — the natural
        precondition for the vision layer. Returns (pid, window_id), found by
        the window's title (the <title> of the page) via the app_name/title
        fields list_windows actually exposes."""
        import subprocess
        subprocess.run(["open", "-na", "Google Chrome", "--args",
                        f"--app={url}", "--new-window"],
                       check=False, capture_output=True, text=True)
        # The app-mode window's title is the page <title> ("Sketch").
        return cua.find_window(app_contains="chrome", title_contains="sketch")

    # ── Layer 1: extract ──────────────────────────────────────────────────────
    async def _run_extract(self, cua, pid, window_id, goal, app, bundle_id, m):
        try:
            state, _ = await asyncio.to_thread(
                cua.scan, pid, window_id, m.get("query"), True)
        except PreconditionError:
            return None      # let the cascade fall through to a11y/vision
        content = state.get("tree_markdown", "").strip()
        if not content:
            return None
        return self._pack(goal, app, bundle_id, "extract", turns=0,
                          content=content, verified=True)

    # ── Layer 2a: deterministic sequence (no LLM) ─────────────────────────────
    async def _run_sequence(self, cua, pid, window_id, goal, app, bundle_id,
                            sequence, m):
        """Run a fixed action sequence. Each step is one of:
          {type:'hotkey', keys:[...]}        {type:'key', value:'7'}
          {type:'type', text:'...'}          {type:'click', element_index:N}
          {type:'click_xy', x:.., y:..}      {type:'wait', seconds:..}
        No scan/LLM between steps — this is the boring, cheap, reliable layer."""
        actions: list[dict] = []
        for i, step in enumerate(sequence, 1):
            t = step.get("type")
            try:
                if t == "hotkey":
                    await asyncio.to_thread(cua.hotkey, list(step.get("keys", [])), pid)
                elif t == "key":
                    await asyncio.to_thread(cua.press_key, pid, window_id,
                                            str(step.get("value", "Return")))
                elif t == "type":
                    await asyncio.to_thread(cua.type_text, pid, window_id,
                                            str(step.get("text", "")))
                elif t == "click":
                    # element_index needs a fresh scan to populate the cache.
                    await asyncio.to_thread(cua.scan, pid, window_id, m.get("query"), True)
                    await asyncio.to_thread(cua.click, pid, window_id,
                                            element_index=int(step["element_index"]))
                elif t == "click_xy":
                    await asyncio.to_thread(cua.click, pid, window_id,
                                            x=int(step["x"]), y=int(step["y"]))
                elif t == "wait":
                    await asyncio.sleep(float(step.get("seconds", 0.3)))
                else:
                    actions.append({"step": i, "action": step, "outcome": f"error: unknown {t!r}"})
                    continue
                actions.append({"step": i, "action": step, "outcome": "ok"})
            except Exception as e:                              # noqa: BLE001
                actions.append({"step": i, "action": step,
                                "outcome": f"error: {type(e).__name__}: {e}"})
            await asyncio.sleep(step.get("pause", 0.15))

        content, verified = await self._verify(cua, pid, window_id, m)
        ok = verified or all(a["outcome"] == "ok" for a in actions)
        return self._pack(goal, app, bundle_id, "deterministic",
                          turns=len(sequence), content=content,
                          actions=actions, verified=verified, success=ok)

    # ── Electron page path (CDP) ──────────────────────────────────────────────
    async def _run_page_actions(self, cua, pid, window_id, goal, app, bundle_id,
                                page_actions, m):
        """Drive an Electron app's DOM over CDP (GUIDE §7.2). Fixed action
        sequence → surfaced as the 'deterministic' layer.

        Connects directly to the app's --remote-debugging-port via a minimal
        CDP client (computer/cdp.py) for THIS step only — every other layer
        (launch, focus, a11y, vision, recording) still goes through cua-driver.
        cua-driver 0.6.8's own `page` tool hangs against stock Electron apps
        (every action times out at 30s on Slack 4.50; the hang reproduces on a
        freshly-restarted daemon with zero leaked sockets and on a single-frame
        page, so it is the tool's page handler, not a frame/socket issue) even
        though the same CDP target answers Runtime.evaluate in ~10ms. Each step
        maps to one evaluate:
          {action:'query_dom',          css_selector:'…'}
          {action:'click_element',      selector:'…'}
          {action:'execute_javascript', javascript:'…'}
          {action:'get_text'}"""
        port = m.get("electron_debugging_port")
        if not port:
            return self._pack_error(goal, app, bundle_id, "precondition_blocked",
                                    "page_actions require electron_debugging_port")
        try:
            client = await asyncio.to_thread(
                cdp.CDPClient(port, title_hint=m.get("page_title_hint")).connect)
        except Exception as e:                                  # noqa: BLE001
            return self._pack_error(goal, app, bundle_id, "interaction_failed",
                                    f"CDP connect failed on port {port}: {e}")
        actions: list[dict] = []
        content = None
        try:
            for i, step in enumerate(page_actions, 1):
                try:
                    resp = await asyncio.to_thread(cdp.run_page_action, client, step)
                    actions.append({"step": i, "action": step,
                                    "outcome": "ok", "result": resp})
                except Exception as e:                          # noqa: BLE001
                    actions.append({"step": i, "action": step,
                                    "outcome": f"error: {type(e).__name__}: {e}"})
                    return self._pack_error(goal, app, bundle_id, "interaction_failed",
                                            f"page action {i} failed: {e}")
                await asyncio.sleep(step.get("pause", 0.2))
            # Optional read-back via JS as verification content.
            vjs = m.get("verify_js")
            if vjs:
                try:
                    resp = await asyncio.to_thread(client.evaluate, vjs)
                    content = resp if isinstance(resp, str) else _json.dumps(resp)
                except Exception:                               # noqa: BLE001
                    pass
        finally:
            await asyncio.to_thread(client.close)
        return self._pack(goal, app, bundle_id, "deterministic",
                          turns=len(page_actions), content=content,
                          actions=actions, verified=bool(content), success=True)

    # ── Layer 2b / 3 driver runs ──────────────────────────────────────────────
    async def _drive(self, DriverCls, cua, client, pid, window_id, goal, app,
                     artifacts_dir, provider_pin, max_steps, m) -> DriverResult:
        sub = None
        if artifacts_dir:
            sub = str(Path(artifacts_dir) / DriverCls.LAYER_NAME)
        cfg = DriverConfig(
            goal=goal, pid=pid, window_id=window_id, app_name=app,
            max_steps=max_steps, artifacts_dir=sub, query=m.get("query"),
            provider=provider_pin, model=m.get("model"))
        drv = DriverCls(cua, client, cfg)
        return await drv.run()

    async def _verify(self, cua, pid, window_id, m) -> tuple[str | None, bool]:
        """Re-scan and check the post-condition. Two modes:
          verify_display — match only against AXStaticText *values* (the right
                           check for a Calculator/readout; avoids matching an
                           element index like [56] elsewhere in the tree).
          verify_query   — looser: case-insensitive substring over the markdown.
        Bidi control marks (U+200E/200F that Calculator wraps its display in)
        are stripped before comparison."""
        try:
            state, _ = await asyncio.to_thread(
                cua.scan, pid, window_id, None, True)
        except PreconditionError:
            return None, False
        md = state.get("tree_markdown", "")

        def clean(s: str) -> str:
            return s.replace("‎", "").replace("‏", "").strip()

        vd = m.get("verify_display")
        if vd:
            import re as _re
            values = [clean(v) for v in _re.findall(r'AXStaticText\s*=\s*"([^"]*)"', md)]
            verified = any(clean(vd) == v or clean(vd) in v for v in values)
            return (md.strip() or None), verified
        vq = m.get("verify_query")
        verified = bool(vq) and vq.lower() in md.lower()
        return (md.strip() or None), verified

    # ── goal classification ───────────────────────────────────────────────────
    def _is_read_goal(self, goal: str) -> bool:
        g = goal.lower()
        if any(v in g for v in _INTERACTIVE_VERBS):
            return False
        return any(v in g for v in _READ_VERBS)

    # ── recording teardown ────────────────────────────────────────────────────
    async def _stop_recording(self, cua, m) -> None:
        if m.get("record"):
            try:
                await asyncio.to_thread(cua.stop_recording)
            except Exception:                                   # noqa: BLE001
                pass

    def _finish(self, result: AgentResult, elapsed: float) -> AgentResult:
        if not result.elapsed_s:
            result.elapsed_s = elapsed
        return result

    # ── packers ────────────────────────────────────────────────────────────
    def _pack(self, goal, app, bundle_id, path, *, turns, content=None,
              actions=None, verified=False, success=True,
              traj_dir=None, elapsed=0.0) -> AgentResult:
        out = ComputerOutput(
            goal=goal, app=app, bundle_id=bundle_id, path=path, turns=turns,
            content=content, actions=actions or [], verified=verified,
            trajectory_dir=traj_dir)
        return AgentResult(success=success, agent_name=self.NAME,
                          output=out.model_dump(), elapsed_s=elapsed)

    def _pack_driver(self, path, goal, app, bundle_id, drv: DriverResult,
                     traj_dir) -> AgentResult:
        actions = [{"turn": s.turn, "thinking": s.thinking,
                    "actions": s.actions, "outcome": s.outcome,
                    "tokens_in": s.tokens_in, "tokens_out": s.tokens_out}
                   for s in drv.steps]
        out = ComputerOutput(
            goal=goal, app=app, bundle_id=bundle_id, path=path,
            turns=len(drv.steps), content=drv.final_markdown or None,
            actions=actions, verified=drv.success, trajectory_dir=traj_dir)
        return AgentResult(success=drv.success, agent_name=self.NAME,
                          output=out.model_dump())

    def _pack_error(self, goal, app, bundle_id, code, msg, *,
                    traj_dir=None, elapsed=0.0) -> AgentResult:
        out = ComputerOutput(
            goal=goal, app=app, bundle_id=bundle_id, path="extract", turns=0,
            content=None, trajectory_dir=traj_dir)
        return AgentResult(success=False, agent_name=self.NAME,
                          output=out.model_dump(), error=msg, error_code=code,
                          elapsed_s=elapsed)
