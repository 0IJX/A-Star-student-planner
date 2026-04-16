from __future__ import annotations

import random
from typing import Dict, List, Tuple

from .models import SimulationConstraints, StudentRecord, StudentState


def list_what_if_presets() -> List[Tuple[str, Dict[str, object]]]:
    return [
        ("Study limit tighter (2h/day)", {"max_study_hours_per_day": 2.0}),
        ("Deadline closer (-3 days)", {"deadline_shift_days": -3}),
        ("Tutor unavailable", {"tutor_available": False}),
    ]


def preset_names() -> List[str]:
    return [item[0] for item in list_what_if_presets()]


def apply_named_preset(base: SimulationConstraints, preset_name: str) -> SimulationConstraints:
    for name, overrides in list_what_if_presets():
        if name == preset_name:
            return base.merged(**overrides)
    return base


def generate_random_record(index: int = 1, seed: int | None = None) -> StudentRecord:
    rng = random.Random(seed)
    record_id = f"S{index:03d}"
    state = StudentState(
        attendance_rate=rng.uniform(45.0, 92.0),
        missing_submissions=rng.randint(0, 5),
        avg_quiz_score=rng.uniform(40.0, 90.0),
        lms_activity=rng.uniform(30.0, 90.0),
        study_hours_per_week=rng.uniform(1.0, 12.0),
        days_to_deadline=rng.randint(1, 20),
        fatigue=rng.uniform(8.0, 72.0),
    ).clamp()
    return StudentRecord(
        student_id=record_id,
        state=state,
        available_hours_per_day=rng.uniform(6.0, 10.0),
    )

