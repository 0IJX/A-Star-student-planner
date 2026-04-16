from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List

from ..actions import ACTION_DURATIONS_HOURS, ACTION_STUDY_LOAD
from ..planner import PlanResult


@dataclass(frozen=True)
class ScheduledStep:
    index: int
    day: int
    session: int
    action: str
    duration_hours: float


@dataclass(frozen=True)
class StepBlock:
    day: int
    start_session: int
    end_session: int
    action: str
    start_index: int
    end_index: int
    total_duration_hours: float


def _action_purpose(action_name: str) -> str:
    purposes = {
        "Attend_Class": "go to class and stay on track",
        "Study_1_Hour": "learn the lesson better",
        "Submit_Assignment": "finish missing work",
        "Practice_Quiz": "improve quiz marks",
        "Meet_Tutor": "ask for help on hard parts",
        "Rest": "get energy back",
    }
    return purposes.get(action_name, "move closer to goal")


def _impact_sentence(before, after) -> str:
    parts: List[str] = []
    if after.missing_submissions != before.missing_submissions:
        parts.append(f"missing {before.missing_submissions}->{after.missing_submissions}")
    if abs(after.avg_quiz_score - before.avg_quiz_score) >= 0.2:
        parts.append(f"quiz {before.avg_quiz_score:.1f}->{after.avg_quiz_score:.1f}")
    if abs(after.attendance_rate - before.attendance_rate) >= 0.2:
        parts.append(f"attendance {before.attendance_rate:.1f}->{after.attendance_rate:.1f}")
    if abs(after.lms_activity - before.lms_activity) >= 0.2:
        parts.append(f"lms {before.lms_activity:.1f}->{after.lms_activity:.1f}")
    if abs(after.fatigue - before.fatigue) >= 0.2:
        parts.append(f"fatigue {before.fatigue:.1f}->{after.fatigue:.1f}")
    if not parts:
        return "small change, but still moving."
    return ", ".join(parts) + "."


def _group_steps(steps: List[ScheduledStep]) -> List[StepBlock]:
    if not steps:
        return []

    blocks: List[StepBlock] = []
    start = steps[0]
    end = steps[0]
    duration = steps[0].duration_hours

    for step in steps[1:]:
        same_action = step.action == start.action
        same_day = step.day == start.day
        consecutive_session = step.session == end.session + 1
        if same_action and same_day and consecutive_session:
            end = step
            duration += step.duration_hours
            continue

        blocks.append(
            StepBlock(
                day=start.day,
                start_session=start.session,
                end_session=end.session,
                action=start.action,
                start_index=start.index,
                end_index=end.index,
                total_duration_hours=duration,
            )
        )
        start = step
        end = step
        duration = step.duration_hours

    blocks.append(
        StepBlock(
            day=start.day,
            start_session=start.session,
            end_session=end.session,
            action=start.action,
            start_index=start.index,
            end_index=end.index,
            total_duration_hours=duration,
        )
    )
    return blocks


def build_scheduled_steps(
    actions: Iterable[str],
    available_hours_per_day: float,
    max_study_hours_per_day: float,
    max_same_action_streak: int = 4,
) -> List[ScheduledStep]:
    steps: List[ScheduledStep] = []

    day_capacity = max(1.0, float(available_hours_per_day))
    study_cap = max(0.5, float(max_study_hours_per_day))
    max_streak = max(1, int(max_same_action_streak))

    day = 1
    session = 1
    used_hours = 0.0
    used_study_hours = 0.0
    previous_action = ""
    current_streak = 0

    for index, action in enumerate(actions, start=1):
        duration = float(ACTION_DURATIONS_HOURS.get(action, 1.0))
        study_load = float(ACTION_STUDY_LOAD.get(action, 0.0))

        next_streak = current_streak + 1 if action == previous_action else 1
        needs_new_day_for_time = (used_hours + duration) > day_capacity + 1e-9
        needs_new_day_for_study = (used_study_hours + study_load) > study_cap + 1e-9
        needs_new_day_for_pacing = next_streak > max_streak
        if needs_new_day_for_time or needs_new_day_for_study or needs_new_day_for_pacing:
            day += 1
            session = 1
            used_hours = 0.0
            used_study_hours = 0.0
            next_streak = 1

        steps.append(
            ScheduledStep(
                index=index,
                day=day,
                session=session,
                action=action,
                duration_hours=duration,
            )
        )

        used_hours += duration
        used_study_hours += study_load
        session += 1
        previous_action = action
        current_streak = next_streak

    return steps


def build_actionable_plan_text(
    result: PlanResult,
    method_results: Dict[str, PlanResult],
    available_hours_per_day: float,
    max_study_hours_per_day: float,
    nice_method_name: Callable[[str], str],
    nice_action_name: Callable[[str], str],
    nice_status_text: Callable[[str], str],
) -> str:
    title = f"PLAN ({nice_method_name(result.algorithm)})"
    divider = "=" * len(title)
    plan_intro = "Note: do urgent work first, then protect your energy."
    lines = [
        divider,
        title,
        divider,
        f"Risk now: {result.risk_before:.2f}",
        f"Daily time: {available_hours_per_day:.1f}h total | {max_study_hours_per_day:.1f}h study",
        plan_intro,
        "",
    ]

    if not result.actions:
        lines.append("No steps found with current settings.")
    else:
        schedule = build_scheduled_steps(
            result.actions,
            available_hours_per_day=available_hours_per_day,
            max_study_hours_per_day=max_study_hours_per_day,
        )
        blocks = _group_steps(schedule)
        lines.extend(["Steps:", "------"])

        current_day = -1
        block_number = 0
        for block in blocks:
            if block.day != current_day:
                current_day = block.day
                block_number = 0
                if lines[-1] != "------":
                    lines.append("")
                lines.append(f"Day {current_day}:")

            block_number += 1
            action_title = nice_action_name(block.action)
            purpose = _action_purpose(block.action)
            repeats = block.end_index - block.start_index + 1

            before_state = result.states[block.start_index - 1]
            after_state = result.states[block.end_index]
            impact = _impact_sentence(before_state, after_state)

            action_phrase = action_title if repeats == 1 else f"{action_title} x{repeats}"
            if block.start_session == block.end_session:
                session_label = f"session {block.start_session}"
            else:
                session_label = f"sessions {block.start_session}-{block.end_session}"
            lines.append(f"  {block_number}. {session_label} | {block.total_duration_hours:.1f}h | {action_phrase}")
            lines.append(f"     Why: {purpose}.")
            lines.append(f"     Result: {impact}")
            if repeats >= 3 and block.action != "Rest":
                lines.append("     Tip: take a short break before next block.")

    lines.extend(
        [
            "",
            "Summary:",
            "--------",
            f"Status: {nice_status_text(result.final_status)}",
            f"Risk after plan: {result.risk_after:.2f}",
            f"Plan cost: {result.total_cost:.2f}",
            f"Nodes checked: {result.expanded_nodes}",
        ]
    )

    if not result.success:
        lines.append("Note: goal not fully reached. This is the best plan found with current limits.")
    else:
        lines.append("Note: this plan reaches the goal with current limits.")

    lines.extend(["", "Other methods:", "--------------"])
    for method_name in ("A* Search", "Greedy Baseline", "Uniform Cost Search"):
        if method_name == result.algorithm:
            continue
        other = method_results.get(method_name)
        if other is None:
            continue
        reached_text = "goal reached" if other.success else "goal not reached"
        lines.append(
            f"- {nice_method_name(method_name)}: {reached_text}; risk {other.risk_after:.2f}; "
            f"cost {other.total_cost:.2f}; nodes {other.expanded_nodes}"
        )

    return "\n".join(lines)
