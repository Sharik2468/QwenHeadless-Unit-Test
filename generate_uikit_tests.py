#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from uikit_testgen.models import RunConfig
from uikit_testgen.orchestrator import Orchestrator


DEFAULT_LAYOUT = {
    "unit_tests_project": Path("Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj"),
    "headless_tests_project": Path(
        "Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj"
    ),
    "styles_root": Path("Avalonia/NSCore.Avalonia.Theme/Controls"),
    "custom_controls_root": Path("Avalonia/NSCore.Avalonia.Theme/Controls"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover Avalonia UIKit controls and orchestrate Qwen headless test generation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("discover", "run", "recheck", "resume"):
        subparser = subparsers.add_parser(command_name)
        add_shared_arguments(subparser, include_optional_roots=command_name != "resume")

    return parser


def add_shared_arguments(parser: argparse.ArgumentParser, include_optional_roots: bool) -> None:
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--unit-tests-project", type=Path)
    parser.add_argument("--headless-tests-project", type=Path)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--qwen-bin", default="qwen")
    parser.add_argument("--model", default="qwen3-coder-plus")
    parser.add_argument("--include-control-pattern", default="*")
    parser.add_argument("--exclude-control-pattern", action="append", default=[])
    parser.add_argument("--max-controls", type=int, default=-1)
    parser.add_argument("--max-repair-attempts", type=int, default=3)
    parser.add_argument("--approval-mode", default="yolo")
    parser.add_argument("--max-session-turns", type=int, default=30)
    parser.add_argument("--max-wall-time", default="15m")
    parser.add_argument("--max-tool-calls", type=int, default=50)
    parser.add_argument("--unit-test-filter", default="FullyQualifiedName~{control}")
    parser.add_argument("--headless-test-filter", default="FullyQualifiedName~{control}")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    if include_optional_roots:
        parser.add_argument("--styles-root", type=Path)
        parser.add_argument("--custom-controls-root", type=Path)
    else:
        parser.add_argument("--styles-root", type=Path, required=False)
        parser.add_argument("--custom-controls-root", type=Path, required=False)


def resolve_layout_path(repo_root: Path, explicit: Path | None, key: str) -> Path:
    if explicit is not None:
        return explicit
    candidate = repo_root / DEFAULT_LAYOUT[key]
    if candidate.exists():
        return candidate
    raise ValueError(
        f"Could not resolve '{key}'. Pass the corresponding CLI argument explicitly or use a repo with the expected layout."
    )


def build_config(args: argparse.Namespace) -> RunConfig:
    unit_tests_project = resolve_layout_path(args.repo_root, args.unit_tests_project, "unit_tests_project")
    headless_tests_project = resolve_layout_path(
        args.repo_root,
        args.headless_tests_project,
        "headless_tests_project",
    )
    styles_root = resolve_layout_path(args.repo_root, args.styles_root, "styles_root")
    custom_controls_root = args.custom_controls_root
    if custom_controls_root is None:
        default_custom_root = args.repo_root / DEFAULT_LAYOUT["custom_controls_root"]
        custom_controls_root = default_custom_root if default_custom_root.exists() else styles_root
    return RunConfig(
        repo_root=args.repo_root,
        unit_tests_project=unit_tests_project,
        headless_tests_project=headless_tests_project,
        styles_root=styles_root,
        custom_controls_root=custom_controls_root,
        artifacts_dir=args.artifacts_dir,
        qwen_bin=args.qwen_bin,
        model=args.model,
        include_control_pattern=args.include_control_pattern,
        exclude_control_patterns=list(args.exclude_control_pattern),
        max_controls=args.max_controls,
        max_repair_attempts=args.max_repair_attempts,
        approval_mode=args.approval_mode,
        max_session_turns=args.max_session_turns,
        max_wall_time=args.max_wall_time,
        max_tool_calls=args.max_tool_calls,
        build_after_each_control=not args.skip_build,
        test_after_each_control=not args.skip_tests,
        unit_test_filter=args.unit_test_filter,
        headless_test_filter=args.headless_test_filter,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = build_config(args)
    orchestrator = Orchestrator(config)

    if args.command == "discover":
        manifests = orchestrator.discover()
        print(json.dumps([manifest.to_dict() for manifest in manifests], indent=2, ensure_ascii=False))
        return 0
    if args.command == "run":
        print(json.dumps(orchestrator.run(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "recheck":
        print(json.dumps(orchestrator.recheck(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "resume":
        print(json.dumps(orchestrator.resume(), indent=2, ensure_ascii=False))
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
