from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uikit_testgen.discovery import build_fingerprint, discover_controls


class DiscoveryTests(unittest.TestCase):
    def test_discover_controls_groups_nested_style_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            styles_root = root / "Controls"
            button_dir = styles_root / "Button"
            icon_button_dir = button_dir / "IconButton"
            resources_dir = styles_root / "Resources"
            button_dir.mkdir(parents=True)
            icon_button_dir.mkdir(parents=True)
            resources_dir.mkdir(parents=True)

            (styles_root / "Controls.axaml").write_text("<ResourceDictionary />", encoding="utf-8")
            (button_dir / "ButtonTheme.axaml").write_text("<Styles />", encoding="utf-8")
            (button_dir / "Button.axaml").write_text("<ResourceDictionary />", encoding="utf-8")
            (button_dir / "ButtonResources.axaml").write_text("<ResourceDictionary />", encoding="utf-8")
            (icon_button_dir / "IconButtonTheme.axaml").write_text("<Styles />", encoding="utf-8")
            (resources_dir / "InputTokens.cs").write_text("class Tokens {}", encoding="utf-8")

            manifests = discover_controls(styles_root)

            self.assertEqual([manifest.name for manifest in manifests], ["Button", "IconButton"])
            button_manifest = manifests[0]
            self.assertEqual(button_manifest.theme_file.name, "ButtonTheme.axaml")
            self.assertEqual(button_manifest.aggregate_file.name, "Button.axaml")
            self.assertEqual(len(button_manifest.resource_files), 1)
            self.assertEqual(button_manifest.relative_dir, "Button")
            self.assertEqual(button_manifest.group_name, "Button")

    def test_discover_controls_attaches_matching_custom_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            styles_root = root / "Controls"
            custom_root = root / "UIKit"
            time_box_dir = styles_root / "TimeBox"
            time_box_dir.mkdir(parents=True)
            custom_root.mkdir(parents=True)

            (time_box_dir / "TimeBoxTheme.axaml").write_text("<Styles />", encoding="utf-8")
            (custom_root / "TimeBox.cs").write_text(
                "public class TimeBox : TemplatedControl {}",
                encoding="utf-8",
            )

            manifests = discover_controls(styles_root, custom_root)

            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0].kind, "custom_control")
            self.assertEqual([path.name for path in manifests[0].custom_code_files], ["TimeBox.cs"])
            self.assertEqual(manifests[0].relative_dir, "TimeBox")

    def test_fingerprint_changes_when_related_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            styles_root = root / "Controls"
            button_dir = styles_root / "Button"
            button_dir.mkdir(parents=True)
            theme_file = button_dir / "ButtonTheme.axaml"
            theme_file.write_text("<Styles />", encoding="utf-8")

            manifest = discover_controls(styles_root)[0]
            first = build_fingerprint(manifest)
            theme_file.write_text("<Styles>updated</Styles>", encoding="utf-8")
            manifest = discover_controls(styles_root)[0]
            second = build_fingerprint(manifest)

            self.assertNotEqual(first, second)

    def test_discovery_respects_include_and_exclude_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            styles_root = root / "Controls"
            for control_name in ("Button", "CheckBox", "Counter"):
                control_dir = styles_root / control_name
                control_dir.mkdir(parents=True)
                (control_dir / f"{control_name}Theme.axaml").write_text("<Styles />", encoding="utf-8")

            manifests = discover_controls(
                styles_root,
                include_pattern="C*",
                exclude_patterns=["Counter"],
            )

            self.assertEqual([manifest.name for manifest in manifests], ["CheckBox"])


if __name__ == "__main__":
    unittest.main()
