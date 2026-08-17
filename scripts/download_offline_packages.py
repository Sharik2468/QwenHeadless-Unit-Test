#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from testgen_shared.pip_offline import build_download_command, run_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Python packages from requirements.txt into a local folder for offline installation."
    )
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    parser.add_argument("--dest", type=Path, default=Path(".resources/packages"))
    parser.add_argument("--python", dest="python_executable")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    command = build_download_command(
        requirements_file=args.requirements,
        destination_dir=args.dest,
        python_executable=args.python_executable,
    )
    return run_command(command, Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
