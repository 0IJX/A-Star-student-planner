from __future__ import annotations

from typing import List, Tuple

from .models import SimulationConstraints, StudentState


ACTION_NAMES = [
    "Attend_Class",
    "Study_1_Hour",
    "Submit_Assignment",
    "Practice_Quiz",
    "Meet_Tutor",
    "Rest",
]

ACTION_DURATIONS_HOURS = {
    "Attend_Class": 2.0,
    "Study_1_Hour": 1.0,
    "Submit_Assignment": 1.0,
    "Practice_Quiz": 1.0,
    "Meet_Tutor": 1.0,
    "Rest": 2.0,
}

ACTION_STUDY_LOAD = {
    "Attend_Class": 0.3,
    "Study_1_Hour": 1.0,
    "Submit_Assignment": 0.0,
    "Practice_Quiz": 0.8,
    "Meet_Tutor": 0.7,
    "Rest": 0.0,
}


def _urgency_penalty(days_to_deadline: int) -> float:
    return 0.8 if days_to_deadline <= 3 else 0.4 if days_to_deadline <= 7 else 0.0


def _fatigue_penalty(fatigue: float) -> float:
    return 0.6 if fatigue >= 75 else 0.25 if fatigue >= 50 else 0.0


def is_action_allowed(action_name: str, state: StudentState, constraints: SimulationConstraints) -> bool:
    if action_name == "Meet_Tutor" and not constraints.tutor_available:
        return False
    if action_name == "Submit_Assignment" and state.missing_submissions <= 0:
        return False
    if action_name == "Study_1_Hour":
        weekly_cap = constraints.max_study_hours_per_day * 7.0
        if state.study_hours_per_week >= weekly_cap:
            return False
    if action_name == "Rest" and state.fatigue <= 5.0:
        return False
    return True


def apply_action(
    action_name: str,
    state: StudentState,
    constraints: SimulationConstraints,
) -> Tuple[StudentState, float]:
    s = state.clamp()
    urgency = _urgency_penalty(s.days_to_deadline)
    fatigue_penalty = _fatigue_penalty(s.fatigue)

    if action_name == "Attend_Class":
        next_state = StudentState(
            attendance_rate=s.attendance_rate + 3.0,
            missing_submissions=s.missing_submissions,
            avg_quiz_score=s.avg_quiz_score + 0.5,
            lms_activity=s.lms_activity + 5.0,
            study_hours_per_week=s.study_hours_per_week + 0.2,
            days_to_deadline=s.days_to_deadline,
            fatigue=s.fatigue + 4.0,
        )
        return next_state.clamp(), 1.2 + urgency + fatigue_penalty

    if action_name == "Study_1_Hour":
        next_state = StudentState(
            attendance_rate=s.attendance_rate,
            missing_submissions=s.missing_submissions,
            avg_quiz_score=s.avg_quiz_score + 2.8,
            lms_activity=s.lms_activity + 1.8,
            study_hours_per_week=s.study_hours_per_week + 1.0,
            days_to_deadline=s.days_to_deadline,
            fatigue=s.fatigue + 6.0,
        )
        return next_state.clamp(), 1.4 + urgency + fatigue_penalty

    if action_name == "Submit_Assignment":
        next_state = StudentState(
            attendance_rate=s.attendance_rate,
            missing_submissions=max(0, s.missing_submissions - 1),
            avg_quiz_score=s.avg_quiz_score + 0.5,
            lms_activity=s.lms_activity + 1.0,
            study_hours_per_week=s.study_hours_per_week + 0.2,
            days_to_deadline=s.days_to_deadline,
            fatigue=s.fatigue + 5.0,
        )
        return next_state.clamp(), 2.5 + urgency + fatigue_penalty

    if action_name == "Practice_Quiz":
        next_state = StudentState(
            attendance_rate=s.attendance_rate,
            missing_submissions=s.missing_submissions,
            avg_quiz_score=s.avg_quiz_score + 4.0,
            lms_activity=s.lms_activity + 2.0,
            study_hours_per_week=s.study_hours_per_week + 0.6,
            days_to_deadline=s.days_to_deadline,
            fatigue=s.fatigue + 5.0,
        )
        return next_state.clamp(), 1.7 + urgency + fatigue_penalty

    if action_name == "Meet_Tutor":
        next_state = StudentState(
            attendance_rate=s.attendance_rate + 1.0,
            missing_submissions=s.missing_submissions,
            avg_quiz_score=s.avg_quiz_score + 6.0,
            lms_activity=s.lms_activity + 3.0,
            study_hours_per_week=s.study_hours_per_week + 0.8,
            days_to_deadline=s.days_to_deadline,
            fatigue=s.fatigue + 4.0,
        )
        return next_state.clamp(), 2.1 + urgency + fatigue_penalty

    if action_name == "Rest":
        next_state = StudentState(
            attendance_rate=s.attendance_rate,
            missing_submissions=s.missing_submissions,
            avg_quiz_score=s.avg_quiz_score,
            lms_activity=s.lms_activity + 0.5,
            study_hours_per_week=s.study_hours_per_week,
            days_to_deadline=max(0, s.days_to_deadline - 1),
            fatigue=s.fatigue - 12.0,
        )
        return next_state.clamp(), 0.8 + urgency

    raise ValueError(f"Unknown action: {action_name}")


def list_successors(state: StudentState, constraints: SimulationConstraints) -> List[Tuple[str, StudentState, float]]:
    successors: List[Tuple[str, StudentState, float]] = []
    for action_name in ACTION_NAMES:
        if not is_action_allowed(action_name, state, constraints):
            continue
        next_state, cost = apply_action(action_name, state, constraints)
        successors.append((action_name, next_state, cost))
    return successors

