"""vector retrieval"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import artifacts as artifact_store
import gateway
from schemas import MemoryClassification, MemoryItem, ToolCall
from vector_index import VectorIndex

_STATE_DIR = Path(__file__).parent / "state"
_MEMORY_PATH = _STATE_DIR / "memory.json"

_EMBEDDABLE_KINDS = {"fact", "preference", "tool_outcome"}
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "into", "through", "and",
    "or", "but", "not", "this", "that", "these", "those", "it", "its",
    "my", "your", "his", "her", "our", "their", "i", "you", "he", "she",
    "we", "they", "what", "who", "how", "when", "where", "why", "which",
    "me", "him", "us", "them", "so", "if", "then", "than", "as", "up",
}


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


class Memory:
    def __init__(self) -> None:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._items: list[MemoryItem] = self._load()
        self._rebuild_vector_index_if_needed()

    def _load(self) -> list[MemoryItem]:
        if not _MEMORY_PATH.exists():
            return []
        raw = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
        return [MemoryItem.model_validate(item) for item in raw]

    def _save(self) -> None:
        _MEMORY_PATH.write_text(
            json.dumps([item.model_dump(mode="json") for item in self._items], indent=2),
            encoding="utf-8",
        )

    def _rebuild_vector_index_if_needed(self) -> None:
        idx = VectorIndex(_STATE_DIR)
        if idx.size > 0:
            return
        for item in self._items:
            if item.embedding is not None:
                idx.add(item.id, item.embedding)
        if idx.size > 0:
            idx.persist()

    def _try_embed(self, text: str, task_type: str) -> list[float] | None:
        try:
            return list(gateway.embed(text, task_type=task_type)["embedding"])
        except Exception:
            return None

    def _vector_read(
        self,
        query: str,
        kinds: list[str] | None = None,
        top_k: int = 8,
    ) -> list[MemoryItem]:
        qvec = self._try_embed(query, task_type="retrieval_query")
        if qvec is None:
            return []
        idx = VectorIndex(_STATE_DIR)
        if idx.size == 0:
            return []
        hits = idx.search(qvec, k=top_k * 2 if kinds else top_k)
        by_id = {item.id: item for item in self._items}
        out: list[MemoryItem] = []
        for item_id, _score in hits:
            item = by_id.get(item_id)
            if not item:
                continue
            if kinds and item.kind not in kinds:
                continue
            if item.artifact_id and not artifact_store.exists(item.artifact_id):
                continue
            out.append(item)
            if len(out) >= top_k:
                break
        return out

    def _keyword_read(
        self,
        query: str,
        history: list[dict],
        kinds: list[str] | None = None,
        top_k: int = 8,
    ) -> list[MemoryItem]:
        history_text = " ".join(
            str(e.get("text", ""))
            + " "
            + str(e.get("tool", ""))
            + " "
            + str(e.get("arguments", ""))
            for e in history[-5:]
        )
        query_tokens = _tokenize(query + " " + history_text)
        candidates = self._items
        if kinds:
            candidates = [item for item in candidates if item.kind in kinds]
        scored: list[tuple[int, MemoryItem]] = []
        for item in candidates:
            item_tokens = set(item.keywords) | _tokenize(item.descriptor)
            score = len(query_tokens & item_tokens)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            item for _, item in scored[:top_k]
            if not item.artifact_id or artifact_store.exists(item.artifact_id)
        ]

    def read(
        self,
        query: str,
        history: list[dict],
        kinds: list[str] | None = None,
        top_k: int = 8,
    ) -> list[MemoryItem]:
        vec_hits = self._vector_read(query, kinds=kinds, top_k=top_k)
        if vec_hits:
            return vec_hits
        return self._keyword_read(query, history, kinds=kinds, top_k=top_k)

    def filter(
        self,
        kinds: list[str] | None = None,
        goal_id: str | None = None,
        recent: int | None = None,
    ) -> list[MemoryItem]:
        results = list(self._items)
        if kinds:
            results = [i for i in results if i.kind in kinds]
        if goal_id:
            results = [i for i in results if i.goal_id == goal_id]
        if recent is not None:
            results = results[-recent:]
        return results

    def relevant(
        self,
        query: str,
        kinds: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        # Kept for compatibility; vector-first read is the primary relevance path.
        return self.read(query, history=[], kinds=kinds, top_k=top_k)

    def _persist_item(self, item: MemoryItem) -> MemoryItem:
        self._items.append(item)
        self._save()
        if item.embedding is not None and item.kind in _EMBEDDABLE_KINDS:
            idx = VectorIndex(_STATE_DIR)
            idx.add(item.id, item.embedding)
            idx.persist()
        return item

    def remember(
        self,
        raw_text: str,
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        classification = gateway.chat_structured(
            messages=[
                {
                    "role": "user",
                    "content": f"Classify and extract this memory item:\n\n{raw_text}",
                }
            ],
            schema=MemoryClassification,
            system=(
                "You classify text into structured memory items for an AI agent. "
                "Extract key facts or preferences and assign keywords that will help "
                "future retrieval find this item."
            ),
            provider="g",
            auto_route="memory",
            temperature=0.3,
        )
        embedding = None
        if classification.kind in _EMBEDDABLE_KINDS:
            embedding = self._try_embed(classification.descriptor, "retrieval_document")
        item = MemoryItem(
            id=f"mem:{uuid.uuid4().hex[:8]}",
            kind=classification.kind,
            keywords=classification.keywords,
            descriptor=classification.descriptor,
            value=classification.value or {"raw": raw_text},
            artifact_id=None,
            embedding=embedding,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=classification.confidence,
            created_at=datetime.now(timezone.utc),
        )
        return self._persist_item(item)

    def record_outcome(
        self,
        tool_call: ToolCall,
        result_text: str,
        artifact_id: str | None,
        run_id: str,
        goal_id: str | None,
    ) -> MemoryItem:
        arg_tokens = " ".join(str(v) for v in tool_call.arguments.values())
        keywords = list(_tokenize(tool_call.name + " " + arg_tokens))[:10]
        arg_preview = ", ".join(
            f"{k}={str(v)[:30]}" for k, v in list(tool_call.arguments.items())[:2]
        )
        descriptor = f"{tool_call.name}({arg_preview}) -> {result_text[:80]}"
        embedding = self._try_embed(descriptor, "retrieval_document")
        item = MemoryItem(
            id=f"mem:{uuid.uuid4().hex[:8]}",
            kind="tool_outcome",
            keywords=keywords,
            descriptor=descriptor,
            value={
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
                "result_preview": result_text[:500],
            },
            artifact_id=artifact_id,
            embedding=embedding,
            source="action",
            run_id=run_id,
            goal_id=goal_id,
            confidence=1.0,
            created_at=datetime.now(timezone.utc),
        )
        return self._persist_item(item)

    def add_fact(
        self,
        descriptor: str,
        *,
        value: dict | None,
        keywords: list[str] | None,
        source: str,
        run_id: str,
        goal_id: str | None = None,
    ) -> MemoryItem:
        embedding = self._try_embed(descriptor, "retrieval_document")
        item = MemoryItem(
            id=f"mem:{uuid.uuid4().hex[:8]}",
            kind="fact",
            keywords=list({k.lower() for k in (keywords or list(_tokenize(descriptor))[:10])}),
            descriptor=descriptor,
            value=value or {},
            artifact_id=None,
            embedding=embedding,
            source=source,
            run_id=run_id,
            goal_id=goal_id,
            confidence=1.0,
            created_at=datetime.now(timezone.utc),
        )
        return self._persist_item(item)
