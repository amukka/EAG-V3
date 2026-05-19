"""
Session 6 agent — four-role cognitive architecture.

Roles:
    Memory · Perception · Decision · Action

Contracts:
    schemas.py (Pydantic v2)

Substrate:
    gateway.py

Tools:
    MCP server via stdio

Run:
    uv run agent6.py "Your query here"

    OR

    python agent6.py "Your query here"

Reset state:
    Remove-Item -Recurse state\    # PowerShell
    rm -rf state/                  # bash
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from mcp import (
    ClientSession,
    StdioServerParameters,
)

from mcp.client.stdio import stdio_client

import artifacts as artifact_store
import gateway

from action import Action
from decision import Decision
from memory import Memory
from perception import Perception

from schemas import (
    DecisionOutput,
    Goal,
)

# ──────────────────────────────────────────────────────────────────────────────
# Environment
# ──────────────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

MAX_ITERATIONS = 12

# ──────────────────────────────────────────────────────────────────────────────
# Role instances
# ──────────────────────────────────────────────────────────────────────────────

_memory = Memory()
_perception = Perception()
_decision = Decision()
_action = Action()

# ──────────────────────────────────────────────────────────────────────────────
# MCP Session
# ──────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def mcp_session():
    """
    Create MCP stdio session.
    """

    server_script = str(
        Path(__file__).parent / "mcp_server.py"
    )

    params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(params) as (read, write):

        async with ClientSession(read, write) as session:

            await session.initialize()

            yield session


async def load_tools(session) -> list:
    """
    Load MCP tool definitions.
    """

    result = await session.list_tools()

    return result.tools


def tools_for_decision(mcp_tools: list) -> list[dict]:
    """
    Convert MCP tools into Decision-compatible schema.
    """

    tools = []

    for tool in mcp_tools:

        tools.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": (
                    tool.inputSchema
                    if hasattr(tool, "inputSchema")
                    else {}
                ),
            }
        )

    return tools

# ──────────────────────────────────────────────────────────────────────────────
# Final Answer
# ──────────────────────────────────────────────────────────────────────────────


def final_answer(history: list[dict]) -> str:
    """
    Build final answer from history.
    """

    answers_by_goal: dict[str, str] = {}

    for event in history:

        if event.get("kind") == "answer":

            goal_id = event.get(
                "goal_id",
                str(event["iter"]),
            )

            answers_by_goal[goal_id] = event["text"]

    answers = list(answers_by_goal.values())

    # No answers → summarize tools
    if not answers:

        tool_lines = []

        for event in history:

            if event.get("kind") == "action":

                tool_lines.append(
                    f"{event.get('tool', '?')}: "
                    f"{event.get('result_descriptor', '')}"
                )

        if tool_lines:
            return (
                "Research completed:\n\n"
                + "\n\n".join(tool_lines)
            )

        return "No answer produced."

    # One answer
    if len(answers) == 1:
        return answers[0]

    # Multiple answers
    return "\n\n".join(answers)

# ──────────────────────────────────────────────────────────────────────────────
# Main Agent Loop
# ──────────────────────────────────────────────────────────────────────────────


async def run(query: str) -> str:

    gateway.ensure_gateway()

    run_id = uuid.uuid4().hex[:8]

    history: list[dict] = []

    prior_goals: list[Goal] = []

    # ──────────────────────────────────────────────────────────────────
    # Initial memory write
    # ──────────────────────────────────────────────────────────────────

    mem_item = _memory.remember(
        query,
        source="user_query",
        run_id=run_id,
    )

    print(
        "[memory.remember] "
        f"classified as kind={mem_item.kind!r} "
        f"keywords={mem_item.keywords[:6]}"
    )

    # ──────────────────────────────────────────────────────────────────
    # MCP session
    # ──────────────────────────────────────────────────────────────────

    async with mcp_session() as session:

        mcp_tools = await load_tools(session)

        tools = tools_for_decision(mcp_tools)

        # ──────────────────────────────────────────────────────────────
        # Iterative loop
        # ──────────────────────────────────────────────────────────────

        for iteration in range(1, MAX_ITERATIONS + 1):

            # ──────────────────────────────────────────────────────
            # Force-close repeated answer loops
            # ──────────────────────────────────────────────────────

            if prior_goals:

                counts: dict[str, int] = {}

                for event in history:

                    if event.get("kind") == "answer":

                        goal_id = event.get("goal_id", "")

                        counts[goal_id] = (
                            counts.get(goal_id, 0) + 1
                        )

                updated_goals = []

                for goal in prior_goals:

                    if counts.get(goal.id, 0) >= 2:

                        updated_goals.append(
                            Goal(
                                id=goal.id,
                                text=goal.text,
                                done=True,
                                attach_artifact_id=None,
                            )
                        )

                    else:
                        updated_goals.append(goal)

                prior_goals = updated_goals

            # ──────────────────────────────────────────────────────
            # Memory read
            # ──────────────────────────────────────────────────────

            hits = _memory.read(query, history)

            print(
                f"[memory.read] "
                f"{len(hits)} hit"
                f"{'s' if len(hits) != 1 else ''}"
            )

            # ──────────────────────────────────────────────────────
            # Perception
            # ──────────────────────────────────────────────────────

            observation = _perception.observe(
                query=query,
                hits=hits,
                history=history,
                prior_goals=prior_goals,
                run_id=run_id,
            )

            prior_goals = observation.goals

            log_iteration(iteration, observation.goals)

            # All done
            if observation.all_done:
                break

            # Current goal
            goal = observation.next_unfinished()

            if goal is None:
                break

            # ──────────────────────────────────────────────────────
            # Artifact auto-attachment
            # ──────────────────────────────────────────────────────

            # Auto-attach latest artifact if goal needs synthesis
            if not goal.attach_artifact_id:

                latest_artifact = None

                for event in reversed(history):

                    if event.get("artifact_id"):

                        latest_artifact = event["artifact_id"]
                        break

                if latest_artifact:

                    goal = Goal(
                        id=goal.id,
                        text=goal.text,
                        done=goal.done,
                        attach_artifact_id=latest_artifact,
                    )

                    print(
                        "[auto-attach] "
                        f"{latest_artifact}"
                    )

            # ──────────────────────────────────────────────────────
            # Load attached artifact
            # ──────────────────────────────────────────────────────

            attached: list[tuple[str, bytes]] = []

            if (
                goal.attach_artifact_id
                and artifact_store.exists(
                    goal.attach_artifact_id
                )
            ):

                artifact_bytes = artifact_store.get_bytes(
                    goal.attach_artifact_id
                )

                attached.append(
                    (
                        goal.attach_artifact_id,
                        artifact_bytes,
                    )
                )

                print(
                    "[attach] "
                    f"{goal.attach_artifact_id} "
                    f"({len(artifact_bytes):,} bytes)"
                )

            # ──────────────────────────────────────────────────────
            # Decision
            # ──────────────────────────────────────────────────────

            output: DecisionOutput = (
                _decision.next_step(
                    goal=goal,
                    hits=hits,
                    attached=attached,
                    history=history,
                    tools=tools,
                )
            )

            # Final answer
            if output.is_answer:

                print(
                    "[decision] ANSWER: "
                    f"{output.answer[:120]}..."
                )

                history.append(
                    {
                        "iter": iteration,
                        "kind": "answer",
                        "goal_id": goal.id,
                        "text": output.answer,
                    }
                )

                continue

            # No-op
            if output.tool_call is None:

                history.append(
                    {
                        "iter": iteration,
                        "kind": "noop",
                        "goal_id": goal.id,
                        "reason": "no action",
                    }
                )

                continue

            # ──────────────────────────────────────────────────────
            # Action
            # ──────────────────────────────────────────────────────

            print(
                "[decision] TOOL_CALL: "
                f"{output.tool_call.name}"
                f"({output.tool_call.arguments})"
            )

            result_text, artifact_id = (
                await _action.execute(
                    session,
                    output.tool_call,
                )
            )

            print(
                "[action] → "
                f"{result_text[:120]}"
            )

            # Persist tool result
            _memory.record_outcome(
                tool_call=output.tool_call,
                result_text=result_text,
                artifact_id=artifact_id,
                run_id=run_id,
                goal_id=goal.id,
            )

            # Add to history
            history.append(
                {
                    "iter": iteration,
                    "kind": "action",
                    "goal_id": goal.id,
                    "tool": output.tool_call.name,
                    "arguments": output.tool_call.arguments,
                    "result_descriptor": result_text[:2_000],
                    "artifact_id": artifact_id,
                }
            )

    # ──────────────────────────────────────────────────────────────────
    # Final response
    # ──────────────────────────────────────────────────────────────────

    return final_answer(history)

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────


def log_iteration(
    iteration: int,
    goals: list[Goal],
) -> None:

    print(f"\n─── iter {iteration} ───")

    for goal in goals:

        status = (
            "[done]"
            if goal.done
            else "[open]"
        )

        attach = (
            f" attach={goal.attach_artifact_id}"
            if goal.attach_artifact_id
            else ""
        )

        print(
            f"[perception] "
            f"{status} "
            f"{goal.text}"
            f"{attach}"
        )

# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":

    import platform

    # Windows asyncio compatibility
    if platform.system() == "Windows":

        asyncio.set_event_loop_policy(
            asyncio.WindowsProactorEventLoopPolicy()
        )

    # Query
    query = " ".join(sys.argv[1:]).strip()

    if not query:
        query = input("Query: ").strip()

    if not query:
        print(
            "No query provided.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Logging
    log_path = (
        Path(__file__).parent / "runs.log"
    )

    class Tee:

        def __init__(self, *files):
            self.files = files

        def write(self, data):
            for file in self.files:
                file.write(data)

        def flush(self):
            for file in self.files:
                try:
                    file.flush()
                except Exception:
                    pass

        @property
        def encoding(self):
            return "utf-8"

    with open(
        log_path,
        "a",
        encoding="utf-8",
    ) as log:

        log.write("\n" + "=" * 60 + "\n")
        log.write(f"QUERY: {query}\n")
        log.write(
            f"TIME: {datetime.now().isoformat()}\n"
        )
        log.write("=" * 60 + "\n")

        original_stdout = sys.stdout

        sys.stdout = Tee(
            original_stdout,
            log,
        )

        try:

            answer = asyncio.run(
                run(query)
            )

            print(f"\nFINAL:\n{answer}")

        finally:

            sys.stdout = original_stdout