# Patch: erpnext Financial Report — columnar Growth-view KeyError fix

**App:** erpnext (GPLv3) · **File:** `erpnext/accounts/doctype/financial_report_template/financial_report_engine.py`
**Type:** bug fix (not security) · **First shipped:** image `v16-prod-80` (2026-06-30)

## Problem
`GrowthViewTransformer.transform()` looked up the bare period key (e.g. `dec_2026`).
That key exists only on single-segment (vertical) templates; columnar /
multi-segment templates (e.g. "Horizontal Balance Sheet (Columnar)") store values
under `seg_<n>_<period>` keys, so the bare lookup raised `KeyError` and crashed the
report in the **Growth** view. Growth is the only view that runs this transformer,
so all other views were unaffected.

## Our modification
Iterate the real segment prefixes from `row_data["_segment_info"]`, try the bare
prefix and every segment prefix, and skip keys that aren't present / non-numeric
cells. Behaviour for vertical (single-segment) templates is unchanged.

## How it is applied
`financial_report_growth_columnar.py` uses the Python AST to locate only
`GrowthViewTransformer.transform`, then requires the exact reviewed legacy method
hash before replacing it. It preserves all other transformers, compiles before
writing, and rejects unknown method bodies even under `python -O`. A patched
method must match the complete replacement; a marker alone is insufficient.

The current ERPNext 16.50.0 runtime already contains the upstream segment-aware
implementation. Its source remains byte-for-byte unchanged by this patcher.
The v215 recipe inherits that fixed runtime and does not run this historical
patch. The patcher is retained for documented older builds; its regression tests
cover unrelated transformers, unknown source, misleading markers and idempotence.
