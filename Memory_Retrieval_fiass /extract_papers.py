import asyncio
from pathlib import Path
import re
import sys

# Add current directory to path so we can import mcp_server
sys.path.insert(0, str(Path(__file__).parent))
from mcp_server import _crawl4ai_fetch

SANDBOX = Path(__file__).parent / "sandbox"

def extract_urls_from_markdown(content: str) -> list[str]:
    # Match markdown links [text](url)
    md_links = re.findall(r'\[.*?\]\((https?://[^\s\)]+)\)', content)
    # Match plain URLs
    plain_urls = re.findall(r'(https?://[^\s\)\(\[\]\{\}]+)', content)
    urls = list(set(md_links + plain_urls))
    return urls

async def main():
    attention_path = SANDBOX / "papers" / "attention.md"
    if not attention_path.exists():
        print(f"Error: {attention_path} does not exist!")
        return

    print(f"Reading {attention_path}...")
    content = attention_path.read_text(encoding="utf-8")
    urls = extract_urls_from_markdown(content)
    
    # Prioritize html experimental url
    target_url = None
    for url in urls:
        if "arxiv.org/html/" in url:
            target_url = url
            break
    if not target_url:
        for url in urls:
            if "arxiv.org/abs/" in url:
                target_url = url
                break
    if not target_url:
        for url in urls:
            if "arxiv.org/pdf/" in url:
                target_url = url.replace("arxiv.org/pdf/", "arxiv.org/html/")
                break

    if not target_url:
        print("No target URL found in attention.md!")
        return

    print(f"Target URL found: {target_url}")
    print("Crawling URL via crawl4ai...")
    result = await _crawl4ai_fetch(target_url)
    
    text = result.get("text", "")
    if not text.strip():
        print("Crawling failed: empty content returned.")
        return
        
    crawled_path = SANDBOX / "papers" / "attention_crawled.md"
    header = f"# Crawled Content from {target_url}\n\n"
    crawled_path.write_text(header + text, encoding="utf-8")
    print(f"Successfully saved crawled text to {crawled_path}")

if __name__ == "__main__":
    asyncio.run(main())
