from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from testgen_shared.pip_offline import build_download_command, build_install_command


class OfflinePipTests(unittest.TestCase):
    def test_build_download_command_uses_requirements_and_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requirements = root / "requirements.txt"
            destination = root / "packages"
            command = build_download_command(
                requirements_file=requirements,
                destination_dir=destination,
                python_executable="python3",
            )

            self.assertEqual(
                command,
                [
                    "python3",
                    "-m",
                    "pip",
                    "download",
                    "-r",
                    str(requirements),
                    "-d",
                    str(destination),
                ],
            )

    def test_build_install_command_uses_local_folder_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            requirements = root / "requirements.txt"
            packages = root / "packages"
            command = build_install_command(
                requirements_file=requirements,
                packages_dir=packages,
                python_executable="python3",
            )

            self.assertEqual(
                command,
                [
                    "python3",
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    f"--find-links={packages}",
                    "-r",
                    str(requirements),
                ],
            )


if __name__ == "__main__":
    unittest.main()
