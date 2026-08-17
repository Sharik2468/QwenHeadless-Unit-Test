#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from testgen_shared.pip_offline import build_install_command, run_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Python packages from a local folder without using internet access."
    )
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--packages", type=Path, default=Path(".resources/packages"))
    parser.add_argument("--python", dest="python_executable")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    command = build_install_command(
        requirements_file=args.requirements,
        packages_dir=args.packages,
        python_executable=args.python_executable,
    )
    return run_command(command, Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
