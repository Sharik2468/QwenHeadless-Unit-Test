#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_testgen.project_unit import (
    ProjectUnitConfig,
    ProjectUnitOrchestrator,
    autodetect_test_project,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan and generate classic unit tests for one .NET source project with Qwen headless."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("plan", "run", "resume"):
        subparser = subparsers.add_parser(command_name)
        add_shared_arguments(subparser)

    return parser


def add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-project", type=Path, required=True)
    parser.add_argument("--test-project", type=Path)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--qwen-bin", default="qwen")
    parser.add_argument("--model", default="qwen3-coder-plus")
    parser.add_argument("--approval-mode", default="yolo")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--max-repair-attempts", type=int, default=3)
    parser.add_argument("--max-session-turns", type=int, default=30)
    parser.add_argument("--max-wall-time", default="15m")
    parser.add_argument("--max-tool-calls", type=int, default=50)
    parser.add_argument("--test-filter-template", default="FullyQualifiedName~{candidate}")


def build_config(args: argparse.Namespace) -> ProjectUnitConfig:
    test_project = args.test_project or autodetect_test_project(args.repo_root, args.source_project)
    if test_project is None:
        raise ValueError(
            "Could not auto-detect a test project. Pass --test-project explicitly."
        )
    return ProjectUnitConfig(
        repo_root=args.repo_root,
        source_project=args.source_project,
        test_project=test_project,
        artifacts_dir=args.artifacts_dir,
        qwen_bin=args.qwen_bin,
        model=args.model,
        approval_mode=args.approval_mode,
        max_candidates=args.max_candidates,
        max_repair_attempts=args.max_repair_attempts,
        max_session_turns=args.max_session_turns,
        max_wall_time=args.max_wall_time,
        max_tool_calls=args.max_tool_calls,
        test_filter_template=args.test_filter_template,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = build_config(args)
    orchestrator = ProjectUnitOrchestrator(config)

    if args.command == "plan":
        print(json.dumps(orchestrator.plan(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "run":
        print(json.dumps(orchestrator.run(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "resume":
        print(json.dumps(orchestrator.resume(), indent=2, ensure_ascii=False))
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
