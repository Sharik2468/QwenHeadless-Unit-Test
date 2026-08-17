from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def default_python_executable() -> str:
    return sys.executable or "python3"


def build_download_command(
    requirements_file: Path,
    destination_dir: Path,
    python_executable: str | None = None,
) -> list[str]:
    python_executable = python_executable or default_python_executable()
    return [
        python_executable,
        "-m",
        "pip",
        "download",
        "-r",
        str(requirements_file),
        "-d",
        str(destination_dir),
    ]


def build_install_command(
    requirements_file: Path,
    packages_dir: Path,
    python_executable: str | None = None,
) -> list[str]:
    python_executable = python_executable or default_python_executable()
    return [
        python_executable,
        "-m",
        "pip",
        "install",
        "--no-index",
        f"--find-links={packages_dir}",
        "-r",
        str(requirements_file),
    ]


def run_command(command: list[str], working_directory: Path) -> int:
    completed = subprocess.run(command, cwd=working_directory, check=False)
    return completed.returncode
