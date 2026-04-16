from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from time import perf_counter
from typing import Callable, Dict, List, Optional, Tuple

from .actions import list_successors
from .models import PlannerSettings, SimulationConstraints, StudentState


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _fast_risk_score(state: StudentState, settings: PlannerSettings) -> float:
    weights = settings.risk.weights
    attendance = 100.0 - state.attendance_rate
    missing = _clamp(float(state.missing_submissions) * 20.0, 0.0, 100.0)
    quiz = 100.0 - state.avg_quiz_score
    lms = 100.0 - state.lms_activity
    study = _clamp((10.0 - state.study_hours_per_week) * 10.0, 0.0, 100.0)
    deadline = _clamp((14.0 - float(state.days_to_deadline)) * (100.0 / 14.0), 0.0, 100.0)
    fatigue = state.fatigue

    score = (
        float(weights.get("attendance", 0.0)) * attendance
        + float(weights.get("missing", 0.0)) * missing
        + float(weights.get("quiz", 0.0)) * quiz
        + float(weights.get("lms", 0.0)) * lms
        + float(weights.get("study", 0.0)) * study
        + float(weights.get("deadline", 0.0)) * deadline
        + float(weights.get("fatigue", 0.0)) * fatigue
    )
    return _clamp(score, 0.0, 100.0)


def _goal_reached(state: StudentState, settings: PlannerSettings, risk_score_fn: Callable[[StudentState], float]) -> bool:
    if risk_score_fn(state) > settings.risk.threshold:
        return False
    if settings.risk.require_zero_missing and state.missing_submissions != 0:
        return False
    return True


@dataclass
class SearchNode:
    priority: float
    g_cost: float
    h_cost: float
    step: int
    state: StudentState
    parent: Optional["SearchNode"] = None
    action_name: Optional[str] = None


@dataclass
class PlanResult:
    algorithm: str
    success: bool
    actions: List[str]
    states: List[StudentState]
    total_cost: float
    risk_before: float
    risk_after: float
    final_status: str
    runtime_ms: float
    expanded_nodes: int

    def action_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for action in self.actions:
            counts[action] = counts.get(action, 0) + 1
        return counts


@dataclass(frozen=True)
class SearchBudget:
    max_expanded_nodes: int
    max_frontier_size: int
    max_runtime_ms: float


def _prepare_initial_state(initial_state: StudentState, constraints: SimulationConstraints) -> StudentState:
    state = initial_state.clamp()
    shifted_days = max(0, state.days_to_deadline + constraints.deadline_shift_days)
    return StudentState(
        attendance_rate=state.attendance_rate,
        missing_submissions=state.missing_submissions,
        avg_quiz_score=state.avg_quiz_score,
        lms_activity=state.lms_activity,
        study_hours_per_week=state.study_hours_per_week,
        days_to_deadline=shifted_days,
        fatigue=state.fatigue,
    ).clamp()


def estimate_remaining_cost(state: StudentState, settings: PlannerSettings) -> float:
    # Admissible/consistent lower bound:
    # if missing submissions must be zero, each Submit_Assignment can reduce at most 1 missing item,
    # and the minimum base submit cost is 2.5, so remaining_missing * 2.5 is a safe lower bound.
    if not settings.risk.require_zero_missing:
        return 0.0
    remaining_missing = max(0, int(state.missing_submissions))
    return float(remaining_missing) * 2.5


def _search_budget(settings: PlannerSettings) -> SearchBudget:
    steps = max(1, int(settings.max_steps))
    max_expanded = 8_000 + (steps * 450)
    max_expanded = max(12_000, min(60_000, max_expanded))
    max_frontier = max_expanded * 2
    max_runtime_ms = max(1_500.0, min(7_000.0, 1_200.0 + (steps * 90.0)))
    return SearchBudget(
        max_expanded_nodes=max_expanded,
        max_frontier_size=max_frontier,
        max_runtime_ms=max_runtime_ms,
    )


def _is_better_progress(
    candidate: SearchNode,
    current_best: SearchNode,
    risk_score_fn: Callable[[StudentState], float],
) -> bool:
    cand_risk = risk_score_fn(candidate.state)
    best_risk = risk_score_fn(current_best.state)
    if cand_risk < best_risk - 1e-9:
        return True
    if abs(cand_risk - best_risk) <= 1e-9 and candidate.state.missing_submissions < current_best.state.missing_submissions:
        return True
    if abs(cand_risk - best_risk) <= 1e-9 and candidate.state.missing_submissions == current_best.state.missing_submissions:
        return candidate.g_cost < current_best.g_cost
    return False


def _reconstruct(node: SearchNode) -> Tuple[List[str], List[StudentState]]:
    actions: List[str] = []
    states: List[StudentState] = []
    current: Optional[SearchNode] = node
    while current is not None:
        states.append(current.state)
        if current.action_name:
            actions.append(current.action_name)
        current = current.parent
    actions.reverse()
    states.reverse()
    return actions, states


def _to_result(
    algorithm: str,
    node: SearchNode,
    success: bool,
    risk_before: float,
    runtime_ms: float,
    expanded_nodes: int,
    settings: PlannerSettings,
    risk_score_fn: Optional[Callable[[StudentState], float]] = None,
) -> PlanResult:
    actions, states = _reconstruct(node)
    score_fn = risk_score_fn or (lambda s: _fast_risk_score(s, settings))
    risk_after = score_fn(node.state)
    final_status = "Not At-Risk" if _goal_reached(node.state, settings, score_fn) else "At-Risk"
    return PlanResult(
        algorithm=algorithm,
        success=success,
        actions=actions,
        states=states,
        total_cost=float(node.g_cost),
        risk_before=float(risk_before),
        risk_after=float(risk_after),
        final_status=final_status,
        runtime_ms=runtime_ms,
        expanded_nodes=int(expanded_nodes),
    )


def _push_node(
    heap: list[tuple[float, float, float, int, SearchNode]],
    node: SearchNode,
    tie_primary: float,
    tie_secondary: float,
    serial: int,
) -> None:
    # Deterministic frontier ordering:
    # 1) priority (f, g, or h depending on algorithm)
    # 2) tie_primary (usually lower h or fewer missing submissions)
    # 3) tie_secondary (usually lower g)
    # 4) insertion serial
    heappush(heap, (node.priority, tie_primary, tie_secondary, serial, node))


def run_a_star(
    initial_state: StudentState,
    settings: PlannerSettings,
    constraints: SimulationConstraints,
) -> PlanResult:
    start_time = perf_counter()
    start_state = _prepare_initial_state(initial_state, constraints)
    risk_cache: Dict[tuple[int, int, int, int, int, int, int], float] = {}

    def risk_score(state: StudentState) -> float:
        key = state.key()
        cached = risk_cache.get(key)
        if cached is not None:
            return cached
        value = _fast_risk_score(state, settings)
        risk_cache[key] = value
        return value

    risk_before = risk_score(start_state)

    start_h = estimate_remaining_cost(start_state, settings)
    start_node = SearchNode(
        priority=start_h,
        g_cost=0.0,
        h_cost=start_h,
        step=0,
        state=start_state,
    )

    open_heap: List[tuple[float, float, float, int, SearchNode]] = []
    push_serial = 0
    _push_node(open_heap, start_node, start_h, 0.0, push_serial)
    best_g: Dict[tuple[int, int, int, int, int, int, int], float] = {start_state.key(): 0.0}
    expanded = 0
    best_progress = start_node
    budget = _search_budget(settings)

    while open_heap:
        if expanded >= budget.max_expanded_nodes:
            break
        if len(open_heap) > budget.max_frontier_size:
            break
        if (perf_counter() - start_time) * 1000.0 >= budget.max_runtime_ms:
            break

        current = heappop(open_heap)[-1]
        current_key = current.state.key()
        best_for_current = best_g.get(current_key)
        if best_for_current is not None and current.g_cost > best_for_current + 1e-9:
            continue
        expanded += 1

        if _goal_reached(current.state, settings, risk_score):
            runtime_ms = (perf_counter() - start_time) * 1000.0
            return _to_result("A* Search", current, True, risk_before, runtime_ms, expanded, settings, risk_score)

        if current.step >= settings.max_steps:
            if _is_better_progress(current, best_progress, risk_score):
                best_progress = current
            continue

        if _is_better_progress(current, best_progress, risk_score):
            best_progress = current

        for action_name, next_state, action_cost in list_successors(current.state, constraints):
            next_g = current.g_cost + action_cost
            next_key = next_state.key()
            prev_best = best_g.get(next_key)
            if prev_best is not None and next_g >= prev_best - 1e-9:
                continue

            best_g[next_key] = next_g
            next_risk = risk_score(next_state)
            next_h = estimate_remaining_cost(next_state, settings)
            child = SearchNode(
                priority=next_g + next_h,
                g_cost=next_g,
                h_cost=next_h,
                step=current.step + 1,
                state=next_state,
                parent=current,
                action_name=action_name,
            )
            push_serial += 1
            _push_node(
                open_heap,
                child,
                tie_primary=next_h,
                tie_secondary=next_g,
                serial=push_serial,
            )

    runtime_ms = (perf_counter() - start_time) * 1000.0
    return _to_result("A* Search", best_progress, False, risk_before, runtime_ms, expanded, settings, risk_score)


def run_uniform_cost_search(
    initial_state: StudentState,
    settings: PlannerSettings,
    constraints: SimulationConstraints,
) -> PlanResult:
    start_time = perf_counter()
    start_state = _prepare_initial_state(initial_state, constraints)
    risk_cache: Dict[tuple[int, int, int, int, int, int, int], float] = {}

    def risk_score(state: StudentState) -> float:
        key = state.key()
        cached = risk_cache.get(key)
        if cached is not None:
            return cached
        value = _fast_risk_score(state, settings)
        risk_cache[key] = value
        return value

    risk_before = risk_score(start_state)

    start_node = SearchNode(
        priority=0.0,
        g_cost=0.0,
        h_cost=0.0,
        step=0,
        state=start_state,
    )

    open_heap: List[tuple[float, float, float, int, SearchNode]] = []
    push_serial = 0
    _push_node(open_heap, start_node, 0.0, 0.0, push_serial)
    best_g: Dict[tuple[int, int, int, int, int, int, int], float] = {start_state.key(): 0.0}
    expanded = 0
    best_progress = start_node
    budget = _search_budget(settings)

    while open_heap:
        if expanded >= budget.max_expanded_nodes:
            break
        if len(open_heap) > budget.max_frontier_size:
            break
        if (perf_counter() - start_time) * 1000.0 >= budget.max_runtime_ms:
            break

        current = heappop(open_heap)[-1]
        current_key = current.state.key()
        best_for_current = best_g.get(current_key)
        if best_for_current is not None and current.g_cost > best_for_current + 1e-9:
            continue
        expanded += 1

        if _goal_reached(current.state, settings, risk_score):
            runtime_ms = (perf_counter() - start_time) * 1000.0
            return _to_result("Uniform Cost Search", current, True, risk_before, runtime_ms, expanded, settings, risk_score)

        if current.step >= settings.max_steps:
            if _is_better_progress(current, best_progress, risk_score):
                best_progress = current
            continue

        if _is_better_progress(current, best_progress, risk_score):
            best_progress = current

        for action_name, next_state, action_cost in list_successors(current.state, constraints):
            next_g = current.g_cost + action_cost
            next_key = next_state.key()
            prev_best = best_g.get(next_key)
            if prev_best is not None and next_g >= prev_best - 1e-9:
                continue

            best_g[next_key] = next_g
            child = SearchNode(
                priority=next_g,
                g_cost=next_g,
                h_cost=0.0,
                step=current.step + 1,
                state=next_state,
                parent=current,
                action_name=action_name,
            )
            push_serial += 1
            _push_node(
                open_heap,
                child,
                tie_primary=float(next_state.missing_submissions),
                tie_secondary=next_g,
                serial=push_serial,
            )

    runtime_ms = (perf_counter() - start_time) * 1000.0
    return _to_result("Uniform Cost Search", best_progress, False, risk_before, runtime_ms, expanded, settings, risk_score)


def run_greedy(
    initial_state: StudentState,
    settings: PlannerSettings,
    constraints: SimulationConstraints,
) -> PlanResult:
    start_time = perf_counter()
    start_state = _prepare_initial_state(initial_state, constraints)
    risk_cache: Dict[tuple[int, int, int, int, int, int, int], float] = {}

    def risk_score(state: StudentState) -> float:
        key = state.key()
        cached = risk_cache.get(key)
        if cached is not None:
            return cached
        value = _fast_risk_score(state, settings)
        risk_cache[key] = value
        return value

    def heuristic(state: StudentState) -> float:
        # Greedy is an informed baseline (not guaranteed optimal):
        # lower missing first, then lower risk gap.
        admissible_part = estimate_remaining_cost(state, settings)
        risk_gap = max(0.0, risk_score(state) - settings.risk.threshold)
        return admissible_part + (0.04 * risk_gap)

    risk_before = risk_score(start_state)

    start_h = heuristic(start_state)
    start_node = SearchNode(
        priority=start_h,
        g_cost=0.0,
        h_cost=start_h,
        step=0,
        state=start_state,
    )
    open_heap: List[tuple[float, float, float, int, SearchNode]] = []
    push_serial = 0
    _push_node(open_heap, start_node, start_h, 0.0, push_serial)
    best_seen: Dict[tuple[int, int, int, int, int, int, int], tuple[float, float]] = {
        start_state.key(): (start_h, 0.0)
    }
    expanded = 0
    best_progress = start_node
    budget = _search_budget(settings)

    while open_heap:
        if expanded >= budget.max_expanded_nodes:
            break
        if len(open_heap) > budget.max_frontier_size:
            break
        if (perf_counter() - start_time) * 1000.0 >= budget.max_runtime_ms:
            break

        current = heappop(open_heap)[-1]
        current_key = current.state.key()
        best_known = best_seen.get(current_key)
        if best_known is not None:
            best_h, best_g = best_known
            stale_h = current.h_cost > best_h + 1e-9
            stale_g = abs(current.h_cost - best_h) <= 1e-9 and current.g_cost > best_g + 1e-9
            if stale_h or stale_g:
                continue

        expanded += 1
        if _goal_reached(current.state, settings, risk_score):
            runtime_ms = (perf_counter() - start_time) * 1000.0
            return _to_result("Greedy Baseline", current, True, risk_before, runtime_ms, expanded, settings, risk_score)

        if current.step >= settings.max_steps:
            if _is_better_progress(current, best_progress, risk_score):
                best_progress = current
            continue

        if _is_better_progress(current, best_progress, risk_score):
            best_progress = current

        for action_name, next_state, action_cost in list_successors(current.state, constraints):
            next_h = heuristic(next_state)
            next_g = current.g_cost + action_cost
            next_key = next_state.key()
            prev = best_seen.get(next_key)
            if prev is not None:
                prev_h, prev_g = prev
                worse_h = next_h > prev_h + 1e-9
                worse_g = abs(next_h - prev_h) <= 1e-9 and next_g >= prev_g - 1e-9
                if worse_h or worse_g:
                    continue

            best_seen[next_key] = (next_h, next_g)
            child = SearchNode(
                priority=next_h,
                g_cost=next_g,
                h_cost=next_h,
                step=current.step + 1,
                state=next_state,
                parent=current,
                action_name=action_name,
            )
            push_serial += 1
            _push_node(
                open_heap,
                child,
                tie_primary=float(next_state.missing_submissions),
                tie_secondary=next_g,
                serial=push_serial,
            )

    runtime_ms = (perf_counter() - start_time) * 1000.0
    success = _goal_reached(best_progress.state, settings, risk_score)
    return _to_result("Greedy Baseline", best_progress, success, risk_before, runtime_ms, expanded, settings, risk_score)


def comparison_rows(*results: PlanResult) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for result in results:
        rows.append(
            {
                "method": result.algorithm,
                "status": result.final_status,
                "total_cost": round(result.total_cost, 2),
                "runtime_ms": round(result.runtime_ms, 2),
                "expanded_nodes": result.expanded_nodes,
                "risk_after": round(result.risk_after, 2),
            }
        )
    return rows
