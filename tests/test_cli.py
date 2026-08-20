from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from generate_uikit_tests import build_config, build_parser


class CliConfigTests(unittest.TestCase):
    def test_build_config_autodetects_nscore_uikit_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            unit = repo_root / "Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj"
            headless = (
                repo_root
                / "Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj"
            )
            styles = repo_root / "Avalonia/NSCore.Avalonia.Theme/Controls"
            unit.parent.mkdir(parents=True)
            headless.parent.mkdir(parents=True)
            styles.mkdir(parents=True)
            unit.write_text("<Project />", encoding="utf-8")
            headless.write_text("<Project />", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(
                [
                    "discover",
                    "--repo-root",
                    str(repo_root),
                    "--artifacts-dir",
                    str(repo_root / ".artifacts"),
                ]
            )

            config = build_config(args)

            self.assertEqual(config.unit_tests_project, unit)
            self.assertEqual(config.headless_tests_project, headless)
            self.assertEqual(config.styles_root, styles)
            self.assertEqual(config.custom_controls_root, styles)

    def test_build_config_preserves_reference_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            unit = repo_root / "Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj"
            headless = (
                repo_root
                / "Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj"
            )
            styles = repo_root / "Avalonia/NSCore.Avalonia.Theme/Controls"
            reference_dir = repo_root / "external-ref"
            unit.parent.mkdir(parents=True)
            headless.parent.mkdir(parents=True)
            styles.mkdir(parents=True)
            reference_dir.mkdir(parents=True)
            unit.write_text("<Project />", encoding="utf-8")
            headless.write_text("<Project />", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(
                [
                    "discover",
                    "--repo-root",
                    str(repo_root),
                    "--artifacts-dir",
                    str(repo_root / ".artifacts"),
                    "--reference-path",
                    str(reference_dir),
                ]
            )

            config = build_config(args)

            self.assertEqual(config.reference_paths, [reference_dir])

    def test_build_config_preserves_skip_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            unit = repo_root / "Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj"
            headless = (
                repo_root
                / "Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj"
            )
            styles = repo_root / "Avalonia/NSCore.Avalonia.Theme/Controls"
            unit.parent.mkdir(parents=True)
            headless.parent.mkdir(parents=True)
            styles.mkdir(parents=True)
            unit.write_text("<Project />", encoding="utf-8")
            headless.write_text("<Project />", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(
                [
                    "run",
                    "--repo-root",
                    str(repo_root),
                    "--artifacts-dir",
                    str(repo_root / ".artifacts"),
                    "--skip-controls",
                    "3",
                ]
            )

            config = build_config(args)

            self.assertEqual(config.skip_controls, 3)

    def test_build_config_preserves_start_from_control(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            unit = repo_root / "Avalonia/NSCore.UIKit.Controls.UnitTests/NSCore.UIKit.Controls.UnitTests.csproj"
            headless = (
                repo_root
                / "Avalonia/NSCore.UIKit.Headless.XUnit.UnitTests/NSCore.UIKit.Headless.XUnit.UnitTests.csproj"
            )
            styles = repo_root / "Avalonia/NSCore.Avalonia.Theme/Controls"
            unit.parent.mkdir(parents=True)
            headless.parent.mkdir(parents=True)
            styles.mkdir(parents=True)
            unit.write_text("<Project />", encoding="utf-8")
            headless.write_text("<Project />", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(
                [
                    "run",
                    "--repo-root",
                    str(repo_root),
                    "--artifacts-dir",
                    str(repo_root / ".artifacts"),
                    "--start-from-control",
                    "Counter",
                ]
            )

            config = build_config(args)

            self.assertEqual(config.start_from_control, "Counter")


if __name__ == "__main__":
    unittest.main()
