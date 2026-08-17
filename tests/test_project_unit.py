from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from generate_project_unit_tests import build_config, build_parser
from uikit_testgen.project_unit import autodetect_test_project


class ProjectUnitTests(unittest.TestCase):
    def test_autodetect_test_project_prefers_matching_unit_tests_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            source_project = repo_root / "src/MyProduct/MyProduct.csproj"
            best_test = repo_root / "tests/MyProduct.UnitTests/MyProduct.UnitTests.csproj"
            other_test = repo_root / "tests/Shared.Tests/Shared.Tests.csproj"
            source_project.parent.mkdir(parents=True)
            best_test.parent.mkdir(parents=True)
            other_test.parent.mkdir(parents=True)
            source_project.write_text("<Project />", encoding="utf-8")
            best_test.write_text("<Project />", encoding="utf-8")
            other_test.write_text("<Project />", encoding="utf-8")

            detected = autodetect_test_project(repo_root, source_project)

            self.assertEqual(detected, best_test)

    def test_build_config_uses_autodetected_test_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            source_project = repo_root / "src/App/App.csproj"
            test_project = repo_root / "tests/App.Tests/App.Tests.csproj"
            source_project.parent.mkdir(parents=True)
            test_project.parent.mkdir(parents=True)
            source_project.write_text("<Project />", encoding="utf-8")
            test_project.write_text("<Project />", encoding="utf-8")

            parser = build_parser()
            args = parser.parse_args(
                [
                    "plan",
                    "--repo-root",
                    str(repo_root),
                    "--source-project",
                    str(source_project),
                    "--artifacts-dir",
                    str(repo_root / ".artifacts"),
                ]
            )

            config = build_config(args)

            self.assertEqual(config.source_project, source_project)
            self.assertEqual(config.test_project, test_project)


if __name__ == "__main__":
    unittest.main()
