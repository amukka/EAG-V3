import json
import os

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import CAREER_AGENT_SYSTEM_PROMPT
from tools import GEMINI_TOOLS, call_tool

# ── Load environment variables ───────────────────────────────────────────────
load_dotenv()

# ── Gemini Client ────────────────────────────────────────────────────────────
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash-lite"

# ── Example prompts ──────────────────────────────────────────────────────────
EXAMPLES = [
    (
        "Marketing Manager → Data Scientist",
        (
            "I am a Marketing Manager with skills in Excel, PowerPoint, "
            "and project management. I want to become a Data Scientist "
            "in 6 months. I can study 15 hours per week."
        ),
    ),
    (
        "Nurse → ML Engineer",
        (
            "I am a nurse with skills in Excel and basic data reporting. "
            "I want to become an ML Engineer in 4 months. "
            "I can study 10 hours per week."
        ),
    ),
]

# ── Tool styling ─────────────────────────────────────────────────────────────
TOOL_ICONS = {
    "show_reasoning": "💭",
    "skill_gap_analysis": "🔍",
    "allocate_learning_hours": "📅",
    "check_feasibility": "✅",
    "replan_with_constraints": "🔄",
    "verify": "🔢",
    "fallback_reasoning": "⚠️",
}

TOOL_COLORS = {
    "show_reasoning": "#e8f4f8",
    "skill_gap_analysis": "#f0f8e8",
    "allocate_learning_hours": "#fff8e8",
    "check_feasibility": "#e8f8f0",
    "replan_with_constraints": "#fce8f8",
    "verify": "#e8ecf8",
    "fallback_reasoning": "#f8ece8",
}

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Career AI Transition Agent",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Career AI Transition Agent")

st.caption(
    "Powered by Gemini 2.0 Flash · Structured multi-step reasoning with tool use"
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Your Career Goal")

    choice = st.radio(
        "Choose an example or enter your own:",
        [label for label, _ in EXAMPLES] + ["Custom goal"],
    )

    if choice == "Custom goal":
        user_input = st.text_area(
            "Describe your goal:",
            placeholder=(
                "I am a [current role] with skills in [skills]. "
                "I want to become a [target role] in [N] months. "
                "I can study [X] hours per week."
            ),
            height=160,
        )
    else:
        user_input = next(
            text for label, text in EXAMPLES if label == choice
        )
        st.info(user_input)

    st.divider()

    run = st.button(
        "▶ Run Agent",
        type="primary",
        use_container_width=True,
        disabled=not user_input,
    )

    st.divider()

    st.markdown("### Tools Available")

    for name, icon in TOOL_ICONS.items():
        st.markdown(f"{icon} `{name}`")

# ── Main Screen ──────────────────────────────────────────────────────────────
if not run:
    st.markdown(
        """
        ### How it works

        1. Pick an example or describe your own career transition goal
        2. Click **Run Agent**
        3. Watch each tool execute step by step
        4. Get a complete week-by-week learning plan
        """
    )
    st.stop()

st.divider()

if len(user_input) > 80:
    st.subheader(f"Goal: _{user_input[:80]}..._")
else:
    st.subheader(f"Goal: _{user_input}_")

st.divider()

# ── Agent Conversation State ─────────────────────────────────────────────────
contents = [
    types.Content(
        role="user",
        parts=[types.Part(text=user_input)],
    )
]

turn_counter = st.empty()

# ── Agent Loop ───────────────────────────────────────────────────────────────
for turn in range(30):

    turn_counter.caption(f"Turn {turn + 1} / 30")

    with st.spinner("Gemini is thinking..."):

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=CAREER_AGENT_SYSTEM_PROMPT,
                tools=GEMINI_TOOLS,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )

    model_content = response.candidates[0].content

    contents.append(model_content)

    text_parts = []
    function_calls = []

    # ── Parse model response ─────────────────────────────────────────────────
    for part in model_content.parts:

        if part.text:
            text_parts.append(part.text.strip())

        if part.function_call:
            function_calls.append(part.function_call)

    # ── Show SELF_CHECK logs ────────────────────────────────────────────────
    for text in text_parts:

        for line in text.splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("SELF_CHECK: yes"):
                st.success(f"✓ {line}")

            elif line.startswith("SELF_CHECK: no"):
                st.error(f"✗ {line}")

            elif line.startswith("SELF_CHECK"):
                st.warning(f"⚠ {line}")

    # ── Final answer if no tools ────────────────────────────────────────────
    if not function_calls:

        turn_counter.empty()

        st.divider()

        st.subheader("📋 Final Career Transition Plan")

        plan_lines = []

        for text in text_parts:

            for line in text.splitlines():

                cleaned = line.strip()

                if cleaned and not cleaned.startswith("SELF_CHECK"):
                    plan_lines.append(cleaned)

        final_text = "\n".join(plan_lines)

        if final_text:
            st.success(final_text)
        else:
            st.info(
                "Plan complete — see tool outputs above for the full schedule."
            )

        st.balloons()

        break

    # ── Execute tools ───────────────────────────────────────────────────────
    fn_response_parts = []

    for fc in function_calls:

        args = dict(fc.args) if fc.args else {}

        icon = TOOL_ICONS.get(fc.name, "🔧")
        bg = TOOL_COLORS.get(fc.name, "#f8f8f8")

        with st.expander(f"{icon} {fc.name}", expanded=True):

            col_in, col_out = st.columns(2)

            # ── Input ───────────────────────────────────────────────────────
            with col_in:
                st.markdown("##### Input")
                st.json(args)

            # ── Execute tool ───────────────────────────────────────────────
            result = call_tool(fc.name, args)

            # ── Output ─────────────────────────────────────────────────────
            with col_out:
                st.markdown("##### Output")

                try:
                    parsed = json.loads(result)
                    st.json(parsed)

                except json.JSONDecodeError:
                    st.code(result)

        # ── Send tool response back to Gemini ──────────────────────────────
        fn_response_parts.append(
            types.Part(
                function_response=types.FunctionResponse(
                    name=fc.name,
                    response={"result": result},
                )
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=fn_response_parts,
        )
    )