"""Session 10: framework-free client for the cua-driver daemon.

cua-driver is a Rust binary that exposes the OS accessibility + input APIs
as a JSON tool surface over a Unix socket. We talk to it exactly the way
CUA_DRIVER_GUIDE.md §3.3 recommends for a custom Python agent: shell out to
`cua-driver call <tool> <json>` through a running daemon (~30 ms/call). No
SDK, no MCP client, no raw socket — same "callers stay clean, the binary owns
the OS quirks" discipline the Browser skill keeps with the V9 gateway.

This module owns three things the layers above it should never re-implement:

  1. Binary + daemon lifecycle (`ensure_daemon`, `status`).
  2. The macOS precondition guards that turn cua-driver's *silent* failures
     into loud ones — an empty AX tree (`element_count == 0`) is raised as
     PreconditionError, never returned as if it were a real scan.
  3. AX-tree markdown parsing into a turn-scoped element list, de-duped by
     first occurrence (CUA_DRIVER_GUIDE §6.3: the walker emits some windows
     twice; the first occurrence is the canonical one).

Everything above — which element to click, when to escalate to vision — is
the driver/skill's job, not this module's.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


# ── exceptions ────────────────────────────────────────────────────────────────
class CuaError(RuntimeError):
    """A cua-driver call exited non-zero or returned malformed JSON."""


class PreconditionError(CuaError):
    """The precondition layer failed: empty AX tree, missing TCC grant,
    un-activated window, or a daemon that never started. The skill maps this
    to error_code='precondition_blocked' — the desktop twin of the Browser
    skill's gateway_blocked. No later layer can recover it."""


# ── parsed AX element ───────────────────────────────────────────────────────
@dataclass
class AXElement:
    element_index: int
    role: str            # AXButton, AXTextField, AXStaticText, …
    name: str            # accessible name / label / value
    raw: str             # the source markdown line, for debugging

    def __str__(self) -> str:
        return f"[{self.element_index}] {self.role} {self.name!r}"


# The element index is the FIRST bracketed integer on a line — cua-driver
# 0.6.8 renders it as a bare `[193]` (the CUA_DRIVER_GUIDE's `[element_index N]`
# is an older/idealised form; we accept both). The optional `element_index`
# keyword keeps us forward-compatible. Role is the first AX* token after the
# index; name is the first double-quoted run; actions live in `[actions=[...]]`.
_IDX_RE = re.compile(r"\[(?:element_index\s+)?(\d+)\]")
_ROLE_RE = re.compile(r"\b(AX[A-Za-z]+)\b")
_NAME_RE = re.compile(r'"([^"]*)"')
# cua-driver 0.6.8 renders control labels two ways: menu items as quoted
# strings (`AXMenuItem "About This Mac"`) and buttons/controls as a parenthesised
# title right after the role (`AXButton (7) [id=Seven ...]`). Reading only the
# quoted form leaves every button nameless, which blinds the a11y layer.
_PAREN_NAME_RE = re.compile(r"^\s*AX[A-Za-z]+\s+\(([^)]*)\)")
_ID_RE = re.compile(r"\bid=([A-Za-z0-9_.:+-]+)")
_ACTIONS_RE = re.compile(r"actions=\[([^\]]*)\]")
# Roles worth surfacing to the LLM even when unnamed (e.g. a blank text field).
_KEEP_UNNAMED = {"AXTextField", "AXTextArea", "AXComboBox", "AXSlider",
                 "AXCheckBox", "AXTextInput"}


def parse_elements(tree_markdown: str,
                   actionable_only: bool = True) -> list[AXElement]:
    """Parse `get_window_state.tree_markdown` into a legend of elements.

    - Index format is `[N]` (or legacy `[element_index N]`); we take the first
      bracketed integer on the line.
    - De-dupes by (role, name) keeping the FIRST index — the walker can emit a
      window subtree twice (GUIDE §6.3) and the first copy is the canonical one.
    - With actionable_only (the default) we drop nodes that have no `press`/
      `pick`/`confirm` action AND no name — pure containers and static text
      that the LLM can't act on. Named or input-role nodes are always kept so
      the model still has labels to reason over."""
    out: list[AXElement] = []
    seen: set[tuple[str, str]] = set()
    for line in (tree_markdown or "").splitlines():
        m = _IDX_RE.search(line)
        if not m:
            continue
        idx = int(m.group(1))
        tail = line[m.end():]
        role_m = _ROLE_RE.search(tail) or _ROLE_RE.search(line)
        role = role_m.group(1) if role_m else "AXUnknown"
        # Prefer a quoted name (menu items), then a parenthesised title
        # (buttons/controls), then the stable AX id as a last resort.
        q = _NAME_RE.search(tail)
        p = _PAREN_NAME_RE.search(tail)
        i = _ID_RE.search(tail)
        name = (q.group(1) if q else
                p.group(1) if p else
                i.group(1) if i else "")
        if actionable_only:
            acts_m = _ACTIONS_RE.search(line)
            acts = acts_m.group(1) if acts_m else ""
            clickable = any(a in acts for a in ("press", "pick", "confirm"))
            if not name and not clickable and role not in _KEEP_UNNAMED:
                continue
        key = (role, name)
        if name and key in seen:        # only dedupe *named* elements
            continue
        if name:
            seen.add(key)
        out.append(AXElement(idx, role, name, line.strip()))
    return out


# ── the client ────────────────────────────────────────────────────────────────
class CuaDriver:
    """Thin synchronous wrapper over `cua-driver call`. The async driver loop
    above wraps each method in asyncio.to_thread so the V9 gateway call and the
    OS call don't block each other."""

    def __init__(self, bin_path: Optional[str] = None,
                 session: Optional[str] = None,
                 call_timeout: float = 30.0):
        self.bin = bin_path or self._resolve_bin()
        self.session = session
        self.call_timeout = call_timeout

    @staticmethod
    def _resolve_bin() -> str:
        # Install drops a symlink in ~/.local/bin and may not be on PATH in a
        # non-login shell, so check the canonical location first.
        local = Path.home() / ".local" / "bin" / "cua-driver"
        if local.exists():
            return str(local)
        found = shutil.which("cua-driver")
        if found:
            return found
        raise CuaError(
            "cua-driver binary not found. Install it:\n"
            '  /bin/bash -c "$(curl -fsSL '
            'https://raw.githubusercontent.com/trycua/cua/main/'
            'libs/cua-driver/scripts/install.sh)"'
        )

    # ── raw call ────────────────────────────────────────────────────────────
    def call(self, tool: str, args: dict[str, Any] | None = None,
             timeout: Optional[float] = None) -> dict[str, Any]:
        payload = dict(args or {})
        proc = subprocess.run(
            [self.bin, "call", tool, json.dumps(payload)],
            capture_output=True, text=True,
            timeout=timeout or self.call_timeout,
        )
        if proc.returncode != 0:
            raise CuaError(f"{tool} failed (exit {proc.returncode}): "
                           f"{proc.stderr.strip() or proc.stdout.strip()}")
        out = proc.stdout.strip()
        if not out:
            return {}
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"raw": out}

    # ── daemon lifecycle ──────────────────────────────────────────────────────
    def status(self) -> bool:
        """True when a daemon is serving the socket."""
        try:
            p = subprocess.run([self.bin, "status"], capture_output=True,
                               text=True, timeout=5)
        except Exception:                                       # noqa: BLE001
            return False
        blob = (p.stdout + p.stderr).lower()
        return p.returncode == 0 and ("running" in blob or "pid" in blob)

    def ensure_daemon(self) -> None:
        """Start `cua-driver serve` if not already up. The element-index cache
        lives in the daemon's memory; without it every element_index click
        fails with 'not found in cache' (GUIDE §3.1/§6.2)."""
        if self.status():
            return
        subprocess.Popen([self.bin, "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Daemon is ready once the socket appears; poll briefly.
        for _ in range(20):
            time.sleep(0.25)
            if self.status():
                return
        raise CuaError("cua-driver daemon did not come up after `serve`.")

    # ── discovery / launch ────────────────────────────────────────────────────
    def launch_app(self, *, bundle_id: Optional[str] = None,
                   name: Optional[str] = None,
                   electron_debugging_port: Optional[int] = None,
                   webkit_inspector_port: Optional[int] = None,
                   creates_new_application_instance: bool = False) -> dict:
        args: dict[str, Any] = {}
        if bundle_id:                args["bundle_id"] = bundle_id
        if name:                     args["name"] = name
        if electron_debugging_port:  args["electron_debugging_port"] = electron_debugging_port
        if webkit_inspector_port:    args["webkit_inspector_port"] = webkit_inspector_port
        # Forces a fresh instance (-n) even if the app is already running — the
        # only way to attach a debug port to e.g. VS Code without clobbering
        # the user's existing editor window.
        if creates_new_application_instance:
            args["creates_new_application_instance"] = True
        return self.call("launch_app", args)

    def list_windows(self) -> list[dict]:
        return self.call("list_windows").get("windows", [])

    def first_window_id(self, pid: int, retries: int = 8,
                        delay: float = 0.4) -> int:
        """Resolve `pid`'s real top-level window id. A process owns several
        WindowServer entries — the system menu bar shows up as a full-width,
        ~30px-tall window with is_on_screen=false, and the real app window is a
        normally-sized on-screen one. Returning the first match (the menu bar)
        makes get_window_state walk only the menu, which is exactly the
        'scan returned 204 menu items, no buttons' symptom. So we score: prefer
        on-screen, then largest area, and skip menu-bar-shaped pseudo-windows."""
        def is_menubar(w: dict) -> bool:
            b = w.get("bounds") or {}
            return (b.get("y", 1) == 0 and (b.get("height") or 0) <= 40
                    and (b.get("width") or 0) >= 1280)

        for _ in range(retries):
            cands = [w for w in self.list_windows()
                     if w.get("pid") == pid and w.get("window_id") is not None
                     and not is_menubar(w)]
            if cands:
                def score(w):
                    b = w.get("bounds") or {}
                    area = (b.get("width") or 0) * (b.get("height") or 0)
                    return (1 if w.get("is_on_screen") else 0, area)
                return int(max(cands, key=score)["window_id"])
            time.sleep(delay)
        raise CuaError(f"no real app window registered for pid={pid} after "
                       f"{retries} tries (only menu-bar pseudo-windows seen)")

    def find_window(self, *, app_contains: str = "", title_contains: str = "",
                    retries: int = 20, delay: float = 0.4) -> tuple[int, int]:
        """Find a window by app_name / title substring (case-insensitive).
        Returns (pid, window_id). Used to attach to an app this process did not
        launch directly — e.g. a Chrome app-mode window."""
        ac, tc = app_contains.lower(), title_contains.lower()
        for _ in range(retries):
            for w in self.list_windows():
                app = (w.get("app_name") or "").lower()
                title = (w.get("title") or "").lower()
                if (not ac or ac in app) and (not tc or tc in title) \
                        and w.get("pid") and w.get("window_id") is not None:
                    return int(w["pid"]), int(w["window_id"])
            time.sleep(delay)
        raise CuaError(f"no window matching app~{app_contains!r} "
                       f"title~{title_contains!r} appeared")

    def is_app_running(self, *, bundle_id: Optional[str] = None,
                       name: Optional[str] = None) -> int | None:
        """Return the pid of a running app matched by bundle_id (preferred) or
        name substring, else None. Uses list_apps, which reports a reliable
        bundle_id + running flag — far better than matching window app_name
        (VS Code's bundle is com.microsoft.VSCode but its app_name is just
        'Code', so a name match misses). Lets the skill detect an Electron app
        that is already up and so cannot have a debug port attached
        retroactively."""
        apps = self.call("list_apps").get("apps", [])
        if bundle_id:
            for a in apps:
                if a.get("running") and a.get("bundle_id") == bundle_id \
                        and a.get("pid"):
                    return int(a["pid"])
        if name:
            n = name.lower()
            for a in apps:
                if a.get("running") and n in (a.get("name") or "").lower() \
                        and a.get("pid"):
                    return int(a["pid"])
        return None

    def activate(self, app_name: str, settle: float = 1.0) -> None:
        """macOS workaround (GUIDE §6.1): launch_app never steals focus, and a
        backgrounded window's button subtree is not realised in AX. AppleScript
        activation brings it forward; bring_to_front is Windows-only."""
        subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to activate'],
            check=False, capture_output=True, text=True,
        )
        time.sleep(settle)

    def kill_app(self, pid: int) -> dict:
        return self.call("kill_app", {"pid": pid})

    # ── perception (the precondition guard lives here) ────────────────────────
    def get_window_state(self, pid: int, window_id: int, *,
                         capture_mode: str = "ax",
                         query: Optional[str] = None,
                         screenshot_out_file: Optional[str] = None,
                         guard: bool = True) -> dict:
        """Scan one window. With guard=True (the default for AX scans) an empty
        tree is raised as PreconditionError rather than returned — cua-driver
        fails *silently* on a missing TCC grant or un-activated window
        (GUIDE §6.6), and an unchecked empty scan turns into a misleading
        'element_index not found in cache' three lines later.

        Callers that *expect* a possibly-empty tree (the vision escalation
        check) pass guard=False and inspect element_count themselves."""
        args: dict[str, Any] = {"pid": pid, "window_id": window_id,
                                "capture_mode": capture_mode}
        if query:                args["query"] = query
        if screenshot_out_file:  args["screenshot_out_file"] = screenshot_out_file
        state = self.call("get_window_state", args)
        if guard and int(state.get("element_count", 0)) == 0:
            raise PreconditionError(
                "cua-driver returned an empty AX tree (element_count=0). "
                "Check: (1) `cua-driver permissions grant` ran and both "
                "Accessibility + Screen Recording are granted to "
                "com.trycua.driver, (2) the app window was activated, "
                "(3) QT_ACCESSIBILITY=1 for Qt apps. This window may also be "
                "an Electron/canvas surface with no AX nodes — use the page "
                "tool or vision."
            )
        return state

    def scan(self, pid: int, window_id: int, query: Optional[str] = None,
             guard: bool = True) -> tuple[dict, list[AXElement]]:
        """get_window_state + parse, the way the driver loop wants it."""
        state = self.get_window_state(pid, window_id, capture_mode="ax",
                                      query=query, guard=guard)
        return state, parse_elements(state.get("tree_markdown", ""))

    def screenshot(self, pid: int, window_id: int, out_file: str) -> str:
        """Capture a PNG of the window for the vision layer. capture_mode
        'vision' returns the screenshot without walking AX."""
        self.get_window_state(pid, window_id, capture_mode="vision",
                              screenshot_out_file=out_file, guard=False)
        return out_file

    # ── action ────────────────────────────────────────────────────────────────
    def click(self, pid: int, window_id: int, *,
              element_index: Optional[int] = None,
              x: Optional[int] = None, y: Optional[int] = None,
              count: int = 1) -> dict:
        args: dict[str, Any] = {"pid": pid, "window_id": window_id}
        if element_index is not None:
            args["element_index"] = element_index
        elif x is not None and y is not None:
            args["x"], args["y"] = x, y
        else:
            raise CuaError("click needs element_index or (x, y)")
        if count != 1:
            args["count"] = count
        return self.call("click", args)

    def type_text(self, pid: int, window_id: int, text: str) -> dict:
        return self.call("type_text",
                         {"pid": pid, "window_id": window_id, "text": text})

    def press_key(self, pid: int, window_id: int, key: str) -> dict:
        return self.call("press_key",
                         {"pid": pid, "window_id": window_id, "key": key})

    def hotkey(self, keys: list[str], pid: Optional[int] = None) -> dict:
        args: dict[str, Any] = {"keys": keys}
        if pid is not None:
            args["pid"] = pid
        return self.call("hotkey", args)

    def page(self, pid: int, action: str, *,
             window_id: Optional[int] = None,
             selector: Optional[str] = None,
             css_selector: Optional[str] = None,
             javascript: Optional[str] = None,
             bundle_id: Optional[str] = None) -> dict:
        """Drive an Electron/VS Code/browser DOM via CDP. Requires the app to
        have been launched with electron_debugging_port (GUIDE §7.2).

        cua-driver 0.6.8 `page` actions:
          execute_javascript (javascript=)   run JS, return result
          get_text                            visible page text
          query_dom (css_selector=)          find elements
          click_element (selector=)          click + animate the agent cursor
        """
        args: dict[str, Any] = {"pid": pid, "action": action}
        if window_id is not None:    args["window_id"] = window_id
        if selector is not None:     args["selector"] = selector
        if css_selector is not None: args["css_selector"] = css_selector
        if javascript is not None:   args["javascript"] = javascript
        if bundle_id is not None:    args["bundle_id"] = bundle_id
        return self.call("page", args)

    # ── recording / replay (the assignment's evidence) ────────────────────────
    def start_recording(self, output_dir: str) -> dict:
        return self.call("start_recording", {"output_dir": output_dir})

    def stop_recording(self) -> dict:
        return self.call("stop_recording")

    def replay_trajectory(self, trajectory_dir: str) -> dict:
        return self.call("replay_trajectory", {"trajectory_dir": trajectory_dir})

    # ── agent-cursor overlay (visible-action demos) ───────────────────────────
    def set_agent_cursor(self, enabled: bool = True) -> dict:
        """The assignment's YouTube demo requires the agent-cursor overlay to
        be visible. Default-on for MCP sessions, off otherwise — so we turn it
        on explicitly."""
        return self.call("set_agent_cursor_enabled", {"enabled": enabled})
