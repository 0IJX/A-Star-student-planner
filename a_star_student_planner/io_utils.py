from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from .models import StudentRecord, StudentState


REQUIRED_COLUMNS = [
    "attendance_rate",
    "missing_submissions",
    "avg_quiz_score",
    "lms_activity",
    "study_hours_per_week",
    "days_to_deadline",
]


def _validate_columns(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError("CSV has no header row.")
    missing = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def load_students_csv(path: str | Path) -> List[StudentRecord]:
    csv_path = Path(path)
    records: List[StudentRecord] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _validate_columns(reader.fieldnames)
        for index, row in enumerate(reader, start=1):
            student_id = (row.get("student_id") or "").strip() or f"S{index:03d}"
            state = StudentState(
                attendance_rate=float(row["attendance_rate"]),
                missing_submissions=int(float(row["missing_submissions"])),
                avg_quiz_score=float(row["avg_quiz_score"]),
                lms_activity=float(row["lms_activity"]),
                study_hours_per_week=float(row["study_hours_per_week"]),
                days_to_deadline=int(float(row["days_to_deadline"])),
                fatigue=float(row.get("fatigue", 20.0) or 20.0),
            ).clamp()
            available_hours_raw = row.get("available_hours_per_day", 8.0)
            try:
                available_hours = max(1.0, float(available_hours_raw or 8.0))
            except (TypeError, ValueError):
                available_hours = 8.0
            records.append(
                StudentRecord(
                    student_id=student_id,
                    state=state,
                    available_hours_per_day=available_hours,
                )
            )
    if not records:
        raise ValueError("CSV is empty.")
    return records

