"""
Validates Perception and Decision prompts against the Session 5
PROMPT_EVALUATOR_SYSTEM_PROMPT criteria.

Run:
    uv run validate_prompts.py

Compares the evaluator's output against the PoP claims in the README.
Exits with code 1 if any criterion that the PoP claims is True
evaluates False.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")


import gateway
from perception import _SYSTEM as PERCEPTION_PROMPT
from decision import _SYSTEM as DECISION_PROMPT


# ── Evaluator system prompt (from Session 5) ──────────────────────────────────

_EVALUATOR_SYSTEM = """
You are a Prompt Evaluation Assistant.

You will receive a prompt written by a student.
Your job is to review this prompt and assess how well it supports
structured, step-by-step reasoning in an LLM
(e.g., for math, logic, planning, or tool use).

Evaluate the prompt on the following criteria:

1. Explicit Reasoning Instructions
- Does the prompt tell the model to reason step-by-step?
- Does it include instructions like "explain your thinking"
  or "think before you answer"?

2. Structured Output Format
- Does the prompt enforce a predictable output format
  (e.g., FUNCTION_CALL, JSON, numbered steps)?
- Is the output easy to parse or validate?

3. Separation of Reasoning and Tools
- Are reasoning steps clearly separated from computation
  or tool-use steps?
- Is it clear when to calculate, when to verify, when to reason?

4. Conversation Loop Support
- Could this prompt work in a back-and-forth (multi-turn) setting?
- Is there a way to update the context with results from previous steps?

5. Instructional Framing
- Are there examples of desired behavior or "formats" to follow?
- Does the prompt define exactly how responses should look?

6. Internal Self-Checks
- Does the prompt instruct the model to self-verify
  or sanity-check intermediate steps?

7. Reasoning Type Awareness
- Does the prompt encourage the model to tag or identify
  the type of reasoning used
  (e.g., arithmetic, logic, lookup)?

8. Error Handling or Fallbacks
- Does the prompt specify what to do if an answer is uncertain,
  a tool fails, or the model is unsure?

9. Overall Clarity and Robustness
- Is the prompt easy to follow?
- Is it likely to reduce hallucination and drift?

Respond with a structured review in this exact JSON format:

{
  "explicit_reasoning": true,
  "structured_output": true,
  "tool_separation": true,
  "conversation_loop": true,
  "instructional_framing": true,
  "internal_self_checks": false,
  "reasoning_type_awareness": false,
  "fallbacks": false,
  "overall_clarity":
    "Excellent structure, but could improve with self-checks and error fallbacks."
}

Only return the JSON object.
No extra text before or after.
"""


# ── Pydantic schema for evaluator output ──────────────────────────────────────

class EvalResult(BaseModel):
    explicit_reasoning: bool
    structured_output: bool
    tool_separation: bool
    conversation_loop: bool
    instructional_framing: bool
    internal_self_checks: bool
    reasoning_type_awareness: bool
    fallbacks: bool
    overall_clarity: str


# ── PoP claims (what the README asserts) ──────────────────────────────────────

_POP_CLAIMS: dict[str, dict[str, bool]] = {
    "Perception": {
        "explicit_reasoning": True,
        "structured_output": True,
        "tool_separation": True,
        "conversation_loop": True,
        "instructional_framing": True,
        "internal_self_checks": True,
        "reasoning_type_awareness": True,
        "fallbacks": True,
    },
    "Decision": {
        "explicit_reasoning": True,
        "structured_output": True,
        "tool_separation": True,
        "conversation_loop": True,
        "instructional_framing": True,
        "internal_self_checks": True,
        "reasoning_type_awareness": True,
        "fallbacks": True,
    },
}


# ── Validation logic ──────────────────────────────────────────────────────────

def validate(role: str, prompt: str) -> tuple[EvalResult, list[str]]:
    """
    Returns:
        (eval_result, list_of_failures)
    """

    print(f"\n{'─' * 50}")
    print(f"Evaluating: {role}")
    print(f"{'─' * 50}")

    result = gateway.chat_structured(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        schema=EvalResult,
        system=_EVALUATOR_SYSTEM,
        provider="g",
        temperature=0.3,
    )

    claims = _POP_CLAIMS[role]
    failures: list[str] = []

    for criterion, claimed_value in claims.items():
        actual_value = getattr(result, criterion)

        status = "✅" if actual_value == claimed_value else "❌"

        print(
            f" {status} {criterion}: "
            f"actual={actual_value} claimed={claimed_value}"
        )

        if actual_value != claimed_value:
            failures.append(
                f"{criterion}: "
                f"PoP claims {claimed_value} "
                f"but evaluator returned {actual_value}"
            )

    print(f"\n overall_clarity: {result.overall_clarity}")

    return result, failures


def main() -> None:
    gateway.ensure_gateway()

    all_failures: dict[str, list[str]] = {}

    for role, prompt in [
        ("Perception", PERCEPTION_PROMPT),
        ("Decision", DECISION_PROMPT),
    ]:
        _, failures = validate(role, prompt)

        if failures:
            all_failures[role] = failures

    print(f"\n{'═' * 50}")

    if not all_failures:
        print("✅ All PoP claims validated successfully.")
        sys.exit(0)

    print("❌ Validation failures found:\n")

    for role, failures in all_failures.items():
        print(f" {role}:")

        for failure in failures:
            print(f"   - {failure}")

    print("\nFix the failing criteria in the prompt, then re-run.")
    sys.exit(1)


if __name__ == "__main__":
    main()