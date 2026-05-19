"""
Minimal LLM Gateway — Groq
Runs on port 8101

Start:
    python llm_gateway/server.py

Requires:
    GROQ_API_KEY in .env

Optional:
    GROQ_MODEL=qwen-qwq-32b
"""

import asyncio
import re
import os
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# -------------------------------------------------------------------
# Load environment
# -------------------------------------------------------------------

load_dotenv(Path(__file__).parent.parent / ".env")

PORT = int(os.getenv("GATEWAY_PORT", "8101"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "qwen-qwq-32b",
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# -------------------------------------------------------------------
# FastAPI app
# -------------------------------------------------------------------

app = FastAPI(
    title="LLM Gateway - Groq",
)

# -------------------------------------------------------------------
# Request schema
# -------------------------------------------------------------------


class ChatRequest(BaseModel):
    messages: list[dict]
    max_tokens: int = 2048
    temperature: float = 0.7

    # accepted but ignored
    provider: str | None = None

    stream: bool = False


# -------------------------------------------------------------------
# Groq call
# -------------------------------------------------------------------


async def call_groq(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> dict:

    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY missing in .env",
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    retries = 3
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(
                timeout=180,
            ) as client:
                response = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except Exception as exc:
            if attempt == retries - 1:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to reach Groq: {exc}",
                )
            await asyncio.sleep(2 * (attempt + 1))
            continue

        if response.status_code == 429:
            if attempt < retries - 1:
                try:
                    err_msg = response.json().get("error", {}).get("message", "")
                    match = re.search(r"try again in (\d+\.?\d*)s", err_msg)
                    sleep_time = float(match.group(1)) + 0.5 if match else 6.0
                except Exception:
                    sleep_time = 6.0
                print(f"[gateway] Groq 429 Rate Limit. Sleeping for {sleep_time:.2f}s before retry...", flush=True)
                await asyncio.sleep(sleep_time)
                continue

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Groq API error {response.status_code}: "
                    f"{response.text[:500]}"
                ),
            )
        break

    data = response.json()

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception:
        text = ""

    usage = data.get("usage", {})

    return {
        "provider": "groq",
        "model": GROQ_MODEL,
        "text": text,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------


@app.post("/v1/chat")
async def chat(req: ChatRequest):

    return await call_groq(
        messages=req.messages,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )


@app.get("/v1/providers")
async def providers():

    return {
        "providers": ["groq"],
        "model": GROQ_MODEL,
        "status": "ok",
    }


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":

    print(
        f"Starting Groq Gateway "
        f"({GROQ_MODEL}) on port {PORT}"
    )

    if GROQ_API_KEY:
        print("GROQ_API_KEY detected")
    else:
        print("WARNING: GROQ_API_KEY missing")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
    )