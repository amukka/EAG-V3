"""Flask backend for the Chrome Extension.

Provides API endpoints to accept files/URLs from the Chrome extension,
save them to the sandbox, and index them into FAISS using the `index_document`
logic (by invoking the same chunk+embed pipeline).
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

import memory
from agent import run as agent_run
import re
from mcp_server import _crawl4ai_fetch, index_document

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)
CORS(app)  # Allow Chrome extension to make requests

SANDBOX = Path(__file__).parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)


def _safe(path: str) -> Path:
    p = (SANDBOX / path).resolve()
    base = SANDBOX.resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Path '{path}' escapes the sandbox")
    return p


def extract_urls_from_markdown(content: str) -> list[str]:
    # Match markdown links [text](url)
    md_links = re.findall(r'\[.*?\]\((https?://[^\s\)]+)\)', content)
    # Match plain URLs
    plain_urls = re.findall(r'(https?://[^\s\)\(\[\]\{\}]+)', content)
    urls = list(set(md_links + plain_urls))
    return urls


@app.route("/api/status", methods=["GET"])
def get_status():
    """Return indexing stats."""
    # Count facts in memory.json
    try:
        items = memory._load()
        facts = [i for i in items if i.kind == "fact" and "sandbox:" in i.source]
        
        sources = set(f.source for f in facts)
        return jsonify({
            "status": "online",
            "indexed_documents": len(sources),
            "total_chunks": len(facts),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/index", methods=["POST"])
def index_file():
    """Accept a file from the extension, save to sandbox, and index it."""
    data = request.json
    if not data or "filename" not in data or "content" not in data:
        return jsonify({"error": "Missing filename or content"}), 400

    filename = data["filename"]
    content = data["content"]

    # 1. Write to sandbox
    sandbox_path = SANDBOX / filename
    sandbox_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_path.write_text(content, encoding="utf-8")

    # 2. Index the document (uses mcp_server.py logic directly)
    try:
        result = index_document(filename)
        return jsonify({
            "message": "File indexed successfully",
            "details": result
        })
    except Exception as e:
        return jsonify({"error": f"Failed to index: {str(e)}"}), 500


@app.route("/api/index-url", methods=["POST"])
def index_url():
    """Fetch a URL using crawl4ai, save to sandbox, and index it."""
    data = request.json
    if not data or "url" not in data:
        return jsonify({"error": "Missing url"}), 400

    url = data["url"]
    
    # Run async fetch in sync Flask route
    try:
        fetch_result = asyncio.run(_crawl4ai_fetch(url))
        content = fetch_result.get("text", "")
        
        if not content.strip():
            return jsonify({"error": "No content found at URL"}), 400

        # Save to sandbox as domain name
        domain = url.split("//")[-1].split("/")[0]
        safe_name = "".join([c if c.isalnum() else "_" for c in domain]) + ".md"
        sandbox_path = SANDBOX / safe_name
        sandbox_path.write_text(content, encoding="utf-8")

        # Index it
        result = index_document(safe_name)
        return jsonify({
            "message": "URL indexed successfully",
            "details": result,
            "filename": safe_name
        })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch/index URL: {str(e)}"}), 500


@app.route("/api/query", methods=["POST"])
def query_agent():
    """Run a query through the agent."""
    data = request.json
    if not data or "query" not in data:
        return jsonify({"error": "Missing query"}), 400

    try:
        answer = asyncio.run(agent_run(data["query"]))
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sandbox-files", methods=["GET"])
def list_sandbox_files():
    """List all files in the sandbox recursively."""
    try:
        files = []
        for root, _, filenames in os.walk(SANDBOX):
            for filename in filenames:
                if filename.startswith('.'):
                    continue
                full_path = Path(root) / filename
                rel_path = full_path.relative_to(SANDBOX)
                files.append(str(rel_path))
        return jsonify({"files": sorted(files)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/crawl-file", methods=["POST"])
def crawl_file():
    """Read a sandbox file, extract arXiv/web URLs, crawl them with crawl4ai, and save to sandbox."""
    data = request.json
    if not data or "path" not in data:
        return jsonify({"error": "Missing path"}), 400

    path = data["path"]
    try:
        sandbox_path = _safe(path)
        if not sandbox_path.exists():
            return jsonify({"error": f"File '{path}' does not exist"}), 404

        content = sandbox_path.read_text(encoding="utf-8")
        urls = extract_urls_from_markdown(content)

        # Find the best URL to crawl
        target_url = None
        # 1. Look for html version
        for url in urls:
            if "arxiv.org/html/" in url:
                target_url = url
                break
        # 2. Look for abs version
        if not target_url:
            for url in urls:
                if "arxiv.org/abs/" in url:
                    target_url = url
                    break
        # 3. Look for pdf version and convert to html/abs
        if not target_url:
            for url in urls:
                if "arxiv.org/pdf/" in url:
                    target_url = url.replace("arxiv.org/pdf/", "arxiv.org/html/")
                    break
        # 4. Fallback to any external URL
        if not target_url:
            for url in urls:
                if "arxiv.org" in url and not any(x in url for x in ["static", "login", "help", "about", "donate"]):
                    target_url = url
                    break
                elif "arxiv.org" not in url and not any(x in url for x in ["cornell.edu", "simonsfoundation", "creativecommons"]):
                    target_url = url
                    break

        if not target_url:
            return jsonify({"error": "No crawlable URL found in file"}), 400

        # Crawl the target URL
        fetch_result = asyncio.run(_crawl4ai_fetch(target_url))
        fetched_content = fetch_result.get("text", "")

        if not fetched_content.strip():
            return jsonify({"error": f"No content crawled from {target_url}"}), 400

        # Save to sandbox
        stem = sandbox_path.stem
        # Add _crawled suffix
        new_filename = f"{stem}_crawled.md"
        new_path = sandbox_path.parent / new_filename

        # Add a header indicating source
        header = f"# Crawled Content from {target_url}\n\n"
        new_path.write_text(header + fetched_content, encoding="utf-8")

        return jsonify({
            "message": "Crawl completed successfully",
            "url": target_url,
            "filename": str(new_path.relative_to(SANDBOX))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/index-sandbox", methods=["POST"])
def index_sandbox_file():
    """Index an existing sandbox file."""
    data = request.json
    if not data or "path" not in data:
        return jsonify({"error": "Missing path"}), 400

    path = data["path"]
    try:
        # Index the document
        result = index_document(path)
        return jsonify({
            "message": "File indexed successfully",
            "details": result
        })
    except Exception as e:
        return jsonify({"error": f"Failed to index: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("API_SERVER_PORT", 5050))
    print(f"Starting API server on port {port}...")
    app.run(host="127.0.0.1", port=port, debug=True)
