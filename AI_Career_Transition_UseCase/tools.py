"""
tools.py
--------

Architecture:
1. Internal _impl functions
   - Pure business logic
   - Validated using Pydantic schemas

2. Public tool functions
   - Simple Gemini-callable signatures
   - Validate input via Pydantic
   - Call internal implementations

Exports:
- GEMINI_TOOLS
- GEMINI_DISPATCH
- call_tool()
"""

import json

from schemas import (
    AllocateLearningHours,
    CheckFeasibility,
    FallbackReasoning,
    ReplanWithConstraints,
    ShowReasoning,
    SkillGapAnalysis,
    Verify,
)

# ──────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ──────────────────────────────────────────────────────────────────────────────

SKILL_HOURS: dict[str, int] = {
    "Python": 80,
    "SQL": 40,
    "Statistics": 60,
    "Machine Learning": 100,
    "Deep Learning": 120,
    "Data Visualization": 50,
    "Excel": 20,
    "Tableau": 40,
    "R": 60,
    "Spark": 80,
    "Cloud (AWS/GCP)": 60,
    "NLP": 80,
    "Computer Vision": 80,
    "Power BI": 30,
}

ROLE_REQUIREMENTS: dict[str, list[str]] = {
    "Data Scientist": [
        "Python",
        "SQL",
        "Statistics",
        "Machine Learning",
        "Data Visualization",
    ],
    "ML Engineer": [
        "Python",
        "Machine Learning",
        "Deep Learning",
        "Cloud (AWS/GCP)",
        "SQL",
    ],
    "Data Analyst": [
        "SQL",
        "Excel",
        "Python",
        "Data Visualization",
        "Statistics",
    ],
    "AI Researcher": [
        "Python",
        "Statistics",
        "Machine Learning",
        "Deep Learning",
        "NLP",
    ],
    "Business Analyst": [
        "SQL",
        "Excel",
        "Tableau",
        "Statistics",
        "Power BI",
    ],
}

SKILL_DEPENDENCIES: dict[str, list[str]] = {
    "Machine Learning": [
        "Python",
        "Statistics",
    ],
    "Deep Learning": [
        "Machine Learning",
        "Python",
    ],
    "NLP": [
        "Python",
        "Machine Learning",
    ],
    "Computer Vision": [
        "Python",
        "Deep Learning",
    ],
    "Spark": [
        "Python",
        "SQL",
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# Internal Implementations
# ──────────────────────────────────────────────────────────────────────────────


def _impl_show_reasoning(
    step: str,
    reasoning_type: str,
) -> str:

    print(f" [{reasoning_type.upper()}] {step}")

    return (
        f"Reasoning logged: "
        f"[{reasoning_type}] {step}"
    )


def _impl_skill_gap_analysis(
    current_skills: list[str],
    target_role: str,
) -> str:

    required = ROLE_REQUIREMENTS.get(target_role)

    if not required:

        return json.dumps(
            {
                "error": f"Unknown role '{target_role}'",
                "available_roles": list(
                    ROLE_REQUIREMENTS.keys()
                ),
            }
        )

    current_lower = {
        s.lower() for s in current_skills
    }

    missing = [
        s
        for s in required
        if s.lower() not in current_lower
    ]

    already_have = [
        s
        for s in required
        if s.lower() in current_lower
    ]

    return json.dumps(
        {
            "target_role": target_role,
            "required_skills": required,
            "already_have": already_have,
            "missing_skills": missing,
            "total_missing": len(missing),
        }
    )


def _impl_allocate_learning_hours(
    skills: list[str],
    hours_per_week: int,
) -> str:

    ordered = _topological_sort(
        skills,
        SKILL_DEPENDENCIES,
    )

    schedule: list[dict] = []

    cumulative_hours = 0
    cumulative_weeks = 0.0

    for skill in ordered:

        hours = SKILL_HOURS.get(skill, 40)

        weeks = round(
            hours / hours_per_week,
            1,
        )

        cumulative_hours += hours

        cumulative_weeks = round(
            cumulative_weeks + weeks,
            1,
        )

        schedule.append(
            {
                "skill": skill,
                "hours": hours,
                "weeks": weeks,
                "cumulative_weeks": cumulative_weeks,
            }
        )

    return json.dumps(
        {
            "ordered_schedule": schedule,
            "total_hours": cumulative_hours,
            "total_weeks": cumulative_weeks,
            "hours_per_week": hours_per_week,
        }
    )


def _impl_check_feasibility(
    total_hours_needed: int,
    hours_per_week: int,
    target_weeks: int,
) -> str:

    available_hours = (
        hours_per_week * target_weeks
    )

    feasible = (
        available_hours >= total_hours_needed
    )

    shortfall = max(
        0,
        total_hours_needed - available_hours,
    )

    return json.dumps(
        {
            "feasible": feasible,
            "total_hours_needed": total_hours_needed,
            "available_hours": available_hours,
            "weeks_needed": round(
                total_hours_needed / hours_per_week,
                1,
            ),
            "target_weeks": target_weeks,
            "shortfall_hours": shortfall,
            "shortfall_weeks": (
                round(
                    shortfall / hours_per_week,
                    1,
                )
                if shortfall
                else 0
            ),
        }
    )


def _impl_replan_with_constraints(
    skills_with_hours: dict,
    priority_order: list[str],
    max_weeks: int,
    hours_per_week: int,
) -> str:

    budget_hours = (
        max_weeks * hours_per_week
    )

    kept = []
    dropped = []

    used_hours = 0

    for skill in priority_order:

        skill_hours = (
            skills_with_hours.get(skill, 0)
        )

        if used_hours + skill_hours <= budget_hours:

            kept.append(
                {
                    "skill": skill,
                    "hours": skill_hours,
                }
            )

            used_hours += skill_hours

        else:

            dropped.append(
                {
                    "skill": skill,
                    "hours": skill_hours,
                    "reason": "Exceeds budget",
                }
            )

    return json.dumps(
        {
            "kept_skills": kept,
            "dropped_skills": dropped,
            "total_hours_used": used_hours,
            "budget_hours": budget_hours,
            "weeks_used": round(
                used_hours / hours_per_week,
                1,
            ),
            "feasible": True,
        }
    )


def _impl_verify(
    expression: str,
    expected: str,
) -> str:

    try:

        actual = str(eval(expression))  # noqa: S307

        return json.dumps(
            {
                "expression": expression,
                "expected": expected,
                "actual": actual,
                "match": (
                    actual.lower()
                    == expected.lower()
                ),
            }
        )

    except Exception as e:

        return json.dumps(
            {
                "error": str(e),
                "expression": expression,
            }
        )


def _impl_fallback_reasoning(
    failed_step: str,
    reason: str,
) -> str:

    print(
        f" [FALLBACK] '{failed_step}' → {reason}"
    )

    return (
        f"Fallback triggered for "
        f"'{failed_step}': {reason}. "
        f"Replanning required."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public Gemini-Callable Tool Functions
# ──────────────────────────────────────────────────────────────────────────────

# Gemini automatically extracts schemas from:
# - Type hints
# - Docstrings
#
# Pydantic validation happens internally.


def show_reasoning(
    step: str,
    reasoning_type: str,
) -> str:
    """
    Display a tagged reasoning step
    before any tool call.
    """

    validated = ShowReasoning.model_validate(
        {
            "step": step,
            "reasoning_type": reasoning_type,
        }
    )

    return _impl_show_reasoning(
        validated.step,
        validated.reasoning_type,
    )


def skill_gap_analysis(
    current_skills: list[str],
    target_role: str,
) -> str:
    """
    Identify missing skills required
    for the target role.
    """

    validated = (
        SkillGapAnalysis.model_validate(
            {
                "current_skills": current_skills,
                "target_role": target_role,
            }
        )
    )

    return _impl_skill_gap_analysis(
        validated.current_skills,
        validated.target_role,
    )


def allocate_learning_hours(
    skills: list[str],
    hours_per_week: int,
) -> str:
    """
    Allocate weekly study hours
    while respecting dependencies.
    """

    validated = (
        AllocateLearningHours.model_validate(
            {
                "skills": skills,
                "hours_per_week": hours_per_week,
                "dependencies": SKILL_DEPENDENCIES,
            }
        )
    )

    return _impl_allocate_learning_hours(
        validated.skills,
        validated.hours_per_week,
    )


def check_feasibility(
    total_hours_needed: int,
    hours_per_week: int,
    target_weeks: int,
) -> str:
    """
    Check whether the plan
    fits the target timeline.
    """

    validated = (
        CheckFeasibility.model_validate(
            {
                "total_hours_needed": total_hours_needed,
                "hours_per_week": hours_per_week,
                "target_weeks": target_weeks,
            }
        )
    )

    return _impl_check_feasibility(
        validated.total_hours_needed,
        validated.hours_per_week,
        validated.target_weeks,
    )


def replan_with_constraints(
    skills_with_hours: dict,
    priority_order: list[str],
    max_weeks: int,
    hours_per_week: int,
) -> str:
    """
    Drop low-priority skills
    to fit the deadline.
    """

    validated = (
        ReplanWithConstraints.model_validate(
            {
                "skills_with_hours": skills_with_hours,
                "priority_order": priority_order,
                "max_weeks": max_weeks,
                "hours_per_week": hours_per_week,
            }
        )
    )

    return _impl_replan_with_constraints(
        validated.skills_with_hours,
        validated.priority_order,
        validated.max_weeks,
        validated.hours_per_week,
    )


def verify(
    expression: str,
    expected: str,
) -> str:
    """
    Verify a mathematical
    or logical expression.
    """

    validated = Verify.model_validate(
        {
            "expression": expression,
            "expected": expected,
        }
    )

    return _impl_verify(
        validated.expression,
        validated.expected,
    )


def fallback_reasoning(
    failed_step: str,
    reason: str,
) -> str:
    """
    Trigger fallback reasoning
    when a step fails.
    """

    validated = (
        FallbackReasoning.model_validate(
            {
                "failed_step": failed_step,
                "reason": reason,
            }
        )
    )

    return _impl_fallback_reasoning(
        validated.failed_step,
        validated.reason,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Gemini Tool Registry
# ──────────────────────────────────────────────────────────────────────────────

GEMINI_TOOLS = [
    show_reasoning,
    skill_gap_analysis,
    allocate_learning_hours,
    check_feasibility,
    replan_with_constraints,
    verify,
    fallback_reasoning,
]

GEMINI_DISPATCH: dict[str, callable] = {
    fn.__name__: fn
    for fn in GEMINI_TOOLS
}


# ──────────────────────────────────────────────────────────────────────────────
# Tool Dispatcher
# ──────────────────────────────────────────────────────────────────────────────


def call_tool(
    name: str,
    args: dict,
) -> str:
    """
    Look up a tool by name
    and execute it.
    """

    fn = GEMINI_DISPATCH.get(name)

    if not fn:
        return f"ERROR: Unknown tool '{name}'"

    try:

        return fn(**args)

    except Exception as e:

        return (
            f"ERROR in '{name}': {e}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────


def _topological_sort(
    skills: list[str],
    dependencies: dict[str, list[str]],
) -> list[str]:

    visited: set[str] = set()

    result: list[str] = []

    def visit(skill: str) -> None:

        if skill in visited:
            return

        visited.add(skill)

        for dependency in dependencies.get(
            skill,
            [],
        ):

            if dependency in skills:
                visit(dependency)

        result.append(skill)

    for skill in skills:
        visit(skill)

    return result