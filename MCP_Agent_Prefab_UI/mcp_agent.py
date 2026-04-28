"""
Agentic loop over facts_server.py using Gemini.

Flow:
  1. fetch_news        — get 4 latest headlines
  2. save_fact         — save each headline
  3. show_facts_ui     — display results in UI
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# =========================
# CONFIG
# =========================
load_dotenv()

# MODEL = "gemini-3.1-flash-lite-preview"
MODEL= "gemini-2.5-flash-lite"
MAX_ITERATIONS = 8

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

LOG_FILE = Path(__file__).parent / "agent_log.json"


# =========================
# LOGGING
# =========================
def _write_log(steps: list):
    LOG_FILE.write_text(json.dumps(steps, indent=2))


# =========================
# TOOL DESCRIPTION FORMATTER
# =========================
def describe_tools(tools) -> str:
    lines = []
    for i, t in enumerate(tools, 1):
        props = (t.inputSchema or {}).get("properties", {})
        params = ", ".join(
            f"{name}: {p.get('type', '?')}" for name, p in props.items()
        ) or "no params"

        lines.append(f"{i}. {t.name}({params}) — {t.description or ''}")

    return "\n".join(lines)


# =========================
# SAFE RESPONSE PARSER
# =========================
def extract_action(text: str) -> str:
    text = (text or "").strip()

    for line in text.splitlines():
        if line.startswith("FUNCTION_CALL:"):
            return line.strip()
        if line.startswith("FINAL_ANSWER:"):
            return line.strip()

    return ""


# =========================
# MAIN AGENT LOOP
# =========================
async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).parent / "facts_server.py")],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("✅ Connected to MCP facts_server\n")

            tools = (await session.list_tools()).tools
            tools_desc = describe_tools(tools)

            # =========================
            # SYSTEM PROMPT
            # =========================
            system_prompt = f"""
You are a world news agent.

You must solve the task by calling tools ONE AT A TIME.

Available tools:
{tools_desc}

Response format (STRICT):
- FUNCTION_CALL: tool_name|arg1|arg2
- FINAL_ANSWER: summary

Rules:
- Call only one tool at a time.
- Use exact tool names.
- Use arguments in exact order.
- If a tool fails, try again or choose another.
- After each tool result, decide next step.
- Finish with FINAL_ANSWER.
"""

            # =========================
            # TASK
            # =========================
            task = (
                "Fetch 4 latest world news headlines. "
                "Save each headline using save_fact (4 calls). "
                "Finally call show_facts_ui."
            )

            history = []
            _write_log([])

            # =========================
            # LOOP
            # =========================
            for iteration in range(1, MAX_ITERATIONS + 1):
                print(f"\n--- Iteration {iteration} ---")

                context = "\n".join(history) if history else "(no prior steps)"

                prompt = f"""
{system_prompt}

Task:
{task}

Previous steps:
{context}

What is your next action?
"""

                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                )

                raw_text = response.text or ""
                action = extract_action(raw_text)

                print(f"LLM RAW:\n{raw_text}\n")
                print(f"Parsed Action: {action}")

                if not action:
                    print("❌ Invalid response format. Stopping.")
                    break

                # =========================
                # FINAL ANSWER
                # =========================
                if action.startswith("FINAL_ANSWER:"):
                    print("\n✅ Agent Finished")
                    print(action)
                    break

                # =========================
                # FUNCTION CALL
                # =========================
                if not action.startswith("FUNCTION_CALL:"):
                    print("❌ Unexpected format. Stopping.")
                    break

                _, call = action.split(":", 1)
                parts = [p.strip() for p in call.split("|")]

                func_name = parts[0]
                raw_args = parts[1:]

                tool = next((t for t in tools if t.name == func_name), None)

                if tool is None:
                    msg = f"❌ Unknown tool: {func_name}"
                    print(msg)
                    history.append(msg)
                    continue

                # =========================
                # ARGUMENT HANDLING
                # =========================
                props = (tool.inputSchema or {}).get("properties", {})
                prop_names = list(props.keys())

                if len(raw_args) != len(prop_names):
                    msg = f"❌ Argument mismatch for {func_name}"
                    print(msg)
                    history.append(msg)
                    continue

                arguments = dict(zip(prop_names, raw_args))

                print(f"→ Calling {func_name} with {arguments}")

                try:
                    result = await session.call_tool(
                        func_name,
                        arguments=arguments
                    )

                    payload = (
                        result.content[0].text
                        if result.content and hasattr(result.content[0], "text")
                        else str(result)
                    )

                except Exception as e:
                    payload = f"ERROR: {str(e)}"

                print(f"← Result: {payload}")

                step = f"Step {iteration}: {func_name}({arguments}) → {payload}"
                history.append(step)

                _write_log(history)

            else:
                print("\n⚠️ Max iterations reached without completion.")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    asyncio.run(main())