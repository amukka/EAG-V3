"""
Action role — pure MCP dispatch, no LLM calls.

Large results (fetch_url and anything over ARTIFACT_THRESHOLD bytes)
are pushed to the artifact store.

The loop receives:
    - short descriptor
    - optional artifact_id

Decision never loads raw bytes directly from Action.
"""

from __future__ import annotations

import json

import artifacts as artifact_store

from schemas import ToolCall


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

# Always store these tool outputs as artifacts
_ALWAYS_ARTIFACT = {
    "fetch_url",
}

# Store any response larger than this
_ARTIFACT_THRESHOLD = 2_000

# Hard truncate giant payloads before storing
_MAX_STORE_SIZE = 20_000


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _trim_wttr(raw: str) -> str:
    """
    Reduce wttr.in JSON payload into a compact weather summary.
    """

    try:
        outer = json.loads(raw)

        # fetch_url wrapper usually stores actual page text in "text"
        payload = outer.get("text", "{}")

        data = json.loads(payload)

        lines: list[str] = []

        current = data.get("current_condition", [{}])[0]

        desc = (
            current.get("weatherDesc", [{}])[0]
            .get("value", "?")
        )

        temp_c = current.get("temp_C", "?")
        temp_f = current.get("temp_F", "?")
        humidity = current.get("humidity", "?")

        lines.append(
            f"Current: {desc}, "
            f"{temp_c}°C / {temp_f}°F, "
            f"humidity {humidity}%"
        )

        for day in data.get("weather", []):
            date = day.get("date", "?")

            hourly = day.get("hourly", [{}])

            weather_desc = (
                hourly[min(4, len(hourly) - 1)]
                .get("weatherDesc", [{}])[0]
                .get("value", "?")
            )

            min_c = day.get("mintempC", "?")
            max_c = day.get("maxtempC", "?")

            lines.append(
                f"{date}: {weather_desc}, "
                f"{min_c}–{max_c}°C"
            )

        return "\n".join(lines)

    except Exception:
        # fallback
        return raw[:2_000]


def _make_descriptor(tool_name: str, arguments: dict) -> str:
    """
    Small human-readable descriptor.
    """

    preview_parts = []

    for k, v in list(arguments.items())[:2]:
        preview_parts.append(f"{k}={str(v)[:40]}")

    preview = ", ".join(preview_parts)

    return f"{tool_name}({preview})"


def _prepare_content(tool_call: ToolCall, raw: str) -> str:
    """
    Prepare content before storing.
    """

    args_text = str(tool_call.arguments)

    # Special handling for wttr.in giant JSON
    if "wttr.in" in args_text:
        return _trim_wttr(raw)

    # Truncate giant payloads
    if len(raw) > _MAX_STORE_SIZE:
        return (
            raw[:_MAX_STORE_SIZE]
            + f"\n...[truncated — total {len(raw):,} chars]"
        )

    return raw


# ──────────────────────────────────────────────────────────────────────────────
# Action Role
# ──────────────────────────────────────────────────────────────────────────────

class Action:

    async def execute(
        self,
        session,
        tool_call: ToolCall,
    ) -> tuple[str, str | None]:
        """
        Execute a single MCP tool call.

        Returns:
            (
                descriptor_or_small_result,
                artifact_id | None
            )
        """

        # ──────────────────────────────────────────────────────────────────
        # Execute MCP tool
        # ──────────────────────────────────────────────────────────────────

        try:
            result = await session.call_tool(
                tool_call.name,
                arguments=tool_call.arguments,
            )

        except Exception as exc:
            return (
                f"Error calling {tool_call.name}: {exc}"[:300],
                None,
            )

        # ──────────────────────────────────────────────────────────────────
        # Extract raw text
        # ──────────────────────────────────────────────────────────────────

        content_items = getattr(result, "content", [])

        if content_items:
            first = content_items[0]

            raw = (
                getattr(first, "text", None)
                or str(first)
            )
        else:
            raw = str(result)

        # ──────────────────────────────────────────────────────────────────
        # Decide whether to store as artifact
        # ──────────────────────────────────────────────────────────────────

        should_store = (
            tool_call.name in _ALWAYS_ARTIFACT
            or len(raw) > _ARTIFACT_THRESHOLD
        )

        # ──────────────────────────────────────────────────────────────────
        # Store large payloads
        # ──────────────────────────────────────────────────────────────────

        if should_store:

            descriptor = _make_descriptor(
                tool_call.name,
                tool_call.arguments,
            )

            content_to_store = _prepare_content(
                tool_call,
                raw,
            )

            artifact_id = artifact_store.store(
                content_to_store.encode("utf-8"),
                content_type="text/markdown",
                source=tool_call.name,
                descriptor=descriptor,
            )

            if len(raw) < 1_000_000:
                size_str = f"{len(raw):,} chars"
            else:
                size_str = f"{len(raw) / 1_048_576:.1f} MB"

            summary = (
                f"{descriptor} → "
                f"{size_str} stored as {artifact_id}"
            )

            return summary, artifact_id

        # ──────────────────────────────────────────────────────────────────
        # Small payload → inline directly
        # ──────────────────────────────────────────────────────────────────

        return raw[:2_000], None