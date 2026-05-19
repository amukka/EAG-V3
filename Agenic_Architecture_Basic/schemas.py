"""
Typed contracts shared across all four cognitive roles.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────────────────
# Durable Memory
# ──────────────────────────────────────────────────────────────────────────────

class MemoryItem(BaseModel):

    id: str

    kind: Literal[
        "fact",
        "preference",
        "tool_outcome",
        "scratchpad",
    ]

    keywords: list[str]

    # Short human-readable summary
    descriptor: str

    # Structured payload
    value: dict

    # Optional artifact handle
    artifact_id: str | None

    source: str

    run_id: str

    goal_id: str | None

    confidence: float

    created_at: datetime


class Artifact(BaseModel):

    # Example:
    #     art:12
    id: str

    content_type: str

    size_bytes: int

    source: str

    descriptor: str


# ──────────────────────────────────────────────────────────────────────────────
# Perception Output
# ──────────────────────────────────────────────────────────────────────────────

class GoalDraft(BaseModel):
    """
    Output emitted by the Perception LLM.

    Important:
        - no stable id
        - uses artifact_index only
    """

    text: str

    done: bool

    artifact_index: int | None = None


class PerceptionOutput(BaseModel):

    goals: list[GoalDraft]


# ──────────────────────────────────────────────────────────────────────────────
# Stable Runtime Goal
# ──────────────────────────────────────────────────────────────────────────────

class Goal(BaseModel):

    id: str

    text: str

    done: bool

    attach_artifact_id: str | None = None


class Observation(BaseModel):

    goals: list[Goal]

    @property
    def all_done(self) -> bool:
        """
        True if all goals are completed.
        """

        return (
            bool(self.goals)
            and all(g.done for g in self.goals)
        )

    def next_unfinished(
        self,
    ) -> Goal | None:
        """
        Return the first unfinished goal.
        """

        return next(
            (
                g
                for g in self.goals
                if not g.done
            ),
            None,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Decision Output
# ──────────────────────────────────────────────────────────────────────────────

class ToolCall(BaseModel):

    name: str

    arguments: dict


class DecisionOutput(BaseModel):

    answer: str | None = None

    tool_call: ToolCall | None = None

    @property
    def is_answer(self) -> bool:
        """
        True when the Decision role
        produced a final answer.
        """

        return self.answer is not None


# ──────────────────────────────────────────────────────────────────────────────
# Memory Classification
# ──────────────────────────────────────────────────────────────────────────────

class MemoryClassification(BaseModel):

    kind: Literal[
        "fact",
        "preference",
        "tool_outcome",
        "scratchpad",
    ]

    keywords: list[str]

    descriptor: str

    value: dict

    confidence: float


# ──────────────────────────────────────────────────────────────────────────────
# Relevance Ranking
# ──────────────────────────────────────────────────────────────────────────────

class RelevanceResult(BaseModel):

    indices: list[int]