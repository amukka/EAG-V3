"""
Career AI Transition Agent — MCP + native Gemini tool-calling edition.

Flow:
1. Spawn ./mcp_server.py over stdio and list its tools.
2. Convert MCP tool schemas into Gemini types.FunctionDeclaration objects.
3. Pass tools= to generate_content(); Gemini calls tools natively.
4. Execute function_calls in parallel via asyncio.TaskGroup + MCP.
5. Feed function_response parts back and continue until Gemini returns text only.
6. AgentTrace records every LLM call and tool call for observability.

Usage:
    uv run main.py
    uv run main.py "I am a nurse. I want to become a Data Scientist in 6 months."
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from prompts import CAREER_AGENT_SYSTEM_PROMPT

# ──────────────────────────────────────────────────────────────────────────────
# Environment Setup
# ──────────────────────────────────────────────────────────────────────────────

load_dotenv()

MODEL = "gemini-2.0-flash"

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

DIVIDER = "─" * 62

# ──────────────────────────────────────────────────────────────────────────────
# Observability / Tracing
# ──────────────────────────────────────────────────────────────────────────────


class AgentTrace:
    """
    Collects every LLM call and tool call for reporting.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    def add(self, **kwargs) -> None:
        self.events.append(kwargs)

    def print_summary(self) -> None:

        llm_events = [
            e for e in self.events if e["kind"] == "llm_call"
        ]

        tool_events = [
            e for e in self.events if e["kind"] == "tool_call"
        ]

        total_in = sum(
            e.get("input_tokens", 0) or 0 for e in llm_events
        )

        total_out = sum(
            e.get("output_tokens", 0) or 0 for e in llm_events
        )

        total_cached = sum(
            e.get("cache_read", 0) or 0 for e in llm_events
        )

        total_ms = sum(
            e.get("latency_ms", 0) or 0 for e in llm_events
        )

        print(f"\n{'═' * 62}")
        print(" AGENT TRACE SUMMARY")
        print(f"{'─' * 62}")

        print(f" LLM calls   : {len(llm_events)}")
        print(f" Tool calls  : {len(tool_events)}")
        print(f" Tokens in   : {total_in}")
        print(f" Tokens out  : {total_out}")
        print(f" Cached      : {total_cached}")
        print(f" Total ms    : {total_ms}")

        print(f"{'─' * 62}")
        print(" LLM CALL DETAIL")

        for e in llm_events:

            print(
                f" turn {e['turn']:>2} "
                f"model={e['model']} "
                f"in={e['input_tokens']} "
                f"out={e['output_tokens']} "
                f"cached={e.get('cache_read', 0) or 0} "
                f"{e['latency_ms']}ms"
            )

        print(f"{'─' * 62}")
        print(" TOOL CALL DETAIL")

        for e in tool_events:

            result_preview = str(
                e.get("tool_result", "")
            )[:80]

            print(
                f" turn {e['turn']:>2} "
                f"{e['tool_name']} → {result_preview}"
            )

        print(f"{'═' * 62}\n")


# ──────────────────────────────────────────────────────────────────────────────
# MCP → Gemini Tool Conversion
# ──────────────────────────────────────────────────────────────────────────────


def _map_type(json_type: str) -> types.Type:

    return {
        "string": types.Type.STRING,
        "number": types.Type.NUMBER,
        "integer": types.Type.INTEGER,
        "boolean": types.Type.BOOLEAN,
        "array": types.Type.ARRAY,
        "object": types.Type.OBJECT,
    }.get(json_type, types.Type.STRING)


def _json_schema_to_gemini(js: dict) -> types.Schema:
    """
    Recursively convert JSON schema to Gemini schema.
    """

    jtype = js.get("type", "string")

    kwargs: dict = {
        "type": _map_type(jtype)
    }

    if jtype == "array":

        kwargs["items"] = _json_schema_to_gemini(
            js.get("items", {})
        )

    if jtype == "object":

        props = js.get("properties", {})

        if props:

            kwargs["properties"] = {
                k: _json_schema_to_gemini(v)
                for k, v in props.items()
            }

    return types.Schema(**kwargs)


def mcp_tools_to_gemini(tools) -> list[types.Tool]:
    """
    Convert MCP tools into Gemini FunctionDeclarations.
    """

    declarations = []

    for t in tools:

        schema = t.inputSchema or {}

        properties = schema.get("properties", {}) or {}

        required = schema.get("required", []) or []

        declarations.append(
            types.FunctionDeclaration(
                name=t.name,
                description=t.description or "",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        k: _json_schema_to_gemini(v)
                        for k, v in properties.items()
                    },
                    required=required,
                ),
            )
        )

    return [
        types.Tool(
            function_declarations=declarations
        )
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Parallel Tool Execution
# ──────────────────────────────────────────────────────────────────────────────


async def dispatch_tool_calls(
    session: ClientSession,
    function_calls: list[types.FunctionCall],
    tool_names: set[str],
    turn: int,
    trace: AgentTrace,
) -> list[types.Part]:

    async def _call_one(fc: types.FunctionCall) -> types.Part:

        if fc.name not in tool_names:
            raise RuntimeError(
                f"Unknown tool called: {fc.name}"
            )

        args = dict(fc.args) if fc.args else {}

        print(f"\n→ TOOL: {fc.name}")

        print(
            f" Args: {json.dumps(args, indent=2)}"
        )

        result = await session.call_tool(
            fc.name,
            args,
        )

        tool_text = (
            result.content[0].text
            if result.content
            else ""
        )

        try:

            parsed = json.loads(tool_text)

            pretty = json.dumps(
                parsed,
                indent=2,
            )

            lines = pretty.splitlines()

            display = "\n ".join(lines[:15])

            if len(lines) > 15:
                display += "\n ... (truncated)"

            print(f" Result:\n {display}")

        except json.JSONDecodeError:

            print(f" Result: {tool_text[:300]}")

        trace.add(
            kind="tool_call",
            turn=turn,
            tool_name=fc.name,
            tool_args=args,
            tool_result=tool_text,
        )

        return types.Part(
            function_response=types.FunctionResponse(
                name=fc.name,
                response={"result": tool_text},
            )
        )

    async with asyncio.TaskGroup() as tg:

        tasks = [
            tg.create_task(_call_one(fc))
            for fc in function_calls
        ]

    return [t.result() for t in tasks]


# ──────────────────────────────────────────────────────────────────────────────
# Context Printer
# ──────────────────────────────────────────────────────────────────────────────


def _print_contents(contents: list) -> None:

    print(
        f"\n [context sent to Gemini — {len(contents)} messages]"
    )

    for i, c in enumerate(contents):

        role = c.role.upper().ljust(6)

        for part in c.parts:

            if hasattr(part, "text") and part.text:

                preview = (
                    part.text.strip()
                    .replace("\n", " ")[:120]
                )

                print(
                    f" [{i}] {role} text : {preview}"
                )

            if (
                hasattr(part, "function_call")
                and part.function_call
            ):

                fc = part.function_call

                print(
                    f" [{i}] {role} fn_call : "
                    f"{fc.name}({json.dumps(dict(fc.args))})"
                )

            if (
                hasattr(part, "function_response")
                and part.function_response
            ):

                fr = part.function_response

                result = str(
                    fr.response.get("result", "")
                )[:100]

                print(
                    f" [{i}] {role} fn_response : "
                    f"{fr.name} → {result}"
                )


# ──────────────────────────────────────────────────────────────────────────────
# Interactive Pause
# ──────────────────────────────────────────────────────────────────────────────


async def _pause(label: str) -> None:

    await asyncio.to_thread(
        input,
        f"\n── {label} ── Press Enter to continue..."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Agent Loop
# ──────────────────────────────────────────────────────────────────────────────


async def run_agent(
    user_message: str,
    max_turns: int = 30,
) -> str:

    trace = AgentTrace()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            str(
                Path(__file__).with_name(
                    "mcp_server.py"
                )
            )
        ],
    )

    async with stdio_client(server_params) as (
        read,
        write,
    ):

        async with ClientSession(read, write) as session:

            await session.initialize()

            tool_list = (
                await session.list_tools()
            ).tools

            tool_names = {
                t.name for t in tool_list
            }

            gemini_tools = mcp_tools_to_gemini(
                tool_list
            )

            print(f"\n{DIVIDER}")

            print(f"User: {user_message}")

            print(DIVIDER)

            contents: list[types.Content] = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=user_message
                        )
                    ],
                )
            ]

            for turn in range(1, max_turns + 1):

                print(
                    f"\n─── turn {turn} → Gemini "
                    f"{'─' * 38}"
                )

                _print_contents(contents)

                t0 = time.perf_counter()

                response = client.models.generate_content(
                    model=MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=CAREER_AGENT_SYSTEM_PROMPT,
                        tools=gemini_tools,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                        temperature=0,
                        max_output_tokens=8192,
                    ),
                )

                latency_ms = round(
                    (time.perf_counter() - t0) * 1000
                )

                usage = response.usage_metadata

                input_tokens = (
                    getattr(
                        usage,
                        "prompt_token_count",
                        0,
                    )
                    or 0
                )

                output_tokens = (
                    getattr(
                        usage,
                        "candidates_token_count",
                        0,
                    )
                    or 0
                )

                cached_tokens = (
                    getattr(
                        usage,
                        "cached_content_token_count",
                        0,
                    )
                    or 0
                )

                model_content = (
                    response.candidates[0].content
                )

                contents.append(model_content)

                text_parts = []

                function_calls = []

                for part in model_content.parts:

                    if part.text:
                        text_parts.append(
                            part.text.strip()
                        )

                    if part.function_call:
                        function_calls.append(
                            part.function_call
                        )

                trace.add(
                    kind="llm_call",
                    turn=turn,
                    model=MODEL,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read=cached_tokens,
                    text=(
                        "\n".join(text_parts)
                        if text_parts
                        else None
                    ),
                    payload={
                        "tool_calls": [
                            fc.name
                            for fc in function_calls
                        ]
                    },
                )

                print(f" model     : {MODEL}")

                print(
                    f" latency   : {latency_ms} ms"
                )

                print(
                    f" tokens    : "
                    f"in={input_tokens} "
                    f"out={output_tokens} "
                    f"cached={cached_tokens}"
                )

                print(
                    f" tool calls requested: "
                    f"{len(function_calls)}"
                )

                if function_calls:

                    print(
                        " tools queued : "
                        + ", ".join(
                            fc.name
                            for fc in function_calls
                        )
                    )

                for text in text_parts:

                    for line in text.splitlines():

                        tag = (
                            "\n "
                            if line.startswith(
                                "SELF_CHECK"
                            )
                            else " "
                        )

                        print(f"{tag}{line}")

                await _pause(
                    f"turn {turn} — LLM response"
                )

                if not function_calls:

                    final_text = "\n".join(
                        text_parts
                    )

                    print(f"\n{DIVIDER}\n")

                    trace.print_summary()

                    return final_text

                parallel_note = (
                    ", parallel via TaskGroup"
                    if len(function_calls) > 1
                    else ""
                )

                print(
                    f"\n─── turn {turn} → MCP "
                    f"({len(function_calls)} calls"
                    f"{parallel_note}) "
                    f"{'─' * 22}"
                )

                fn_response_parts = (
                    await dispatch_tool_calls(
                        session,
                        function_calls,
                        tool_names,
                        turn,
                        trace,
                    )
                )

                await _pause(
                    f"turn {turn} — tool results"
                )

                contents.append(
                    types.Content(
                        role="user",
                        parts=fn_response_parts,
                    )
                )

    trace.print_summary()

    return (
        "Agent did not reach a final answer "
        "within the turn limit."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:

    examples = [
        (
            "I am a Marketing Manager with skills in Excel, "
            "PowerPoint, and project management. "
            "I want to become a Data Scientist in 6 months. "
            "I can study 15 hours per week."
        ),
        (
            "I am a nurse with skills in Excel and "
            "basic data reporting. "
            "I want to become an ML Engineer in 4 months. "
            "I can study 10 hours per week."
        ),
    ]

    if len(sys.argv) > 1:

        user_input = " ".join(sys.argv[1:])

    else:

        print(
            "Career AI Transition Agent "
            "(MCP + native Gemini tool calling)"
        )

        print(DIVIDER)

        print("Example queries:\n")

        for i, ex in enumerate(examples, 1):
            print(f" {i}. {ex}\n")

        choice = input(
            "Enter number (1/2) "
            "or type your own goal: "
        ).strip()

        if choice == "1":
            user_input = examples[0]

        elif choice == "2":
            user_input = examples[1]

        else:
            user_input = (
                choice or examples[0]
            )

    asyncio.run(run_agent(user_input))


if __name__ == "__main__":
    main()