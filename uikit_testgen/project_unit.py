from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import utc_now_iso
from .qwen import QwenRunResult, run_qwen


@dataclass(slots=True)
class ProjectUnitConfig:
    repo_root: Path
    source_project: Path
    test_project: Path
    artifacts_dir: Path
    qwen_bin: str = "qwen"
    model: str = "qwen3-coder-plus"
    approval_mode: str = "yolo"
    max_candidates: int = 10
    max_repair_attempts: int = 3
    max_session_turns: int = 30
    max_wall_time: str = "15m"
    max_tool_calls: int = 50
    test_filter_template: str = "FullyQualifiedName~{candidate}"

    def to_dict(self) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(self).items()
        }


def autodetect_test_project(repo_root: Path, source_project: Path) -> Path | None:
    source_stem = source_project.stem.lower()
    source_dir_name = source_project.parent.name.lower()
    ranked: list[tuple[int, Path]] = []

    for path in repo_root.rglob("*.csproj"):
        lowered = path.name.lower()
        if path == source_project or "test" not in lowered:
            continue

        score = 0
        if source_stem in lowered:
            score += 5
        if source_dir_name in lowered:
            score += 4
        if any(token in lowered for token in ("unittest", "unittests", ".tests", "tests")):
            score += 2
        if path.parent.parent == source_project.parent.parent:
            score += 1
        ranked.append((score, path))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], str(item[1])))
    return ranked[0][1]


class ProjectUnitOrchestrator:
    def __init__(self, config: ProjectUnitConfig) -> None:
        self.config = config
        self.config.artifacts_dir.mkdir(parents=True, exist_ok=True)
        (self.config.artifacts_dir / "candidates").mkdir(parents=True, exist_ok=True)
        self.plan_path = self.config.artifacts_dir / "planning_result.json"
        self.progress_path = self.config.artifacts_dir / "project_unit_progress.json"

    def plan(self) -> dict[str, Any]:
        prompt = self._build_plan_prompt()
        output_path = self.config.artifacts_dir / "plan-qwen-output.json"
        result = self._invoke_qwen(
            prompt=prompt,
            output_path=output_path,
        )
        if not self.plan_path.exists():
            fallback = {
                "project": self.config.source_project.stem,
                "status": "partial",
                "summary": result.assistant_messages[-1] if result.assistant_messages else "",
                "candidates": [],
            }
            self.plan_path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False), encoding="utf-8")
        return json.loads(self.plan_path.read_text(encoding="utf-8"))

    def run(self) -> dict[str, Any]:
        plan = self.plan()
        candidates = plan.get("candidates", [])
        progress = {
            "status": "running",
            "project": self.config.source_project.stem,
            "source_project": str(self.config.source_project),
            "test_project": str(self.config.test_project),
            "updated_at": utc_now_iso(),
            "candidates": {
                candidate["id"]: {
                    "name": candidate.get("name", candidate["id"]),
                    "status": "pending",
                }
                for candidate in candidates
            },
        }
        self._save_progress(progress)

        for candidate in candidates:
            self._process_candidate(candidate, progress)

        progress["status"] = "completed"
        progress["updated_at"] = utc_now_iso()
        self._save_progress(progress)
        return progress

    def resume(self) -> dict[str, Any]:
        if not self.progress_path.exists() or not self.plan_path.exists():
            raise FileNotFoundError("Missing progress or plan file. Run 'run' or 'plan' first.")

        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        progress = json.loads(self.progress_path.read_text(encoding="utf-8"))
        progress["status"] = "running"

        for candidate in plan.get("candidates", []):
            state = progress.get("candidates", {}).get(candidate["id"], {}).get("status", "pending")
            if state in {"verified", "manual_review", "skipped"}:
                continue
            self._process_candidate(candidate, progress)

        progress["status"] = "completed"
        progress["updated_at"] = utc_now_iso()
        self._save_progress(progress)
        return progress

    def _process_candidate(self, candidate: dict[str, Any], progress: dict[str, Any]) -> None:
        candidate_id = candidate["id"]
        candidate_dir = self.config.artifacts_dir / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        report_path = candidate_dir / "result.json"
        prompt_path = candidate_dir / "prompt.txt"
        qwen_output_path = candidate_dir / "qwen-output.json"
        build_log_path = candidate_dir / "build.log"
        test_log_path = candidate_dir / "test.log"

        state = progress["candidates"].setdefault(
            candidate_id,
            {"name": candidate.get("name", candidate_id), "status": "pending"},
        )
        state["status"] = "running"
        state["updated_at"] = utc_now_iso()
        self._save_progress(progress)

        prompt = self._build_implementation_prompt(candidate, report_path)
        prompt_path.write_text(prompt, encoding="utf-8")
        qwen_result = self._invoke_qwen(prompt=prompt, output_path=qwen_output_path)

        build_ok = self._run_build(build_log_path)
        test_ok = build_ok and self._run_tests(candidate, test_log_path)

        if build_ok and test_ok:
            result = self._load_or_fallback_result(report_path, candidate, build_log_path, test_log_path, qwen_result)
            result["status"] = "verified"
            report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            state["status"] = "verified"
            state["updated_at"] = utc_now_iso()
            self._save_progress(progress)
            return

        session_id = qwen_result.session_id
        for attempt in range(1, self.config.max_repair_attempts + 1):
            state["status"] = "repairing"
            state["attempt"] = attempt
            state["updated_at"] = utc_now_iso()
            self._save_progress(progress)
            repair_prompt = self._build_repair_prompt(
                candidate,
                build_log_path.read_text(encoding="utf-8", errors="ignore") if build_log_path.exists() else "",
                test_log_path.read_text(encoding="utf-8", errors="ignore") if test_log_path.exists() else "",
            )
            prompt_path.write_text(repair_prompt, encoding="utf-8")
            qwen_result = self._invoke_qwen(
                prompt=repair_prompt,
                output_path=qwen_output_path,
                resume_session_id=session_id,
                max_session_turns=15,
                max_wall_time="10m",
                max_tool_calls=30,
            )
            session_id = qwen_result.session_id or session_id

            build_ok = self._run_build(build_log_path)
            test_ok = build_ok and self._run_tests(candidate, test_log_path)
            if build_ok and test_ok:
                result = self._load_or_fallback_result(
                    report_path,
                    candidate,
                    build_log_path,
                    test_log_path,
                    qwen_result,
                )
                result["status"] = "verified"
                report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                state["status"] = "verified"
                state["updated_at"] = utc_now_iso()
                self._save_progress(progress)
                return

        result = self._load_or_fallback_result(report_path, candidate, build_log_path, test_log_path, qwen_result)
        result["status"] = "manual_review"
        result.setdefault("notes", []).append("Automatic repair attempts exhausted.")
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        state["status"] = "manual_review"
        state["updated_at"] = utc_now_iso()
        self._save_progress(progress)

    def _build_plan_prompt(self) -> str:
        return f"""You are planning unit test coverage improvements for one .NET project.

Repository root:
{self.config.repo_root}

Source project:
{self.config.source_project}

Test project:
{self.config.test_project}

Goal:
Inspect the source project and identify the best unit-test candidates in this project.
Focus only on classic unit tests. Do not propose UI automation, headless UI tests, snapshot tests,
or end-to-end tests.

Prioritize:
- pure logic
- services
- validators
- parsers
- mappers
- stateful classes with deterministic behavior
- repository-owned application code

De-prioritize or skip:
- framework-owned behavior
- trivial DTOs
- classes that only proxy a dependency without logic
- code that requires heavy environment integration

Write a JSON plan to this path:
{self.plan_path}

JSON requirements:
- project
- status
- summary
- candidates: array of objects with
  - id
  - name
  - target_files
  - reason
  - proposed_tests
  - priority
  - complexity
  - test_filter_hint

Rules:
- return at most {self.config.max_candidates} candidates
- prefer candidates that are realistic to implement today
- if a file is too integration-heavy, skip it
- if existing tests already cover something well, do not duplicate them

After writing the JSON plan file, return a short plain-text summary.
"""

    def _build_implementation_prompt(self, candidate: dict[str, Any], report_path: Path) -> str:
        candidate_json = json.dumps(candidate, indent=2, ensure_ascii=False)
        return f"""You are implementing unit tests for one planned candidate in a .NET project.

Repository root:
{self.config.repo_root}

Source project:
{self.config.source_project}

Test project:
{self.config.test_project}

Candidate:
{candidate_json}

Goal:
Create or update classic unit tests only for this candidate. Do not add headless UI tests,
integration tests, or end-to-end tests.

Rules:
1. Prefer test-only changes.
2. Only modify production code if a tiny, clearly justified change is required to make intended behavior testable.
3. Keep tests deterministic and isolated.
4. Build the source and test project after changes.
5. Run relevant unit tests.
6. If tests fail, fix them if possible.
7. Write a JSON result file to:
{report_path}

The result JSON must include:
- candidate_id
- candidate_name
- status
- created_tests
- updated_tests
- build
- test_run
- notes

Return a short plain-text summary after writing the JSON result file.
"""

    def _build_repair_prompt(self, candidate: dict[str, Any], build_log: str, test_log: str) -> str:
        return f"""Fix the unit tests for candidate {candidate['id']}.

Only modify tests related to this candidate unless a tiny supporting change is required.

Build log excerpt:
{build_log[-12000:]}

Test log excerpt:
{test_log[-12000:]}
"""

    def _run_build(self, log_path: Path) -> bool:
        commands = [
            ["dotnet", "build", str(self.config.source_project)],
            ["dotnet", "build", str(self.config.test_project)],
        ]
        outputs: list[str] = []
        success = True
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=self.config.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            outputs.append(f"$ {' '.join(command)}\n{completed.stdout}\n{completed.stderr}")
            if completed.returncode != 0:
                success = False
        log_path.write_text("\n\n".join(outputs), encoding="utf-8")
        return success

    def _run_tests(self, candidate: dict[str, Any], log_path: Path) -> bool:
        hint = candidate.get("test_filter_hint") or candidate.get("name") or candidate["id"]
        command = [
            "dotnet",
            "test",
            str(self.config.test_project),
            "--filter",
            self.config.test_filter_template.format(candidate=hint),
        ]
        completed = subprocess.run(
            command,
            cwd=self.config.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        log_path.write_text(f"$ {' '.join(command)}\n{completed.stdout}\n{completed.stderr}", encoding="utf-8")
        return completed.returncode == 0

    def _invoke_qwen(
        self,
        prompt: str,
        output_path: Path,
        resume_session_id: str | None = None,
        max_session_turns: int | None = None,
        max_wall_time: str | None = None,
        max_tool_calls: int | None = None,
    ) -> QwenRunResult:
        return run_qwen(
            qwen_bin=self.config.qwen_bin,
            prompt=prompt,
            repo_root=self.config.repo_root,
            model=self.config.model,
            approval_mode=self.config.approval_mode,
            max_session_turns=max_session_turns or self.config.max_session_turns,
            max_wall_time=max_wall_time or self.config.max_wall_time,
            max_tool_calls=max_tool_calls or self.config.max_tool_calls,
            output_path=output_path,
            resume_session_id=resume_session_id,
        )

    def _load_or_fallback_result(
        self,
        report_path: Path,
        candidate: dict[str, Any],
        build_log_path: Path,
        test_log_path: Path,
        qwen_result: QwenRunResult,
    ) -> dict[str, Any]:
        if report_path.exists():
            return json.loads(report_path.read_text(encoding="utf-8"))
        return {
            "candidate_id": candidate["id"],
            "candidate_name": candidate.get("name", candidate["id"]),
            "status": "partial",
            "created_tests": [],
            "updated_tests": [],
            "build": {"log_file": str(build_log_path)},
            "test_run": {"log_file": str(test_log_path)},
            "notes": qwen_result.assistant_messages[-2:],
        }

    def _save_progress(self, progress: dict[str, Any]) -> None:
        self.progress_path.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
