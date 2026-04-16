from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from .models import PlannerSettings
from .planner import PlanResult


def _pretty_action_name(name: str) -> str:
    alias = {
        "Attend_Class": "Attend",
        "Study_1_Hour": "Study 1h",
        "Submit_Assignment": "Submit",
        "Practice_Quiz": "Quiz",
        "Meet_Tutor": "Tutor",
        "Rest": "Rest",
    }
    if name in alias:
        return alias[name]
    cleaned = name.replace("_", " ").strip()
    if len(cleaned) <= 14:
        return cleaned
    return f"{cleaned[:12]}.."


def _method_label(name: str) -> str:
    return {
        "A* Search": "A*",
        "Greedy Baseline": "Greedy",
        "Uniform Cost Search": "UCS",
    }.get(name, name)


def draw_result_charts(
    figure: Figure,
    a_star_result: PlanResult,
    greedy_result: PlanResult,
    uniform_cost_result: PlanResult,
    active_method_name: str,
    palette: dict[str, str],
    settings: PlannerSettings | None = None,
) -> None:
    """Draw simple comparison + action-count charts for class presentation."""
    figure.clear()
    figure.set_facecolor(palette["panel_bg"])
    figure.set_layout_engine(None)
    left = 0.06
    right = 0.96
    bottom = 0.09
    top = 0.95
    hspace = 0.24
    figure.subplots_adjust(left=left, right=right, bottom=bottom, top=top, hspace=hspace)

    _ = settings
    grid = figure.add_gridspec(2, 1, height_ratios=[1.0, 1.0], hspace=hspace)
    ax_risk = figure.add_subplot(grid[0, 0])
    ax_counts = figure.add_subplot(grid[1, 0])

    for axis in (ax_risk, ax_counts):
        axis.set_facecolor(palette["panel_bg"])
        axis.tick_params(colors=palette["muted"])
        axis.set_axisbelow(True)
        for spine in axis.spines.values():
            spine.set_color(palette["border"])
    before_color = "#96A0AA"  # muted gray-blue
    after_color = "#B4BBC3"   # muted light gray
    count_color = "#8A939D"   # muted medium gray

    results = [a_star_result, greedy_result, uniform_cost_result]
    active_result = next((item for item in results if item.algorithm == active_method_name), a_star_result)
    labels = [_method_label(r.algorithm) for r in results]
    before_vals = [float(result.risk_before) for result in results]
    after_vals = [float(result.risk_after) for result in results]
    x_positions = list(range(len(results)))
    width_bar = 0.34

    before_pos = [x - width_bar / 2 for x in x_positions]
    after_pos = [x + width_bar / 2 for x in x_positions]

    before_bars = ax_risk.bar(
        before_pos,
        before_vals,
        width=width_bar,
        color=before_color,
        edgecolor=palette["border"],
        linewidth=0.6,
        label="Before",
    )
    after_bars = ax_risk.bar(
        after_pos,
        after_vals,
        width=width_bar,
        color=after_color,
        edgecolor=palette["border"],
        linewidth=0.6,
        label="After",
    )
    ax_risk.set_xticks(x_positions)
    ax_risk.set_xticklabels(labels)
    ax_risk.set_title("Risk Before vs After", loc="left", color=palette["text"], pad=8)
    ax_risk.set_ylabel("Risk", color=palette["muted"])
    ax_risk.tick_params(axis="x", pad=3)
    ax_risk.set_ylim(0, 100)
    ax_risk.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax_risk.grid(axis="y", linestyle="-", linewidth=0.7, color=palette["border"], alpha=0.5)
    for tick_label, _result in zip(ax_risk.get_xticklabels(), results):
        tick_label.set_color(palette["muted"])
        tick_label.set_fontweight("normal")
    for bar in [*before_bars, *after_bars]:
        ax_risk.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.0,
            f"{bar.get_height():.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
            color=palette["muted"],
        )
    risk_legend = ax_risk.legend(frameon=False, loc="upper right")
    for text in risk_legend.get_texts():
        text.set_color(palette["muted"])

    counts = active_result.action_counts()
    action_names = [_pretty_action_name(name) for name in counts.keys()]
    action_values = list(counts.values())
    if action_names:
        bars = ax_counts.bar(action_names, action_values, color=count_color, edgecolor=palette["border"], linewidth=0.6)
        ax_counts.set_ylim(0, max(1.0, float(max(action_values)) + 0.5))
        ax_counts.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax_counts.grid(axis="y", linestyle="-", linewidth=0.7, color=palette["border"], alpha=0.5)
        ax_counts.margins(x=0.05)
        if len(action_names) > 2:
            ax_counts.tick_params(axis="x", labelrotation=22)
        for bar, value in zip(bars, action_values):
            ax_counts.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{value}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=palette["muted"],
            )
    else:
        ax_counts.text(
            0.5,
            0.5,
            "No actions",
            ha="center",
            va="center",
            transform=ax_counts.transAxes,
            color=palette["muted"],
        )
        ax_counts.set_ylim(0, 1)
        ax_counts.margins(x=0.08)

    ax_counts.set_title("Action counts", loc="left", color=palette["text"], pad=8)
    ax_counts.set_ylabel("Count", color=palette["muted"])
    ax_counts.tick_params(axis="x", pad=3)

    # Visual separator between top and bottom charts.
    top_pos = ax_risk.get_position()
    bottom_pos = ax_counts.get_position()
    mid_y = (top_pos.y0 + bottom_pos.y1) / 2.0
    separator = Line2D(
        [left, right],
        [mid_y, mid_y],
        transform=figure.transFigure,
        color=palette["border"],
        linewidth=1.05,
        alpha=0.9,
    )
    figure.add_artist(separator)

    if figure.canvas is not None:
        figure.canvas.draw_idle()
