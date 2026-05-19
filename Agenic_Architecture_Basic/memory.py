"""
Memory service.

Provides typed storage for:

    - facts
    - preferences
    - tool outcomes
    - scratchpad memory

Persistence:
    state/memory.json

Read path:
    - pure keyword search
    - zero LLM cost

Write path:
    - remember() uses one LLM call
    - record_outcome() uses no LLM call
"""

from __future__ import annotations

import json
import re
import uuid

from datetime import datetime, timezone
from pathlib import Path

import gateway

from schemas import (
    MemoryClassification,
    MemoryItem,
    RelevanceResult,
    ToolCall,
)


# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

_STATE_DIR = (
    Path(__file__).parent
    / "state"
)

_MEMORY_PATH = (
    _STATE_DIR
    / "memory.json"
)


# ──────────────────────────────────────────────────────────────────────────────
# Stopwords
# ──────────────────────────────────────────────────────────────────────────────

_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "into",
    "through",
    "and",
    "or",
    "but",
    "not",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "my",
    "your",
    "his",
    "her",
    "our",
    "their",
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "what",
    "who",
    "how",
    "when",
    "where",
    "why",
    "which",
    "me",
    "him",
    "us",
    "them",
    "so",
    "if",
    "then",
    "than",
    "as",
    "up",
}


# ──────────────────────────────────────────────────────────────────────────────
# Tokenization
# ──────────────────────────────────────────────────────────────────────────────

def _tokenize(
    text: str,
) -> set[str]:
    """
    Convert text into searchable keyword tokens.
    """

    tokens = re.findall(
        r"\b\w+\b",
        text.lower(),
    )

    return {
        token
        for token in tokens
        if (
            token not in _STOPWORDS
            and len(token) > 1
        )
    }


# ──────────────────────────────────────────────────────────────────────────────
# Memory Service
# ──────────────────────────────────────────────────────────────────────────────

class Memory:

    def __init__(self) -> None:

        _STATE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._items: list[MemoryItem] = (
            self._load()
        )

    # ──────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────

    def _load(
        self,
    ) -> list[MemoryItem]:
        """
        Load memory items from disk.
        """

        if not _MEMORY_PATH.exists():
            return []

        raw = json.loads(
            _MEMORY_PATH.read_text(
                encoding="utf-8"
            )
        )

        return [
            MemoryItem.model_validate(item)
            for item in raw
        ]

    def _save(self) -> None:
        """
        Persist memory items to disk.
        """

        _MEMORY_PATH.write_text(
            json.dumps(
                [
                    item.model_dump(
                        mode="json"
                    )
                    for item in self._items
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

    # ──────────────────────────────────────────
    # Reads (No LLM Cost)
    # ──────────────────────────────────────────

    def read(
        self,
        query: str,
        history: list[dict],
        kinds: list[str] | None = None,
        top_k: int = 8,
    ) -> list[MemoryItem]:
        """
        Keyword-overlap search.

        Runs every iteration at zero LLM cost.
        """

        history_text = " ".join(
            (
                str(e.get("text", ""))
                + " "
                + str(e.get("tool", ""))
                + " "
                + str(e.get("arguments", ""))
            )
            for e in history[-5:]
        )

        query_tokens = _tokenize(
            query + " " + history_text
        )

        candidates = self._items

        if kinds:

            candidates = [
                item
                for item in candidates
                if item.kind in kinds
            ]

        scored: list[
            tuple[int, MemoryItem]
        ] = []

        for item in candidates:

            item_tokens = (
                set(item.keywords)
                | _tokenize(item.descriptor)
            )

            score = len(
                query_tokens & item_tokens
            )

            if score > 0:
                scored.append(
                    (score, item)
                )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        hits = [
            item
            for _, item in scored[:top_k]
        ]

        # Remove stale artifact references

        import artifacts as _art_store

        valid: list[MemoryItem] = []

        for item in hits:

            if (
                item.artifact_id
                and not _art_store.exists(
                    item.artifact_id
                )
            ):
                continue

            valid.append(item)

        return valid

    def filter(
        self,
        kinds: list[str] | None = None,
        goal_id: str | None = None,
        recent: int | None = None,
    ) -> list[MemoryItem]:
        """
        Structured filtering.
        No LLM cost.
        """

        results = list(self._items)

        if kinds:

            results = [
                item
                for item in results
                if item.kind in kinds
            ]

        if goal_id:

            results = [
                item
                for item in results
                if item.goal_id == goal_id
            ]

        if recent is not None:
            results = results[-recent:]

        return results

    def relevant(
        self,
        query: str,
        kinds: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        """
        LLM-scored relevance ranking.

        Used only when keyword recall is weak.
        """

        candidates = self.filter(
            kinds=kinds
        )

        if not candidates:
            return []

        candidates_text = "\n".join(
            (
                f"{i}: "
                f"{item.descriptor} "
                f"(kind={item.kind})"
            )
            for i, item in enumerate(candidates)
        )

        result = gateway.chat_structured(
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Query: {query}\n\n"
                        f"Memory items:\n"
                        f"{candidates_text}\n\n"
                        f"Return the indices "
                        f"(0-based) of the "
                        f"{top_k} most relevant items."
                    ),
                }
            ],
            schema=RelevanceResult,
            provider="g",
            auto_route="memory",
            temperature=0.3,
        )

        indices = [
            i
            for i in result.indices
            if 0 <= i < len(candidates)
        ][:top_k]

        return [
            candidates[i]
            for i in indices
        ]

    # ──────────────────────────────────────────
    # Writes
    # ──────────────────────────────────────────

    def remember(
        self,
        raw_text: str,
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        """
        Classify free-form text into MemoryItem.

        Uses one LLM call.
        """

        classification = gateway.chat_structured(
            messages=[
                {
                    "role": "user",
                    "content":
                        (
                            "Classify and extract "
                            "this memory item:\n\n"
                            f"{raw_text}"
                        ),
                }
            ],
            schema=MemoryClassification,
            system=(
                "You classify text into "
                "structured memory items "
                "for an AI agent.\n\n"
                "Extract key facts and "
                "preferences.\n\n"
                "Generate keywords useful "
                "for future search."
            ),
            provider="g",
            auto_route="memory",
            temperature=0.3,
        )

        item = MemoryItem(
            id=f"mem:{uuid.uuid4().hex[:8]}",
            kind=classification.kind,
            keywords=classification.keywords,
            descriptor=classification.descriptor,
            value=classification.value,
            artifact_id=None,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=classification.confidence,
            created_at=datetime.now(
                timezone.utc
            ),
        )

        self._items.append(item)

        self._save()

        return item

    def record_outcome(
        self,
        tool_call: ToolCall,
        result_text: str,
        artifact_id: str | None,
        run_id: str,
        goal_id: str | None,
    ) -> MemoryItem:
        """
        Record MCP tool execution.

        No LLM cost.
        """

        arg_tokens = " ".join(
            str(v)
            for v in tool_call.arguments.values()
        )

        keywords = list(
            _tokenize(
                tool_call.name
                + " "
                + arg_tokens
            )
        )[:10]

        arg_preview = ", ".join(
            (
                f"{k}={str(v)[:30]}"
            )
            for k, v in list(
                tool_call.arguments.items()
            )[:2]
        )

        item = MemoryItem(
            id=f"mem:{uuid.uuid4().hex[:8]}",
            kind="tool_outcome",
            keywords=keywords,
            descriptor=(
                f"{tool_call.name}"
                f"({arg_preview}) "
                f"→ {result_text[:80]}"
            ),
            value={
                "tool": tool_call.name,
                "arguments":
                    tool_call.arguments,
                "result_preview":
                    result_text[:500],
            },
            artifact_id=artifact_id,
            source="action",
            run_id=run_id,
            goal_id=goal_id,
            confidence=1.0,
            created_at=datetime.now(
                timezone.utc
            ),
        )

        self._items.append(item)

        self._save()

        return item