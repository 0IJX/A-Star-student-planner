from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


def default_weights() -> Dict[str, float]:
    return {
        "attendance": 0.30,
        "missing": 0.25,
        "quiz": 0.20,
        "lms": 0.10,
        "study": 0.08,
        "deadline": 0.04,
        "fatigue": 0.03,
    }


@dataclass(frozen=True)
class StudentState:
    attendance_rate: float
    missing_submissions: int
    avg_quiz_score: float
    lms_activity: float
    study_hours_per_week: float
    days_to_deadline: int
    fatigue: float = 20.0

    def clamp(self) -> "StudentState":
        return StudentState(
            attendance_rate=max(0.0, min(100.0, float(self.attendance_rate))),
            missing_submissions=max(0, int(round(self.missing_submissions))),
            avg_quiz_score=max(0.0, min(100.0, float(self.avg_quiz_score))),
            lms_activity=max(0.0, min(100.0, float(self.lms_activity))),
            study_hours_per_week=max(0.0, min(40.0, float(self.study_hours_per_week))),
            days_to_deadline=max(0, int(round(self.days_to_deadline))),
            fatigue=max(0.0, min(100.0, float(self.fatigue))),
        )

    def key(self) -> tuple[int, int, int, int, int, int, int]:
        attendance = max(0.0, min(100.0, float(self.attendance_rate)))
        missing = max(0, int(round(self.missing_submissions)))
        quiz = max(0.0, min(100.0, float(self.avg_quiz_score)))
        lms = max(0.0, min(100.0, float(self.lms_activity)))
        study = max(0.0, min(40.0, float(self.study_hours_per_week)))
        deadline = max(0, int(round(self.days_to_deadline)))
        fatigue = max(0.0, min(100.0, float(self.fatigue)))
        return (
            int(round(attendance * 10)),
            int(missing),
            int(round(quiz * 10)),
            int(round(lms * 10)),
            int(round(study * 10)),
            int(deadline),
            int(round(fatigue * 10)),
        )


@dataclass(frozen=True)
class StudentRecord:
    student_id: str
    state: StudentState
    available_hours_per_day: float = 8.0


@dataclass(frozen=True)
class RiskConfig:
    threshold: float = 35.0
    require_zero_missing: bool = True
    weights: Dict[str, float] = field(default_factory=default_weights)


@dataclass(frozen=True)
class PlannerSettings:
    risk: RiskConfig = field(default_factory=RiskConfig)
    max_steps: int = 18


@dataclass(frozen=True)
class SimulationConstraints:
    max_study_hours_per_day: float = 4.0
    tutor_available: bool = True
    deadline_shift_days: int = 0
    available_hours_per_day: float = 8.0

    def merged(self, **overrides: object) -> "SimulationConstraints":
        data = {
            "max_study_hours_per_day": self.max_study_hours_per_day,
            "tutor_available": self.tutor_available,
            "deadline_shift_days": self.deadline_shift_days,
            "available_hours_per_day": self.available_hours_per_day,
        }
        data.update(overrides)
        return SimulationConstraints(
            max_study_hours_per_day=float(data["max_study_hours_per_day"]),
            tutor_available=bool(data["tutor_available"]),
            deadline_shift_days=int(data["deadline_shift_days"]),
            available_hours_per_day=max(1.0, float(data["available_hours_per_day"])),
        )
