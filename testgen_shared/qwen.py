from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class QwenRunResult:
    returncode: int
    stdout: str
    stderr: str
    session_id: str | None
    assistant_messages: list[str]
    raw_events: list[dict[str, Any]]


def _parse_json_output(stdout: str) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    session_id: str | None = None
    assistant_messages: list[str] = []
    raw_events: list[dict[str, Any]] = []

    stripped = stdout.strip()
    if not stripped:
        return session_id, assistant_messages, raw_events

    payload = json.loads(stripped.lstrip("\ufeff"))
    if not isinstance(payload, list):
        return session_id, assistant_messages, raw_events

    raw_events = [event for event in payload if isinstance(event, dict)]
    for event in raw_events:
        session_id = session_id or event.get("session_id")
        if event.get("type") != "assistant":
            continue
        message = event.get("message", {})
        content = message.get("content", [])
        text_chunks = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        if text_chunks:
            assistant_messages.append("\n".join(chunk for chunk in text_chunks if chunk))

    return session_id, assistant_messages, raw_events


def run_qwen(
    qwen_bin: str,
    prompt: str,
    repo_root: Path,
    model: str,
    approval_mode: str,
    max_session_turns: int,
    max_wall_time: str | None,
    max_tool_calls: int | None,
    output_path: Path,
    resume_session_id: str | None = None,
) -> QwenRunResult:
    command = build_qwen_command(
        qwen_bin=qwen_bin,
        model=model,
        approval_mode=approval_mode,
        max_session_turns=max_session_turns,
        max_wall_time=max_wall_time,
        max_tool_calls=max_tool_calls,
        resume_session_id=resume_session_id,
    )

    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Could not start Qwen executable '{qwen_bin}'. Make sure it is installed, available in PATH, "
            f"or pass an explicit path with --qwen-bin."
        ) from exc
    output_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path = output_path.with_suffix(".stderr.txt")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    try:
        session_id, assistant_messages, raw_events = _parse_json_output(completed.stdout)
    except JSONDecodeError as exc:
        stdout_excerpt = completed.stdout[:1000].strip()
        stderr_excerpt = completed.stderr[:1000].strip()
        raise RuntimeError(
            "Qwen returned non-JSON stdout despite '--output-format json'. "
            f"See raw stdout in '{output_path}' and stderr in '{stderr_path}'. "
            f"Stdout excerpt: {stdout_excerpt!r}. Stderr excerpt: {stderr_excerpt!r}."
        ) from exc
    return QwenRunResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        session_id=session_id,
        assistant_messages=assistant_messages,
        raw_events=raw_events,
    )


def build_qwen_command(
    qwen_bin: str,
    model: str,
    approval_mode: str,
    max_session_turns: int,
    max_wall_time: str | None,
    max_tool_calls: int | None,
    resume_session_id: str | None = None,
) -> list[str]:
    command = [
        qwen_bin,
        "--output-format",
        "json",
        "--model",
        model,
        "--max-session-turns",
        str(max_session_turns),
    ]
    if max_wall_time is not None:
        command.extend(["--max-wall-time", str(max_wall_time)])
    if max_tool_calls is not None:
        command.extend(["--max-tool-calls", str(max_tool_calls)])
    if approval_mode == "yolo":
        command.append("-y")
    else:
        command.extend(["--approval-mode", approval_mode])
    if resume_session_id:
        command.extend(["--resume", resume_session_id])
    return command
