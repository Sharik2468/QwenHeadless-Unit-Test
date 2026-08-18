from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stringify_paths(payload: Any) -> Any:
    if isinstance(payload, Path):
        return str(payload)
    if isinstance(payload, list):
        return [_stringify_paths(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _stringify_paths(value) for key, value in payload.items()}
    return payload


@dataclass(slots=True)
class ControlManifest:
    name: str
    kind: str
    style_dir: Path
    relative_dir: str
    group_name: str
    theme_file: Path | None = None
    theme_files: list[Path] = field(default_factory=list)
    aggregate_file: Path | None = None
    aggregate_files: list[Path] = field(default_factory=list)
    resource_files: list[Path] = field(default_factory=list)
    token_files: list[Path] = field(default_factory=list)
    custom_code_files: list[Path] = field(default_factory=list)
    related_files: list[Path] = field(default_factory=list)
    discovered_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return _stringify_paths(asdict(self))


@dataclass(slots=True)
class ControlResult:
    control: str
    status: str
    created_tests: list[str] = field(default_factory=list)
    updated_tests: list[str] = field(default_factory=list)
    generation_outcome: str | None = None
    existing_tests_preserved: bool | None = None
    checks_added: dict[str, Any] = field(default_factory=dict)
    unresolved_issues: list[dict[str, Any]] = field(default_factory=list)
    build: dict[str, Any] = field(default_factory=dict)
    test_run: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ControlResult":
        supported_fields = {item.name for item in fields(cls)}
        normalized = {key: value for key, value in payload.items() if key in supported_fields}
        normalized.setdefault("control", str(payload.get("control", "")))
        normalized.setdefault("status", str(payload.get("status", "partial")))
        result = cls(**normalized)
        ignored_fields = sorted(set(payload) - supported_fields)
        if ignored_fields:
            result.notes.append(
                "Ignored unsupported report fields: " + ", ".join(ignored_fields)
            )
        return result


@dataclass(slots=True)
class ControlProgress:
    status: str = "pending"
    attempt: int = 0
    session_id: str | None = None
    fingerprint: str | None = None
    last_stage: str | None = None
    last_error: str | None = None
    started_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunConfig:
    repo_root: Path
    unit_tests_project: Path
    headless_tests_project: Path
    styles_root: Path
    custom_controls_root: Path | None
    artifacts_dir: Path
    qwen_bin: str = "qwen"
    model: str = "qwen3-coder-plus"
    include_control_pattern: str = "*"
    exclude_control_patterns: list[str] = field(default_factory=list)
    max_controls: int = -1
    max_repair_attempts: int = 3
    approval_mode: str = "yolo"
    max_session_turns: int = 30
    max_wall_time: str | None = None
    max_tool_calls: int | None = None
    build_after_each_control: bool = True
    test_after_each_control: bool = True
    unit_test_filter: str = "FullyQualifiedName~{control}"
    headless_test_filter: str = "FullyQualifiedName~{control}"
    reference_paths: list[Path] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _stringify_paths(asdict(self))
