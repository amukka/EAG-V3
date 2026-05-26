
"""Typed contracts shared across all four cognitive roles."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ── Durable memory ────────────────────────────────────────────────────────────

class MemoryItem(BaseModel):
    id: str
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str            # one short human-readable line
    value: dict                # structured payload
    artifact_id: str | None    # handle into the artifact store
    embedding: list[float] | None = None
    source: str
    run_id: str
    goal_id: str | None
    confidence: float
    created_at: datetime


class Artifact(BaseModel):
    id: str                    # "art:<sha256-prefix>"
    content_type: str
    size_bytes: int
    source: str
    descriptor: str


# ── Perception output ─────────────────────────────────────────────────────────

class GoalDraft(BaseModel):
    """What the Perception LLM emits — no id, uses artifact_index."""
    text: str
    done: bool
    artifact_index: int | None = None


class PerceptionOutput(BaseModel):
    goals: list[GoalDraft]


# ── Loop-level goal (with stable id owned by the loop) ───────────────────────

class Goal(BaseModel):
    id: str
    text: str
    done: bool
    attach_artifact_id: str | None = None


class Observation(BaseModel):
    goals: list[Goal]

    @property
    def all_done(self) -> bool:
        return bool(self.goals) and all(g.done for g in self.goals)

    def next_unfinished(self) -> Goal | None:
        return next((g for g in self.goals if not g.done), None)


# ── Decision output ───────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    name: str
    arguments: dict


class DecisionOutput(BaseModel):
    answer: str | None = None
    tool_call: ToolCall | None = None

    @property
    def is_answer(self) -> bool:
        return self.answer is not None


# ── Memory classification (LLM output for remember()) ────────────────────────

class MemoryClassification(BaseModel):
    kind: Literal["fact", "preference", "tool_outcome", "scratchpad"]
    keywords: list[str]
    descriptor: str
    value: dict
    confidence: float


# ── Relevance ranking (LLM output for memory.relevant()) ─────────────────────

class RelevanceResult(BaseModel):
    indices: list[int]