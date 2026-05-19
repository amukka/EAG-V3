"""
Perception role — orchestrates goals and completion tracking.
Compatible with Ollama + Qwen2.5.
"""

from __future__ import annotations

import json
import uuid

import gateway
from schemas import (
    Goal,
    MemoryItem,
    Observation,
    PerceptionOutput,
)

_SYSTEM = """
You are the Perception module in a deterministic goal-tracking system.

You MUST follow rules exactly. No reasoning, no explanations, no self-talk.

──────────────────────────────────────────────
INPUT STRUCTURE
──────────────────────────────────────────────
You receive:
- USER QUERY
- PRIOR GOALS (optional)
- RUN HISTORY (optional)
- MEMORY HITS (optional)

──────────────────────────────────────────────
OUTPUT STRUCTURE (STRICT)
──────────────────────────────────────────────
Return ONLY:

{
  "output_goals": [
    {
      "id": string,
      "goal": string,
      "done": boolean,
      "artifact_index": integer | null
    }
  ]
}

No additional fields allowed.

──────────────────────────────────────────────
RULES
──────────────────────────────────────────────

1. DECOMPOSITION RULE
- If PRIOR GOALS is empty:
  Create 1–4 goals.
- Each goal must be atomic but NOT over-split.
- If multiple facts come from same source → combine into one goal.
- Prefer 2-stage structure: fetch → extract.

2. DONE RULE (deterministic)
A goal is done=true IF AND ONLY IF:

- Fetch goal:
  A matching "action" exists in RUN HISTORY with same URL or source.

- Extract goal:
  A matching "answer" exists in RUN HISTORY that fully satisfies goal.

- Plan goal:
  RUN HISTORY contains "answer" with a concrete plan.

Otherwise done=false.

Once done=true, it must never become false.

3. ARTIFACT RULE
- Only set artifact_index if:
  - goal is not done
  - MEMORY HITS contains a valid integer index
  - AND goal explicitly requires raw fetched content

Otherwise set null.

4. ORDER RULE
- Preserve exact order of PRIOR GOALS
- Do not reorder, remove, or insert goals

5. SELF-CONSISTENCY RULE
- If PRIOR GOALS exist:
  - copy all goals unchanged except updated fields
- Never modify goal text or ids

6. FALLBACK RULE
- If query is unclear → single goal = restated query

──────────────────────────────────────────────
CONSTRAINTS
──────────────────────────────────────────────
- No reasoning text in output
- No extra keys
- No commentary
- Deterministic updates only
"""


class Perception:

    def observe(
        self,
        query: str,
        hits: list[MemoryItem],
        history: list[dict],
        prior_goals: list[Goal],
        run_id: str,
    ) -> Observation:

        artifact_map: dict[int, str] = {}
        art_idx = 0

        hit_lines: list[str] = []

        for i, hit in enumerate(hits):

            line = (
                f"[{i}] {hit.descriptor} "
                f"(kind={hit.kind}, source={hit.source})"
            )

            if hit.artifact_id:
                line += f" [ARTIFACT INDEX={art_idx}]"
                artifact_map[art_idx] = hit.artifact_id
                art_idx += 1

            hit_lines.append(line)

        hits_text = "\n".join(hit_lines) if hit_lines else "(none)"

        history_text = (
            json.dumps(history[-10:], indent=2)
            if history else "[]"
        )

        if prior_goals:
            prior_text = "\n".join(
                f"[{i}] "
                f"{'[DONE]' if g.done else '[OPEN]'} "
                f"{g.text}"
                for i, g in enumerate(prior_goals)
            )
        else:
            prior_text = "(empty)"

        user_msg = f"""
USER QUERY:
{query}

MEMORY HITS:
{hits_text}

RUN HISTORY:
{history_text}

PRIOR GOALS:
{prior_text}
"""

        output: PerceptionOutput = gateway.chat_structured(
            messages=[
                {
                    "role": "user",
                    "content": user_msg,
                }
            ],
            schema=PerceptionOutput,
            system=_SYSTEM,
            provider="g",
            temperature=0.8,
            max_tokens=1024,
        )

        goals = merge_goals(
            prior_goals,
            output.goals,
            artifact_map,
        )

        return Observation(goals=goals)


def merge_goals(
    prior: list[Goal],
    drafts: list,
    artifact_map: dict[int, str],
) -> list[Goal]:

    # First iteration
    if not prior:

        result: list[Goal] = []

        for i, draft in enumerate(drafts):

            artifact_id = None

            if draft.artifact_index is not None:
                artifact_id = artifact_map.get(
                    draft.artifact_index
                )

            result.append(
                Goal(
                    id=f"g{i}:{uuid.uuid4().hex[:6]}",
                    text=draft.text,
                    done=draft.done,
                    attach_artifact_id=artifact_id,
                )
            )

        return result

    # Existing goals
    merged: list[Goal] = []

    for i, goal in enumerate(prior):

        if i >= len(drafts):
            merged.append(goal)
            continue

        draft = drafts[i]

        artifact_id = None

        if draft.artifact_index is not None:
            artifact_id = artifact_map.get(
                draft.artifact_index
            )

        merged.append(
            Goal(
                id=goal.id,
                text=draft.text,
                done=goal.done or draft.done,
                attach_artifact_id=artifact_id,
            )
        )

    return merged