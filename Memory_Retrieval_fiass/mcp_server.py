
"""
server.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import certifi
import httpx
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
import artifacts as _artifacts  # noqa: E402
import memory as _memory  # noqa: E402

MAX_SEARCH_RESULTS = 5  # hard cap — Tavily prices per result

load_dotenv(Path(__file__).parent / ".env")

mcp = FastMCP("eagv3-s6-server")

ALLOW_INSECURE_FETCH = os.environ.get("ALLOW_INSECURE_FETCH", "1").strip().lower() in {
    "1", "true", "yes", "on"
}

SANDBOX = Path(__file__).parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)

USAGE_PATH = Path(__file__).parent / "usage.json"
MONTHLY_CAP = 950  # leave 50/mo headroom on Tavily
_usage_lock = threading.Lock()
_mem = _memory.Memory()


def _safe(path: str) -> Path:
    p = (SANDBOX / path).resolve()
    base = SANDBOX.resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Path '{path}' escapes the sandbox")
    return p


def _empty_usage(month: str) -> dict:
    return {
        "month": month,
        "tavily": {"count": 0, "errors": 0},
        "duckduckgo": {"count": 0, "errors": 0},
    }


def _load_usage() -> dict:
    month = datetime.now().strftime("%Y-%m")
    if not USAGE_PATH.exists():
        return _empty_usage(month)
    try:
        data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_usage(month)
    if data.get("month") != month:
        return _empty_usage(month)
    for k in ("tavily", "duckduckgo"):
        data.setdefault(k, {"count": 0, "errors": 0})
    return data


def _save_usage(data: dict) -> None:
    USAGE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _bump(provider: str, field: str = "count") -> None:
    with _usage_lock:
        data = _load_usage()
        data[provider][field] = data[provider].get(field, 0) + 1
        _save_usage(data)


def _under_cap(provider: str) -> bool:
    return _load_usage()[provider]["count"] < MONTHLY_CAP


def _tavily_search(query: str, max_results: int) -> list[dict]:
    from tavily import TavilyClient

    client = TavilyClient(os.environ["TAVILY_API_KEY"])
    resp = client.search(query=query, max_results=max_results, search_depth="advanced")
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in resp.get("results", [])
    ]


def _ddg_search(query: str, max_results: int) -> list[dict]:
    import time
    hits: list[dict] = []
    for attempt in range(3):
        try:
            hits = list(DDGS().text(query, max_results=max_results))
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


async def _crawl4ai_fetch(url: str) -> dict:
    """Fetch page content — Wikipedia API for wikipedia.org, httpx for everything else."""
    import re as _re

    def _http_client(*, accept: str | None = None, timeout: int = 30) -> httpx.AsyncClient:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        if accept:
            headers["Accept"] = accept

        # Prefer an explicit CA bundle so environments with custom OpenSSL stores
        # still validate public cert chains consistently.
        verify_path = os.environ.get("SSL_CERT_FILE") or certifi.where()
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
            verify=verify_path,
        )

    async def _get_with_ssl_fallback(
        req_url: str,
        *,
        accept: str | None = None,
        params: dict | None = None,
        timeout: int = 30,
    ) -> httpx.Response:
        try:
            async with _http_client(accept=accept, timeout=timeout) as client:
                return await client.get(req_url, params=params)
        except Exception as exc:
            if ALLOW_INSECURE_FETCH and "CERTIFICATE_VERIFY_FAILED" in str(exc):
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": accept or "*/*",
                    },
                    verify=False,
                ) as client:
                    return await client.get(req_url, params=params)
            raise

    wiki_match = _re.search(r"wikipedia\.org/wiki/([^#?]+)", url)
    if wiki_match:
        title = wiki_match.group(1)
        # Full browser headers to pass CDN bot detection
        wiki_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Referer": "https://en.wikipedia.org/",
        }

        # Attempt 1: MediaWiki extracts API (full plain-text article)
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": "1",
            "format": "json",
            "redirects": "1",
        }
        rm = await _get_with_ssl_fallback(
            "https://en.wikipedia.org/w/api.php",
            accept="application/json",
            params=params,
            timeout=30,
        )
        if rm.status_code == 200:
            pages = rm.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            mw_text = page.get("extract", "")
            if len(mw_text) > 500:
                return {
                    "status": 200,
                    "content_type": "text/plain; wikipedia-api",
                    "length_bytes": len(mw_text.encode("utf-8")),
                    "text": mw_text,
                }

        # Attempt 2: REST API summary (clean intro with dates/bio)
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        rs = await _get_with_ssl_fallback(
            summary_url,
            accept="application/json",
            timeout=30,
        )
        if rs.status_code == 200:
            summary_text = rs.json().get("extract", "")
            if len(summary_text) > 100:
                return {
                    "status": 200,
                    "content_type": "text/plain; wikipedia-summary",
                    "length_bytes": len(summary_text.encode("utf-8")),
                    "text": summary_text,
                }

        # Attempt 3: action=raw returns raw wikitext (LLM can parse dates/facts from it)
        raw_url = f"https://en.wikipedia.org/w/index.php?title={title}&action=raw"
        rr = await _get_with_ssl_fallback(
            raw_url,
            accept="text/plain",
            timeout=30,
        )
        if rr.status_code == 200 and len(rr.text) > 100:
            return {
                "status": 200,
                "content_type": "text/plain; wikipedia-wikitext",
                "length_bytes": len(rr.text.encode("utf-8")),
                "text": rr.text[:60_000],
            }

        # Fallback: DBpedia (different domain — not Wikimedia CDN)
        dbpedia_url = f"https://dbpedia.org/data/{title}.json"
        rd = await _get_with_ssl_fallback(
            dbpedia_url,
            accept="application/json",
            timeout=30,
        )
        if rd.status_code == 200:
            entity = rd.json().get(f"http://dbpedia.org/resource/{title}", {})
            if entity:
                def _pick(prop: str) -> list[str]:
                    out: list[str] = []
                    for k, vals in entity.items():
                        if not isinstance(vals, list):
                            continue
                        if k.split("/")[-1] == prop or k.split("#")[-1] == prop:
                            out.extend(str(v.get("value", "")) for v in vals if isinstance(v, dict))
                    return out

                birth = next(iter(_pick("birthDate")), "unknown")
                death = next(iter(_pick("deathDate")), "unknown")
                birth_place = next((v for v in _pick("birthPlace") if len(v) > 5 and "dbpedia" not in v), "unknown")
                death_place = next((v for v in _pick("deathPlace") if len(v) > 5 and "dbpedia" not in v), "unknown")
                birth_name = next(iter(_pick("birthName")), title.replace("_", " "))
                known_for = [k.split("/")[-1].replace("_", " ") for k in _pick("knownFor") if "dbpedia.org/resource/" in k]

                lines = [
                    f"{birth_name}",
                    f"Born: {birth} in {birth_place}",
                    f"Died: {death} in {death_place}",
                    f"Known for: {', '.join(known_for[:10])}",
                ]
                text = "\n".join(lines)
                return {
                    "status": 200,
                    "content_type": "text/plain; dbpedia",
                    "length_bytes": len(text.encode("utf-8")),
                    "text": text,
                }

        raise ValueError(
            f"All data sources blocked for '{title}'. Use web_search instead."
        )

    r = await _get_with_ssl_fallback(
        url,
        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        timeout=30,
    )

    content_type = r.headers.get("content-type", "")
    text = r.text

    if "html" in content_type:
        text = _re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", text, flags=_re.DOTALL | _re.IGNORECASE)
        text = _re.sub(r"<[^>]+>", " ", text)
        text = _re.sub(r"\s+", " ", text).strip()

    return {
        "status": r.status_code,
        "content_type": content_type,
        "length_bytes": len(text.encode("utf-8")),
        "text": text,
    }


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web (Tavily primary, DDG fallback). Hard-capped at 5 results. Example: web_search("python asyncio tutorial", 3)."""
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
    if os.environ.get("TAVILY_API_KEY") and _under_cap("tavily"):
        try:
            results = _tavily_search(query, max_results)
            if results:
                _bump("tavily")
                return results
        except Exception:
            _bump("tavily", "errors")
    results = _ddg_search(query, max_results)
    _bump("duckduckgo")
    return results


@mcp.tool()
async def fetch_url(url: str, timeout: int = 60) -> dict:
    """Fetch clean markdown from a URL via crawl4ai (headless Chromium). Example: fetch_url("https://example.com")."""
    return await _crawl4ai_fetch(url)


@mcp.tool()
def get_time(timezone: str = "UTC") -> dict:
    """Current time in a named IANA timezone. Example: get_time("Asia/Kolkata")."""
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    offset = now.utcoffset()
    offset_hours = offset.total_seconds() / 3600 if offset else 0.0
    return {
        "iso": now.isoformat(),
        "human": now.strftime("%A, %d %B %Y %H:%M:%S %Z"),
        "timezone": timezone,
        "offset_hours": offset_hours,
    }


@mcp.tool()
def currency_convert(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert money between ISO-3 currencies via frankfurter.dev. Example: currency_convert(100, "USD", "INR")."""
    f = from_currency.upper()
    t = to_currency.upper()
    url = f"https://api.frankfurter.dev/v1/latest?amount={amount}&base={f}&symbols={t}"
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    converted = data["rates"][t]
    return {
        "amount": amount,
        "from": f,
        "to": t,
        "rate": converted / amount if amount else 0.0,
        "converted": converted,
        "date": data["date"],
        "source": "frankfurter.dev",
    }


@mcp.tool()
def read_file(path: str) -> dict:
    """Read a UTF-8 text file from the sandbox. Example: read_file("notes.txt"). Do NOT pass artifact IDs (art:N) here."""
    if path.startswith("art:"):
        raise ValueError(
            f"'{path}' is an artifact handle, not a sandbox file. "
            "Artifacts are injected automatically by the system — do not use read_file to access them."
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
    """List a directory inside the sandbox. Example: list_dir(".")."""
    p = _safe(path)
    out = []
    for child in sorted(p.iterdir()):
        is_dir = child.is_dir()
        out.append({
            "name": child.name,
            "type": "dir" if is_dir else "file",
            "size_bytes": 0 if is_dir else child.stat().st_size,
        })
    return out


@mcp.tool()
def create_file(path: str, content: str) -> dict:
    """Create a new file in the sandbox; errors if it already exists. Parent directories are created automatically. Example: create_file("reminders/birthday.txt", "Reminder: May 15")."""
    p = _safe(path)
    if p.exists():
        raise ValueError(f"File '{path}' already exists")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "size_bytes": p.stat().st_size}


@mcp.tool()
def update_file(path: str, content: str) -> dict:
    """Overwrite an existing sandbox file. Example: update_file("hello.txt", "new body")."""
    p = _safe(path)
    if not p.exists():
        raise ValueError(f"File '{path}' does not exist")
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path, "size_bytes": p.stat().st_size}


@mcp.tool()
def edit_file(path: str, find: str, replace: str, replace_all: bool = False) -> dict:
    """Find-and-replace inside a sandbox file. Example: edit_file("hello.txt", "foo", "bar")."""
    p = _safe(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(find)
    if count == 0:
        raise ValueError(f"'{find}' not found in '{path}'")
    if count > 1 and not replace_all:
        raise ValueError(
            f"'{find}' occurs {count} times in '{path}'; pass replace_all=True"
        )
    new_text = text.replace(find, replace) if replace_all else text.replace(find, replace, 1)
    p.write_text(new_text, encoding="utf-8")
    replacements = count if replace_all else 1
    return {
        "ok": True,
        "path": path,
        "replacements": replacements,
        "size_bytes": p.stat().st_size,
    }


def _read_for_index(path: str) -> tuple[str, str]:
    if path.startswith("art:"):
        return _artifacts.get_bytes(path).decode("utf-8", errors="replace"), path
    p = _safe(path)
    return p.read_text(encoding="utf-8"), f"sandbox:{path}"


def _chunk_text(text: str, size: int = 400, overlap: int = 80) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    stride = max(1, size - overlap)
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + size]))
        if i + size >= len(words):
            break
        i += stride
    return chunks



@mcp.tool()
def index_document(path: str, chunk_size: int = 400, overlap: int = 80) -> dict:
    """Chunk a sandbox file or artifact and write each chunk into Memory as searchable facts. Use this for persistent indexing before later retrieval queries."""
    text, source = _read_for_index(path)
    if not text.strip():
        return {"path": path, "source": source, "chunks_indexed": 0, "warning": "empty content"}
    chunks = _chunk_text(text, size=chunk_size, overlap=overlap)
    run_id = f"index-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    indexed = 0
    for i, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        descriptor = f"[{source} chunk {i+1}/{len(chunks)}] {preview}"
        _mem.add_fact(
            descriptor=descriptor,
            value={
                "chunk": chunk,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": source,
            },
            keywords=None,
            source=source,
            run_id=run_id,
        )
        indexed += 1
    return {
        "path": path,
        "source": source,
        "chunks_indexed": indexed,
        "chunk_size": chunk_size,
        "overlap": overlap,
    }


@mcp.tool()
def search_knowledge(query: str, k: int = 8) -> list[dict]:
    """Vector search over indexed fact chunks. Returns up to k ranked chunks with provenance.
    Call this rather than re-fetching URLs or re-reading source files whenever Memory already
    contains indexed chunks for the topic. Use k=8 or higher when synthesizing multi-point answers.
    Example: search_knowledge("attention mechanism key contributions", 8)."""
    q = (query or "").lower()

    # Entity-aware retrieval: when comparing two named papers, pull from each separately
    # so one paper doesn't dominate the top-k hits.
    _PAPER_ALIASES = {
        "react": "ReAct paper reasoning acting",
        "chain-of-thought": "Chain-of-Thought paper reasoning steps",
        "chain of thought": "Chain-of-Thought paper reasoning steps",
        "cot": "Chain-of-Thought paper reasoning steps",
        "dpo": "DPO direct preference optimization",
        "lora": "LoRA low-rank adaptation",
        "attention": "Attention Transformer self-attention",
        "transformer": "Attention Transformer self-attention",
    }
    entity_items: list = []
    matched = [alias_q for kw, alias_q in _PAPER_ALIASES.items() if kw in q]
    if len(matched) >= 1:
        per_k = max(4, k)
        for alias_q in matched:
            entity_items.extend(
                _mem.read(alias_q, history=[], kinds=["fact"], top_k=per_k * 4)
            )

    # Use vector search directly to get similarity scores alongside items.
    _RELEVANCE_THRESHOLD = 0.50  # cosine similarity below this = weak/off-topic match
    scored_items: list[tuple[float, object]] = []
    try:
        qvec = _mem._try_embed(query, "retrieval_query")
        if qvec is not None:
            from vector_index import VectorIndex
            idx = VectorIndex(_STATE_DIR)
            raw_hits = idx.search(qvec, k=max(k * 8, 48))
            by_id = {item.id: item for item in _mem._items}
            for item_id, score in raw_hits:
                item = by_id.get(item_id)
                if item and item.kind == "fact":
                    scored_items.append((score, item))
    except Exception:
        pass
    if not scored_items:
        plain = _mem.read(query, history=[], kinds=["fact"], top_k=max(k * 6, 24))
        scored_items = [(0.0, item) for item in plain]
    scored_items = [(0.9, item) for item in entity_items] + scored_items  # entity hits first

    # Prefer real indexed chunks over generic fact rows (e.g. remembered user query summaries).
    indexed: list = []
    scores: list[float] = []
    seen: set[tuple[str, int | None]] = set()
    for entry in scored_items:
        score, item = (entry if isinstance(entry, tuple) else (0.0, entry))
        val = item.value or {}
        chunk = val.get("chunk")
        if not (isinstance(chunk, str) and chunk.strip()):
            continue
        src = str(val.get("source") or item.source or "")
        desc = item.descriptor or ""
        is_indexed = (
            desc.startswith("[sandbox:")
            or desc.startswith("[art:")
            or src.startswith("sandbox:")
            or src.startswith("art:")
        )
        if not is_indexed:
            continue
        key = (src, val.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        indexed.append(item)
        scores.append(score)
        if len(indexed) >= k:
            break

    chosen = indexed
    top_score = max(scores) if scores else 0.0
    results = [
        {
            "id": item.id,
            "descriptor": item.descriptor,
            "source": item.source,
            "similarity_score": round(score, 3),
            "chunk_preview": (item.value.get("chunk") or "")[:2000],
            "metadata": {k_: v for k_, v in item.value.items() if k_ != "chunk"},
        }
        for item, score in zip(chosen, scores)
    ]
    if results:
        low_confidence = top_score < _RELEVANCE_THRESHOLD
        results.append({
            "note": (
                f"Top similarity score: {top_score:.3f} (scale 0–1). "
                + (
                    "LOW CONFIDENCE — score below 0.50 means the query concept is likely NOT "
                    "covered in the indexed papers. Do NOT synthesise a connection. "
                    "Answer: 'The indexed papers do not directly cover <topic>.' "
                    "You may mention which paper is the closest match and why it is not the same thing."
                    if low_confidence else
                    "Chunks are retrieved by vector similarity — synthesise by explaining HOW "
                    "each chunk relates to the concept. If chunks are about a different topic, say so."
                )
            )
        })
    return results


def _extract_best_url(md_text: str) -> str | None:
    """Pick the highest-quality URL from a markdown paper file (prefers arxiv html > abs > doi)."""
    all_urls = re.findall(r"https?://[^\s\)\(\[\]\{\}\"<>]+", md_text)
    all_urls = [u.rstrip(">),.;\"") for u in all_urls]

    skip = ["login", "/static/", "icons/", "show-email", "prevnext",
            "list/cs", "search/author", "reddit.com", "IgnoreMe",
            "status.arxiv", "bibsonomy", "semanticscholar", "scholar.google",
            "dblp", "influencemap", "core.ac.uk", "paperswithcode",
            "huggingface", "replicate", "dagshub", "litmaps", "scite",
            "connectedpapers", "alphaxiv", "txyz", "sciencecast"]

    def _rank(url: str) -> int:
        p = urlparse(url)
        if "arxiv.org" not in p.netloc and "doi.org" not in p.netloc:
            return -1
        if any(s in url for s in skip):
            return -1
        if re.search(r"/html/\d{4}\.\d{4,5}", url):
            return 3   # full paper HTML — best
        if re.search(r"/abs/\d{4}\.\d{4,5}", url):
            return 2   # abstract page
        if "doi.org" in p.netloc:
            return 1
        return 0

    ranked = sorted(((url, _rank(url)) for url in all_urls), key=lambda x: -x[1])
    best = next((url for url, rank in ranked if rank > 0), None)
    return best


def _fetch_and_clean(url: str) -> str | None:
    """Fetch a URL and return clean plain text (strips nav/script/style noise)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    try:
        r = httpx.get(url, timeout=25.0, follow_redirects=True, verify=False,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"})
        if r.status_code != 200:
            return None
        ct = (r.headers.get("content-type") or "").lower()
        if "pdf" in ct:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
            tag.decompose()
        container = soup.find("main") or soup.find("article") or soup
        text = "\n".join(line.strip() for line in container.get_text("\n").splitlines() if line.strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text if len(text) >= 500 else None
    except Exception:
        return None


@mcp.tool()
def index_paper_md(path: str) -> dict:
    """Index a paper markdown file by extracting its best URL, fetching the full HTML,
    cleaning noise, saving as a .txt file, and indexing the chunks.
    Use this instead of index_document when the source is a .md paper file.
    Example: index_paper_md("papers/attention.md")"""
    p = _safe(path)
    md_text = p.read_text(encoding="utf-8", errors="ignore")

    url = _extract_best_url(md_text)
    if not url:
        return {"ok": False, "path": path, "error": "No suitable URL found in markdown file"}

    text = _fetch_and_clean(url)
    if not text:
        return {"ok": False, "path": path, "url": url, "error": "Failed to fetch or content too short"}

    # Save clean text alongside the .md file
    slug = hashlib.sha1(url.encode()).hexdigest()[:10]
    txt_name = f"{p.stem}__{urlparse(url).netloc}__{slug}.txt"
    txt_path = p.parent / txt_name
    txt_path.write_text(f"SOURCE: {url}\nSOURCE_MD: {path}\n\n{text}", encoding="utf-8")

    # Index the saved file
    rel_txt = str(txt_path.relative_to(SANDBOX))
    result = index_document(rel_txt)
    result["source_url"] = url
    result["txt_file"] = rel_txt
    return result


@mcp.tool()
def memory_stats() -> dict:
    """Return counts of indexed chunks and memory items. Use this to answer questions like 'how many chunks were indexed'."""
    all_items = _mem.filter()
    by_kind: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for item in all_items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        src = item.source or "unknown"
        # Group paper chunks by their document name
        if src.startswith("sandbox:papers/"):
            doc = src.split("sandbox:papers/")[1]
            by_source[doc] = by_source.get(doc, 0) + 1
        else:
            by_source[src] = by_source.get(src, 0) + 1
    paper_chunks = sum(v for k, v in by_source.items() if "__" in k or k.endswith(".txt") or k.endswith(".md"))
    return {
        "total_items": len(all_items),
        "by_kind": by_kind,
        "paper_chunks_total": paper_chunks,
        "chunks_by_document": {k: v for k, v in sorted(by_source.items()) if "__" in k or k.endswith(".txt") or k.endswith(".md")},
        "other_sources": {k: v for k, v in by_source.items() if "__" not in k and not k.endswith(".txt") and not k.endswith(".md")},
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
