#!/usr/bin/env python3
"""Stage fix: GrowthViewTransformer KeyError on columnar financial reports.

Symptom (prod, emeaboutique.nexumair.com, 2026-06-29):
    Balance Sheet, report_template="Horizontal Balance Sheet (Columnar)",
    selected_view="Growth"  ->  builtins.KeyError: 'dec_2026'

Cause:
    GrowthViewTransformer.transform() looked up the BARE period key
    (e.g. 'dec_2026'). That key only exists on single-segment (vertical)
    templates. Columnar / multi-segment templates store values under
    seg_<n>_<period> keys, so the bare lookup raised KeyError and crashed
    the report. Growth view is the ONLY view that runs this transformer
    (financial_report_engine.py: apply_view_transformation, gated on
    selected_view == "Growth"), so every other view was unaffected.

Fix:
    Iterate the real segment prefixes from row_data["_segment_info"] and
    skip any key not present. Behaviour for vertical (single-segment)
    templates is unchanged.

Usage (run inside the derived image build, against the baked erpnext app):
    python3 apply.py \
      /home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/\
financial_report_template/financial_report_engine.py

Idempotent (re-running is a no-op) and verifies the result compiles.
"""
import sys
import py_compile

MARKER = "PATCHED (NexumAir): segment-aware growth lookup"

NEW_METHOD = '''\tdef transform(self) -> None:
\t\t# PATCHED (NexumAir): segment-aware growth lookup.
\t\t# Vertical (single-segment) templates store values under BARE period keys;
\t\t# columnar / multi-segment templates store them under seg_<n>_<period> keys.
\t\t# Try the bare prefix AND every segment prefix, skipping keys that aren't
\t\t# present and non-numeric cells (empty/ragged segments store ""), so both
\t\t# layouts work and neither crashes (upstream bare-key lookup raised KeyError
\t\t# on columnar templates, e.g. 'dec_2026').
\t\tfor row_data in self.formatted_rows:
\t\t\tif row_data.get("is_blank_line"):
\t\t\t\tcontinue

\t\t\tseg_info = row_data.get("_segment_info") or {}
\t\t\ttotal_segments = seg_info.get("total_segments") or 0
\t\t\tprefixes = [""] + [f"seg_{n}_" for n in range(total_segments)]

\t\t\ttransformed_values = {}
\t\t\tfor prefix in prefixes:
\t\t\t\tfor i in range(len(self.period_list)):
\t\t\t\t\tcurrent_key = prefix + self.period_list[i]["key"]
\t\t\t\t\tif current_key not in row_data:
\t\t\t\t\t\tcontinue

\t\t\t\t\tcurrent_value = row_data[current_key]
\t\t\t\t\tif i == 0:
\t\t\t\t\t\ttransformed_values[current_key] = current_value
\t\t\t\t\t\tcontinue

\t\t\t\t\tprevious_value = row_data.get(prefix + self.period_list[i - 1]["key"], 0)
\t\t\t\t\tif not isinstance(current_value, (int, float)) or not isinstance(
\t\t\t\t\t\tprevious_value, (int, float)
\t\t\t\t\t):
\t\t\t\t\t\tcontinue

\t\t\t\t\ttransformed_values[current_key] = self._calculate_growth(
\t\t\t\t\t\tprevious_value, current_value
\t\t\t\t\t)

\t\t\trow_data.update(transformed_values)
'''

ANCHOR_START = "\tdef transform(self) -> None:"
ANCHOR_END = "\n\tdef _calculate_growth"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 apply.py <path-to-financial_report_engine.py>")
        return 2
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    if MARKER in src:
        print("already patched, nothing to do:", path)
        return 0

    try:
        start = src.index(ANCHOR_START)
        end = src.index(ANCHOR_END, start) + 1  # keep the newline before _calculate_growth
    except ValueError:
        print("ERROR: anchors not found - upstream code shape changed; re-review before applying.")
        return 1

    patched = src[:start] + NEW_METHOD + "\n" + src[end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)

    py_compile.compile(path, doraise=True)
    print("patched + compiles OK:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
