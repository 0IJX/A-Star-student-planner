from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QObject, QPoint, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ..exports import export_all
from ..io_utils import load_students_csv
from ..models import PlannerSettings, RiskConfig, SimulationConstraints, StudentRecord, StudentState
from ..planner import PlanResult, comparison_rows, run_a_star, run_greedy, run_uniform_cost_search
from ..plots import draw_result_charts
from ..risk import compute_risk_score
from ..scenarios import apply_named_preset, generate_random_record, list_what_if_presets, preset_names
from .plan_steps import build_actionable_plan_text
from .theme import available_themes, base_stylesheet, planner_palette, risk_color, risk_status
from .what_if_output import build_what_if_text

SEARCH_METHODS = ["A* Search", "Greedy Baseline", "Uniform Cost Search"]
METHOD_LABELS = {
    "A* Search": "A*",
    "Greedy Baseline": "Greedy",
    "Uniform Cost Search": "UCS",
}
ACTION_LABELS = {
    "Attend_Class": "Go to class",
    "Study_1_Hour": "Study 1 hour",
    "Submit_Assignment": "Submit assignment",
    "Practice_Quiz": "Practice quiz",
    "Meet_Tutor": "Meet tutor",
    "Rest": "Take a break",
}


@dataclass
class SliderSpec:
    key: str
    label: str
    minimum: float
    maximum: float
    default: float
    scale: int
    fmt: str


PARAMETER_SPECS = [
    SliderSpec("attendance_rate", "Attendance Rate", 0.0, 100.0, 75.0, 1, "{:.0f}"),
    SliderSpec("missing_submissions", "Missing Submissions", 0.0, 10.0, 2.0, 1, "{:.0f}"),
    SliderSpec("avg_quiz_score", "Avg Quiz Score", 0.0, 100.0, 60.0, 1, "{:.0f}"),
    SliderSpec("lms_activity", "LMS Activity", 0.0, 100.0, 50.0, 1, "{:.0f}"),
    SliderSpec("study_hours_per_week", "Study Hours / Week", 0.0, 40.0, 6.0, 10, "{:.1f}"),
    SliderSpec("days_to_deadline", "Days to Deadline", 1.0, 30.0, 14.0, 1, "{:.0f}"),
    SliderSpec("fatigue", "Fatigue", 0.0, 100.0, 20.0, 1, "{:.0f}"),
]

WEIGHT_SPECS = [
    ("attendance", "Attendance Weight"),
    ("missing", "Missing Weight"),
    ("quiz", "Quiz Weight"),
    ("lms", "LMS Weight"),
    ("study", "Study Weight"),
    ("deadline", "Deadline Weight"),
    ("fatigue", "Fatigue Weight"),
]

PARAMETER_HELP: Dict[str, str] = {
    "attendance_rate": "Student's class attendance.",
    "missing_submissions": "Assignments not submitted.",
    "avg_quiz_score": "Average quiz score.",
    "lms_activity": "Activity on the online platform.",
    "study_hours_per_week": "Weekly study hours.",
    "days_to_deadline": "Days left for deadlines.",
    "fatigue": "Current tiredness level.",
}

WEIGHT_HELP: Dict[str, str] = {
    "attendance": "How much attendance matters in risk score.",
    "missing": "How much missing work matters in risk score.",
    "quiz": "How much quiz marks matter in risk score.",
    "lms": "How much LMS activity matters in risk score.",
    "study": "How much study time matters in risk score.",
    "deadline": "How much deadline pressure matters in risk score.",
    "fatigue": "How much tiredness matters in risk score.",
}

CONTROL_HELP: Dict[str, str] = {
    "Risk Threshold": "If risk is lower than this, student is okay.",
    "Max Steps": "Maximum steps allowed in one plan.",
    "Max Study Hours / Day": "Study limit per day for what-if.",
    "Deadline Shift (Days)": "Move deadline earlier or later.",
}

METRIC_HELP: Dict[str, str] = {
    "status": "Final planner outcome after actions.",
    "risk_before": "Risk score before planning.",
    "risk_after": "Risk score after planning.",
    "cost": "Total cost of the selected plan.",
    "runtime": "How long the algorithm took to run.",
    "nodes": "How many search nodes were expanded.",
}


class CustomToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet(
            "border-radius:8px; border:1px solid #ddd; color:#222; background:#fff; padding:8px 14px; font-size:13px; font-family:sans-serif; white-space:nowrap;"
        )
        self.hide()

    def show_tooltip(self, text, pos):
        self.setText(text)
        self.adjustSize()
        self.move(pos)
        self.show()

    def hide_tooltip(self):
        self.hide()


class HelpIconLabel(QLabel):
    _custom_tooltip = None  # Shared instance

    def __init__(self, help_text: str, parent: QWidget | None = None) -> None:
        super().__init__("!", parent)
        self._help_text = help_text
        self.setProperty("role", "help_icon")
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        # Keep icon visibly circular even if theme selector isn't applied immediately.
        self.setStyleSheet("border-radius:9px; padding:0;")
        if HelpIconLabel._custom_tooltip is None:
            HelpIconLabel._custom_tooltip = CustomToolTip()

    def enterEvent(self, event) -> None:  # noqa: N802
        # Show custom tooltip above right of the icon
        global_pos = self.mapToGlobal(self.rect().topRight())
        offset = QPoint(12, -self.height() - 12)
        HelpIconLabel._custom_tooltip.show_tooltip(self._help_text, global_pos + offset)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        HelpIconLabel._custom_tooltip.hide_tooltip()
        super().leaveEvent(event)


class PlannerWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        state: StudentState,
        settings: PlannerSettings,
        constraints: SimulationConstraints,
        student_id: str,
    ) -> None:
        super().__init__()
        self.state = state
        self.settings = settings
        self.constraints = constraints
        self.student_id = student_id

    @Slot()
    def run(self) -> None:
        try:
            a_star = run_a_star(self.state, self.settings, self.constraints)
            greedy = run_greedy(self.state, self.settings, self.constraints)
            ucs = run_uniform_cost_search(self.state, self.settings, self.constraints)
            self.finished.emit(
                {
                    "student_id": self.student_id,
                    "settings": self.settings,
                    "constraints": self.constraints,
                    "a_star": a_star,
                    "greedy": greedy,
                    "uniform_cost": ucs,
                }
            )
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


class WhatIfWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        state: StudentState,
        settings: PlannerSettings,
        constraints: SimulationConstraints,
    ) -> None:
        super().__init__()
        self.state = state
        self.settings = settings
        self.constraints = constraints

    @Slot()
    def run(self) -> None:
        try:
            rows: List[Dict[str, object]] = []
            for case_name, overrides in list_what_if_presets():
                case_constraints = self.constraints.merged(**overrides)
                case_result = run_a_star(self.state, self.settings, case_constraints)
                rows.append(
                    {
                        "case": case_name,
                        "success": case_result.success,
                        "final_status": case_result.final_status,
                        "total_cost": round(case_result.total_cost, 2),
                        "risk_after": round(case_result.risk_after, 2),
                        "steps": len(case_result.actions),
                        "expanded_nodes": case_result.expanded_nodes,
                    }
                )
            self.finished.emit(rows)
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.current_theme_name = "Studio Light"
        self.palette = planner_palette(self.current_theme_name)
        self.project_root = self._resolve_project_root()
        self.icon_path = self._resolve_icon_path()
        self.sidebar_icon_path = self._resolve_sidebar_icon_path()
        self.window_icon = self._build_window_icon()
        if self.window_icon is not None:
            self.setWindowIcon(self.window_icon)
        self.records: List[StudentRecord] = []
        self.filtered_records: List[StudentRecord] = []
        self.random_counter = 1
        self.last_run: Optional[Dict[str, object]] = None
        self.last_what_if_rows: List[Dict[str, object]] = []
        self.method_results: Dict[str, PlanResult] = {}
        self.selected_method = "A* Search"
        self._applying_record = False
        self._is_busy = False
        self._planner_thread: Optional[QThread] = None
        self._planner_worker: Optional[PlannerWorker] = None
        self._what_if_thread: Optional[QThread] = None
        self._what_if_worker: Optional[WhatIfWorker] = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview_text)

        self.slider_controls: Dict[str, Dict[str, object]] = {}
        self.weight_controls: Dict[str, Dict[str, object]] = {}
        self.metric_labels: Dict[str, QLabel] = {}
        self.parameter_frames: List[QFrame] = []
        self.weight_frames: List[QFrame] = []
        self.method_buttons: Dict[str, QPushButton] = {}

        self.setWindowTitle("A-Star Student Planner")
        self.resize(1460, 1020)
        self.setMinimumSize(900, 640)
        self.setStyleSheet(base_stylesheet(self.palette))
        # --- Splash screen removed ---

        self._build_ui()
        self._bind_shortcuts()
        self._apply_responsive_layout(self.width())
        self._clear_chart_panel()
        # --- About dialog shortcut ---




    @staticmethod
    def _resolve_project_root() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[2]

    def _resolve_icon_path(self) -> Optional[Path]:
        # Use .ico for Windows, .png for others (future-proof)
        import platform
        candidates = []
        if platform.system() == "Windows":
            candidates.append(self.project_root / "assets" / "app.ico")
            if getattr(sys, "frozen", False):
                candidates.insert(0, Path(sys.executable).resolve().parent / "assets" / "app.ico")
        else:
            candidates.append(self.project_root / "assets" / "kid-icon.png")
        for item in candidates:
            if item.exists():
                return item
        return None

    def _resolve_sidebar_icon_path(self) -> Optional[Path]:
        png_path = self.project_root / "assets" / "kid-icon.png"
        if png_path.exists():
            return png_path
        return self._resolve_icon_path()

    def _build_window_icon(self) -> Optional[QIcon]:
        if self.icon_path is None:
            return None
        src = QPixmap(str(self.icon_path))
        if src.isNull():
            return None
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256, 512):
            icon.addPixmap(src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return icon

    def _icon_pixmap(self, size: int) -> QPixmap:
        if self.icon_path is None:
            return QPixmap()
        src = QPixmap(str(self.icon_path))
        if src.isNull():
            return QPixmap()
        return src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _sidebar_icon_pixmap(self, size: int) -> QPixmap:
        if self.sidebar_icon_path is None:
            return QPixmap()
        src = QPixmap(str(self.sidebar_icon_path))
        if src.isNull():
            return QPixmap()
        return src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    @staticmethod
    def _cover_crop_pixmap(pix: QPixmap, width: int, height: int) -> QPixmap:
        scaled = pix.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - width) // 2)
        y = max(0, (scaled.height() - height) // 2)
        return scaled.copy(x, y, width, height)


    def _card(self, role: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("role", role)
        return frame

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        self.topbar = self._build_topbar()
        root_layout.addWidget(self.topbar)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.main_splitter, 1)

        self.sidebar_scroll, self.sidebar, self.sidebar_layout = self._create_scroll_panel()
        self.main_scroll, self.main_host, self.main_layout = self._create_scroll_panel()

        self.main_splitter.addWidget(self.sidebar_scroll)
        self.main_splitter.addWidget(self.main_scroll)
        self.main_splitter.setSizes([520, 900])

        self._build_sidebar()
        self._build_hero()
        self._build_input()
        self._build_controls()
        self._build_weights()
        self._build_results()

        self._init_status_busy_widgets()
        self.statusBar().showMessage("Ready")

    def _create_scroll_panel(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(10)
        scroll.setWidget(host)
        return scroll, host, layout

    def _build_topbar(self) -> QFrame:
        bar = self._card("topbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(2)
        title = QLabel("A* Student Planner")
        title.setProperty("role", "title")
        title_wrap.addWidget(title)
        layout.addLayout(title_wrap, 1)

        theme_label = QLabel("Color")
        theme_label.setProperty("role", "tiny")
        layout.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(available_themes())
        self.theme_combo.setCurrentText(self.current_theme_name)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.theme_combo.setMinimumWidth(170)
        layout.addWidget(self.theme_combo)

        self.top_reset_btn = QPushButton("Reset All")
        self.top_reset_btn.setProperty("variant", "subtle")
        self.top_reset_btn.clicked.connect(self._reset_controls)
        layout.addWidget(self.top_reset_btn)

        self.top_run_btn = QPushButton("Run Plan")
        self.top_run_btn.clicked.connect(self._on_run_planner)
        layout.addWidget(self.top_run_btn)

        self.top_export_btn = QPushButton("Save Files")
        self.top_export_btn.setProperty("variant", "success")
        self.top_export_btn.clicked.connect(self._on_export)
        layout.addWidget(self.top_export_btn)
        return bar

    def _init_status_busy_widgets(self) -> None:
        self.status_busy_label = QLabel("Running...")
        self.status_busy_label.setProperty("role", "tiny")
        self.status_busy_label.setVisible(False)

        self.status_spinner = QProgressBar()
        self.status_spinner.setRange(0, 0)
        self.status_spinner.setTextVisible(False)
        self.status_spinner.setFixedSize(92, 12)
        self.status_spinner.setVisible(False)
        self._apply_spinner_style()

        self.statusBar().addPermanentWidget(self.status_busy_label)
        self.statusBar().addPermanentWidget(self.status_spinner)

    def _apply_spinner_style(self) -> None:
        if not hasattr(self, "status_spinner"):
            return
        self.status_spinner.setStyleSheet(
            "QProgressBar {"
            f"border: 1px solid {self.palette['border']};"
            f"background: {self.palette['panel_alt']};"
            "border-radius: 6px;"
            "}"
            "QProgressBar::chunk {"
            f"background: {self.palette['accent']};"
            "border-radius: 5px;"
            "}"
        )
        self.status_busy_label.setStyleSheet(
            f"color:{self.palette['muted']};font-size:12px;font-weight:600;padding-right:6px;"
        )

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_run_planner)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._on_export)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self._on_run_what_if)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._reset_controls)

    def _build_sidebar(self) -> None:
        self.sidebar.setProperty("role", "sidebar_surface")
        layout = self.sidebar_layout
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top_card = self._card("card")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(12, 12, 12, 12)
        top_layout.setSpacing(8)

        info_row = QHBoxLayout()

        logo_label = QLabel()
        logo_label.setFixedSize(124, 124)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("background: transparent; margin: 0px; padding: 0px;")
        sidebar_icon = self._sidebar_icon_pixmap(124)
        if not sidebar_icon.isNull():
            logo_label.setPixmap(self._cover_crop_pixmap(sidebar_icon, 124, 124))
        info_row.addWidget(logo_label)

        info = QVBoxLayout()
        title = QLabel("Student Info")
        title.setProperty("role", "section_title")
        info.addWidget(title)
        self.count_label = QLabel("0 students")
        self.count_label.setProperty("role", "tiny")
        info.addWidget(self.count_label)
        self.sidebar_selected_label = QLabel("Chosen: none")
        self.sidebar_selected_label.setProperty("role", "tiny")
        info.addWidget(self.sidebar_selected_label)
        info.addStretch()
        info_row.addLayout(info, 1)
        top_layout.addLayout(info_row)

        self.student_filter = QLineEdit()
        self.student_filter.setPlaceholderText("Find student ID...")
        self.student_filter.textChanged.connect(self._on_student_filter)
        top_layout.addWidget(self.student_filter)

        self.student_combo = QComboBox()
        self.student_combo.addItem("No students loaded")
        self.student_combo.currentTextChanged.connect(self._on_student_selected)
        top_layout.addWidget(self.student_combo)

        self.sidebar_preview = QTextEdit()
        self.sidebar_preview.setReadOnly(True)
        self.sidebar_preview.setMinimumHeight(90)
        self.sidebar_preview.setStyleSheet("font-family:Consolas;font-size:12px;")
        self.sidebar_preview.setPlainText("Open a CSV or make a random student to start.")
        top_layout.addWidget(self.sidebar_preview)
        layout.addWidget(top_card)

        action_card = self._card("card")
        a = QVBoxLayout(action_card)
        a.setContentsMargins(12, 12, 12, 12)
        a.setSpacing(8)
        a_title = QLabel("Quick Buttons")
        a_title.setProperty("role", "section_title")
        a.addWidget(a_title)

        row1 = QHBoxLayout()
        self.load_csv_btn = QPushButton("Open CSV")
        self.load_csv_btn.clicked.connect(self._on_load_csv)
        row1.addWidget(self.load_csv_btn)
        a.addLayout(row1)

        row2 = QHBoxLayout()
        self.random_btn = QPushButton("Make Random Student")
        self.random_btn.clicked.connect(self._on_generate)
        row2.addWidget(self.random_btn)
        self.reset_controls_btn = QPushButton("Reset All")
        self.reset_controls_btn.setProperty("variant", "subtle")
        self.reset_controls_btn.clicked.connect(self._reset_controls)
        row2.addWidget(self.reset_controls_btn)
        a.addLayout(row2)
        layout.addWidget(action_card)

        risk_card = self._card("card")
        r = QVBoxLayout(risk_card)
        r.setContentsMargins(12, 12, 12, 12)
        r.setSpacing(8)
        r_title = QLabel("Risk Right Now")
        r_title.setProperty("role", "section_title")
        r.addWidget(r_title)
        self.risk_display = QLabel("0.00")
        self.risk_display.setStyleSheet("font-size:36px;font-weight:700;")
        r.addWidget(self.risk_display)
        self.risk_state = QLabel("Waiting...")
        self.risk_state.setProperty("role", "tiny")
        self.risk_state.setFrameShape(QFrame.NoFrame)
        r.addWidget(self.risk_state)
        self.risk_progress = QProgressBar()
        self.risk_progress.setRange(0, 100)
        self.risk_progress.setValue(0)
        self.risk_progress.setFormat("")
        r.addWidget(self.risk_progress)
        self.projected = QLabel("After plan: -")
        self.projected.setProperty("role", "tiny")
        r.addWidget(self.projected)
        layout.addWidget(risk_card)

        layout.addStretch()

    def _build_hero(self) -> None:
        self.hero = self._card("hero")
        l = QVBoxLayout(self.hero)
        l.setContentsMargins(18, 16, 18, 16)
        l.setSpacing(8)

        title = QLabel("Plan Settings")
        title.setProperty("role", "section_title")
        l.addWidget(title)

    

        chips = QHBoxLayout()
        chips.setSpacing(10)
        self.dataset_chip = QLabel("Students: 0")
        self.dataset_chip.setProperty("role", "tiny")
        chips.addWidget(self.dataset_chip)
        self.student_chip = QLabel("Chosen: none")
        self.student_chip.setProperty("role", "tiny")
        chips.addWidget(self.student_chip)
        self.status_chip = QLabel("State: ready")
        self.status_chip.setProperty("role", "tiny")
        chips.addWidget(self.status_chip)
        self.method_chip = QLabel("Method: A*")
        self.method_chip.setProperty("role", "tiny")
        chips.addWidget(self.method_chip)
        chips.addStretch()
        l.addLayout(chips)
        self._style_info_chips()

        self.main_layout.addWidget(self.hero)

    def _style_info_chips(self) -> None:
        style = (
            f"QLabel {{ background: {self.palette['panel_bg']}; border: 1px solid {self.palette['border']}; "
            f"border-radius: 11px; padding: 5px 10px; color: {self.palette['muted']}; }}"
        )
        for chip in (self.dataset_chip, self.student_chip, self.status_chip, self.method_chip):
            chip.setStyleSheet(style)

    def _build_input(self) -> None:
        self.input_card = self._card("card")
        l = QVBoxLayout(self.input_card)
        l.setContentsMargins(20, 18, 20, 18)
        l.setSpacing(10)

        title = QLabel("Student Inputs")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        l.addWidget(title)

        self.dataset_preview = QTextEdit()
        self.dataset_preview.setReadOnly(True)
        self.dataset_preview.setMinimumHeight(160)  # Make the Student Inputs preview slightly smaller
        self.dataset_preview.setStyleSheet("font-family:Consolas;font-size:12px;color:#454545;")
        self.dataset_preview.setPlainText("Student values will show here.")
        l.addWidget(self.dataset_preview)

        holder = QWidget()
        self.parameter_grid = QGridLayout(holder)
        self.parameter_grid.setContentsMargins(0, 0, 0, 0)
        self.parameter_grid.setHorizontalSpacing(8)
        self.parameter_grid.setVerticalSpacing(8)
        l.addWidget(holder)

        for spec in PARAMETER_SPECS:
            frame = self._create_parameter_slider(spec)
            self.parameter_frames.append(frame)

        self.main_layout.addWidget(self.input_card)

    def _build_controls(self) -> None:
        self.controls_host = QWidget()
        self.controls_grid = QGridLayout(self.controls_host)
        self.controls_grid.setContentsMargins(0, 0, 0, 0)
        self.controls_grid.setHorizontalSpacing(8)
        self.controls_grid.setVerticalSpacing(12)
        self.rules_constraints_layout = self.controls_grid

        self.rules_card = self._card("card")
        r = QVBoxLayout(self.rules_card)
        r.setContentsMargins(20, 18, 20, 18)
        r.setSpacing(10)
        t = QLabel("Rules")
        t.setStyleSheet("font-size:18px;font-weight:700;")
        r.addWidget(t)

        self.threshold_control = self._create_control_slider("Risk Threshold", 0.0, 100.0, 35.0, 1, "{:.0f}")
        r.addWidget(self.threshold_control["frame"])
        self.max_steps_control = self._create_control_slider("Max Steps", 1.0, 30.0, 18.0, 1, "{:.0f}")
        r.addWidget(self.max_steps_control["frame"])
        self.require_missing_zero = QCheckBox("Missing work must be 0")
        self.require_missing_zero.setChecked(True)
        self.require_missing_zero.stateChanged.connect(
            lambda _: self._invalidate_results_if_present("Goal rule changed. Run the plan again.")
        )
        self.require_missing_zero.stateChanged.connect(lambda _: self._update_live_risk())
        missing_row = QHBoxLayout()
        missing_row.addWidget(self.require_missing_zero)
        missing_row.addWidget(
            self._make_help_icon("When enabled, planner goal requires missing submissions to be exactly 0.")
        )
        missing_row.addStretch()
        r.addLayout(missing_row)

        self.constraints_card = self._card("card")
        c = QVBoxLayout(self.constraints_card)
        c.setContentsMargins(20, 18, 20, 18)
        c.setSpacing(10)
        ct = QLabel("What-if")
        ct.setStyleSheet("font-size:18px;font-weight:700;")
        c.addWidget(ct)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom")
        self.preset_combo.addItems(preset_names())
        self.preset_combo.currentTextChanged.connect(
            lambda _: self._invalidate_results_if_present("What-if preset changed.")
        )
        c.addWidget(self.preset_combo)
        self.max_study_control = self._create_control_slider("Max Study Hours / Day", 0.5, 8.0, 4.0, 10, "{:.1f}")
        c.addWidget(self.max_study_control["frame"])
        self.deadline_shift_control = self._create_control_slider("Deadline Shift (Days)", -14.0, 14.0, 0.0, 1, "{:.0f}")
        c.addWidget(self.deadline_shift_control["frame"])
        self.tutor_box = QCheckBox("Tutor is available")
        self.tutor_box.setChecked(True)
        self.tutor_box.stateChanged.connect(
            lambda _: self._invalidate_results_if_present("What-if constraints changed. Run again.")
        )
        tutor_row = QHBoxLayout()
        tutor_row.addWidget(self.tutor_box)
        tutor_row.addWidget(
            self._make_help_icon("If tutor is unavailable, tutor-related actions will not be used.")
        )
        tutor_row.addStretch()
        c.addLayout(tutor_row)
        apply_btn = QPushButton("Use Preset")
        apply_btn.clicked.connect(self._on_apply_preset)
        c.addWidget(apply_btn)

        self.controls_grid.addWidget(self.rules_card, 0, 0)
        self.controls_grid.addWidget(self.constraints_card, 0, 1)
        self.main_layout.addWidget(self.controls_host)

    def _build_weights(self) -> None:
        self.weights_card = self._card("card")
        w = QVBoxLayout(self.weights_card)
        w.setContentsMargins(20, 18, 20, 18)
        w.setSpacing(10)

        title = QLabel("Risk Weights")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        w.addWidget(title)
        tip = QLabel("Keep these default unless you need to change them.")
        tip.setStyleSheet("font-size:13px;color:#454545;")
        w.addWidget(tip)

        holder = QWidget()
        self.weight_grid = QGridLayout(holder)
        self.weight_grid.setContentsMargins(0, 0, 0, 0)
        self.weight_grid.setHorizontalSpacing(8)
        self.weight_grid.setVerticalSpacing(8)
        w.addWidget(holder)

        defaults = RiskConfig().weights
        for key, label in WEIGHT_SPECS:
            frame = self._create_weight_slider(key, label, defaults[key])
            self.weight_frames.append(frame)

        self.main_layout.addWidget(self.weights_card)

    def _build_results(self) -> None:
        self.run_btn = QPushButton("Make Recovery Plan")
        self.run_btn.setProperty("role", "run")
        self.run_btn.clicked.connect(self._on_run_planner)
        self.main_layout.addWidget(self.run_btn)

        utility_row = QHBoxLayout()
        self.what_if_btn = QPushButton("Run 3 What-if Cases")
        self.what_if_btn.clicked.connect(self._on_run_what_if)
        utility_row.addWidget(self.what_if_btn)
        self.export_btn = QPushButton("Save Results")
        self.export_btn.setProperty("variant", "success")
        self.export_btn.clicked.connect(self._on_export)
        utility_row.addWidget(self.export_btn)
        self.copy_plan_btn = QPushButton("Copy Steps")
        self.copy_plan_btn.setProperty("variant", "subtle")
        self.copy_plan_btn.clicked.connect(self._copy_plan)
        utility_row.addWidget(self.copy_plan_btn)
        self.best_method_btn = QPushButton("Pick Best")
        self.best_method_btn.setProperty("variant", "subtle")
        self.best_method_btn.clicked.connect(self._pick_best_method)
        utility_row.addWidget(self.best_method_btn)
        self.main_layout.addLayout(utility_row)

        self.results_card = self._card("card")
        o = QVBoxLayout(self.results_card)
        o.setContentsMargins(20, 18, 20, 20)
        o.setSpacing(12)
        title = QLabel("Plan Results")
        title.setProperty("role", "section_title")
        o.addWidget(title)

        method_row = QHBoxLayout()
        label = QLabel("Methods")
        label.setProperty("role", "tiny")
        method_row.addWidget(label)
        method_row.addStretch()
        for method in SEARCH_METHODS:
            btn = QPushButton(self._nice_method_name(method))
            btn.setCheckable(True)
            btn.setProperty("role", "method")
            btn.clicked.connect(lambda checked, m=method: self._on_method(m, checked))
            method_row.addWidget(btn)
            self.method_buttons[method] = btn
        self.method_buttons["A* Search"].setChecked(True)
        o.addLayout(method_row)

        metrics_holder = QWidget()
        metrics = QGridLayout(metrics_holder)
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(8)
        metrics.setVerticalSpacing(8)
        specs = [
            ("status", "State"),
            ("risk_before", "Risk Before"),
            ("risk_after", "Risk After"),
            ("cost", "Cost"),
            ("runtime", "Time (ms)"),
            ("nodes", "Nodes"),
        ]
        for i, (key, text) in enumerate(specs):
            card = self._card("card_alt")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 14, 14, 14)
            header = QHBoxLayout()
            h = QLabel(text)
            h.setProperty("role", "tiny")
            header.addWidget(h)
            header.addWidget(self._make_help_icon(METRIC_HELP.get(key, text)))
            header.addStretch()
            cl.addLayout(header)
            v = QLabel("-")
            v.setStyleSheet("font-size:22px;font-weight:700;")
            cl.addWidget(v)
            self.metric_labels[key] = v
            metrics.addWidget(card, i // 3, i % 3)
        o.addWidget(metrics_holder)

        self.content_splitter = QSplitter(Qt.Vertical)
        self.content_splitter.setChildrenCollapsible(False)
        self.plan_card = self._card("card")
        p = QVBoxLayout(self.plan_card)
        p.setContentsMargins(16, 16, 16, 16)
        plan_title = QLabel("Plan Steps")
        plan_title.setProperty("role", "section_title")
        p.addWidget(plan_title)
        self.plan_text = QTextEdit()
        self.plan_text.setReadOnly(True)
        self.plan_text.setMinimumHeight(300)  # Make the plan steps area bigger
        self.plan_text.setStyleSheet("font-family:Consolas;font-size:13px;")
        self.plan_text.setPlainText("Plan will show here...")
        p.addWidget(self.plan_text)

        self.chart_card = self._card("card")
        ch = QVBoxLayout(self.chart_card)
        ch.setContentsMargins(16, 16, 16, 16)
        chart_title = QLabel("Charts")
        chart_title.setProperty("role", "section_title")
        ch.addWidget(chart_title)
        self.figure = Figure(figsize=(9.4, 7.0), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_card.setMinimumHeight(680)
        ch.addWidget(self.canvas)

        self.content_splitter.addWidget(self.plan_card)
        self.content_splitter.addWidget(self.chart_card)
        self.content_splitter.setStretchFactor(0, 2)
        self.content_splitter.setStretchFactor(1, 5)
        self.content_splitter.setSizes([220, 860])
        o.addWidget(self.content_splitter)

        comp_card = self._card("card")
        comp_card.setMinimumHeight(260)  # Make the card bigger for visibility
        cp = QVBoxLayout(comp_card)
        cp.setContentsMargins(16, 16, 16, 16)
        cmp_title = QLabel("Method Comparison")
        cmp_title.setProperty("role", "section_title")
        cp.addWidget(cmp_title)
        self.comparison = QTableWidget(len(SEARCH_METHODS), 6)
        self.comparison.setMinimumHeight(200)  # Make the table itself bigger
        self.comparison.setHorizontalHeaderLabels(["Method", "Status", "Risk", "Cost", "Time (ms)", "Nodes"])
        self.comparison.verticalHeader().setVisible(False)
        self.comparison.setEditTriggers(QTableWidget.NoEditTriggers)
        self.comparison.setSelectionMode(QTableWidget.NoSelection)
        self.comparison.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.comparison.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comparison.horizontalHeader().setStretchLastSection(True)
        self.comparison.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.comparison.horizontalHeader().setMinimumSectionSize(90)
        self.comparison.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.comparison.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, method in enumerate(SEARCH_METHODS):
            method_item = QTableWidgetItem(self._nice_method_name(method))
            method_item.setTextAlignment(Qt.AlignCenter)
            self.comparison.setItem(row, 0, method_item)
            for col in range(1, 6):
                item = QTableWidgetItem("-")
                item.setTextAlignment(Qt.AlignCenter)
                self.comparison.setItem(row, col, item)
        cp.addWidget(self.comparison, 1)
        o.addWidget(comp_card)

        self.bottom_splitter = QSplitter(Qt.Horizontal)
        self.bottom_splitter.setChildrenCollapsible(False)
        self.whatif_card = self._card("card")
        wh = QVBoxLayout(self.whatif_card)
        wh.setContentsMargins(16, 16, 16, 16)
        w_title = QLabel("What-if Results")
        w_title.setProperty("role", "section_title")
        wh.addWidget(w_title)
        self.whatif_text = QTextEdit()
        self.whatif_text.setReadOnly(True)
        self.whatif_text.setMinimumHeight(180)
        self.whatif_text.setStyleSheet("font-family:Consolas;font-size:13px;")
        self.whatif_text.setPlainText("What-if results show here.")
        wh.addWidget(self.whatif_text)

        self.log_card = self._card("card")
        lg = QVBoxLayout(self.log_card)
        lg.setContentsMargins(16, 16, 16, 16)
        log_title = QLabel("App Log")
        log_title.setProperty("role", "section_title")
        lg.addWidget(log_title)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(230)
        self.log_text.setStyleSheet("font-family:Consolas;font-size:12px;")
        lg.addWidget(self.log_text)

        self.bottom_splitter.addWidget(self.whatif_card)
        self.bottom_splitter.addWidget(self.log_card)
        self.bottom_splitter.setSizes([520, 600])
        o.addWidget(self.bottom_splitter)

        self.main_layout.addWidget(self.results_card)

    def _create_parameter_slider(self, spec: SliderSpec) -> QFrame:
        frame = self._card("card_alt")
        l = QVBoxLayout(frame)
        l.setContentsMargins(16, 14, 16, 16)
        l.setSpacing(8)
        head = QHBoxLayout()
        name = QLabel(spec.label)
        name.setStyleSheet("font-size:14px;font-weight:700;")
        help_icon = self._make_help_icon(PARAMETER_HELP.get(spec.key, spec.label))
        val = QLabel(spec.fmt.format(spec.default))
        val.setStyleSheet("font-size:14px;font-weight:700;")
        head.addWidget(name)
        head.addWidget(help_icon)
        head.addStretch()
        head.addWidget(val)
        l.addLayout(head)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(int(round(spec.minimum * spec.scale)))
        slider.setMaximum(int(round(spec.maximum * spec.scale)))
        slider.setValue(int(round(spec.default * spec.scale)))
        slider.valueChanged.connect(lambda _: self._on_parameter_change(spec.key))
        l.addWidget(slider)
        self.slider_controls[spec.key] = {"spec": spec, "slider": slider, "value_label": val}
        return frame

    def _create_weight_slider(self, key: str, label: str, default_value: float) -> QFrame:
        frame = self._card("card_alt")
        l = QVBoxLayout(frame)
        l.setContentsMargins(16, 14, 16, 16)
        l.setSpacing(8)
        head = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet("font-size:13px;font-weight:700;")
        help_icon = self._make_help_icon(WEIGHT_HELP.get(key, label))
        val = QLabel(f"{default_value:.2f}")
        val.setStyleSheet("font-size:13px;font-weight:700;")
        head.addWidget(name)
        head.addWidget(help_icon)
        head.addStretch()
        head.addWidget(val)
        l.addLayout(head)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(int(round(default_value * 100)))
        slider.valueChanged.connect(lambda _: self._on_weight_change(key))
        l.addWidget(slider)
        self.weight_controls[key] = {"slider": slider, "value_label": val}
        return frame

    def _create_control_slider(
        self,
        label: str,
        minimum: float,
        maximum: float,
        default: float,
        scale: int,
        fmt: str,
    ) -> Dict[str, object]:
        frame = self._card("card_alt")
        l = QVBoxLayout(frame)
        l.setContentsMargins(16, 14, 16, 16)
        l.setSpacing(8)
        head = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet("font-size:13px;font-weight:700;")
        help_icon = self._make_help_icon(CONTROL_HELP.get(label, label))
        val = QLabel(fmt.format(default))
        val.setStyleSheet("font-size:13px;font-weight:700;")
        head.addWidget(name)
        head.addWidget(help_icon)
        head.addStretch()
        head.addWidget(val)
        l.addLayout(head)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(int(round(minimum * scale)))
        slider.setMaximum(int(round(maximum * scale)))
        slider.setValue(int(round(default * scale)))
        slider.valueChanged.connect(lambda _: val.setText(fmt.format(slider.value() / scale)))
        slider.valueChanged.connect(lambda _: self._invalidate_results_if_present("Planner settings changed. Run the plan again."))
        slider.valueChanged.connect(lambda _: self._update_live_risk())
        l.addWidget(slider)
        return {"frame": frame, "slider": slider, "scale": scale}

    def _param_value(self, key: str) -> float:
        c = self.slider_controls[key]
        spec: SliderSpec = c["spec"]
        return c["slider"].value() / spec.scale

    def _build_state(self) -> StudentState:
        vals = {key: self._param_value(key) for key in self.slider_controls}
        return StudentState(
            attendance_rate=vals["attendance_rate"],
            missing_submissions=int(round(vals["missing_submissions"])),
            avg_quiz_score=vals["avg_quiz_score"],
            lms_activity=vals["lms_activity"],
            study_hours_per_week=vals["study_hours_per_week"],
            days_to_deadline=int(round(vals["days_to_deadline"])),
            fatigue=vals["fatigue"],
        ).clamp()

    def _read_settings(self) -> PlannerSettings:
        weights = {k: c["slider"].value() / 100.0 for k, c in self.weight_controls.items()}
        risk = RiskConfig(
            threshold=self.threshold_control["slider"].value() / self.threshold_control["scale"],
            require_zero_missing=self.require_missing_zero.isChecked(),
            weights=weights,
        )
        max_steps = int(round(self.max_steps_control["slider"].value() / self.max_steps_control["scale"]))
        return PlannerSettings(risk=risk, max_steps=max_steps)

    def _read_constraints(self) -> SimulationConstraints:
        selected_record = self._find_record(self._selected_student_id())
        available_hours = selected_record.available_hours_per_day if selected_record is not None else 8.0
        return SimulationConstraints(
            max_study_hours_per_day=self.max_study_control["slider"].value() / self.max_study_control["scale"],
            tutor_available=self.tutor_box.isChecked(),
            deadline_shift_days=int(round(self.deadline_shift_control["slider"].value() / self.deadline_shift_control["scale"])),
            available_hours_per_day=max(1.0, float(available_hours)),
        )

    def _replace_text(self, widget: QTextEdit, text: str) -> None:
        widget.setPlainText(text)

    def _make_help_icon(self, text: str) -> QLabel:
        icon = HelpIconLabel(text, self)
        icon.setVisible(True)
        icon.setFixedSize(18, 18)
        icon.setToolTip("")  # Ensure no default Qt tooltip is set
        return icon

    def _clear_chart_panel(self, message: str = "Run plan to see charts.") -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(1, 1, 1)
        axis.set_facecolor(self.palette["panel_bg"])
        axis.axis("off")
        axis.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            color=self.palette["muted"],
            fontsize=12,
            transform=axis.transAxes,
        )
        self.canvas.draw_idle()

    def _clear_results_view(self, reason: str = "") -> None:
        had_results = bool(self.method_results or self.last_run or self.last_what_if_rows)
        self.method_results = {}
        self.last_run = None
        self.last_what_if_rows = []
        self.selected_method = "A* Search"

        if hasattr(self, "method_buttons"):
            for name, button in self.method_buttons.items():
                button.setChecked(name == "A* Search")

        if "status" in self.metric_labels:
            self.metric_labels["status"].setText("-")
            self.metric_labels["status"].setStyleSheet(f"font-size:22px;font-weight:700;color:{self.palette['text']};")
        for key in ("risk_before", "risk_after", "cost", "runtime", "nodes"):
            if key in self.metric_labels:
                self.metric_labels[key].setText("-")

        if hasattr(self, "projected"):
            self.projected.setText("After plan: -")
        if hasattr(self, "method_chip"):
            self.method_chip.setText("Method: A*")
        if hasattr(self, "plan_text"):
            self._replace_text(self.plan_text, "Plan will show here...")
        if hasattr(self, "whatif_text"):
            self._replace_text(self.whatif_text, "What-if results show here.")
        if hasattr(self, "comparison"):
            for row, method in enumerate(SEARCH_METHODS):
                method_item = self.comparison.item(row, 0)
                if method_item is None:
                    method_item = QTableWidgetItem()
                    self.comparison.setItem(row, 0, method_item)
                method_item.setText(self._nice_method_name(method))
                method_item.setTextAlignment(Qt.AlignCenter)
                method_item.setForeground(QColor(self.palette["text"]))
                method_item.setBackground(QColor(self.palette["panel_alt"]))

                for col in range(1, self.comparison.columnCount()):
                    cell = self.comparison.item(row, col)
                    if cell is None:
                        cell = QTableWidgetItem()
                        self.comparison.setItem(row, col, cell)
                    cell.setText("-")
                    cell.setTextAlignment(Qt.AlignCenter)
                    cell.setForeground(QColor(self.palette["text"]))
                    cell.setBackground(QColor(self.palette["panel_alt"]))
            self.comparison.viewport().update()

        if hasattr(self, "canvas"):
            self._clear_chart_panel()

        if reason and had_results:
            self._log(reason)

    def _invalidate_results_if_present(self, reason: str) -> None:
        if self._is_busy or self._applying_record:
            return
        if not (self.method_results or self.last_run or self.last_what_if_rows):
            return
        self._clear_results_view(reason)

    def _nice_method_name(self, method: str) -> str:
        return METHOD_LABELS.get(method, method)

    def _nice_action_name(self, action: str) -> str:
        return ACTION_LABELS.get(action, action.replace("_", " "))

    def _nice_status_text(self, status: str) -> str:
        status_map = {
            "Not At-Risk": "Safe",
            "At-Risk": "At Risk",
            "On Track": "Good",
            "Watch Closely": "Needs Work",
        }
        return status_map.get(status, status)

    def _queue_preview_update(self) -> None:
        self._preview_timer.start(45)

    def _has_loaded_students(self) -> bool:
        return bool(self.records)

    def _selected_student_id(self) -> str:
        value = self.student_combo.currentText().strip()
        if not value or value == "No students loaded":
            return ""
        return value

    def _upsert_record_state(self, student_id: str, state: StudentState) -> None:
        if not student_id:
            return
        existing = self._find_record(student_id)
        available_hours = existing.available_hours_per_day if existing is not None else 8.0
        updated = StudentRecord(
            student_id=student_id,
            state=state.clamp(),
            available_hours_per_day=available_hours,
        )
        for index, rec in enumerate(self.records):
            if rec.student_id == student_id:
                self.records[index] = updated
                break
        for index, rec in enumerate(self.filtered_records):
            if rec.student_id == student_id:
                self.filtered_records[index] = updated
                break

    def _sync_selected_student_state(self) -> None:
        if self._applying_record or not self._has_loaded_students():
            return
        student_id = self._selected_student_id()
        if not student_id:
            return
        self._upsert_record_state(student_id, self._build_state())

    def _on_parameter_change(self, key: str) -> None:
        c = self.slider_controls[key]
        spec: SliderSpec = c["spec"]
        c["value_label"].setText(spec.fmt.format(self._param_value(key)))
        if self._applying_record:
            return
        self._invalidate_results_if_present("Inputs changed. Run the plan again.")
        self._sync_selected_student_state()
        self._update_live_risk()
        self._queue_preview_update()

    def _on_weight_change(self, key: str) -> None:
        value = self.weight_controls[key]["slider"].value() / 100.0
        self.weight_controls[key]["value_label"].setText(f"{value:.2f}")
        self._invalidate_results_if_present("Risk weights changed. Run the plan again.")
        self._update_live_risk()

    def _update_live_risk(self) -> None:
        state = self._build_state()
        settings = self._read_settings()
        score = compute_risk_score(state, settings.risk)
        color = risk_color(score, settings.risk.threshold, self.palette)
        soft_color = QColor(color).lighter(120).name()
        self.risk_display.setText(f"{score:.2f}")
        self.risk_display.setStyleSheet(f"font-size:36px;font-weight:700;color:{color};")
        status_text = risk_status(score, settings.risk.threshold)
        self.risk_state.setText(self._nice_status_text(status_text))
        self.risk_state.setStyleSheet(f"font-size:12px;font-weight:700;color:{color};")
        self.status_chip.setText(f"State: {self._nice_status_text(status_text)}")
        self.risk_progress.setValue(int(max(0, min(100, round(score)))))
        self.risk_progress.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {self.palette['border']}; background: {self.palette['panel_alt']};"
            f" border-radius: 8px; text-align: center; color: {self.palette['muted']}; }}"
            f"QProgressBar::chunk {{ border-radius: 7px; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {soft_color}, stop:1 {color}); }}"
        )

    def _update_preview_text(self) -> None:
        state = self._build_state()
        text = (
            f"Student: {self.student_combo.currentText()}\n"
            f"Attendance: {state.attendance_rate:.1f}\n"
            f"Missing: {state.missing_submissions}\n"
            f"Quiz: {state.avg_quiz_score:.1f}\n"
            f"LMS: {state.lms_activity:.1f}\n"
            f"Study Hours: {state.study_hours_per_week:.1f}\n"
            f"Deadline: {state.days_to_deadline} day(s)\n"
            f"Fatigue: {state.fatigue:.1f}"
        )
        self._replace_text(self.sidebar_preview, text)
        self._replace_text(self.dataset_preview, text)

    def _find_record(self, student_id: str) -> Optional[StudentRecord]:
        for rec in self.records:
            if rec.student_id == student_id:
                return rec
        return None

    def _apply_record(self, record: StudentRecord) -> None:
        self._applying_record = True
        vals = {
            "attendance_rate": record.state.attendance_rate,
            "missing_submissions": float(record.state.missing_submissions),
            "avg_quiz_score": record.state.avg_quiz_score,
            "lms_activity": record.state.lms_activity,
            "study_hours_per_week": record.state.study_hours_per_week,
            "days_to_deadline": float(record.state.days_to_deadline),
            "fatigue": record.state.fatigue,
        }
        try:
            for key, value in vals.items():
                c = self.slider_controls[key]
                spec: SliderSpec = c["spec"]
                c["slider"].setValue(int(round(value * spec.scale)))
                c["value_label"].setText(spec.fmt.format(value))
        finally:
            self._applying_record = False
        self.student_chip.setText(f"Chosen: {record.student_id}")
        self.sidebar_selected_label.setText(f"Chosen: {record.student_id}")
        self._update_live_risk()
        self._update_preview_text()

    def _load_records(self, path: Path) -> None:
        previous = self.student_combo.currentText()
        self.records = load_students_csv(path)
        self.filtered_records = list(self.records)
        self._rebuild_student_combo(self.filtered_records, previous)
        if self.filtered_records:
            selected = self._find_record(self.student_combo.currentText()) or self.filtered_records[0]
            self._apply_record(selected)
        self.count_label.setText(f"{len(self.records)} students")
        self.dataset_chip.setText(f"Students: {len(self.records)}")
        self._update_preview_text()

    def _rebuild_student_combo(self, records: List[StudentRecord], preferred_id: str | None = None) -> None:
        self.student_combo.blockSignals(True)
        self.student_combo.clear()
        if not records:
            self.student_combo.addItem("No students loaded")
            self.student_combo.setEnabled(False)
            self.student_combo.blockSignals(False)
            return
        self.student_combo.setEnabled(True)
        for record in records:
            self.student_combo.addItem(record.student_id)
        if preferred_id and preferred_id in [r.student_id for r in records]:
            self.student_combo.setCurrentText(preferred_id)
        else:
            self.student_combo.setCurrentText(records[0].student_id)
        self.student_combo.blockSignals(False)

    def _on_student_selected(self, student_id: str) -> None:
        rec = self._find_record(student_id)
        if rec is not None:
            self._invalidate_results_if_present("Student changed. Run the plan again.")
            self._apply_record(rec)

    def _on_student_filter(self, text: str) -> None:
        query = text.strip().lower()
        selected = self.student_combo.currentText()
        if not query:
            self.filtered_records = list(self.records)
        else:
            self.filtered_records = [r for r in self.records if query in r.student_id.lower()]
        self._rebuild_student_combo(self.filtered_records, selected)
        if self.filtered_records:
            record = self._find_record(self.student_combo.currentText()) or self.filtered_records[0]
            self._apply_record(record)


    def _on_load_csv(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose CSV File", str(self.project_root), "CSV Files (*.csv *.CSV)")
        if not file_path:
            return
        try:
            self._load_records(Path(file_path))
            self._clear_results_view("Dataset changed. Previous run results were cleared.")
            self._log(f"CSV file loaded: {file_path}")
            QMessageBox.information(self, "Done", f"CSV loaded:\n{file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Problem", f"Could not open CSV.\n{exc}")

    def _on_generate(self) -> None:
        rec = generate_random_record(index=self.random_counter)
        self.random_counter += 1
        self.records.append(rec)
        self.filtered_records = list(self.records)
        self._rebuild_student_combo(self.filtered_records, rec.student_id)
        self._apply_record(rec)
        self._clear_results_view("Scenario changed. Previous run results were cleared.")
        self.count_label.setText(f"{len(self.records)} students")
        self.dataset_chip.setText(f"Students: {len(self.records)}")
        self._update_preview_text()
        self._log(f"Random student made: {rec.student_id}")

    def _on_apply_preset(self) -> None:
        selected = self.preset_combo.currentText()
        if selected == "Custom":
            return
        preset = apply_named_preset(SimulationConstraints(), selected)
        self.max_study_control["slider"].setValue(int(round(preset.max_study_hours_per_day * self.max_study_control["scale"])))
        self.deadline_shift_control["slider"].setValue(int(round(preset.deadline_shift_days * self.deadline_shift_control["scale"])))
        self.tutor_box.setChecked(preset.tutor_available)
        self._invalidate_results_if_present("Preset applied. Run the plan again.")
        self._log(f"Preset used: {selected}")

    def _on_method(self, method: str, checked: bool) -> None:
        if not checked:
            return
        self.selected_method = method
        for name, btn in self.method_buttons.items():
            if name != method:
                btn.setChecked(False)
        self._render_method(method)
        self.method_chip.setText(f"Method: {self._nice_method_name(method)}")

    def _render_plan(self, result: PlanResult) -> None:
        constraints = self._read_constraints()
        if self.last_run and isinstance(self.last_run.get("constraints"), SimulationConstraints):
            constraints = self.last_run["constraints"]
        plan_text = build_actionable_plan_text(
            result=result,
            method_results=self.method_results,
            available_hours_per_day=max(1.0, float(constraints.available_hours_per_day)),
            max_study_hours_per_day=max(0.5, float(constraints.max_study_hours_per_day)),
            nice_method_name=self._nice_method_name,
            nice_action_name=self._nice_action_name,
            nice_status_text=self._nice_status_text,
        )
        self._replace_text(self.plan_text, plan_text)

    def _render_comparison(self) -> None:
        rows = comparison_rows(*(self.method_results[m] for m in SEARCH_METHODS))
        for row_index, row in enumerate(rows):
            status_raw = str(row["status"])
            status_ok = status_raw in {"Not At-Risk", "On Track"}
            values = [
                self._nice_method_name(str(row["method"])),
                self._nice_status_text(status_raw),
                f"{row['risk_after']:.2f}",
                f"{row['total_cost']:.2f}",
                f"{row['runtime_ms']:.2f}",
                str(row["expanded_nodes"]),
            ]
            for col, value in enumerate(values):
                item = self.comparison.item(row_index, col)
                if item is None:
                    item = QTableWidgetItem()
                    self.comparison.setItem(row_index, col, item)
                item.setText(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(self.palette["panel_alt"]))
                color = risk_color(0.0, 35.0, self.palette) if (col == 1 and status_ok) else (
                    risk_color(100.0, 35.0, self.palette) if col == 1 else self.palette["text"]
                )
                item.setForeground(QColor(color))
        self.comparison.viewport().update()

    def _render_method(self, method_name: str) -> None:
        result = self.method_results.get(method_name)
        if result is None:
            return
        status_ok = result.final_status in {"Not At-Risk", "On Track"}
        status_color = risk_color(0.0, 35.0, self.palette) if status_ok else risk_color(100.0, 35.0, self.palette)
        self.metric_labels["status"].setText(self._nice_status_text(result.final_status))
        self.metric_labels["status"].setStyleSheet(
            f"font-size:22px;font-weight:700;color:{status_color};"
        )
        self.metric_labels["risk_before"].setText(f"{result.risk_before:.2f}")
        self.metric_labels["risk_after"].setText(f"{result.risk_after:.2f}")
        self.metric_labels["cost"].setText(f"{result.total_cost:.2f}")
        self.metric_labels["runtime"].setText(f"{result.runtime_ms:.2f}")
        self.metric_labels["nodes"].setText(str(result.expanded_nodes))
        self.projected.setText(f"After plan: {result.risk_after:.2f}")
        self.method_chip.setText(f"Method: {self._nice_method_name(result.algorithm)}")
        self._render_plan(result)
        chart_settings = self._read_settings()
        if self.last_run and isinstance(self.last_run.get("settings"), PlannerSettings):
            chart_settings = self.last_run["settings"]
        draw_result_charts(
            self.figure,
            self.method_results["A* Search"],
            self.method_results["Greedy Baseline"],
            self.method_results["Uniform Cost Search"],
            result.algorithm,
            self.palette,
            settings=chart_settings,
        )
        self.canvas.draw()

    def _on_run_planner(self) -> None:
        if self._planner_thread is not None:
            self._log("Plan is already running. Please wait...")
            return
        if self._what_if_thread is not None:
            self._log("What-if is running. Please wait...")
            return

        self._sync_selected_student_state()
        settings = self._read_settings()
        constraints = self._read_constraints()
        student_id = self._selected_student_id() or self.student_combo.currentText()
        selected_record = self._find_record(student_id)
        state = selected_record.state if selected_record is not None else self._build_state()
        self._set_busy(True, "Running plan...")

        thread = QThread(self)
        worker = PlannerWorker(state, settings, constraints, student_id)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_planner_finished)
        worker.failed.connect(self._on_planner_failed)
        worker.finished.connect(self._cleanup_planner_thread)
        worker.failed.connect(self._cleanup_planner_thread)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._planner_thread = thread
        self._planner_worker = worker
        thread.start()

    def _on_run_what_if(self) -> None:
        if self._what_if_thread is not None:
            self._log("What-if is already running. Please wait...")
            return
        if self._planner_thread is not None:
            self._log("Plan is running. Wait before starting what-if.")
            return

        self._sync_selected_student_state()
        student_id = self._selected_student_id()
        selected_record = self._find_record(student_id)
        state = selected_record.state if selected_record is not None else self._build_state()
        settings = self._read_settings()
        base = self._read_constraints()
        self._set_busy(True, "Running what-if...")

        thread = QThread(self)
        worker = WhatIfWorker(state, settings, base)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_what_if_finished)
        worker.failed.connect(self._on_what_if_failed)
        worker.finished.connect(self._cleanup_what_if_thread)
        worker.failed.connect(self._cleanup_what_if_thread)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._what_if_thread = thread
        self._what_if_worker = worker
        thread.start()

    @Slot(object)
    def _on_planner_finished(self, payload: object) -> None:
        try:
            if not isinstance(payload, dict):
                raise ValueError("Plan returned invalid data.")

            a_star = payload["a_star"]
            greedy = payload["greedy"]
            ucs = payload["uniform_cost"]
            student_id = str(payload["student_id"])

            self.method_results = {
                "A* Search": a_star,
                "Greedy Baseline": greedy,
                "Uniform Cost Search": ucs,
            }
            self.last_run = {
                "student_id": student_id,
                "settings": payload["settings"],
                "constraints": payload["constraints"],
                "a_star": a_star,
                "greedy": greedy,
                "uniform_cost": ucs,
            }
            self._render_comparison()
            if self.selected_method not in self.method_results:
                self.selected_method = "A* Search"
            self.method_buttons[self.selected_method].setChecked(True)
            self._render_method(self.selected_method)
            self._log(
                f"Plan finished for {student_id}: "
                f"A*={self._nice_status_text(a_star.final_status)}, "
                f"Greedy={self._nice_status_text(greedy.final_status)}, "
                f"UCS={self._nice_status_text(ucs.final_status)}"
            )
        except Exception:  # noqa: BLE001
            self._on_planner_failed(traceback.format_exc())

    @Slot(str)
    def _on_planner_failed(self, error_text: str) -> None:
        short_error = error_text.strip().splitlines()[-1] if error_text.strip() else "Unknown planner error."
        self._log(f"Plan failed: {short_error}")
        QMessageBox.critical(self, "Plan Error", f"Plan failed.\n\n{short_error}")

    @Slot(object)
    def _on_what_if_finished(self, payload: object) -> None:
        try:
            rows = payload if isinstance(payload, list) else []
            self.last_what_if_rows = rows
            what_if_text = build_what_if_text(rows, nice_status_text=self._nice_status_text)
            self._replace_text(self.whatif_text, what_if_text)
            self._log("What-if finished (3 cases).")
        except Exception:  # noqa: BLE001
            self._on_what_if_failed(traceback.format_exc())

    @Slot(str)
    def _on_what_if_failed(self, error_text: str) -> None:
        short_error = error_text.strip().splitlines()[-1] if error_text.strip() else "Unknown what-if error."
        self._log(f"What-if failed: {short_error}")
        QMessageBox.critical(self, "What-if Error", f"What-if failed.\n\n{short_error}")

    @Slot(object)
    def _cleanup_planner_thread(self, _payload: object) -> None:
        if self._planner_worker is not None:
            self._planner_worker.deleteLater()
        self._planner_worker = None
        self._planner_thread = None
        self._set_busy(False, "Ready")

    @Slot(object)
    def _cleanup_what_if_thread(self, _payload: object) -> None:
        if self._what_if_worker is not None:
            self._what_if_worker.deleteLater()
        self._what_if_worker = None
        self._what_if_thread = None
        self._set_busy(False, "Ready")

    def _copy_plan(self) -> None:
        text = self.plan_text.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Note", "No plan text to copy yet.")
            return
        QApplication.clipboard().setText(text)
        self._log("Plan steps copied.")

    def _pick_best_method(self) -> None:
        if not self.method_results:
            QMessageBox.information(self, "Note", "Run the plan first.")
            return
        best = min(
            self.method_results.values(),
            key=lambda item: (item.total_cost, item.risk_after, item.runtime_ms),
        )
        self.selected_method = best.algorithm
        for name, btn in self.method_buttons.items():
            btn.setChecked(name == best.algorithm)
        self._render_method(best.algorithm)
        self._log(f"Best method picked: {self._nice_method_name(best.algorithm)}")

    def _on_export(self) -> None:
        if not self.last_run:
            QMessageBox.information(self, "Note", "Run the plan first, then save files.")
            return
        selected_dir = QFileDialog.getExistingDirectory(self, "Choose Folder to Save", str(self.project_root / "exports"))
        if not selected_dir:
            return
        student_id = str(self.last_run["student_id"])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = Path(selected_dir) / f"{student_id}_{timestamp}"
        try:
            export_all(
                output_dir=export_dir,
                student_id=student_id,
                a_star_result=self.last_run["a_star"],
                greedy_result=self.last_run["greedy"],
                uniform_cost_result=self.last_run["uniform_cost"],
                what_if_rows=self.last_what_if_rows,
                settings=self.last_run["settings"],
                constraints=self.last_run["constraints"],
            )
            self.figure.savefig(export_dir / "charts.png", dpi=220, bbox_inches="tight")
            self._log(f"Files saved to {export_dir}")
            QMessageBox.information(self, "Done", f"Files saved in:\n{export_dir}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Problem", f"Could not save files.\n{exc}")

    def _reset_controls(self) -> None:
        self._clear_results_view("Controls reset. Previous run results were cleared.")
        self._applying_record = True
        try:
            for spec in PARAMETER_SPECS:
                c = self.slider_controls[spec.key]
                c["slider"].setValue(int(round(spec.default * spec.scale)))
                c["value_label"].setText(spec.fmt.format(spec.default))

            defaults = RiskConfig().weights
            for key, default_value in defaults.items():
                c = self.weight_controls[key]
                c["slider"].setValue(int(round(default_value * 100)))
                c["value_label"].setText(f"{default_value:.2f}")

            self.threshold_control["slider"].setValue(35)
            self.max_steps_control["slider"].setValue(18)
            self.max_study_control["slider"].setValue(40)
            self.deadline_shift_control["slider"].setValue(0)
            self.require_missing_zero.setChecked(True)
            self.tutor_box.setChecked(True)
            self.preset_combo.setCurrentText("Custom")
        finally:
            self._applying_record = False
        self._sync_selected_student_state()
        self._update_live_risk()
        self._update_preview_text()
        self._log("All values reset.")

    def _on_theme_changed(self, theme_name: str) -> None:
        self.current_theme_name = theme_name
        self.palette = planner_palette(theme_name)
        self.setStyleSheet(base_stylesheet(self.palette))
        self._apply_spinner_style()
        if hasattr(self, "dataset_chip"):
            self._style_info_chips()
        if hasattr(self, "risk_display"):
            self._update_live_risk()
        if self.method_results:
            self._render_method(self.selected_method)
            self._render_comparison()
        else:
            self._clear_chart_panel()
        self._log(f"Theme changed: {theme_name}")

    def _log(self, message: str) -> None:
        cleaned_message = " ".join(str(message).split())
        if hasattr(self, "log_text"):
            self.log_text.append(f"- {datetime.now().strftime('%H:%M:%S')} | {cleaned_message}")
        self.statusBar().showMessage(cleaned_message, 3000)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        if busy == self._is_busy:
            if message:
                self.statusBar().showMessage(message)
            return

        self._is_busy = busy
        for attr_name in (
            "run_btn",
            "top_run_btn",
            "what_if_btn",
            "top_export_btn",
            "export_btn",
            "best_method_btn",
            "copy_plan_btn",
            "load_csv_btn",
            "random_btn",
            "reset_controls_btn",
            "top_reset_btn",
        ):
            if hasattr(self, attr_name):
                getattr(self, attr_name).setEnabled(not busy)

        for button in self.method_buttons.values():
            button.setEnabled(not busy)

        for control in self.slider_controls.values():
            control["slider"].setEnabled(not busy)
        for control in self.weight_controls.values():
            control["slider"].setEnabled(not busy)

        for attr_name in (
            "student_combo",
            "student_filter",
            "preset_combo",
            "theme_combo",
            "require_missing_zero",
            "tutor_box",
        ):
            if hasattr(self, attr_name):
                getattr(self, attr_name).setEnabled(not busy)

        for control_attr in (
            "threshold_control",
            "max_steps_control",
            "max_study_control",
            "deadline_shift_control",
        ):
            if hasattr(self, control_attr):
                getattr(self, control_attr)["slider"].setEnabled(not busy)

        if busy:
            if hasattr(self, "status_busy_label"):
                self.status_busy_label.setText(message or "Running...")
                self.status_busy_label.setVisible(True)
            if hasattr(self, "status_spinner"):
                self.status_spinner.setVisible(True)
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            if hasattr(self, "status_spinner"):
                self.status_spinner.setVisible(False)
            if hasattr(self, "status_busy_label"):
                self.status_busy_label.setVisible(False)

        if message:
            self.statusBar().showMessage(message)

    def _regrid(self, layout: QGridLayout, frames: List[QFrame], columns: int) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        for idx, frame in enumerate(frames):
            layout.addWidget(frame, idx // columns, idx % columns)
        for col in range(columns):
            layout.setColumnStretch(col, 1)

    def _apply_responsive_layout(self, width: int) -> None:
        stack_main = width < 1240
        self.main_splitter.setOrientation(Qt.Vertical if stack_main else Qt.Horizontal)
        if stack_main:
            self.main_splitter.setSizes([560, 720])
        else:
            self.main_splitter.setSizes([520, 900])

        left_width = self.sidebar_scroll.viewport().width()
        param_cols = 1 if left_width < 760 else 2
        weight_cols = 1 if left_width < 760 else 2
        self._regrid(self.parameter_grid, self.parameter_frames, param_cols)
        self._regrid(self.weight_grid, self.weight_frames, weight_cols)

        self.rules_constraints_layout.removeWidget(self.rules_card)
        self.rules_constraints_layout.removeWidget(self.constraints_card)
        if left_width < 760:
            self.rules_constraints_layout.addWidget(self.rules_card, 0, 0)
            self.rules_constraints_layout.addWidget(self.constraints_card, 1, 0)
        else:
            self.rules_constraints_layout.addWidget(self.rules_card, 0, 0)
            self.rules_constraints_layout.addWidget(self.constraints_card, 0, 1)

        right_width = self.main_scroll.viewport().width()
        stack_results = right_width < 980
        self.content_splitter.setOrientation(Qt.Vertical)
        self.bottom_splitter.setOrientation(Qt.Vertical if stack_results else Qt.Horizontal)
        if stack_results:
            self.content_splitter.setSizes([180, 760])
            self.bottom_splitter.setSizes([280, 280])
        else:
            self.content_splitter.setSizes([220, 900])
            self.bottom_splitter.setSizes([520, 600])

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._planner_thread is not None or self._what_if_thread is not None:
            QMessageBox.information(self, "Please Wait", "A run is still in progress. Please wait a moment.")
            event.ignore()
            return
        super().closeEvent(event)


def run_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    for effect_name in ("UI_AnimateTooltip", "UI_FadeTooltip"):
        effect = getattr(Qt.UIEffect, effect_name, None)
        if effect is not None:
            app.setEffectEnabled(effect, False)
    window = MainWindow()
    window.show()
    return app.exec()
