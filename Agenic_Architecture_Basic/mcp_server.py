"""
MCP server for EAGV3 Session 6.

Nine tools, stdio transport:
    - web_search
    - fetch_url
    - get_time
    - currency_convert
    - read_file
    - list_dir
    - create_file
    - update_file
    - edit_file

Features:
- Tavily search with DuckDuckGo fallback
- Usage logging with monthly rollover
- Wikipedia optimized fetching
- Sandboxed file operations
- Currency conversion
- Timezone utilities

Run:
    python mcp_server.py
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# DuckDuckGo import compatibility
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

MAX_SEARCH_RESULTS = 5
MONTHLY_CAP = 950

BASE_DIR = Path(__file__).parent

SANDBOX = BASE_DIR / "sandbox"
SANDBOX.mkdir(exist_ok=True)

USAGE_PATH = BASE_DIR / "usage.json"

load_dotenv(BASE_DIR / ".env")

mcp = FastMCP("eagv3-s6-server")

_usage_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────
# Safe sandbox path handling
# ─────────────────────────────────────────────────────────────

def _safe(path: str) -> Path:
    """
    Prevent sandbox escape attacks.
    """

    p = (SANDBOX / path).resolve()
    base = SANDBOX.resolve()

    if p != base and base not in p.parents:
        raise ValueError(
            f"Path '{path}' escapes the sandbox"
        )

    return p


# ─────────────────────────────────────────────────────────────
# Usage tracking
# ─────────────────────────────────────────────────────────────

def _empty_usage(month: str) -> dict:

    return {
        "month": month,
        "tavily": {
            "count": 0,
            "errors": 0,
        },
        "duckduckgo": {
            "count": 0,
            "errors": 0,
        },
    }


def _load_usage() -> dict:

    month = datetime.now().strftime("%Y-%m")

    if not USAGE_PATH.exists():
        return _empty_usage(month)

    try:
        data = json.loads(
            USAGE_PATH.read_text(encoding="utf-8")
        )

    except (json.JSONDecodeError, OSError):
        return _empty_usage(month)

    if data.get("month") != month:
        return _empty_usage(month)

    for provider in ("tavily", "duckduckgo"):
        data.setdefault(
            provider,
            {"count": 0, "errors": 0},
        )

    return data


def _save_usage(data: dict) -> None:

    USAGE_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def _bump(provider: str, field: str = "count") -> None:

    with _usage_lock:

        data = _load_usage()

        data[provider][field] = (
            data[provider].get(field, 0) + 1
        )

        _save_usage(data)


def _under_cap(provider: str) -> bool:

    data = _load_usage()

    return data[provider]["count"] < MONTHLY_CAP


# ─────────────────────────────────────────────────────────────
# Tavily Search
# ─────────────────────────────────────────────────────────────

def _tavily_search(
    query: str,
    max_results: int,
) -> list[dict]:

    from tavily import TavilyClient

    client = TavilyClient(
        os.environ["TAVILY_API_KEY"]
    )

    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
    )

    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in response.get("results", [])
    ]


# ─────────────────────────────────────────────────────────────
# DuckDuckGo Search
# ─────────────────────────────────────────────────────────────

def _ddg_search(
    query: str,
    max_results: int,
) -> list[dict]:

    import time

    hits: list[dict] = []

    for attempt in range(3):

        try:
            hits = list(
                DDGS().text(
                    query,
                    max_results=max_results,
                )
            )

            if hits:
                break

        except Exception:
            hits = []

        if attempt < 2:
            time.sleep(2)

    return [
        {
            "title": h.get("title", ""),
            "url": h.get("href", ""),
            "snippet": h.get("body", ""),
        }
        for h in hits
    ]


# ─────────────────────────────────────────────────────────────
# URL Fetching
# ─────────────────────────────────────────────────────────────

async def _crawl4ai_fetch(url: str) -> dict:
    """
    Fetch page content.

    Special handling for Wikipedia.
    """

    import re

    wiki_match = re.search(
        r"wikipedia\.org/wiki/([^#?]+)",
        url,
    )

    # ─────────────────────────────────────────
    # Wikipedia handling
    # ─────────────────────────────────────────

    if wiki_match:

        title = wiki_match.group(1)

        wiki_headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Referer": "https://en.wikipedia.org/",
        }

        # Attempt 1: Wikipedia summary API

        summary_url = (
            "https://en.wikipedia.org/api/rest_v1/"
            f"page/summary/{title}"
        )

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                **wiki_headers,
                "Accept": "application/json",
            },
        ) as client:

            response = await client.get(summary_url)

            if response.status_code == 200:

                summary_text = (
                    response.json().get("extract", "")
                )

                if len(summary_text) > 100:

                    return {
                        "status": 200,
                        "content_type":
                            "text/plain; wikipedia-summary",
                        "length_bytes":
                            len(summary_text.encode("utf-8")),
                        "text": summary_text,
                    }

    # ─────────────────────────────────────────
    # Generic website fallback
    # ─────────────────────────────────────────

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers=headers,
    ) as client:

        response = await client.get(url)

        content_type = response.headers.get(
            "content-type",
            "",
        )

        text = response.text

        if "html" in content_type:

            text = re.sub(
                r"<(script|style)[^>]*>.*?</(script|style)>",
                "",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )

            text = re.sub(r"<[^>]+>", " ", text)

            text = re.sub(r"\s+", " ", text).strip()

        return {
            "status": response.status_code,
            "content_type": content_type,
            "length_bytes": len(
                text.encode("utf-8")
            ),
            "text": text,
        }


# ─────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
) -> list[dict]:
    """
    Search the web.
    """

    max_results = max(
        1,
        min(max_results, MAX_SEARCH_RESULTS),
    )

    # Tavily first

    if (
        os.environ.get("TAVILY_API_KEY")
        and _under_cap("tavily")
    ):

        try:

            results = _tavily_search(
                query,
                max_results,
            )

            if results:
                _bump("tavily")
                return results

        except Exception:
            _bump("tavily", "errors")

    # DuckDuckGo fallback

    results = _ddg_search(
        query,
        max_results,
    )

    _bump("duckduckgo")

    return results


@mcp.tool()
async def fetch_url(
    url: str,
    timeout: int = 60,
) -> dict:
    """
    Fetch clean page text.
    """

    return await _crawl4ai_fetch(url)


@mcp.tool()
def get_time(
    timezone: str = "UTC",
) -> dict:
    """
    Get current time in a timezone.
    """

    tz = ZoneInfo(timezone)

    now = datetime.now(tz)

    offset = now.utcoffset()

    offset_hours = (
        offset.total_seconds() / 3600
        if offset
        else 0.0
    )

    return {
        "iso": now.isoformat(),
        "human": now.strftime(
            "%A, %d %B %Y %H:%M:%S %Z"
        ),
        "timezone": timezone,
        "offset_hours": offset_hours,
    }


@mcp.tool()
def currency_convert(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> dict:
    """
    Currency conversion using frankfurter.dev
    """

    source = from_currency.upper()
    target = to_currency.upper()

    url = (
        "https://api.frankfurter.dev/v1/latest"
        f"?amount={amount}"
        f"&base={source}"
        f"&symbols={target}"
    )

    with httpx.Client(
        timeout=20,
        follow_redirects=True,
    ) as client:

        response = client.get(url)

        response.raise_for_status()

        data = response.json()

    converted = data["rates"][target]

    return {
        "amount": amount,
        "from": source,
        "to": target,
        "rate":
            converted / amount if amount else 0.0,
        "converted": converted,
        "date": data["date"],
        "source": "frankfurter.dev",
    }


@mcp.tool()
def read_file(path: str) -> dict:
    """
    Read a text file from sandbox.
    """

    if path.startswith("art:"):
        raise ValueError(
            "Artifact handles cannot be used "
            "with read_file"
        )

    p = _safe(path)

    text = p.read_text(encoding="utf-8")

    return {
        "path": path,
        "size_bytes": p.stat().st_size,
        "content": text,
        "encoding": "utf-8",
    }


@mcp.tool()
def list_dir(path: str = ".") -> list[dict]:
    """
    List sandbox directory.
    """

    p = _safe(path)

    out = []

    for child in sorted(p.iterdir()):

        out.append({
            "name": child.name,
            "type":
                "dir" if child.is_dir() else "file",
            "size_bytes":
                0 if child.is_dir()
                else child.stat().st_size,
        })

    return out


@mcp.tool()
def create_file(
    path: str,
    content: str,
) -> dict:
    """
    Create a sandbox file.
    """

    p = _safe(path)

    if p.exists():
        raise ValueError(
            f"File '{path}' already exists"
        )

    p.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    p.write_text(
        content,
        encoding="utf-8",
    )

    return {
        "ok": True,
        "path": path,
        "size_bytes": p.stat().st_size,
    }


@mcp.tool()
def update_file(
    path: str,
    content: str,
) -> dict:
    """
    Overwrite existing file.
    """

    p = _safe(path)

    if not p.exists():
        raise ValueError(
            f"File '{path}' does not exist"
        )

    p.write_text(
        content,
        encoding="utf-8",
    )

    return {
        "ok": True,
        "path": path,
        "size_bytes": p.stat().st_size,
    }


@mcp.tool()
def edit_file(
    path: str,
    find: str,
    replace: str,
    replace_all: bool = False,
) -> dict:
    """
    Find and replace inside a file.
    """

    p = _safe(path)

    text = p.read_text(encoding="utf-8")

    count = text.count(find)

    if count == 0:
        raise ValueError(
            f"'{find}' not found in '{path}'"
        )

    if count > 1 and not replace_all:
        raise ValueError(
            f"'{find}' occurs {count} times "
            f"in '{path}'"
        )

    new_text = (
        text.replace(find, replace)
        if replace_all
        else text.replace(find, replace, 1)
    )

    p.write_text(
        new_text,
        encoding="utf-8",
    )

    return {
        "ok": True,
        "path": path,
        "replacements":
            count if replace_all else 1,
        "size_bytes": p.stat().st_size,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print(
        "Starting MCP server "
        "(EAGV3 Session 6)"
    )

    mcp.run(transport="stdio")