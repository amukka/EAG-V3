"""
Action role — pure MCP dispatch, no LLM calls.

Large results (fetch_url and anything over ARTIFACT_THRESHOLD bytes) are pushed
to the artifact store. The loop receives a short descriptor and an optional
artifact_id; Decision never loads raw bytes directly from Action.
"""
from __future__ import annotations

import json

import artifacts as artifact_store
from schemas import ToolCall


def _trim_wttr(raw: str) -> str:
    """Reduce a 45 KB wttr.in JSON to a ~500-char forecast summary."""
    try:
        # raw is the fetch_url wrapper dict; the actual wttr JSON is in raw["text"]
        outer = json.loads(raw)
        data = json.loads(outer["text"])
        lines = []
        current = data.get("current_condition", [{}])[0]
        lines.append(
            f"Current: {current.get('weatherDesc', [{}])[0].get('value', '?')}, "
            f"{current.get('temp_C', '?')}°C / {current.get('temp_F', '?')}°F, "
            f"humidity {current.get('humidity', '?')}%"
        )
        for day in data.get("weather", []):
            date = day.get("date", "?")
            desc = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "?")
            max_c = day.get("maxtempC", "?")
            min_c = day.get("mintempC", "?")
            lines.append(f"{date}: {desc}, {min_c}–{max_c}°C")
        return "\n".join(lines)
    except Exception:
        return raw[:2_000]

# Tools whose output is always stored as an artifact (pages can be 250 KB+)
_ALWAYS_ARTIFACT = {"fetch_url"}
_ARTIFACT_THRESHOLD = 2_000   # chars — inline in history if smaller


class Action:
    async def execute(
        self,
        session,
        tool_call: ToolCall,
    ) -> tuple[str, str | None]:
        """
        Returns (descriptor, artifact_id | None).
        descriptor is a short human-readable summary (≤300 chars) safe to embed in history.
        artifact_id is set when the result was stored in the artifact store.
        """
        try:
            result = await session.call_tool(
                tool_call.name, arguments=tool_call.arguments
            )
        except Exception as exc:
            return f"Error calling {tool_call.name}: {exc}"[:300], None

        # MCP returns a list of content items; pull the first text block
        content_items = getattr(result, "content", [])
        if content_items:
            first = content_items[0]
            raw = getattr(first, "text", None) or str(first)
        else:
            raw = str(result)

        should_store = (
            tool_call.name in _ALWAYS_ARTIFACT or len(raw) > _ARTIFACT_THRESHOLD
        )

        if should_store:
            arg_preview = ", ".join(
                f"{k}={str(v)[:40]}" for k, v in list(tool_call.arguments.items())[:1]
            )
            descriptor_short = f"{tool_call.name}({arg_preview})"
            # Trim wttr.in JSON to just the 3-day forecast summary (~500 chars)
            if "wttr.in" in str(tool_call.arguments):
                content_to_store = _trim_wttr(raw)
            elif len(raw) > 20_000:
                content_to_store = raw[:20_000] + f"\n...[truncated — total {len(raw):,} chars]"
            else:
                content_to_store = raw
            art_id = artifact_store.store(
                content_to_store.encode("utf-8"),
                content_type="text/markdown",
                source=tool_call.name,
                descriptor=descriptor_short,
            )
            size_str = (
                f"{len(raw):,} chars" if len(raw) < 1_000_000 else f"{len(raw) / 1_048_576:.1f} MB"
            )
            return f"{descriptor_short} → {size_str} stored as {art_id}", art_id

        return raw[:2_000], None