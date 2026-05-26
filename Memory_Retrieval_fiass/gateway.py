"""
LLM Gateway V3 client.

Handles:
  - provider / auto_route selection
  - response_format via prompt-level JSON schema injection + parse + retry
  - system prompt embedding into the messages list (gateway-version-agnostic)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel

GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://localhost:8101")
GATEWAY_V7_URL = os.getenv("LLM_GATEWAY_V7_URL", "http://localhost:8107")

T = TypeVar("T", bound=BaseModel)

# auto_route → default provider when no explicit provider is given
_AUTO_ROUTE_PROVIDER: dict[str, str | None] = {
    "perception": "g",
    "memory": "g",
    "decision": None,
}


def _resolve_provider(provider: str | None, auto_route: str | None) -> str | None:
    if provider:
        return provider
    if auto_route:
        return _AUTO_ROUTE_PROVIDER.get(auto_route)
    return None


def chat(
    messages: list[dict],
    *,
    system: str | None = None,
    provider: str | None = None,
    auto_route: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    timeout: float = 180,
) -> str:
    resolved = _resolve_provider(provider, auto_route)

    # Embed system prompt as the first message so it works with any gateway version
    final_messages: list[dict] = []
    if system:
        final_messages.append({"role": "system", "content": system})
    final_messages.extend(messages)

    body: dict = {
        "messages": final_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if resolved:
        body["provider"] = resolved

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            r = httpx.post(f"{GATEWAY_URL}/v1/chat", json=body, timeout=timeout)
            if r.status_code >= 500 and attempt == 0:
                time.sleep(0.5)
                continue
            r.raise_for_status()
            return r.json()["text"]
        except Exception as exc:
            last_err = exc
            if attempt == 0:
                ensure_gateway()
                time.sleep(0.5)
                continue
            break
    raise RuntimeError(f"Gateway chat failed after retry: {last_err}")


def chat_structured(
    messages: list[dict],
    schema: Type[T],
    *,
    system: str | None = None,
    provider: str | None = None,
    auto_route: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 180,
    retries: int = 3,
) -> T:
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    schema_instruction = (
        "\n\nYou MUST respond with ONLY valid JSON that exactly matches this schema. "
        "No markdown fences, no explanation, no extra keys — raw JSON only:\n\n"
        f"{schema_json}"
    )
    full_system = ((system or "") + schema_instruction).strip()

    current_messages = list(messages)
    last_exc: Exception = RuntimeError("no attempts made")

    for attempt in range(retries):
        raw = chat(
            current_messages,
            system=full_system,
            provider=provider,
            auto_route=auto_route,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        try:
            text = _strip_fences(raw)
            parsed = json.loads(text)
            return schema.model_validate(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                current_messages = current_messages + [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            f"That was not valid JSON (error: {exc}). "
                            "Respond with ONLY raw JSON — no markdown, no explanation."
                        ),
                    },
                ]

    raise ValueError(
        f"Structured output failed after {retries} attempts. "
        f"Last error: {last_exc}. Last response: {raw[:400]}"
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def ensure_gateway() -> None:
    try:
        r = httpx.get(f"{GATEWAY_URL}/v1/providers", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        base_dir = Path(__file__).parent
        server_script = base_dir / "llm_gateway" / "server.py"
        if not server_script.exists():
            raise RuntimeError(
                f"LLM Gateway not reachable at {GATEWAY_URL}. "
                f"Start the gateway before running the agent.\nError: {exc}"
            ) from exc

        uv_cmd = shutil.which("uv")
        if uv_cmd:
            cmd = [uv_cmd, "run", "llm_gateway/server.py"]
            cwd = str(base_dir)
        else:
            cmd = [sys.executable, str(server_script)]
            cwd = str(base_dir)

        subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(15):
            time.sleep(1)
            try:
                rr = httpx.get(f"{GATEWAY_URL}/v1/providers", timeout=3)
                rr.raise_for_status()
                return
            except Exception:
                continue

        raise RuntimeError(
            f"LLM Gateway not reachable at {GATEWAY_URL} after auto-start attempt. "
            f"Last error: {exc}"
        ) from exc


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Embed via Ollama nomic-embed-text directly (no gateway proxy needed)."""
    start = time.time()
    for endpoint, payload in (
        (f"{OLLAMA_BASE_URL}/api/embed", {"model": OLLAMA_EMBED_MODEL, "input": text}),
        (f"{OLLAMA_BASE_URL}/api/embeddings", {"model": OLLAMA_EMBED_MODEL, "prompt": text}),
    ):
        try:
            r = httpx.post(endpoint, json=payload, timeout=30.0)
            r.raise_for_status()
            data = r.json()
            embeddings = data.get("embeddings") or data.get("embedding")
            if isinstance(embeddings, list) and embeddings:
                vec = embeddings[0] if isinstance(embeddings[0], list) else embeddings
                return {
                    "embedding": vec,
                    "dim": len(vec),
                    "model": OLLAMA_EMBED_MODEL,
                    "provider": "ollama",
                    "latency_ms": (time.time() - start) * 1000,
                    "task_type": task_type,
                }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                continue
            raise
    raise RuntimeError(f"Ollama embedding failed for model {OLLAMA_EMBED_MODEL!r}")
