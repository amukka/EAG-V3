from pathlib import Path
from urllib.parse import urlparse
import re
import hashlib
from collections import OrderedDict

import httpx
from bs4 import BeautifulSoup


def _normalize_url(url: str) -> str:
    # Remove trailing punctuation that often appears in copied markdown links.
    return url.strip().rstrip(">),.;\"")


def _slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    raw = parsed.netloc + "_" + parsed.path
    if parsed.query:
        raw += "__q_" + parsed.query
    if parsed.fragment:
        raw += "__f_" + parsed.fragment
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw).strip("_")[:110]
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{base}__{digest}" if base else f"url_{digest}"


def _arxiv_key_rank(url: str) -> tuple[str | None, int]:
    """Return a canonical key and rank for arXiv URL variants.

    Higher rank wins when multiple URLs point to effectively the same paper.
    """
    p = urlparse(url)
    if "arxiv.org" not in p.netloc:
        return None, -1

    # /html/1706.03762v7, /abs/1706.03762v7, /abs/1706.03762, /pdf/1706.03762
    m = re.match(r"^/(html|abs|pdf)/([0-9]{4}\.[0-9]{5})(?:v([0-9]+))?", p.path)
    if not m:
        return None, -1

    kind = m.group(1)
    paper_id = m.group(2)
    ver = int(m.group(3) or 0)

    # Prefer html highest, then abs, then pdf; within each prefer latest version.
    base = {"html": 300, "abs": 200, "pdf": 100}.get(kind, 0)
    return f"arxiv:{paper_id}", base + ver


def _load_known_bad_urls(report_path: Path) -> set[str]:
    if not report_path.exists():
        return set()
    bad: set[str] = set()
    for line in report_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        status, _, url = parts[0], parts[1], parts[2]
        if status in {"ERR", "FAIL"}:
            bad.add(_normalize_url(url))
    return bad


def _iter_markdown_files() -> list[Path]:
    """Find all markdown paper files across the known corpus locations."""
    roots = [
        Path("reference_code/S7code/sandbox/papers"),
        Path("S7code/sandbox/papers"),
        Path("sandbox/papers"),
    ]
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            if path not in seen:
                files.append(path)
                seen.add(path)
    return files


def _extract_urls_from_markdown(text: str) -> list[str]:
    md_links = re.findall(r"\[.*?\]\((https?://[^\s\)]+)\)", text)
    plain_urls = re.findall(r"(https?://[^\s\)\(\[\]\{\}\"]+)", text)
    return sorted(set(_normalize_url(u) for u in md_links + plain_urls))


_NO_HTML_MARKERS = [
    "HTML is not available for the source",
    "No HTML for '",
    "html is not available",
]


def main() -> None:
    base = Path("sandbox/papers")
    out_dir = base / "url_text_exports"
    report_path = base / "url_export_report.txt"
    skip_path = base / "url_export_skipped.txt"
    out_dir.mkdir(parents=True, exist_ok=True)

    markdown_files = _iter_markdown_files()
    if not markdown_files:
        raise FileNotFoundError("No markdown files found in known papers folders")

    # Keep likely content pages first; skip obvious static/login/noise links.
    skip_terms = [
        "login",
        "/static/",
        "icons/social",
        "show-email",
        "prevnext",
        "list/cs",
        "search/author",
        "reddit.com/submit",
        "IgnoreMe",
        "status.arxiv.org",
    ]
    keep_patterns = [
        "arxiv.org/html/",
        "arxiv.org/abs/",
        "api.semanticscholar.org/",
        "doi.org/",
    ]

    known_bad_urls = _load_known_bad_urls(report_path)

    client = httpx.Client(
        timeout=25.0,
        follow_redirects=True,
        verify=False,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )

    report: list[str] = []
    newly_bad: set[str] = set()
    ok = 0
    written_files: set[str] = set()
    seen_content: dict[str, str] = {}
    seen_url_keys: OrderedDict[str, tuple[str, int]] = OrderedDict()

    for md_path in markdown_files:
        md_text = md_path.read_text(encoding="utf-8", errors="ignore")
        urls = _extract_urls_from_markdown(md_text)
        skipped_by_rule: list[str] = []

        # First pass: filter by rule and remove exact duplicates inside a paper.
        filtered: list[str] = []
        for u in urls:
            if any(s in u for s in skip_terms):
                skipped_by_rule.append(f"SKIP\trule\t{u}")
                continue
            if any(k in u for k in keep_patterns):
                if u in known_bad_urls:
                    skipped_by_rule.append(f"SKIP\tknown_bad\t{u}")
                    continue
                filtered.append(u)

        # Sort by arxiv rank so HTML is tried before abs, but keep ALL variants.
        # Content-hash deduplication after fetch handles actual duplicates.
        # This lets abs URLs serve as fallback when HTML returns "No HTML available".
        filtered.sort(key=lambda u: _arxiv_key_rank(u)[1], reverse=True)
        report.append(f"FILE\t{md_path.as_posix()}\turls={len(urls)}\tkept={len(filtered)}")
        report.extend(skipped_by_rule)

        for i, url in enumerate(filtered, start=1):
            try:
                r = client.get(url)
                ct = (r.headers.get("content-type") or "").lower()
                if r.status_code != 200:
                    report.append(f"SKIP\tfail_status({r.status_code})\t{url}")
                    newly_bad.add(url)
                    continue
                if "pdf" in ct:
                    report.append(f"SKIP\tpdf\t{url}")
                    continue

                html = r.text
                soup = BeautifulSoup(html, "html.parser")
                for t in soup(["script", "style", "noscript", "svg"]):
                    t.decompose()

                # Prefer main/article containers when present.
                main_el = soup.find("main") or soup.find("article") or soup
                text = "\n".join(line.strip() for line in main_el.get_text("\n").splitlines() if line.strip())

                # Normalize whitespace and keep meaningful pages only.
                text = re.sub(r"\n{3,}", "\n\n", text)
                if len(text) < 500:
                    report.append(f"SKIP\ttoo_short({len(text)})\t{url}")
                    continue
                # Skip arxiv "No HTML available" pages — abs URL will serve as fallback.
                if any(marker.lower() in text.lower() for marker in _NO_HTML_MARKERS):
                    report.append(f"SKIP\tno_html_available\t{url}")
                    newly_bad.add(url)
                    continue

                # Skip near-identical pages after whitespace/case normalization.
                canonical_text = re.sub(r"\s+", " ", text).strip().lower()
                content_hash = hashlib.sha1(canonical_text.encode("utf-8")).hexdigest()
                if content_hash in seen_content:
                    report.append(
                        f"SKIP\tduplicate_content\t{url}\tmatched={seen_content[content_hash]}"
                    )
                    continue

                slug = _slug_for_url(url)
                source_stem = md_path.stem
                out_path = out_dir / f"{source_stem}__{slug}.txt"
                out_path.write_text(f"SOURCE: {url}\nSOURCE_MD: {md_path.as_posix()}\n\n{text}", encoding="utf-8")
                written_files.add(out_path.name)
                seen_content[content_hash] = out_path.name
                ok += 1
                report.append(f"OK\t{len(text)}\t{url}\t{out_path.name}")

                # For arxiv abs pages: also write a dedicated abstract-only file so
                # the abstract embeds cleanly without metadata noise diluting it.
                if "arxiv.org/abs/" in url or "arxiv.org/html/" in url:
                    abstract_el = soup.find("blockquote", class_="abstract")
                    if abstract_el:
                        abstract_text = abstract_el.get_text(" ", strip=True)
                        abstract_text = re.sub(r"^Abstract:\s*", "", abstract_text).strip()
                        if len(abstract_text) > 100:
                            title_el = soup.find("h1", class_="title") or soup.find("h1")
                            title_text = title_el.get_text(" ", strip=True) if title_el else ""
                            title_text = re.sub(r"^Title:\s*", "", title_text).strip()
                            abstract_content = (
                                f"SOURCE: {url}\nSOURCE_MD: {md_path.as_posix()}\n\n"
                                f"Title: {title_text}\n\nAbstract: {abstract_text}"
                            )
                            abs_slug = slug + "__abstract"
                            abs_path = out_dir / f"{source_stem}__{abs_slug}.txt"
                            abs_path.write_text(abstract_content, encoding="utf-8")
                            written_files.add(abs_path.name)
                            report.append(f"OK_ABSTRACT\t{len(abstract_text)}\t{url}\t{abs_path.name}")
            except Exception as e:
                report.append(f"SKIP\terror({type(e).__name__})\t{url}")
                newly_bad.add(url)

    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    skipped_aggregate = sorted(known_bad_urls | newly_bad)
    if skipped_aggregate:
        skip_path.write_text("\n".join(skipped_aggregate) + "\n", encoding="utf-8")

    print(f"Input URLs: {len(urls)}")
    print(f"Filtered URLs: {len(filtered)}")
    print(f"Exported URL responses: {ok}")
    print(f"Unique output files written: {len(written_files)}")
    print(f"Exports folder: {out_dir}")
    print(f"Report file: {report_path}")
    if skipped_aggregate:
        print(f"Skipped URL list: {skip_path}")


if __name__ == "__main__":
    main()
