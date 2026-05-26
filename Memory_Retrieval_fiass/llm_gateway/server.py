"""
Minimal LLM Gateway — Gemini only.
Runs on port 8101.

Start:  python llm_gateway/server.py
        OR
        uv run llm_gateway/server.py

Requires in .env:
    GEMINI_API_KEY=your_key_here
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env")

PORT = int(os.getenv("GATEWAY_PORT", "8101"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


# ── Gemini call ───────────────────────────────────────────────────────────────

def _convert_messages(messages: list[dict]) -> tuple[list, str | None]:
    """Split messages into Gemini contents + optional systemInstruction."""
    contents, system = [], None
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system = content
        else:
            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": content}],
            })
    return contents, system


async def call_gemini(messages: list[dict], max_tokens: int, temperature: float) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(500, "GEMINI_API_KEY not set in .env")

    contents, system = _convert_messages(messages)
    body: dict = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(url, json=body)
    except Exception as exc:
        raise HTTPException(502, f"Gemini transport error: {exc}") from exc

    if r.status_code != 200:
        raise HTTPException(502, f"Gemini error {r.status_code}: {r.text[:300]}")

    try:
        d = r.json()
    except Exception as exc:
        raise HTTPException(502, f"Gemini returned non-JSON response: {r.text[:300]}") from exc

    candidates = d.get("candidates") or []
    if not candidates:
        feedback = d.get("promptFeedback") or {}
        raise HTTPException(
            502,
            f"Gemini returned no candidates: feedback={json.dumps(feedback)[:200]}",
        )

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    usage = d.get("usageMetadata") or {}

    return {
        "provider": "gemini",
        "model": GEMINI_MODEL,
        "text": text,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="LLM Gateway — Gemini")


class ChatRequest(BaseModel):
    messages: list[dict]
    max_tokens: int = 2048
    temperature: float = 0.7
    provider: str | None = None   # accepted but ignored — always Gemini
    stream: bool = False


@app.post("/v1/chat")
async def chat(req: ChatRequest):
    try:
        return await call_gemini(req.messages, req.max_tokens, req.temperature)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Gateway internal error: {exc}") from exc


@app.get("/v1/providers")
async def providers():
    return {
        "providers": ["gemini"],
        "model": GEMINI_MODEL,
        "status": "ok",
    }


if __name__ == "__main__":
    print(f"Starting LLM Gateway (Gemini only) on port {PORT}")
    print(f"Model: {GEMINI_MODEL}")
    print(f"API key: {'set' if GEMINI_API_KEY else 'MISSING — set GEMINI_API_KEY in .env'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)