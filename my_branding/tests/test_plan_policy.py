"""The plan policy contract is shared by Frappe and the real shell adapter."""
from pathlib import Path
import subprocess
import unittest

from my_branding import hooks
from my_branding.plan_policy import AUTO_APPROVE_PLANS, CAPPED_DOCTYPES, CHECKOUT_PRICES_PHP, canonical_plan, infer_plan, policy


class PlanPolicyTests(unittest.TestCase):
    def test_existing_prices_and_approval_rules_are_preserved(self):
        self.assertEqual(CHECKOUT_PRICES_PHP, {"Essentials": 2790, "Business": 8490, "Enterprise": 22740})
        self.assertEqual(AUTO_APPROVE_PLANS, {"free", "starter", "essentials", "business"})
        self.assertEqual(canonical_plan(" Free Tier "), "free")
        self.assertEqual(canonical_plan("Essentials"), "starter")
        self.assertIsNone(canonical_plan("unknown"))

    def test_every_capped_doctype_has_an_enforcement_hook(self):
        self.assertEqual(set(CAPPED_DOCTYPES), set(policy("free")["doc_caps"]))
        for doctype in CAPPED_DOCTYPES:
            self.assertIn("my_branding.doc_caps.enforce_doc_cap", hooks.doc_events[doctype]["before_insert"])

    def test_snapshots_do_not_modify_canonical_policy(self):
        policy("free")["doc_caps"].clear()
        self.assertEqual(policy("free")["doc_caps"]["Customer"], 10)

    def test_legacy_inference_is_preserved(self):
        self.assertEqual(infer_plan(["frappe", "erpnext"]), "free")
        self.assertEqual(infer_plan(["print_designer"]), "starter")
        self.assertEqual(infer_plan(["helpdesk"]), "business")
        self.assertEqual(infer_plan(["drive"]), "enterprise")

    def test_shell_adapter_matches_policy_and_rejects_unknown_plans(self):
        adapter = Path(__file__).parents[2] / "saas/plan-apps.sh"
        if not adapter.exists():
            self.skipTest("Operational adapter is absent from the public source mirror")
        for slug in ("free", "starter", "business", "enterprise"):
            result = subprocess.run(["bash", "-c", '. "$1"; plan_apps "$2"; quota_gb "$2"', "_", str(adapter), slug], text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.splitlines(), [" ".join(policy(slug)["apps"]), str(policy(slug)["quota_gb"])])
        result = subprocess.run(["bash", "-c", '. "$1"; quota_gb unknown', "_", str(adapter)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        for alias in ("essentials", "free tier", "STARTER"):
            result = subprocess.run(["bash", "-c", '. "$1"; plan_apps "$2"', "_", str(adapter), alias], capture_output=True)
            self.assertNotEqual(result.returncode, 0, "Host operations require canonical IDs before mutations")
