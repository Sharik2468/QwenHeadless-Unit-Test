from __future__ import annotations

from pathlib import Path


NO_TESTS_MATCHED_MARKERS = (
    "Нет тестов, соответствующих указанному фильтру",
    "No test matches the given testcase filter",
    "No tests matched the filter",
)

RUNTIME_TEST_MARKERS = (
    "_window.",
    "WaitForLayoutAndRender",
    "MouseMove(",
    "MouseDown(",
    "MouseUp(",
    "TranslatePoint(",
    "ApplyTemplate(",
    "Dispatcher.UIThread",
    "HeadlessWindowExtensions",
    "FindDescendant<",
    ".Show()",
    ".Content =",
    ".Focus(",
)

LOW_VALUE_TOKEN_MARKERS = (
    ".ResourceKey",
    "TypedTokens_",
)


def has_no_tests_matched(log_text: str) -> bool:
    return any(marker in log_text for marker in NO_TESTS_MATCHED_MARKERS)


def low_value_test_reason(file_text: str) -> str | None:
    has_runtime_markers = any(marker in file_text for marker in RUNTIME_TEST_MARKERS)
    has_low_value_token_markers = any(marker in file_text for marker in LOW_VALUE_TOKEN_MARKERS)
    has_resource_lookup_only = "TryFindResource(" in file_text and not has_runtime_markers

    if has_low_value_token_markers and not has_runtime_markers:
        return (
            "Generated test appears to validate token keys or static constants only and does not "
            "exercise a runtime control instance, visual tree, or rendered state."
        )

    if has_resource_lookup_only:
        return (
            "Generated test resolves resources with TryFindResource only, but does not exercise a "
            "runtime control instance, visual tree, focus/interaction state, or rendered output."
        )

    return None


def resolve_reported_test_paths(
    reported_paths: list[str],
    repo_root: Path,
    search_roots: list[Path],
) -> list[Path]:
    resolved: list[Path] = []
    for reported_path in reported_paths:
        path = Path(reported_path)
        if path.is_absolute() and path.exists():
            resolved.append(path)
            continue
        candidate = repo_root / reported_path
        if candidate.exists():
            resolved.append(candidate)
            continue

        basename = path.name
        for search_root in search_roots:
            matches = list(search_root.rglob(basename))
            if len(matches) == 1:
                resolved.append(matches[0])
                break
    return resolved
