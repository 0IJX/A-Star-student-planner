
from __future__ import annotations
from PySide6.QtWidgets import QApplication
import sys
from a_star_student_planner.ui.main_window import run_app

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("A-Star Student Planner")
    app.setOrganizationName("AStarStudentPlanner")
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
