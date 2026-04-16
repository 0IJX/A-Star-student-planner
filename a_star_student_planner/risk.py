from __future__ import annotations

from typing import Dict

from .models import PlannerSettings, RiskConfig, StudentState


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def risk_components(state: StudentState, risk_config: RiskConfig) -> Dict[str, float]:
    s = state.clamp()
    components = {
        "attendance": 100.0 - s.attendance_rate,
        "missing": _clamp(float(s.missing_submissions) * 20.0, 0.0, 100.0),
        "quiz": 100.0 - s.avg_quiz_score,
        "lms": 100.0 - s.lms_activity,
        "study": _clamp((10.0 - s.study_hours_per_week) * 10.0, 0.0, 100.0),
        "deadline": _clamp((14.0 - float(s.days_to_deadline)) * (100.0 / 14.0), 0.0, 100.0),
        "fatigue": s.fatigue,
    }

    score = 0.0
    for key, weight in risk_config.weights.items():
        score += float(weight) * components.get(key, 0.0)
    components["total"] = _clamp(score, 0.0, 100.0)
    return components


def compute_risk_score(state: StudentState, risk_config: RiskConfig) -> float:
    return risk_components(state, risk_config)["total"]


def is_not_at_risk(state: StudentState, settings: PlannerSettings) -> bool:
    score = compute_risk_score(state, settings.risk)
    if score > settings.risk.threshold:
        return False
    if settings.risk.require_zero_missing and state.missing_submissions != 0:
        return False
    return True

