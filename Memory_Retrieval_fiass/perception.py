

"""
Perception role — the orchestrator.

Runs every iteration. Pinned to Gemini (provider="g", temperature=1.0)
because smaller models fail to maintain goal identity across iterations.

Hallucination defences:
  1. Positional identity  — goals have no id in the LLM output; the loop
     owns ids and maps them by position.
  2. Indexed artifact refs — only hits that carry an artifact are numbered;
     the LLM emits an integer index, never a raw "art:..." string.
"""
from __future__ import annotations
import json
import uuid

import gateway
from schemas import Goal, MemoryItem, Observation, PerceptionOutput

_SYSTEM = """\
You are the Perception role in a cognitive agent. You manage goal decomposition and completion tracking.

Before producing output, reason step-by-step through each obligation below. Think carefully
before deciding done=true and before choosing an artifact_index.

OBLIGATIONS — execute in strict order:

1. DECOMPOSE (only when PRIOR GOALS is empty)
   Decompose USER QUERY into 1–4 bounded goals.
   Each goal is a short imperative statement (e.g. "Fetch the Wikipedia page for X").
   Good: "Extract birth date, death date, and three contributions from the fetched page"
   Bad:  "Extract birth date from the fetched page" + "Extract death date from the fetched page"
         (never split extractions from the SAME source into separate goals)
   Rule: when multiple facts must be extracted from the same fetched page or artifact,
         combine them into ONE extraction goal. Prefer 2-goal plans for fetch-then-extract
         queries: one fetch goal, one extraction goal covering all requested facts.

   DISCOVERY PATTERN: When a query requires acting on an unknown set of items (e.g. "index
   every file in papers/"), start with a discovery goal (e.g. "List files in papers/") plus a
   deferred summary goal (e.g. "Report total chunk count"). After the discovery result arrives,
   APPEND one concrete goal per discovered item between the done discovery goal and the summary
   goal. The summary goal always stays last. This may produce more than 4 goals total — that
   is correct and expected for batch operations.

   INDEXED CORPUS PATTERN: If MEMORY HITS already contain fact items whose descriptors start
   with [sandbox: or [art: (these mark previously-indexed chunks of source documents), the
   next goal for any question about that material is to QUERY THE EXISTING KNOWLEDGE BASE
   rather than re-fetch or re-open the original sources. Pair that query goal with a final
   synthesis/answer goal.
   Reasoning type: planning.

2. UPDATE DONE FLAGS
   For each goal in PRIOR GOALS, examine RUN HISTORY.
   Ask yourself: "Does the history contain a direct answer (kind=answer) or a completed
   tool result (kind=action) that fully addresses this goal's text?"
   - A fetch goal is done when kind=action with that URL appears in history.
   - An extract goal is done when kind=answer with the extracted facts appears.
   - A plan goal is done when kind=answer contains a concrete plan.
   CRITICAL: If a kind=action entry has result_descriptor containing "Error" or "error"
   or "No such file" or "does not exist", the action FAILED — do NOT mark the goal done.
   A failed tool call does not satisfy a goal. Keep done=false on any error.
   If you cannot clearly confirm the goal is addressed, keep done=false.
   Set done=true only if the answer is yes. Once done=true, it must stay true.
   Reasoning type: verification.

3. ATTACH ARTIFACT (first unfinished goal only)
   For the first goal where done=false, ask: "Does this goal need raw bytes from a
   previously fetched page or file?" If yes, set artifact_index to one of the integer
   values marked [ARTIFACT INDEX=N] in MEMORY HITS. If no artifact is needed, set null.
   Reasoning type: lookup.

4. PRESERVE ORDER
   Return goals in the SAME ORDER as PRIOR GOALS.
   Do NOT reorder, insert in the middle, or drop goals.

SELF-CHECK before emitting output:
- Every goal that was done=true in PRIOR GOALS is still done=true? If not, fix it.
- Output list length equals PRIOR GOALS length (or fresh decomposition)? If not, fix it.
- artifact_index is null OR one of the integers shown in MEMORY HITS? If not, set null.

FALLBACKS:
- If history is ambiguous and you cannot tell whether a goal is satisfied, keep done=false.
- If no ARTIFACT INDEX appears in MEMORY HITS, always set artifact_index to null.
- If you cannot decompose the query into clear goals, produce one goal: restate the full query.\
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
        # Build numbered artifact index (only hits that carry artifacts get a number)
        artifact_map: dict[int, str] = {}
        art_idx = 0
        hits_lines: list[str] = []
        for i, hit in enumerate(hits):
            line = f"  [{i}] {hit.descriptor}  (kind={hit.kind}, source={hit.source})"
            if hit.artifact_id:
                line += f"  [ARTIFACT INDEX={art_idx}]"
                artifact_map[art_idx] = hit.artifact_id
                art_idx += 1
            hits_lines.append(line)

        hits_text = "\n".join(hits_lines) if hits_lines else "  (none)"
        history_text = json.dumps(history[-10:], indent=2) if history else "[]"

        if prior_goals:
            prior_text = "\n".join(
                f"  [{i}] {'[DONE]' if g.done else '[OPEN]'} {g.text}"
                for i, g in enumerate(prior_goals)
            )
        else:
            prior_text = "  (empty — this is the first iteration)"

        user_msg = (
            f"USER QUERY:\n  {query}\n\n"
            f"MEMORY HITS:\n{hits_text}\n\n"
            f"RUN HISTORY:\n{history_text}\n\n"
            f"PRIOR GOALS:\n{prior_text}"
        )

        output: PerceptionOutput = gateway.chat_structured(
            messages=[{"role": "user", "content": user_msg}],
            schema=PerceptionOutput,
            system=_SYSTEM,
            provider="g",       # pinned — empirically required for goal stability
            temperature=1.0,    # temperature=0 causes Gemini to loop identically
            max_tokens=1024,
        )

        goals = _merge(prior_goals, output.goals, artifact_map)
        return Observation(goals=goals)


def _merge(
    prior: list[Goal],
    drafts: list[PerceptionOutput.__annotations__["goals"].__args__[0]],  # type: ignore[index]
    artifact_map: dict[int, str],
) -> list[Goal]:
    # First iteration: no prior goals → assign fresh ids
    if not prior:
        return [
            Goal(
                id=f"g{i}:{uuid.uuid4().hex[:6]}",
                text=d.text,
                done=d.done,
                attach_artifact_id=(
                    artifact_map.get(d.artifact_index)
                    if d.artifact_index is not None
                    else None
                ),
            )
            for i, d in enumerate(drafts)
        ]

    # Subsequent iterations: preserve ids, update flags, allow appending new goals
    result: list[Goal] = []
    for i, goal in enumerate(prior):
        if i < len(drafts):
            draft = drafts[i]
            art_id = (
                artifact_map.get(draft.artifact_index)
                if draft.artifact_index is not None
                else None
            )
            result.append(
                Goal(
                    id=goal.id,
                    text=draft.text,
                    done=goal.done or draft.done,  # monotonic
                    attach_artifact_id=art_id,
                )
            )
        else:
            # LLM dropped this position — preserve current state
            result.append(goal)

    # Append any new goals discovered dynamically (e.g. after list_dir)
    for j in range(len(prior), len(drafts)):
        draft = drafts[j]
        art_id = (
            artifact_map.get(draft.artifact_index)
            if draft.artifact_index is not None
            else None
        )
        result.append(
            Goal(
                id=f"g{j}:{uuid.uuid4().hex[:6]}",
                text=draft.text,
                done=draft.done,
                attach_artifact_id=art_id,
            )
        )
    return result
