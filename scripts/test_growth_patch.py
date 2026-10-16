"""Fail-closed source patching regressions; no Frappe database required."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PATCH = Path(__file__).parents[1] / "patches/financial_report_growth_columnar.py"
ORIGINAL = """	def transform(self) -> None:
		for row_data in self.formatted_rows:
			if row_data.get("is_blank_line"):
				continue

			transformed_values = {}
			for i in range(len(self.period_list)):
				current_period = self.period_list[i]["key"]

				current_value = row_data[current_period]
				previous_value = row_data[self.period_list[i - 1]["key"]] if i != 0 else 0

				if i == 0:
					transformed_values[current_period] = current_value
				else:
					growth_percent = self._calculate_growth(previous_value, current_value)
					transformed_values[current_period] = growth_percent

			row_data.update(transformed_values)
"""
PREFIX = "class EarlierTransformer:\n\tdef transform(self) -> None:\n\t\tself.keep_me = True\n\n"
SUFFIX = "\n\tdef _calculate_growth(self, old, new):\n\t\treturn (new-old)/old*100 if old else 0\n"


class GrowthPatchTest(unittest.TestCase):
    def invoke(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "engine.py"
            path.write_text(source)
            result = subprocess.run([sys.executable, "-O", str(PATCH), str(path)],
                                    capture_output=True, text=True)
            return result.returncode, path.read_text()

    def test_earlier_transformer_preserved_and_only_growth_changed(self):
        source = PREFIX + "class GrowthViewTransformer:\n" + ORIGINAL + SUFFIX
        code, result = self.invoke(source)
        self.assertEqual(code, 0)
        self.assertTrue(result.startswith(PREFIX))
        self.assertIn("class GrowthViewTransformer:", result)
        self.assertIn("PATCHED (NexumAir)", result)
        self.assertEqual(self.invoke(result), (0, result))

    def test_unknown_growth_body_is_rejected_without_writing(self):
        source = PREFIX + "class GrowthViewTransformer:\n\tdef transform(self) -> None:\n\t\tself.unreviewed = 42\n" + SUFFIX
        code, result = self.invoke(source)
        self.assertNotEqual(code, 0)
        self.assertEqual(result, source)

    def test_upstream_markers_outside_growth_do_not_bypass_review(self):
        source = """class Other:
	def _transform_segmented_row(self, row_data: dict):
		return row_data.get("segment_values")
	def _compute_growth_values(self, source: dict) -> dict:
		return source

class GrowthViewTransformer:
	def transform(self) -> None:
		self.unreviewed = 42
""" + SUFFIX
        code, result = self.invoke(source)
        self.assertNotEqual(code, 0)
        self.assertEqual(result, source)


if __name__ == "__main__":
    unittest.main()
