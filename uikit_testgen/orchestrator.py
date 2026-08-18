from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from testgen_shared.qwen import QwenRunResult, run_qwen
from testgen_shared.test_quality import (
    has_no_tests_matched,
    low_value_test_reason,
    resolve_reported_test_paths,
)

from .discovery import build_fingerprint, discover_controls, manifest_to_json
from .models import ControlManifest, ControlProgress, ControlResult, RunConfig, utc_now_iso


class Orchestrator:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.config.artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.config.artifacts_dir / "controls").mkdir(parents=True, exist_ok=True)
        (self.config.artifacts_dir / "logs").mkdir(parents=True, exist_ok=True)
        self.progress_path = self.config.artifacts_dir / "progress.json"
        self.manifest_path = self.config.artifacts_dir / "controls_manifest.json"

    def discover(self) -> list[ControlManifest]:
        manifests = discover_controls(
            styles_root=self.config.styles_root,
            custom_controls_root=self.config.custom_controls_root,
            include_pattern=self.config.include_control_pattern,
            exclude_patterns=self.config.exclude_control_patterns,
            max_controls=self.config.max_controls,
        )
        self.manifest_path.write_text(manifest_to_json(manifests), encoding="utf-8")
        return manifests

    def run(self) -> dict[str, Any]:
        manifests = self.discover()
        progress = self._load_progress()
        progress.update(
            {
                "run_id": progress.get("run_id", utc_now_iso().replace(":", "-")),
                "repo_root": str(self.config.repo_root),
                "status": "running",
                "queue": [manifest.name for manifest in manifests],
                "current_control": None,
                "controls": progress.get("controls", {}),
            }
        )
        self._save_progress(progress)

        for manifest in manifests:
            progress["current_control"] = manifest.name
            self._save_progress(progress)
            self._process_control(manifest, progress)

        progress["status"] = "completed"
        progress["current_control"] = None
        self._save_progress(progress)
        return progress

    def resume(self) -> dict[str, Any]:
        if not self.progress_path.exists():
            raise FileNotFoundError(f"Progress file not found: {self.progress_path}")
        manifests = self._load_manifests()
        progress = self._load_progress()
        progress["status"] = "running"
        for manifest in manifests:
            status = progress.get("controls", {}).get(manifest.name, {}).get("status", "pending")
            if status in {"verified", "manual_review", "skipped"}:
                continue
            progress["current_control"] = manifest.name
            self._save_progress(progress)
            self._process_control(manifest, progress)
        progress["status"] = "completed"
        progress["current_control"] = None
        self._save_progress(progress)
        return progress

    def recheck(self) -> dict[str, Any]:
        manifests = self._load_manifests() if self.manifest_path.exists() else self.discover()
        progress = self._load_progress()
        progress["status"] = "running"
        progress["queue"] = [manifest.name for manifest in manifests]
        progress["controls"] = progress.get("controls", {})
        for manifest in manifests:
            progress["current_control"] = manifest.name
            self._save_progress(progress)
            self._process_control(manifest, progress, force_verify=True)
        progress["status"] = "completed"
        progress["current_control"] = None
        self._save_progress(progress)
        return progress

    def _process_control(
        self,
        manifest: ControlManifest,
        progress: dict[str, Any],
        force_verify: bool = False,
    ) -> None:
        control_dir = self.config.artifacts_dir / "controls" / manifest.name
        control_dir.mkdir(parents=True, exist_ok=True)
        report_path = control_dir / "result.json"
        research_summary_path = control_dir / "research_summary.json"
        research_prompt_path = control_dir / "research_prompt.txt"
        research_output_path = control_dir / "research-qwen-output.json"
        prompt_path = control_dir / "prompt.txt"
        qwen_output_path = control_dir / "qwen-output.json"
        build_log_path = control_dir / "build.log"
        test_log_path = control_dir / "test.log"
        manifest_path = control_dir / "control_manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        fingerprint = build_fingerprint(manifest)
        control_progress = ControlProgress(
            **progress.get("controls", {}).get(manifest.name, {})
        )
        control_progress.status = "running"
        control_progress.started_at = control_progress.started_at or utc_now_iso()
        control_progress.updated_at = utc_now_iso()
        control_progress.fingerprint = fingerprint
        progress.setdefault("controls", {})[manifest.name] = control_progress.to_dict()
        self._save_progress(progress)

        previous_result = self._read_json(report_path)
        if (
            previous_result
            and previous_result.get("status") in {"verified", "partial"}
            and control_progress.fingerprint == progress["controls"][manifest.name].get("fingerprint")
            and force_verify
        ):
            verify_result = self._verify_existing_tests(manifest, build_log_path, test_log_path)
            self._write_result(report_path, verify_result)
            self._set_control_status(progress, manifest.name, verify_result.status, "recheck")
            return

        if previous_result and force_verify:
            verify_result = self._verify_existing_tests(manifest, build_log_path, test_log_path)
            if verify_result.status == "verified":
                self._write_result(report_path, verify_result)
                self._set_control_status(progress, manifest.name, verify_result.status, "recheck")
                return

        research_summary = self._ensure_research_summary(
            manifest=manifest,
            research_summary_path=research_summary_path,
            research_prompt_path=research_prompt_path,
            research_output_path=research_output_path,
        )
        prompt = self._build_generation_prompt(manifest, report_path, research_summary)
        prompt_path.write_text(prompt, encoding="utf-8")
        qwen_result = self._invoke_generation(manifest.name, prompt, qwen_output_path)
        control_progress.session_id = qwen_result.session_id or control_progress.session_id
        progress["controls"][manifest.name] = control_progress.to_dict()
        self._save_progress(progress)
        early_quality_issue = self._evaluate_generated_test_quality(
            self._load_or_fallback_result(
                report_path,
                manifest.name,
                build_log_path,
                test_log_path,
                qwen_result,
                build_ok=False,
                test_ok=False,
            ),
            manifest,
        )
        if early_quality_issue:
            result = self._load_or_fallback_result(
                report_path,
                manifest.name,
                build_log_path,
                test_log_path,
                qwen_result,
                build_ok=False,
                test_ok=False,
            )
            result.status = "manual_review"
            result.unresolved_issues.append(
                {
                    "type": "quality_guardrail",
                    "reason": early_quality_issue,
                    "severity": "high",
                }
            )
            result.notes.append(
                "Generation stopped before build because the produced tests already degraded into low-value checks."
            )
            self._apply_execution_outcome(
                result,
                build_ok=False,
                test_ok=False,
                build_log_path=build_log_path,
                test_log_path=test_log_path,
                build_attempted=False,
                test_attempted=False,
            )
            self._write_result(report_path, result)
            self._set_control_status(progress, manifest.name, "manual_review", "quality_guardrail", control_progress.session_id)
            return

        build_ok = True
        test_ok = True
        build_attempted = False
        test_attempted = False
        if self.config.build_after_each_control:
            build_attempted = True
            build_ok = self._run_builds(build_log_path)
        if build_ok and self.config.test_after_each_control:
            test_attempted = True
            test_ok = self._run_tests(manifest, test_log_path)

        if build_ok and test_ok:
            result = self._load_or_fallback_result(
                report_path,
                manifest.name,
                build_log_path,
                test_log_path,
                qwen_result,
                build_ok=build_ok,
                test_ok=test_ok,
            )
            self._apply_execution_outcome(
                result,
                build_ok=build_ok,
                test_ok=test_ok,
                build_log_path=build_log_path,
                test_log_path=test_log_path,
                build_attempted=build_attempted,
                test_attempted=test_attempted,
            )
            quality_issue = self._evaluate_generated_test_quality(result, manifest)
            if quality_issue:
                result.status = "manual_review"
                result.unresolved_issues.append(
                    {
                        "type": "quality_guardrail",
                        "reason": quality_issue,
                        "severity": "high",
                    }
                )
                result.notes.append(
                    "Result rejected by runtime quality guardrail instead of being marked verified."
                )
                self._write_result(report_path, result)
                self._set_control_status(progress, manifest.name, "manual_review", "quality_guardrail", control_progress.session_id)
                return
            result.status = "verified"
            self._write_result(report_path, result)
            self._set_control_status(progress, manifest.name, "verified", "completed", control_progress.session_id)
            return

        result = None
        for attempt in range(1, self.config.max_repair_attempts + 1):
            progress["controls"][manifest.name]["attempt"] = attempt
            progress["controls"][manifest.name]["status"] = "repairing"
            progress["controls"][manifest.name]["updated_at"] = utc_now_iso()
            self._save_progress(progress)
            repair_prompt = self._build_repair_prompt(
                manifest.name,
                research_summary,
                build_log_path.read_text(encoding="utf-8", errors="ignore") if build_log_path.exists() else "",
                test_log_path.read_text(encoding="utf-8", errors="ignore") if test_log_path.exists() else "",
            )
            prompt_path.write_text(repair_prompt, encoding="utf-8")
            qwen_result = self._invoke_generation(
                manifest.name,
                repair_prompt,
                qwen_output_path,
                session_turns=15,
            )
            control_progress.session_id = qwen_result.session_id or control_progress.session_id
            progress["controls"][manifest.name] = control_progress.to_dict()
            self._save_progress(progress)
            early_quality_issue = self._evaluate_generated_test_quality(
                self._load_or_fallback_result(
                    report_path,
                    manifest.name,
                    build_log_path,
                    test_log_path,
                    qwen_result,
                    build_ok=False,
                    test_ok=False,
                ),
                manifest,
            )
            if early_quality_issue:
                result = self._load_or_fallback_result(
                    report_path,
                    manifest.name,
                    build_log_path,
                    test_log_path,
                    qwen_result,
                    build_ok=False,
                    test_ok=False,
                )
                result.status = "manual_review"
                result.unresolved_issues.append(
                    {
                        "type": "quality_guardrail",
                        "reason": early_quality_issue,
                        "severity": "high",
                    }
                )
                result.notes.append(
                    "Repair loop stopped because the generated tests degraded into low-value checks."
                )
                self._apply_execution_outcome(
                    result,
                    build_ok=False,
                    test_ok=False,
                    build_log_path=build_log_path,
                    test_log_path=test_log_path,
                    build_attempted=False,
                    test_attempted=False,
                )
                self._write_result(report_path, result)
                self._set_control_status(progress, manifest.name, "manual_review", "quality_guardrail", control_progress.session_id)
                return

            build_attempted = True
            build_ok = self._run_builds(build_log_path)
            test_attempted = build_ok and self.config.test_after_each_control
            test_ok = build_ok and self._run_tests(manifest, test_log_path)
            if build_ok and test_ok:
                result = self._load_or_fallback_result(
                    report_path,
                    manifest.name,
                    build_log_path,
                    test_log_path,
                    qwen_result,
                    build_ok=build_ok,
                    test_ok=test_ok,
                )
                self._apply_execution_outcome(
                    result,
                    build_ok=build_ok,
                    test_ok=test_ok,
                    build_log_path=build_log_path,
                    test_log_path=test_log_path,
                    build_attempted=build_attempted,
                    test_attempted=test_attempted,
                )
                quality_issue = self._evaluate_generated_test_quality(result, manifest)
                if quality_issue:
                    result.status = "manual_review"
                    result.unresolved_issues.append(
                        {
                            "type": "quality_guardrail",
                            "reason": quality_issue,
                            "severity": "high",
                        }
                    )
                    result.notes.append(
                        "Result rejected by runtime quality guardrail instead of being marked verified."
                    )
                    self._write_result(report_path, result)
                    self._set_control_status(progress, manifest.name, "manual_review", "quality_guardrail", control_progress.session_id)
                    return
                result.status = "verified"
                self._write_result(report_path, result)
                self._set_control_status(progress, manifest.name, "verified", "completed", control_progress.session_id)
                return

        result = self._load_or_fallback_result(
            report_path,
            manifest.name,
            build_log_path,
            test_log_path,
            qwen_result,
            build_ok=build_ok,
            test_ok=test_ok,
        )
        self._apply_execution_outcome(
            result,
            build_ok=build_ok,
            test_ok=test_ok,
            build_log_path=build_log_path,
            test_log_path=test_log_path,
            build_attempted=build_attempted,
            test_attempted=test_attempted,
        )
        result.status = "manual_review"
        result.notes.append("Automatic repair attempts exhausted.")
        self._write_result(report_path, result)
        self._set_control_status(progress, manifest.name, "manual_review", "failed", control_progress.session_id)

    def _invoke_generation(
        self,
        control_name: str,
        prompt: str,
        output_path: Path,
        resume_session_id: str | None = None,
        session_turns: int | None = None,
        wall_time: str | None = None,
        tool_calls: int | None = None,
    ) -> QwenRunResult:
        return run_qwen(
            qwen_bin=self.config.qwen_bin,
            prompt=prompt,
            repo_root=self.config.repo_root,
            model=self.config.model,
            approval_mode=self.config.approval_mode,
            max_session_turns=session_turns or self.config.max_session_turns,
            max_wall_time=wall_time or self.config.max_wall_time,
            max_tool_calls=tool_calls or self.config.max_tool_calls,
            output_path=output_path,
            resume_session_id=resume_session_id,
            include_directories=self._extra_include_directories(),
        )

    def _build_generation_prompt(
        self,
        manifest: ControlManifest,
        report_path: Path,
        research_summary: dict[str, Any],
    ) -> str:
        relevant_files = "\n".join(f"- {path}" for path in manifest.related_files)
        reference_paths = self._gather_reference_paths()
        reference_section = (
            "\n".join(f"- {path}" for path in reference_paths)
            if reference_paths
            else "- None provided."
        )
        manifest_json = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
        research_summary_json = json.dumps(research_summary, indent=2, ensure_ascii=False)
        unit_test_policy = (
            "This control has repository-owned custom code files, so classic unit tests for its custom logic are allowed."
            if self._should_run_unit_tests(manifest)
            else "This control has no repository-owned custom code files. Do NOT generate classic unit tests in the unit test project for it; focus on meaningful headless/runtime verification only."
        )
        return f"""You are generating or updating automated tests for one Avalonia UIKit control.

Goal:
Create or update unit tests and headless UI tests only for the target control described below.

Hard constraints:
1. Do not modify production code unless it is absolutely required to make an existing intended API testable. Prefer test-only changes.
2. Do not modify tests for unrelated controls.
3. Do not test built-in Avalonia behavior unless the target control adds custom behavior or custom styling logic on top.
4. Prefer stable assertions over fragile pixel-perfect assertions unless the control already has a stable visual testing pattern.
5. If some expected runtime assertion is ambiguous because of template indirection or unstable visual tree details, keep the stable tests and record the issue in the report instead of inventing brittle checks.
6. The repository already has static analysis for token declarations and XAML resource wiring. Your tests should focus on runtime verification:
   - style values actually applied to the control/template
   - state changes (default/hover/pressed/disabled) where relevant
   - size, spacing, thickness, corner radius, fonts, colors where runtime verification is feasible
   - custom control logic for repository-owned controls only
7. After writing tests, build and run relevant tests. If they fail, fix the tests if possible.
8. Write a JSON report file to the requested report path.
9. Invalid tests must NOT be generated. Specifically, do not generate tests that only compare token names, ResourceKey strings, or other static constants without exercising a real control instance or runtime resource application.
10. If meaningful runtime verification is not possible for a token or style binding, do not replace it with a weak string-based test. Record the gap in unresolved_issues and stop.

Target control:
{manifest_json}

Relevant files:
{relevant_files}

Projects:
- Unit tests project: {self.config.unit_tests_project}
- Headless tests project: {self.config.headless_tests_project}

Unit test policy:
{unit_test_policy}

Reference files and directories to inspect before guessing APIs, control types, namespaces, or test patterns:
{reference_section}

Research summary from a separate exploration session:
{research_summary_json}

Tasks:
1. Analyze the target control.
2. Decide which tests are appropriate:
   - headless runtime style/state tests
   - unit tests for custom logic only when the control has repository-owned custom code files
   - skip fake/low-value tests entirely
3. Use the reference files/directories above before making assumptions about:
   - control CLR types or namespaces
   - headless helper patterns
   - visual-tree traversal utilities
   - how existing tests access runtime-applied values
4. Create or update tests in the specified test projects.
5. Build the affected test projects.
6. Run relevant tests for this control.
7. If build/tests fail, fix up to the limits of this run.
8. Write the final report JSON to:
{report_path}

The final report JSON must include:
- control
- status
- created_tests
- updated_tests
- checks_added
- unresolved_issues
- build
- test_run
- notes

A generated test is only acceptable if it checks runtime-applied behavior or values on the actual control, its template, or its rendered state.
Tests that only validate ResourceKey values or typed token constant names are invalid.

Return a short final summary in plain text after writing the report.
"""

    def _build_repair_prompt(
        self,
        control_name: str,
        research_summary: dict[str, Any],
        build_log: str,
        test_log: str,
    ) -> str:
        reference_paths = self._gather_reference_paths()
        reference_section = (
            "\n".join(f"- {path}" for path in reference_paths)
            if reference_paths
            else "- None provided."
        )
        research_summary_json = json.dumps(research_summary, indent=2, ensure_ascii=False)
        return f"""Fix the generated tests for control {control_name}.

Only modify tests related to {control_name}. Prefer stable assertions. If some checks are too brittle,
keep the reliable tests and record unresolved cases in the report file for this control.
Do NOT degrade into tests that only check ResourceKey values, token names, or TryFindResource-only resource existence.
If meaningful runtime verification cannot be restored, stop and keep the control in manual_review instead of weakening the assertions.
Re-inspect these reference files/directories before guessing APIs or helper patterns:
{reference_section}

Reuse this research summary instead of re-reading broad source trees unless absolutely necessary:
{research_summary_json}

Build log excerpt:
{build_log[-12000:]}

Test log excerpt:
{test_log[-12000:]}
"""

    def _verify_existing_tests(
        self,
        manifest: ControlManifest,
        build_log_path: Path,
        test_log_path: Path,
    ) -> ControlResult:
        build_ok = True
        test_ok = True
        if self.config.build_after_each_control:
            build_ok = self._run_builds(build_log_path)
        if build_ok and self.config.test_after_each_control:
            test_ok = self._run_tests(manifest, test_log_path)
        return ControlResult(
            control=manifest.name,
            status="verified" if build_ok and test_ok else "partial",
            build={
                "attempted": self.config.build_after_each_control,
                "passed": build_ok,
                "log_file": str(build_log_path),
            },
            test_run={
                "attempted": self.config.test_after_each_control,
                "passed": test_ok,
                "log_file": str(test_log_path),
                "failed_tests": [],
            },
            notes=["Rechecked existing tests without regeneration."],
        )

    def _run_builds(self, log_path: Path) -> bool:
        commands = [
            ["dotnet", "build", str(self.config.unit_tests_project)],
            ["dotnet", "build", str(self.config.headless_tests_project)],
        ]
        outputs: list[str] = []
        success = True
        for command in commands:
            completed = self._run_subprocess(command)
            outputs.append(f"$ {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
            if completed.returncode != 0:
                success = False
        log_path.write_text("\n\n".join(outputs), encoding="utf-8")
        return success

    def _run_tests(self, manifest: ControlManifest, log_path: Path) -> bool:
        commands: list[list[str]] = []
        if self._should_run_unit_tests(manifest):
            commands.append(
                [
                    "dotnet",
                    "test",
                    str(self.config.unit_tests_project),
                    "--filter",
                    self.config.unit_test_filter.format(control=manifest.name),
                ]
            )
        commands.append(
            [
                "dotnet",
                "test",
                str(self.config.headless_tests_project),
                "--filter",
                self.config.headless_test_filter.format(control=manifest.name),
            ]
        )
        outputs: list[str] = []
        success = True
        for command in commands:
            completed = self._run_subprocess(command)
            outputs.append(f"$ {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
            if completed.returncode != 0 or has_no_tests_matched(f"{completed.stdout}\n{completed.stderr}"):
                success = False
        log_path.write_text("\n\n".join(outputs), encoding="utf-8")
        return success

    def _evaluate_generated_test_quality(self, result: ControlResult, manifest: ControlManifest) -> str | None:
        reported_paths = [*result.created_tests, *result.updated_tests]
        if not reported_paths:
            return "No created or updated test files were reported, so the run cannot be considered verified."

        resolved_paths = resolve_reported_test_paths(
            reported_paths=reported_paths,
            repo_root=self.config.repo_root,
            search_roots=[
                self.config.unit_tests_project.parent,
                self.config.headless_tests_project.parent,
            ],
        )
        if not resolved_paths:
            return "Generated test file paths could not be resolved on disk for quality inspection."

        for path in resolved_paths:
            if not self._should_run_unit_tests(manifest) and self.config.unit_tests_project.parent in path.parents:
                return (
                    f"{path}: styled_control without custom_code_files should not generate classic unit tests in "
                    f"{self.config.unit_tests_project.parent}."
                )
            file_text = path.read_text(encoding="utf-8", errors="ignore")
            reason = low_value_test_reason(file_text)
            if reason:
                return f"{path}: {reason}"
        return None

    def _should_run_unit_tests(self, manifest: ControlManifest) -> bool:
        return bool(manifest.custom_code_files)

    def _apply_execution_outcome(
        self,
        result: ControlResult,
        build_ok: bool,
        test_ok: bool,
        build_log_path: Path,
        test_log_path: Path,
        build_attempted: bool,
        test_attempted: bool,
    ) -> None:
        result.build = {
            "attempted": build_attempted,
            "passed": build_ok,
            "log_file": str(build_log_path),
        }
        result.test_run = {
            "attempted": test_attempted,
            "passed": test_ok,
            "log_file": str(test_log_path),
            "failed_tests": [],
        }

    def _ensure_research_summary(
        self,
        manifest: ControlManifest,
        research_summary_path: Path,
        research_prompt_path: Path,
        research_output_path: Path,
    ) -> dict[str, Any]:
        if research_summary_path.exists():
            return json.loads(research_summary_path.read_text(encoding="utf-8"))

        prompt = self._build_research_prompt(manifest, research_summary_path)
        research_prompt_path.write_text(prompt, encoding="utf-8")
        qwen_result = self._invoke_generation(
            manifest.name,
            prompt,
            research_output_path,
            session_turns=12,
        )
        if not research_summary_path.exists():
            fallback = {
                "control": manifest.name,
                "status": "partial",
                "summary": qwen_result.assistant_messages[-1] if qwen_result.assistant_messages else "",
                "control_type": None,
                "allowed_test_projects": ["headless"] if not self._should_run_unit_tests(manifest) else ["headless", "unit"],
                "must_verify": [],
                "avoid": ["Do not invent APIs or namespaces."],
            }
            research_summary_path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(research_summary_path.read_text(encoding="utf-8"))

    def _build_research_prompt(self, manifest: ControlManifest, research_summary_path: Path) -> str:
        reference_paths = self._gather_reference_paths()
        reference_section = (
            "\n".join(f"- {path}" for path in reference_paths)
            if reference_paths
            else "- None provided."
        )
        manifest_json = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
        unit_test_policy = (
            "Unit tests for repository-owned custom logic are allowed."
            if self._should_run_unit_tests(manifest)
            else "Do NOT plan classic unit tests in the unit test project for this control; it has no repository-owned custom code files."
        )
        return f"""You are the research phase for one Avalonia UIKit control.

Do NOT write tests, do NOT build projects, and do NOT modify repository source/test files during this phase.
Writing the research summary artifact requested below is required and explicitly allowed.
Your only goal is to inspect the control, framework sources, and existing test helpers so the implementation phase can start from a compact, grounded summary instead of guessing.

Target control manifest:
{manifest_json}

Reference files and directories to inspect as needed:
{reference_section}

Unit test policy:
{unit_test_policy}

Research output requirements:
- Write a JSON summary file to:
{research_summary_path}
- The JSON must include:
  - control
  - status
  - control_type
  - relevant_reference_files
  - allowed_test_projects
  - must_verify
  - avoid
  - summary

Rules:
- Prefer narrow, concrete findings over broad narration.
- Identify the CLR type/namespace only if you can confirm it from the inspected sources.
- If a type/member/visual structure cannot be confirmed, list it in avoid instead of guessing.
- Keep the summary compact so a fresh implementation session can use it without replaying all exploration context.

Return a short plain-text summary after writing the JSON file.
"""

    def _gather_reference_paths(self) -> list[Path]:
        auto_reference_candidates = [
            self.config.headless_tests_project.parent / "HeadlessTestBase.cs",
            self.config.headless_tests_project.parent / "ButtonTest" / "ButtonTestsBase.cs",
            self.config.headless_tests_project.parent / "ButtonTest" / "ButtonTestHelpers.cs",
            *self.config.reference_paths,
        ]
        seen: set[Path] = set()
        resolved: list[Path] = []
        for path in auto_reference_candidates:
            if not path.exists():
                continue
            resolved_path = path.resolve()
            if resolved_path in seen:
                continue
            seen.add(resolved_path)
            resolved.append(path)
        return resolved

    def _extra_include_directories(self) -> list[Path]:
        include_dirs: list[Path] = []
        for path in [self.config.custom_controls_root, *self.config.reference_paths]:
            if path is None:
                continue
            directory = path if path.is_dir() else path.parent
            try:
                if directory.resolve().is_relative_to(self.config.repo_root.resolve()):
                    continue
            except FileNotFoundError:
                pass
            if directory.exists() and directory not in include_dirs:
                include_dirs.append(directory)
        return include_dirs

    def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=self.config.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            executable = command[0]
            raise RuntimeError(
                f"Could not start executable '{executable}'. Make sure it is installed and available in PATH."
            ) from exc

    def _load_or_fallback_result(
        self,
        report_path: Path,
        control_name: str,
        build_log_path: Path,
        test_log_path: Path,
        qwen_result: QwenRunResult,
        build_ok: bool,
        test_ok: bool,
    ) -> ControlResult:
        if report_path.exists():
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            return ControlResult.from_dict(payload)

        return ControlResult(
            control=control_name,
            status="partial",
            build={
                "attempted": self.config.build_after_each_control,
                "passed": build_ok,
                "log_file": str(build_log_path),
            },
            test_run={
                "attempted": self.config.test_after_each_control,
                "passed": test_ok,
                "log_file": str(test_log_path),
                "failed_tests": [],
            },
            notes=qwen_result.assistant_messages[-2:],
        )

    def _set_control_status(
        self,
        progress: dict[str, Any],
        control_name: str,
        status: str,
        stage: str,
        session_id: str | None = None,
    ) -> None:
        record = progress.setdefault("controls", {}).setdefault(control_name, {})
        record["status"] = status
        record["last_stage"] = stage
        record["updated_at"] = utc_now_iso()
        if session_id:
            record["session_id"] = session_id
        self._save_progress(progress)

    def _write_result(self, path: Path, result: ControlResult) -> None:
        path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_manifests(self) -> list[ControlManifest]:
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifests = []
        for item in payload:
            manifests.append(
                ControlManifest(
                    name=item["name"],
                    kind=item["kind"],
                    style_dir=Path(item["style_dir"]),
                    relative_dir=item["relative_dir"],
                    group_name=item["group_name"],
                    theme_file=Path(item["theme_file"]) if item.get("theme_file") else None,
                    theme_files=[Path(path) for path in item.get("theme_files", [])],
                    aggregate_file=Path(item["aggregate_file"]) if item.get("aggregate_file") else None,
                    aggregate_files=[Path(path) for path in item.get("aggregate_files", [])],
                    resource_files=[Path(path) for path in item.get("resource_files", [])],
                    token_files=[Path(path) for path in item.get("token_files", [])],
                    custom_code_files=[Path(path) for path in item.get("custom_code_files", [])],
                    related_files=[Path(path) for path in item.get("related_files", [])],
                    discovered_at=item.get("discovered_at", utc_now_iso()),
                )
            )
        return manifests

    def _load_progress(self) -> dict[str, Any]:
        return self._read_json(self.progress_path) or {}

    def _save_progress(self, progress: dict[str, Any]) -> None:
        self.progress_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
