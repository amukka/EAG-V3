"""Self-contained LLM gateway for Memory_Retrieval_fiass.

No external gateway process required. Talks directly to:
  - Primary:    Ollama (gemma3:27b) via /api/chat
  - Fallback 1: NVIDIA API (OpenAI-compatible)
  - Fallback 2: Groq API (OpenAI-compatible)

Embedding via Ollama nomic-embed-text at /api/embed (768-dim).

Every layer in this agent imports from here so the boot logic lives in
one place. The `LLM` class and `embed()` function are the only exports
other layers need.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── Configuration ───────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Provider ordering for auto-fallback
_PROVIDERS = ["ollama", "nvidia", "groq"]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ollama_available() -> bool:
    """Check if Ollama is reachable."""
    try:
        httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        return True
    except Exception:
        return False


def _build_openai_messages(
    prompt: str,
    system: str | None = None,
) -> list[dict]:
    """Build OpenAI-format messages array."""
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


def _build_openai_tools(tools: list[dict] | None) -> list[dict] | None:
    """Convert our internal tool format to OpenAI function-calling format."""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _extract_json_from_text(text: str) -> dict | None:
    """Try to extract a JSON object from LLM text output."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try to find JSON in code blocks
    patterns = [
        r"```json\s*\n?(.*?)\n?\s*```",
        r"```\s*\n?(.*?)\n?\s*```",
        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if "```" in pattern else match.group(0))
            except (json.JSONDecodeError, IndexError):
                continue
    return None


# ── LLM Class ───────────────────────────────────────────────────────────────

class LLM:
    """Unified LLM interface with auto-fallback across providers.

    Supports chat completion with optional tool calling.
    Routes: ollama → nvidia → groq with automatic failover.
    """

    def __init__(self):
        self._client = httpx.Client(timeout=120.0)

    def chat(
        self,
        prompt: str,
        system: str | None = None,
        *,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        auto_route: str = "default",
        provider: str | None = None,
        response_format: dict | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        cache_system: bool = False,
    ) -> dict:
        """Send a chat completion request with auto-fallback.

        Returns dict with keys:
          - text: str | None (plain text response)
          - parsed: dict | None (if response_format was JSON)
          - tool_calls: list[dict] | None (if tools were used)
          - provider: str (which provider served the request)
          - model: str
          - latency_ms: float
        """
        providers = _PROVIDERS if provider is None else self._resolve_provider(provider)
        last_error = None

        for prov in providers:
            try:
                start = time.time()
                result = self._call_provider(
                    prov, prompt, system,
                    tools=tools, tool_choice=tool_choice,
                    response_format=response_format,
                    temperature=temperature, max_tokens=max_tokens,
                )
                latency = (time.time() - start) * 1000
                result["provider"] = prov
                result["latency_ms"] = latency
                result["auto_route"] = auto_route
                return result
            except Exception as e:
                last_error = e
                print(f"[gateway] {prov} failed for {auto_route}: {e!r}")
                continue

        raise RuntimeError(
            f"All providers failed for {auto_route}. Last error: {last_error!r}"
        )

    def embed(self, text: str, task_type: str = "retrieval_document") -> dict:
        """Compute an embedding via Ollama nomic-embed-text.

        Returns dict: {embedding, dim, model, provider, latency_ms}
        """
        start = time.time()
        try:
            resp = self._client.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={
                    "model": OLLAMA_EMBED_MODEL,
                    "input": text,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns {"embeddings": [[...]]} for /api/embed
            embeddings = data.get("embeddings") or data.get("embedding")
            if isinstance(embeddings, list) and len(embeddings) > 0:
                if isinstance(embeddings[0], list):
                    embedding = embeddings[0]
                else:
                    embedding = embeddings
            else:
                raise ValueError(f"Unexpected embedding response: {data}")

            latency = (time.time() - start) * 1000
            return {
                "embedding": embedding,
                "dim": len(embedding),
                "model": OLLAMA_EMBED_MODEL,
                "provider": "ollama",
                "latency_ms": latency,
                "task_type": task_type,
            }
        except Exception as e:
            raise RuntimeError(f"Embedding failed: {e!r}") from e

    # ── Provider implementations ────────────────────────────────────────────

    def _resolve_provider(self, shortcut: str) -> list[str]:
        """Map a short provider hint to the fallback chain."""
        mapping = {
            "o": ["ollama", "nvidia", "groq"],
            "ollama": ["ollama", "nvidia", "groq"],
            "n": ["nvidia", "groq", "ollama"],
            "nvidia": ["nvidia", "groq", "ollama"],
            "g": ["groq", "nvidia", "ollama"],
            "groq": ["groq", "nvidia", "ollama"],
        }
        return mapping.get(shortcut, _PROVIDERS)

    def _call_provider(
        self,
        provider: str,
        prompt: str,
        system: str | None,
        *,
        tools: list[dict] | None,
        tool_choice: str | None,
        response_format: dict | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        if provider == "ollama":
            return self._call_ollama(
                prompt, system, tools=tools, tool_choice=tool_choice,
                response_format=response_format, temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "nvidia":
            return self._call_openai_compat(
                NVIDIA_BASE_URL, NVIDIA_API_KEY, NVIDIA_MODEL,
                prompt, system, tools=tools, tool_choice=tool_choice,
                response_format=response_format, temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "groq":
            return self._call_openai_compat(
                GROQ_BASE_URL, GROQ_API_KEY, GROQ_MODEL,
                prompt, system, tools=tools, tool_choice=tool_choice,
                response_format=response_format, temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _call_ollama(
        self,
        prompt: str,
        system: str | None,
        *,
        tools: list[dict] | None,
        tool_choice: str | None,
        response_format: dict | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Call Ollama /api/chat endpoint."""
        messages = _build_openai_messages(prompt, system)

        body: dict[str, Any] = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        # Add tools if provided
        if tools:
            body["tools"] = _build_openai_tools(tools)

        # Add format for JSON response
        if response_format and response_format.get("type") in ("json_schema", "json_object"):
            body["format"] = "json"

        resp = self._client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=body,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})
        text = msg.get("content", "")
        tool_calls_raw = msg.get("tool_calls") or []

        # Parse tool calls
        tool_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            tool_calls.append({
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", {}),
            })

        # Parse JSON if requested
        parsed = None
        if response_format and text:
            parsed = _extract_json_from_text(text)

        return {
            "text": text if not tool_calls else None,
            "parsed": parsed,
            "tool_calls": tool_calls if tool_calls else None,
            "model": OLLAMA_MODEL,
        }

    def _call_openai_compat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
        system: str | None,
        *,
        tools: list[dict] | None,
        tool_choice: str | None,
        response_format: dict | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Call an OpenAI-compatible API (NVIDIA, Groq)."""
        if not api_key or api_key.startswith("your_"):
            raise RuntimeError(f"No valid API key configured for {base_url}")

        messages = _build_openai_messages(prompt, system)

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = _build_openai_tools(tools)
            if tool_choice:
                body["tool_choice"] = tool_choice

        if response_format:
            fmt_type = response_format.get("type", "")
            if fmt_type == "json_schema":
                body["response_format"] = {"type": "json_object"}
            elif fmt_type == "json_object":
                body["response_format"] = {"type": "json_object"}

        resp = self._client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        text = msg.get("content", "")
        tool_calls_raw = msg.get("tool_calls") or []

        # Parse tool calls
        tool_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({
                "name": fn.get("name", ""),
                "arguments": args,
            })

        # Parse JSON if requested
        parsed = None
        if response_format and text:
            parsed = _extract_json_from_text(text)

        return {
            "text": text if not tool_calls else None,
            "parsed": parsed,
            "tool_calls": tool_calls if tool_calls else None,
            "model": model,
        }


# ── Module-level helpers ────────────────────────────────────────────────────

def ensure_gateway() -> None:
    """Verify that at least one LLM provider is available. Idempotent."""
    if _ollama_available():
        return
    if NVIDIA_API_KEY and not NVIDIA_API_KEY.startswith("your_"):
        return
    if GROQ_API_KEY and not GROQ_API_KEY.startswith("your_"):
        return
    print("[gateway] WARNING: No LLM provider appears available. "
          "Start Ollama or configure NVIDIA/Groq API keys in .env")


def embed(text: str, task_type: str = "retrieval_document") -> dict:
    """Module-level embedding helper. Delegates to LLM().embed()."""
    return LLM().embed(text, task_type=task_type)


__all__ = ["ensure_gateway", "LLM", "embed"]
