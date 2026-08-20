from __future__ import annotations

import fnmatch
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .models import ControlManifest


AXAML_SUFFIXES = (
    ".axaml",
    "Theme.axaml",
    "Resources.axaml",
    "LightResources.axaml",
    "DarkResources.axaml",
)

INFRASTRUCTURE_DIR_NAMES = {"resources", "presenters"}


def _is_candidate_file(path: Path) -> bool:
    if path.suffix.lower() == ".cs" and path.name.endswith("Tokens.cs"):
        return True
    return any(path.name.endswith(suffix) for suffix in AXAML_SUFFIXES)


def _is_ignored_path(path: Path) -> bool:
    lowered_parts = {part.lower() for part in path.parts}
    return bool({"bin", "obj", ".git"} & lowered_parts)


def _pick_primary_file(files: list[Path], expected_name: str) -> Path | None:
    exact_name = expected_name.lower()
    for file_path in files:
        if file_path.name.lower() == exact_name:
            return file_path
    return files[0] if files else None


def _find_matching_custom_files(control_name: str, custom_root: Path | None) -> list[Path]:
    if custom_root is None or not custom_root.exists():
        return []

    matches: list[Path] = []
    token = f"class {control_name}".lower()
    for path in custom_root.rglob("*.cs"):
        if _is_ignored_path(path):
            continue
        if path.stem.lower() == control_name.lower():
            matches.append(path)
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")
        if token in content.lower():
            matches.append(path)
    return sorted(set(matches))


def discover_controls(
    styles_root: Path,
    custom_controls_root: Path | None = None,
    include_pattern: str = "*",
    exclude_patterns: list[str] | None = None,
    skip_controls: int = 0,
    max_controls: int = -1,
) -> list[ControlManifest]:
    exclude_patterns = exclude_patterns or []
    skip_controls = max(skip_controls, 0)
    grouped: dict[Path, list[Path]] = defaultdict(list)

    for path in styles_root.rglob("*"):
        if not path.is_file() or _is_ignored_path(path) or not _is_candidate_file(path):
            continue
        grouped[path.parent].append(path)

    manifests: list[ControlManifest] = []
    matched_controls = 0
    for directory, files in sorted(grouped.items()):
        if directory == styles_root:
            continue
        control_name = directory.name
        if control_name.lower() in INFRASTRUCTURE_DIR_NAMES:
            continue
        if not fnmatch.fnmatch(control_name, include_pattern):
            continue
        if any(fnmatch.fnmatch(control_name, pattern) for pattern in exclude_patterns):
            continue
        if matched_controls < skip_controls:
            matched_controls += 1
            continue
        matched_controls += 1

        relative_parts = directory.relative_to(styles_root).parts
        relative_dir = "/".join(relative_parts)
        group_name = relative_parts[0]
        theme_files = sorted([path for path in files if path.name.endswith("Theme.axaml")])
        aggregate_candidates = sorted(
            [
                path
                for path in files
                if path.suffix == ".axaml"
                and not path.name.endswith(
                    ("Theme.axaml", "Resources.axaml", "LightResources.axaml", "DarkResources.axaml")
                )
            ]
        )
        resource_files = sorted(
            [
                path
                for path in files
                if path.name.endswith(("Resources.axaml", "LightResources.axaml", "DarkResources.axaml"))
            ]
        )
        token_files = sorted([path for path in files if path.name.endswith("Tokens.cs")])
        custom_code_files = _find_matching_custom_files(control_name, custom_controls_root)
        related_files = sorted({*files, *custom_code_files})

        if not theme_files and not token_files and not custom_code_files:
            continue

        manifest = ControlManifest(
            name=control_name,
            kind="custom_control" if custom_code_files else "styled_control",
            style_dir=directory,
            relative_dir=relative_dir,
            group_name=group_name,
            theme_file=_pick_primary_file(theme_files, f"{control_name}Theme.axaml"),
            theme_files=theme_files,
            aggregate_file=_pick_primary_file(aggregate_candidates, f"{control_name}.axaml"),
            aggregate_files=aggregate_candidates,
            resource_files=resource_files,
            token_files=token_files,
            custom_code_files=custom_code_files,
            related_files=related_files,
        )
        manifests.append(manifest)
        if max_controls > 0 and len(manifests) >= max_controls:
            break

    return manifests


def build_fingerprint(manifest: ControlManifest, extra_files: list[Path] | None = None) -> str:
    digest = hashlib.sha256()
    for path in sorted({*manifest.related_files, *(extra_files or [])}):
        digest.update(str(path).encode("utf-8"))
        if not path.exists():
            digest.update(b"missing")
            continue
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def manifest_to_json(manifests: list[ControlManifest]) -> str:
    payload = [manifest.to_dict() for manifest in manifests]
    return json.dumps(payload, indent=2, ensure_ascii=False)
