from __future__ import annotations

from typing import Callable, Dict, List


def _as_float(row: Dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _as_int(row: Dict[str, object], key: str, default: int = 0) -> int:
    try:
        return int(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _row_status_text(row: Dict[str, object], nice_status_text: Callable[[str], str]) -> str:
    raw_status = str(row.get("final_status", "")).strip() or "Unknown"
    pretty = nice_status_text(raw_status)
    if bool(row.get("success")):
        return pretty
    return f"{pretty} (goal not reached)"


def build_what_if_text(rows: List[Dict[str, object]], nice_status_text: Callable[[str], str]) -> str:
    if not rows:
        return "WHAT-IF CHECK\n============\nNo what-if results yet."

    total = len(rows)
    success_count = sum(1 for row in rows if bool(row.get("success")))
    avg_risk = sum(_as_float(row, "risk_after") for row in rows) / max(1, total)

    best = min(
        rows,
        key=lambda row: (_as_float(row, "risk_after", 10_000.0), _as_float(row, "total_cost", 10_000.0)),
    )
    best_name = str(best.get("case", "Unknown case"))
    best_risk = _as_float(best, "risk_after")
    best_cost = _as_float(best, "total_cost")

    lines = [
        "WHAT-IF CHECK",
        "============",
        f"Cases run: {total}",
        f"Cases that reached goal: {success_count}/{total}",
        f"Average risk after: {avg_risk:.2f}",
        f"Best case: {best_name} (risk {best_risk:.2f}, cost {best_cost:.2f})",
        "",
        "Case details:",
        "------------",
    ]

    for index, row in enumerate(rows, start=1):
        case_name = str(row.get("case", f"Case {index}"))
        status_text = _row_status_text(row, nice_status_text)
        risk_after = _as_float(row, "risk_after")
        total_cost = _as_float(row, "total_cost")
        steps = _as_int(row, "steps")
        nodes = _as_int(row, "expanded_nodes")
        lines.extend(
            [
                f"{index}. {case_name}",
                f"   Result: {status_text}",
                f"   Risk after: {risk_after:.2f}",
                f"   Cost: {total_cost:.2f}",
                f"   Steps: {steps}",
                f"   Nodes checked: {nodes}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()
