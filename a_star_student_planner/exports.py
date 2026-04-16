from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable

from .models import PlannerSettings, SimulationConstraints
from .planner import PlanResult, comparison_rows


def ensure_output_dir(path: str | Path) -> Path:
    output = Path(path)
    output.mkdir(parents=True, exist_ok=True)
    return output


def export_plan_csv(path: str | Path, result: PlanResult) -> Path:
    out = Path(path)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "action"])
        for i, action in enumerate(result.actions, start=1):
            writer.writerow([i, action])
    return out


def export_comparison_csv(path: str | Path, *results: PlanResult) -> Path:
    out = Path(path)
    rows = comparison_rows(*results)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "status", "total_cost", "runtime_ms", "expanded_nodes", "risk_after"])
        writer.writeheader()
        writer.writerows(rows)
    return out


def export_what_if_csv(path: str | Path, rows: Iterable[Dict[str, object]]) -> Path:
    out = Path(path)
    fieldnames = ["case", "success", "final_status", "total_cost", "risk_after", "steps", "expanded_nodes"]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return out


def export_summary_json(
    path: str | Path,
    student_id: str,
    a_star_result: PlanResult,
    greedy_result: PlanResult,
    uniform_cost_result: PlanResult,
    settings: PlannerSettings,
    constraints: SimulationConstraints,
) -> Path:
    out = Path(path)
    payload = {
        "student_id": student_id,
        "settings": {
            "threshold": settings.risk.threshold,
            "require_zero_missing": settings.risk.require_zero_missing,
            "weights": settings.risk.weights,
            "max_steps": settings.max_steps,
        },
        "constraints": {
            "max_study_hours_per_day": constraints.max_study_hours_per_day,
            "tutor_available": constraints.tutor_available,
            "deadline_shift_days": constraints.deadline_shift_days,
            "available_hours_per_day": constraints.available_hours_per_day,
        },
        "results": comparison_rows(a_star_result, greedy_result, uniform_cost_result),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def export_all(
    output_dir: str | Path,
    student_id: str,
    a_star_result: PlanResult,
    greedy_result: PlanResult,
    uniform_cost_result: PlanResult,
    what_if_rows: Iterable[Dict[str, object]],
    settings: PlannerSettings,
    constraints: SimulationConstraints,
) -> Dict[str, str]:
    out_dir = ensure_output_dir(output_dir)
    paths = {
        "summary": str(
            export_summary_json(
                out_dir / "summary.json",
                student_id,
                a_star_result,
                greedy_result,
                uniform_cost_result,
                settings,
                constraints,
            )
        ),
        "a_star_plan": str(export_plan_csv(out_dir / "a_star_plan_steps.csv", a_star_result)),
        "greedy_plan": str(export_plan_csv(out_dir / "greedy_plan_steps.csv", greedy_result)),
        "ucs_plan": str(export_plan_csv(out_dir / "ucs_plan_steps.csv", uniform_cost_result)),
        "comparison": str(export_comparison_csv(out_dir / "comparison_table.csv", a_star_result, greedy_result, uniform_cost_result)),
        "what_if": str(export_what_if_csv(out_dir / "what_if_cases.csv", what_if_rows)),
    }
    return paths

