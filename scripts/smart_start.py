from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


def _log(message: str) -> None:
    print(f"[start] {message}")


def _run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture:
            if result.stdout.strip():
                print(result.stdout.strip())
            if result.stderr.strip():
                print(result.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result


def _detect_host_python() -> list[str]:
    if os.name == "nt":
        candidates = [["py", "-3"], ["python"]]
    else:
        candidates = [["python3"], ["python"]]

    for candidate in candidates:
        probe = _run(
            candidate + ["-c", "import sys; print(sys.executable)"],
            cwd=Path.cwd(),
            check=False,
            capture=True,
        )
        if probe.returncode == 0:
            executable = probe.stdout.strip()
            if executable:
                _log(f"Using host Python: {executable}")
            return candidate
    raise RuntimeError("Python 3 was not found. Install Python and run start again.")


def _venv_python(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


def _requirements_hash(requirements_path: Path) -> str:
    return hashlib.sha256(requirements_path.read_bytes()).hexdigest()


def _requirement_names(requirements_path: Path) -> list[str]:
    names: list[str] = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if match:
            names.append(match.group(1))
    return names


def _missing_required_packages(venv_python: Path, requirements_path: Path, project_root: Path) -> list[str]:
    missing: list[str] = []
    for package_name in _requirement_names(requirements_path):
        probe = _run(
            [str(venv_python), "-m", "pip", "show", package_name],
            cwd=project_root,
            check=False,
            capture=True,
        )
        if probe.returncode != 0:
            missing.append(package_name)
    return missing


def _needs_install(requirements_hash: str, stamp_path: Path, force_install: bool) -> tuple[bool, str]:
    if force_install:
        return True, "forced reinstall"
    if not stamp_path.exists():
        return True, "first install"
    previous = stamp_path.read_text(encoding="utf-8").strip()
    if previous != requirements_hash:
        return True, "requirements changed"
    return False, "requirements unchanged"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart launcher for A* Student Planner.")
    parser.add_argument("--no-run", action="store_true", help="Prepare environment only.")
    parser.add_argument("--force-install", action="store_true", help="Force dependency reinstall.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    requirements_path = project_root / "requirements.txt"
    if not requirements_path.exists():
        raise RuntimeError(f"Missing requirements file: {requirements_path}")

    host_python = _detect_host_python()
    venv_python = _venv_python(project_root)
    venv_dir = venv_python.parents[1]

    if not venv_python.exists():
        _log("Creating virtual environment...")
        _run(host_python + ["-m", "venv", str(venv_dir)], cwd=project_root)
    else:
        _log("Virtual environment already exists.")

    stamp_path = venv_dir / ".requirements.sha256"
    current_hash = _requirements_hash(requirements_path)
    install_needed, reason = _needs_install(current_hash, stamp_path, args.force_install)

    if not install_needed:
        _log("Validating installed packages...")
        missing = _missing_required_packages(venv_python, requirements_path, project_root)
        if missing:
            install_needed = True
            reason = f"missing required packages: {', '.join(missing)}"
        else:
            pip_check = _run([str(venv_python), "-m", "pip", "check"], cwd=project_root, check=False)
            if pip_check.returncode != 0:
                install_needed = True
                reason = "pip check reported broken dependencies"

    if install_needed:
        _log(f"Installing dependencies ({reason})...")
        _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=project_root)
        _run([str(venv_python), "-m", "pip", "install", "-r", str(requirements_path)], cwd=project_root)
        stamp_path.write_text(f"{current_hash}\n", encoding="utf-8")
        _log("Dependencies ready.")
    else:
        _log("Dependencies already up to date.")

    if args.no_run:
        _log("Setup complete (no-run mode).")
        return 0

    _log("Starting app...")
    app_run = _run([str(venv_python), "-B", str(project_root / "main.py")], cwd=project_root, check=False)
    return app_run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
