from pydantic import BaseModel, Field

# ──────────────────────────────────────────────────────────────────────────────
# Show Reasoning
# ──────────────────────────────────────────────────────────────────────────────

class ShowReasoning(BaseModel):
    """
    Display a tagged reasoning step
    before any tool call.
    """

    step: str = Field(
        description="The reasoning step to display"
    )

    reasoning_type: str = Field(
        description=(
            "Type of reasoning: "
            "Arithmetic, Logical, or Lookup"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Skill Gap Analysis
# ──────────────────────────────────────────────────────────────────────────────


class SkillGapAnalysis(BaseModel):
    """
    Identify missing skills required
    for the target role.
    """

    current_skills: list[str] = Field(
        description="Skills the user already has"
    )

    target_role: str = Field(
        description=(
            "The role the user wants "
            "to transition into"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Allocate Learning Hours
# ──────────────────────────────────────────────────────────────────────────────


class AllocateLearningHours(BaseModel):
    """
    Allocate weekly study hours
    while respecting dependencies.
    """

    skills: list[str] = Field(
        description="List of skills to learn"
    )

    hours_per_week: int = Field(
        description=(
            "Hours available to study per week"
        )
    )

    dependencies: dict[str, list[str]] = Field(
        description=(
            "Skill dependency map.\n"
            "Example:\n"
            "{'Machine Learning': ['Python', 'Statistics']}"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Check Feasibility
# ──────────────────────────────────────────────────────────────────────────────


class CheckFeasibility(BaseModel):
    """
    Check whether the learning plan
    fits the target timeline.
    """

    total_hours_needed: int = Field(
        description=(
            "Total hours required to learn "
            "all missing skills"
        )
    )

    hours_per_week: int = Field(
        description=(
            "Hours the user can study per week"
        )
    )

    target_weeks: int = Field(
        description=(
            "Target number of weeks "
            "to complete the transition"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Replan With Constraints
# ──────────────────────────────────────────────────────────────────────────────


class ReplanWithConstraints(BaseModel):
    """
    Drop low-priority skills
    to fit the deadline.
    """

    skills_with_hours: dict[str, int] = Field(
        description=(
            "Mapping of skill → required hours.\n"
            "Example:\n"
            "{'Python': 80, 'Machine Learning': 100}"
        )
    )

    priority_order: list[str] = Field(
        description=(
            "Skills ordered from highest "
            "to lowest priority.\n"
            "Higher-priority skills are kept first."
        )
    )

    max_weeks: int = Field(
        description="Hard deadline in weeks"
    )

    hours_per_week: int = Field(
        description="Hours available per week"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Verify
# ──────────────────────────────────────────────────────────────────────────────


class Verify(BaseModel):
    """
    Verify a mathematical or logical claim.
    """

    expression: str = Field(
        description=(
            "A Python-evaluable expression.\n"
            "Example: '390 >= 330'"
        )
    )

    expected: str = Field(
        description=(
            "Expected result as a string.\n"
            "Example: 'True'"
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fallback Reasoning
# ──────────────────────────────────────────────────────────────────────────────


class FallbackReasoning(BaseModel):
    """
    Trigger fallback reasoning when
    a step fails or becomes infeasible.
    """

    failed_step: str = Field(
        description=(
            "Name of the failed step or tool"
        )
    )

    reason: str = Field(
        description=(
            "Explanation of why the step failed "
            "or produced unexpected results"
        )
    )