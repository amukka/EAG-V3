"""
Document Q&A UI — FastAPI + vanilla JS.

Upload .txt / .md files → auto-index via FAISS → ask questions.

Run:
    python3.11 ui_app.py
Then open http://localhost:8200
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

import mcp_server as _mcp

UPLOAD_DIR = Path(__file__).parent / "sandbox" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

EXTRA_DOCS_DIR = Path(__file__).parent / "extra_docs"
EXTRA_DOCS_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.5:latest"

app = FastAPI(title="Document Q&A")


# ── LLM answer generation (Ollama qwen3.5) ───────────────────────────────────

def _generate_answer(query: str, chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant content found in the indexed documents."

    context_parts = []
    for i, c in enumerate(chunks, 1):
        src = c.get("source", "").split("/")[-1]
        preview = c.get("chunk_preview", "")[:800]
        score = c.get("similarity_score", 0)
        context_parts.append(f"[{i}] Source: {src} (relevance: {score:.2f})\n{preview}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = (
        f"You are a document assistant. Answer the question using ONLY the provided document chunks.\n"
        f"If the chunks do not contain relevant information, say so clearly.\n\n"
        f"QUESTION: {query}\n\n"
        f"DOCUMENT CHUNKS:\n{context}\n\n"
        f"Answer concisely. Cite sources by number [1], [2], etc."
    )
    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        r.raise_for_status()
        raw = r.json().get("response", "")
        # Strip <think>...</think> blocks (qwen3.5 chain-of-thought)
        return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    except Exception as e:
        return f"(LLM unavailable: {e})\n\nRaw chunks:\n{context}"


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.post("/upload")
def upload_files(files: list[UploadFile] = File(...)):
    results = []
    for file in files:
        if not file.filename:
            continue
        dest = UPLOAD_DIR / file.filename
        dest.write_bytes(file.file.read())
        # Path relative to sandbox/ for index_document
        rel = str(dest.relative_to(Path(__file__).parent / "sandbox"))
        try:
            res = _mcp.index_document(rel)
            chunks = int(res.get("chunks_indexed", 0))
            results.append({"file": file.filename, "chunks": chunks, "status": "indexed"})
        except Exception as e:
            results.append({"file": file.filename, "chunks": 0, "status": f"error: {e}"})
    return JSONResponse({"results": results})


@app.get("/extra-files")
def list_extra_files():
    """List all .txt and .md files in extra_docs/."""
    files = sorted(
        f for f in EXTRA_DOCS_DIR.rglob("*")
        if f.suffix.lower() in (".txt", ".md") and f.is_file()
    )
    return JSONResponse({"files": [str(f.relative_to(EXTRA_DOCS_DIR)) for f in files]})


@app.post("/index-local")
def index_local_files(body: dict):
    """Index selected files from extra_docs/ by their relative paths."""
    selected = body.get("files", [])
    results = []
    for rel_name in selected:
        src = EXTRA_DOCS_DIR / rel_name
        if not src.exists():
            results.append({"file": rel_name, "chunks": 0, "status": "not found"})
            continue
        # Copy to uploads/ so mcp_server sandbox path resolution works
        dest = UPLOAD_DIR / src.name
        dest.write_bytes(src.read_bytes())
        rel = str(dest.relative_to(Path(__file__).parent / "sandbox"))
        try:
            res = _mcp.index_document(rel)
            chunks = int(res.get("chunks_indexed", 0))
            results.append({"file": rel_name, "chunks": chunks, "status": "indexed"})
        except Exception as e:
            results.append({"file": rel_name, "chunks": 0, "status": f"error: {e}"})
    return JSONResponse({"results": results})


@app.get("/documents")
def list_documents():
    items = _mcp._mem.filter(kinds=["fact"])
    docs: dict[str, int] = {}
    for item in items:
        src = item.source or ""
        fname = src.split("/")[-1]
        if fname.endswith((".txt", ".md")):
            docs[fname] = docs.get(fname, 0) + 1
    return JSONResponse({"documents": [{"name": k, "chunks": v} for k, v in sorted(docs.items())]})


@app.post("/query")
def query_docs(body: dict):
    q = (body.get("query") or "").strip()
    if not q:
        return JSONResponse({"answer": "Please enter a question.", "sources": []})

    hits = _mcp.search_knowledge(q, k=6)
    # Remove the trailing note dict
    sources = [h for h in hits if "chunk_preview" in h]
    note = next((h.get("note", "") for h in hits if "note" in h), "")

    answer = _generate_answer(q, sources)

    return JSONResponse({
        "answer": answer,
        "sources": [
            {
                "file": s.get("source", "").split("/")[-1],
                "score": s.get("similarity_score", 0),
                "preview": s.get("chunk_preview", "")[:300],
            }
            for s in sources
        ],
        "note": note,
    })


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Document Q&A</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f0f2f5; min-height: 100vh; }
  header { background: #1a1a2e; color: white; padding: 16px 24px;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.3rem; font-weight: 600; }
  header span { font-size: 0.85rem; opacity: 0.6; }
  .layout { display: grid; grid-template-columns: 300px 1fr; gap: 16px;
            padding: 16px; max-width: 1200px; margin: 0 auto; }
  .card { background: white; border-radius: 12px; padding: 20px;
          box-shadow: 0 1px 4px rgba(0,0,0,.08); }

  /* File browser panel */
  .panel-title { font-size: .8rem; color: #888; text-transform: uppercase;
                 letter-spacing: .05em; margin-bottom: 10px; font-weight: 600; }
  .folder-label { font-size: .78rem; color: #aaa; margin-bottom: 8px;
                  word-break: break-all; }
  #file-browser { border: 1px solid #e8e8e8; border-radius: 8px;
                  max-height: 220px; overflow-y: auto; background: #fafafa; }
  .file-row { display: flex; align-items: center; gap: 8px;
              padding: 7px 12px; border-bottom: 1px solid #f0f0f0;
              cursor: pointer; transition: background .15s; }
  .file-row:last-child { border-bottom: none; }
  .file-row:hover { background: #eef1ff; }
  .file-row input[type=checkbox] { width: 15px; height: 15px; cursor: pointer; }
  .file-row label { font-size: .85rem; color: #333; cursor: pointer;
                    flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .no-files { padding: 20px; text-align: center; color: #aaa; font-size: .85rem; }
  .sel-actions { display: flex; gap: 6px; margin-top: 8px; }
  #index-btn { flex: 1; padding: 10px;
               background: #4f6ef7; color: white; border: none;
               border-radius: 8px; font-size: .9rem; cursor: pointer; }
  #index-btn:hover { background: #3a58d8; }
  #index-btn:disabled { background: #aaa; cursor: default; }
  #select-all-btn { padding: 10px 12px; background: #f0f0f0; color: #555;
                    border: none; border-radius: 8px; font-size: .85rem; cursor: pointer; }
  #select-all-btn:hover { background: #e0e0e0; }

  .doc-list { margin-top: 16px; }
  .doc-list h3 { font-size: .85rem; color: #888; text-transform: uppercase;
                 letter-spacing: .05em; margin-bottom: 10px; }
  .doc-item { display: flex; justify-content: space-between; align-items: center;
              padding: 8px 12px; background: #f7f8fc; border-radius: 8px;
              margin-bottom: 6px; font-size: .85rem; }
  .doc-item .name { font-weight: 500; color: #333; max-width: 170px;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .doc-item .badge { background: #e0e7ff; color: #4f6ef7; padding: 2px 8px;
                     border-radius: 20px; font-size: .75rem; white-space: nowrap; }
  .empty-docs { color: #aaa; font-size: .85rem; text-align: center; padding: 16px 0; }

  #upload-log { margin-top: 12px; font-size: .8rem; max-height: 120px;
                overflow-y: auto; }
  .log-ok  { color: #16a34a; padding: 2px 0; }
  .log-err { color: #dc2626; padding: 2px 0; }

  /* Query panel */
  .query-panel { display: flex; flex-direction: column; gap: 12px; }
  .query-box { display: flex; gap: 8px; }
  #query-input { flex: 1; padding: 12px 16px; border: 1.5px solid #e0e0e0;
                 border-radius: 10px; font-size: .95rem; outline: none; }
  #query-input:focus { border-color: #4f6ef7; }
  #ask-btn { padding: 12px 20px; background: #4f6ef7; color: white;
             border: none; border-radius: 10px; font-size: .95rem;
             cursor: pointer; white-space: nowrap; }
  #ask-btn:hover { background: #3a58d8; }
  #ask-btn:disabled { background: #aaa; cursor: default; }

  #answer-area { display: none; }
  .answer-box { background: #f7f8fc; border-left: 4px solid #4f6ef7;
                padding: 16px; border-radius: 0 8px 8px 0; white-space: pre-wrap;
                font-size: .9rem; line-height: 1.6; color: #333; }
  .sources-title { font-size: .8rem; color: #888; text-transform: uppercase;
                   letter-spacing: .05em; margin: 14px 0 8px; }
  .source-item { background: #fafafa; border: 1px solid #eee; border-radius: 8px;
                 padding: 10px 14px; margin-bottom: 8px; }
  .source-header { display: flex; justify-content: space-between;
                   align-items: center; margin-bottom: 6px; }
  .source-name { font-size: .85rem; font-weight: 600; color: #333; }
  .source-score { font-size: .75rem; padding: 2px 8px; border-radius: 20px; }
  .score-high { background: #dcfce7; color: #16a34a; }
  .score-mid  { background: #fef9c3; color: #854d0e; }
  .score-low  { background: #fee2e2; color: #dc2626; }
  .source-preview { font-size: .8rem; color: #666; line-height: 1.5; }
  .note-box { background: #fff8e1; border: 1px solid #fde68a; border-radius: 8px;
              padding: 10px 14px; font-size: .8rem; color: #92400e; margin-top: 8px; }
  .spinner { display: inline-block; width: 18px; height: 18px;
             border: 2px solid #fff; border-top-color: transparent;
             border-radius: 50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .history { display: flex; flex-direction: column; gap: 16px; }
  .history-item { border: 1px solid #e8e8e8; border-radius: 10px;
                  padding: 14px; background: #fff; }
  .history-q { font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }
</style>
</head>
<body>
<header>
  <span>📄</span>
  <h1>Document Q&A</h1>
  <span>Upload files · Index · Ask questions</span>
</header>

<div class="layout">
  <!-- Left: extra_docs browser + indexed list -->
  <div>
    <div class="card">
      <div class="panel-title">📂 extra_docs/</div>
      <div class="folder-label">session6/extra_docs/ — place your .txt / .md files here</div>

      <div id="file-browser"><div class="no-files">Loading…</div></div>

      <div class="sel-actions">
        <button id="select-all-btn" onclick="toggleSelectAll()">Select All</button>
        <button id="index-btn" onclick="indexSelected()" disabled>Index Selected</button>
      </div>
      <div id="upload-log"></div>

      <div class="doc-list">
        <h3>Indexed Documents</h3>
        <div id="doc-list-inner"><div class="empty-docs">No documents indexed yet</div></div>
      </div>
    </div>
  </div>

  <!-- Right: Query -->
  <div class="card query-panel">
    <div class="query-box">
      <input id="query-input" type="text" placeholder="Ask a question about your documents…"
             onkeydown="if(event.key==='Enter')askQuestion()">
      <button id="ask-btn" onclick="askQuestion()">Ask</button>
    </div>
    <div id="answer-area">
      <div class="history" id="history"></div>
    </div>
  </div>
</div>

<script>
let allChecked = false;

async function loadExtraFiles() {
  const browser = document.getElementById('file-browser');
  try {
    const res = await fetch('/extra-files');
    const data = await res.json();
    if (!data.files.length) {
      browser.innerHTML = '<div class="no-files">No .txt / .md files in extra_docs/</div>';
      return;
    }
    browser.innerHTML = data.files.map(f => `
      <div class="file-row" onclick="toggleFile('${f}')">
        <input type="checkbox" id="cb_${CSS.escape(f)}" value="${f}" onchange="updateIndexBtn()">
        <label for="cb_${CSS.escape(f)}">${f}</label>
      </div>`).join('');
  } catch(e) {
    browser.innerHTML = `<div class="no-files">Error loading files: ${e}</div>`;
  }
}

function toggleFile(name) {
  const cb = document.querySelector(`input[value="${name}"]`);
  if (cb) { cb.checked = !cb.checked; updateIndexBtn(); }
}

function updateIndexBtn() {
  const any = [...document.querySelectorAll('#file-browser input[type=checkbox]')].some(c => c.checked);
  document.getElementById('index-btn').disabled = !any;
}

function toggleSelectAll() {
  allChecked = !allChecked;
  document.querySelectorAll('#file-browser input[type=checkbox]').forEach(c => c.checked = allChecked);
  document.getElementById('select-all-btn').textContent = allChecked ? 'Deselect All' : 'Select All';
  updateIndexBtn();
}

async function indexSelected() {
  const selected = [...document.querySelectorAll('#file-browser input:checked')].map(c => c.value);
  if (!selected.length) return;

  const btn = document.getElementById('index-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Indexing…';
  const log = document.getElementById('upload-log');
  log.innerHTML = '';

  try {
    const res = await fetch('/index-local', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: selected })
    });
    const data = await res.json();
    data.results.forEach(r => {
      const div = document.createElement('div');
      div.className = r.status === 'indexed' ? 'log-ok' : 'log-err';
      div.textContent = r.status === 'indexed'
        ? `✓ ${r.file} — ${r.chunks} chunks indexed`
        : `✗ ${r.file} — ${r.status}`;
      log.appendChild(div);
    });
  } catch(e) {
    log.innerHTML = `<div class="log-err">Indexing failed: ${e}</div>`;
  }

  btn.textContent = 'Index Selected';
  refreshDocs();
}

async function refreshDocs() {
  const res = await fetch('/documents');
  const data = await res.json();
  const el = document.getElementById('doc-list-inner');
  if (!data.documents.length) {
    el.innerHTML = '<div class="empty-docs">No documents indexed yet</div>';
    return;
  }
  el.innerHTML = data.documents.map(d =>
    `<div class="doc-item">
       <span class="name" title="${d.name}">${d.name}</span>
       <span class="badge">${d.chunks} chunks</span>
     </div>`
  ).join('');
}

async function askQuestion() {
  const input = document.getElementById('query-input');
  const q = input.value.trim();
  if (!q) return;

  const btn = document.getElementById('ask-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  document.getElementById('answer-area').style.display = 'block';

  // Add a loading item
  const history = document.getElementById('history');
  const item = document.createElement('div');
  item.className = 'history-item';
  item.innerHTML = `<div class="history-q">Q: ${q}</div><div style="color:#aaa;font-size:.85rem">Searching…</div>`;
  history.prepend(item);

  input.value = '';

  try {
    const res = await fetch('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q })
    });
    const data = await res.json();

    const scoreClass = s => s >= 0.55 ? 'score-high' : s >= 0.45 ? 'score-mid' : 'score-low';
    const sourcesHtml = data.sources.length ? `
      <div class="sources-title">Sources (${data.sources.length})</div>
      ${data.sources.map((s,i) => `
        <div class="source-item">
          <div class="source-header">
            <span class="source-name">[${i+1}] ${s.file}</span>
            <span class="source-score ${scoreClass(s.score)}">score: ${s.score.toFixed(2)}</span>
          </div>
          <div class="source-preview">${s.preview.replace(/</g,'&lt;')}</div>
        </div>`).join('')}
    ` : '';
    const noteHtml = data.note && data.note.includes('LOW CONFIDENCE')
      ? `<div class="note-box">⚠️ ${data.note}</div>` : '';

    item.innerHTML = `
      <div class="history-q">Q: ${q}</div>
      <div class="answer-box">${data.answer.replace(/</g,'&lt;')}</div>
      ${sourcesHtml}
      ${noteHtml}
    `;
  } catch(e) {
    item.innerHTML = `<div class="history-q">Q: ${q}</div><div class="log-err">Error: ${e}</div>`;
  }

  btn.disabled = false;
  btn.textContent = 'Ask';
}

// Load on start
loadExtraFiles();
refreshDocs();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return _HTML


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8200, log_level="warning")