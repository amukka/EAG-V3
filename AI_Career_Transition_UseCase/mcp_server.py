import asyncio
import sys
from pathlib import Path

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Allow importing local tools.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools import call_tool  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# MCP Server
# ──────────────────────────────────────────────────────────────────────────────

server = Server("career-ai-transition")

# ──────────────────────────────────────────────────────────────────────────────
# Tool Definitions
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = [

    # ----------------------------------------------------------------------
    # Show Reasoning
    # ----------------------------------------------------------------------
    types.Tool(
        name="show_reasoning",
        description=(
            "Display a tagged reasoning step before any tool call. "
            "Always call this first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "step": {
                    "type": "string"
                },
                "reasoning_type": {
                    "type": "string"
                },
            },
            "required": [
                "step",
                "reasoning_type",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Skill Gap Analysis
    # ----------------------------------------------------------------------
    types.Tool(
        name="skill_gap_analysis",
        description=(
            "Identify missing skills required for the target role."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "current_skills": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                },
                "target_role": {
                    "type": "string"
                },
            },
            "required": [
                "current_skills",
                "target_role",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Allocate Learning Hours
    # ----------------------------------------------------------------------
    types.Tool(
        name="allocate_learning_hours",
        description=(
            "Allocate weekly study hours across skills "
            "based on dependencies."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                },
                "hours_per_week": {
                    "type": "integer"
                },
            },
            "required": [
                "skills",
                "hours_per_week",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Check Feasibility
    # ----------------------------------------------------------------------
    types.Tool(
        name="check_feasibility",
        description=(
            "Check whether the learning plan fits "
            "within the target timeline."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "total_hours_needed": {
                    "type": "integer"
                },
                "hours_per_week": {
                    "type": "integer"
                },
                "target_weeks": {
                    "type": "integer"
                },
            },
            "required": [
                "total_hours_needed",
                "hours_per_week",
                "target_weeks",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Replan With Constraints
    # ----------------------------------------------------------------------
    types.Tool(
        name="replan_with_constraints",
        description=(
            "Drop lower-priority skills to fit "
            "within the hard deadline."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skills_with_hours": {
                    "type": "object"
                },
                "priority_order": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                },
                "max_weeks": {
                    "type": "integer"
                },
                "hours_per_week": {
                    "type": "integer"
                },
            },
            "required": [
                "skills_with_hours",
                "priority_order",
                "max_weeks",
                "hours_per_week",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Verify
    # ----------------------------------------------------------------------
    types.Tool(
        name="verify",
        description=(
            "Verify a mathematical or logical expression."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string"
                },
                "expected": {
                    "type": "string"
                },
            },
            "required": [
                "expression",
                "expected",
            ],
        },
    ),

    # ----------------------------------------------------------------------
    # Fallback Reasoning
    # ----------------------------------------------------------------------
    types.Tool(
        name="fallback_reasoning",
        description=(
            "Trigger fallback reasoning when a plan "
            "fails or becomes infeasible."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "failed_step": {
                    "type": "string"
                },
                "reason": {
                    "type": "string"
                },
            },
            "required": [
                "failed_step",
                "reason",
            ],
        },
    ),
]

# ──────────────────────────────────────────────────────────────────────────────
# MCP Handlers
# ──────────────────────────────────────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """
    Return all available MCP tools.
    """
    return TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict,
) -> list[types.TextContent]:
    """
    Execute a tool and return the result.
    """

    result = call_tool(name, arguments)

    return [
        types.TextContent(
            type="text",
            text=result,
        )
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Main Entry
# ──────────────────────────────────────────────────────────────────────────────


async def main() -> None:

    async with stdio_server() as (read, write):

        await server.run(
            read,
            write,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())