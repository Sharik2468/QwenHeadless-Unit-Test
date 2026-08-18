from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from testgen_shared.test_quality import (
    has_no_tests_matched,
    low_value_test_reason,
    resolve_reported_test_paths,
)


class TestQualityGuardrailsTests(unittest.TestCase):
    def test_has_no_tests_matched_detects_russian_message(self) -> None:
        self.assertTrue(
            has_no_tests_matched(
                "Нет тестов, соответствующих указанному фильтру тестовых случаев \"FullyQualifiedName~AdornerLayer\""
            )
        )

    def test_low_value_test_reason_flags_resource_key_only_tests(self) -> None:
        file_text = """
public void AdornerLayer_TypedTokens_S350BorderRadius_Correct_Key()
{
    var token = Focus.s350_outer_border_radius;
    Assert.Equal("focus.350.outer.border-radius", token.ResourceKey);
}
"""
        reason = low_value_test_reason(file_text)
        self.assertIsNotNone(reason)
        self.assertIn("ResourceKey", reason)

    def test_low_value_test_reason_allows_runtime_headless_checks(self) -> None:
        file_text = """
await Dispatcher.UIThread.InvokeAsync(async () =>
{
    var btn = CreateButton();
    _window.Content = btn;
    _window.Show();
    await WaitForLayoutAndRender();
    Assert.Equal(expected, btn.Height);
});
"""
        self.assertIsNone(low_value_test_reason(file_text))

    def test_resolve_reported_test_paths_can_find_by_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit_root = root / "unit"
            unit_root.mkdir()
            test_file = unit_root / "AdornerLayerTests.cs"
            test_file.write_text("test", encoding="utf-8")

            resolved = resolve_reported_test_paths(
                reported_paths=["AdornerLayerTests.cs"],
                repo_root=root,
                search_roots=[unit_root],
            )

            self.assertEqual(resolved, [test_file])


if __name__ == "__main__":
    unittest.main()
