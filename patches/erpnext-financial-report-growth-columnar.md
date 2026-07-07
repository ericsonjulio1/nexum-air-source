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
`financial_report_growth_columnar.py` in this directory is the idempotent,
anchor-guarded patcher (no-op if already patched via the `PATCHED (NexumAir)`
marker; fails the build loudly if the upstream code shape moves). The image build
runs it against the baked erpnext app. Drop it once upstream fixes the columnar
Growth lookup.
