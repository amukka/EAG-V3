"""Minimal, dependency-free Chrome DevTools Protocol client — used for the
Electron page step ONLY.

Why this exists: cua-driver 0.6.8's `page` tool hangs indefinitely when driving
a stock Electron app (verified against Slack 4.50 — every action times out at
30s, and the hang reproduces on a freshly-restarted daemon with zero leaked
sockets, so it is not a socket/state-leak or a multi-frame deadlock: Slack's
page is a single flat frame). A direct CDP `Runtime.evaluate` against the same
page target returns in ~10ms, so the Electron page path drives the DOM here
instead of shelling out to the page tool. Every other layer (launch, focus,
a11y, vision, recording) still goes through cua-driver.

Scope is deliberately tiny: discover the page target over HTTP, open one raw
websocket (stdlib socket — no `websockets`/`websocket-client` dependency), and
run `Runtime.evaluate`. Every page action the skill needs (query_dom, get_text,
execute_javascript, click_element) is expressed as a JS expression, so a single
evaluate primitive covers them all.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request


class CDPError(Exception):
    pass


def list_targets(port: int, timeout: float = 3.0) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=timeout) as r:
        return json.load(r)


def version(port: int, timeout: float = 3.0) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
        return json.load(r)


class CDPClient:
    """One websocket to one page target. Not thread-safe; use from a worker
    thread via asyncio.to_thread."""

    def __init__(self, port: int, *, title_hint: str | None = None,
                 connect_timeout: float = 5.0):
        self.port = port
        self.title_hint = title_hint
        self.connect_timeout = connect_timeout
        self._sock: socket.socket | None = None
        self._id = 0
        self.target: dict | None = None

    # ── target selection ────────────────────────────────────────────────────
    def _pick_target(self) -> dict:
        pages = [t for t in list_targets(self.port) if t.get("type") == "page"]
        if not pages:
            raise CDPError(f"no CDP 'page' target on port {self.port}")
        if self.title_hint:
            for t in pages:
                if self.title_hint.lower() in (t.get("title") or "").lower():
                    return t
        return pages[0]

    # ── websocket plumbing ──────────────────────────────────────────────────
    def connect(self) -> "CDPClient":
        self.target = self._pick_target()
        ws = self.target["webSocketDebuggerUrl"]            # ws://127.0.0.1:<port><path>
        path = ws.split(str(self.port), 1)[1]
        sock = socket.create_connection(("127.0.0.1", self.port),
                                        timeout=self.connect_timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
             f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
             f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = sock.recv(4096)
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            sock.close()
            raise CDPError(f"websocket upgrade failed: {resp[:120]!r}")
        self._sock = sock
        return self

    def _send(self, obj: dict) -> None:
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        hdr = bytearray([0x81])                              # FIN + text opcode
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        hdr += mask
        self._sock.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv_n(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise CDPError("CDP socket closed mid-frame")
            buf += chunk
        return buf

    def _recv_frame(self) -> bytes:
        b0b1 = self._recv_n(2)
        length = b0b1[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_n(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_n(8))[0]
        return self._recv_n(length)                          # server frames are unmasked

    # ── the one primitive everything maps to ────────────────────────────────
    def evaluate(self, expression: str, *, timeout: float = 15.0, await_promise: bool = False):
        if self._sock is None:
            raise CDPError("not connected")
        self._id += 1
        mid = self._id
        self._send({"id": mid, "method": "Runtime.evaluate", "params": {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise}})
        self._sock.settimeout(timeout)
        while True:
            msg = json.loads(self._recv_frame())
            if msg.get("id") != mid:
                continue                                     # skip events / other ids
            if "error" in msg:
                raise CDPError(f"CDP error: {msg['error']}")
            res = msg.get("result", {})
            if res.get("exceptionDetails"):
                raise CDPError(f"JS exception: {res['exceptionDetails'].get('text')}")
            return res.get("result", {}).get("value")

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()


# JS templates for the page actions the skill drives. Each returns a JSON-able
# value so the trajectory captures a real result instead of an opaque handle.
def _js_query_dom(sel: str, limit: int = 50) -> str:
    s = json.dumps(sel)
    return (f"(()=>{{const els=[...document.querySelectorAll({s})];"
            f"return {{count:els.length,sample:els.slice(0,{limit}).map("
            f"e=>({{tag:e.tagName,id:e.id||null,"
            f"text:(e.textContent||'').trim().slice(0,60)}}))}};}})()")


def _js_get_text(limit: int = 4000) -> str:
    return f"(document.body?document.body.innerText:'').slice(0,{limit})"


def _js_click(sel: str) -> str:
    s = json.dumps(sel)
    return (f"(()=>{{const el=document.querySelector({s});"
            f"if(!el)return {{clicked:false,reason:'not found'}};"
            f"el.click();return {{clicked:true}};}})()")


def run_page_action(client: "CDPClient", step: dict, timeout: float = 15.0):
    """Execute one page-action dict (same shape cua.page took) over CDP and
    return a JSON-able result."""
    action = step.get("action", "query_dom")
    if action == "execute_javascript":
        return client.evaluate(step["javascript"], timeout=timeout)
    if action == "get_text":
        return client.evaluate(_js_get_text(), timeout=timeout)
    if action == "query_dom":
        return client.evaluate(_js_query_dom(step.get("css_selector", "*")), timeout=timeout)
    if action == "click_element":
        return client.evaluate(_js_click(step.get("selector", "")), timeout=timeout)
    raise CDPError(f"unsupported page action: {action!r}")
