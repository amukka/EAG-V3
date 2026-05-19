"""
LLM Gateway V3 client.

Optimized for:
- Ollama
- qwen2.5
- llama3.1
- local structured JSON agents

Features:
- provider / auto_route selection
- structured JSON parsing
- retry handling
- fence stripping
- control character fixing
- better Ollama debugging
"""

from __future__ import annotations

import json
import os
import re
from typing import Type
from typing import TypeVar

import httpx
from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

GATEWAY_URL = os.getenv(
    "LLM_GATEWAY_URL",
    "http://localhost:8101",
)

T = TypeVar("T", bound=BaseModel)


# ──────────────────────────────────────────────────────────────────────────────
# Auto routing
# ──────────────────────────────────────────────────────────────────────────────

# provider values are ignored by Ollama gateway
_AUTO_ROUTE_PROVIDER: dict[str, str | None] = {
    "perception": "g",
    "memory": "g",
    "decision": None,
}


def _resolve_provider(
    provider: str | None,
    auto_route: str | None,
) -> str | None:

    if provider:
        return provider

    if auto_route:
        return _AUTO_ROUTE_PROVIDER.get(auto_route)

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Raw chat
# ──────────────────────────────────────────────────────────────────────────────

def chat(
    messages: list[dict],
    *,
    system: str | None = None,
    provider: str | None = None,
    auto_route: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.2,
    timeout: float = 300,
) -> str:

    resolved = _resolve_provider(
        provider,
        auto_route,
    )

    # embed system prompt as first message
    final_messages: list[dict] = []

    if system:
        final_messages.append(
            {
                "role": "system",
                "content": system,
            }
        )

    final_messages.extend(messages)

    body: dict = {
        "messages": final_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    if resolved:
        body["provider"] = resolved

    try:
        r = httpx.post(
            f"{GATEWAY_URL}/v1/chat",
            json=body,
            timeout=timeout,
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gateway request failed:\n{exc}"
        ) from exc

    # better debugging
    if r.status_code != 200:
        print("\n" + "=" * 80)
        print("GATEWAY ERROR")
        print("=" * 80)
        print(r.text[:4000])
        print("=" * 80 + "\n")

    r.raise_for_status()

    data = r.json()

    if "text" not in data:
        raise ValueError(
            f"Gateway response missing 'text': {data}"
        )

    return data["text"]


# ──────────────────────────────────────────────────────────────────────────────
# Structured chat
# ──────────────────────────────────────────────────────────────────────────────

def chat_structured(
    messages: list[dict],
    schema: Type[T],
    *,
    system: str | None = None,
    provider: str | None = None,
    auto_route: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 512,
    timeout: float = 300,
    retries: int = 2,
) -> T:

    # smaller schema formatting for local models
    schema_json = json.dumps(
        schema.model_json_schema(),
        separators=(",", ":"),
    )

    schema_instruction = (
        "\n\n"
        "Respond ONLY with valid JSON.\n"
        "No markdown.\n"
        "No explanation.\n"
        "Schema:\n"
        f"{schema_json}"
    )

    full_system = (
        ((system or "") + schema_instruction)
        .strip()
    )

    current_messages = list(messages)

    last_exc: Exception = RuntimeError(
        "No attempts made"
    )

    raw = ""

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
            cleaned = _fix_control_chars(
                _strip_fences(raw)
            )

            parsed = json.loads(cleaned)

            return schema.model_validate(parsed)

        except Exception as exc:

            last_exc = exc

            # retry correction
            if attempt < retries - 1:

                current_messages = (
                    current_messages
                    + [
                        {
                            "role": "assistant",
                            "content": raw,
                        },
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was invalid JSON.\n"
                                "Respond ONLY with valid JSON."
                            ),
                        },
                    ]
                )

    raise ValueError(
        "Structured output failed.\n\n"
        f"Last error:\n{last_exc}\n\n"
        f"Last response:\n{raw[:2000]}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fix_control_chars(text: str) -> str:
    """
    Fix invalid control chars inside JSON strings.

    Local models sometimes emit:
    - raw newlines
    - tabs
    - broken escape sequences
    """

    result: list[str] = []

    in_string = False
    i = 0

    while i < len(text):

        c = text[i]

        # escaped char
        if c == "\\" and in_string:

            result.append(c)

            if i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                i += 1

            continue

        # quote
        if c == '"':

            in_string = not in_string
            result.append(c)

        # inside JSON string
        elif in_string:

            if c == "\n":
                result.append("\\n")

            elif c == "\r":
                result.append("\\r")

            elif c == "\t":
                result.append("\\t")

            elif ord(c) < 0x20:
                result.append(
                    f"\\u{ord(c):04x}"
                )

            else:
                result.append(c)

        else:
            result.append(c)

        i += 1

    return "".join(result)


def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences.
    """

    text = text.strip()

    m = re.match(
        r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
        text,
        re.DOTALL,
    )

    if m:
        return m.group(1).strip()

    return text


# ──────────────────────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────────────────────

def ensure_gateway() -> None:

    try:
        r = httpx.get(
            f"{GATEWAY_URL}/v1/providers",
            timeout=5,
        )

        r.raise_for_status()

    except Exception as exc:

        raise RuntimeError(
            f"LLM Gateway not reachable at "
            f"{GATEWAY_URL}\n\n"
            f"Start the gateway first.\n\n"
            f"Error:\n{exc}"
        ) from exc