"""2026-10-20 watchdog checks 9-11 — pure helpers of saas/nexum-watchdog.py.

No frappe needed (the watchdog is a host script), so this also runs without a bench:
    python3 -m unittest my_branding.tests.test_watchdog_jobs     (from the repo root)
    bench --site <site> run-tests --module my_branding.tests.test_watchdog_jobs
"""
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import time
import types
import unittest
from unittest.mock import patch


def _load_watchdog():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "saas", "nexum-watchdog.py")
    if not os.path.exists(path):
        raise unittest.SkipTest("saas/nexum-watchdog.py not present")
    spec = importlib.util.spec_from_file_location("nexum_watchdog", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _job(freq, *statuses, method="app.jobs.thing"):
    """A probe `jobs` entry whose runs (newest first) have the given statuses."""
    runs = [[s, f"2026-10-20 1{i}:00:00", "ValueError: boom" if s == "Failed" else ""]
            for i, s in enumerate(statuses)]
    return {"method": method, "frequency": freq, "runs": runs}


class TestFailingJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wd = _load_watchdog()

    def failing(self, *jobs):
        return [f[0] for f in self.wd.failing_jobs(list(jobs))]

    def test_hourly_needs_three_in_a_row(self):
        self.assertEqual(self.failing(_job("Hourly", "Failed", "Failed", "Failed")), ["app.jobs.thing"])
        self.assertEqual(self.failing(_job("Hourly Long", "Failed", "Failed", "Complete")), [])
        self.assertEqual(self.failing(_job("Hourly Maintenance", "Failed", "Failed")), [])

    def test_complete_breaks_the_streak(self):
        self.assertEqual(self.failing(_job("Hourly", "Failed", "Complete", "Failed")), [])
        self.assertEqual(self.failing(_job("Daily", "Complete", "Failed", "Failed")), [])

    def test_daily_or_slower_fails_on_newest_run(self):
        for freq in ("Daily", "Daily Long", "Daily Maintenance", "Weekly", "Weekly Long",
                     "Monthly", "Monthly Long"):
            self.assertEqual(self.failing(_job(freq, "Failed")), ["app.jobs.thing"], freq)
            self.assertEqual(self.failing(_job(freq, "Complete", "Failed")), [], freq)

    def test_no_runs_is_not_failing(self):
        self.assertEqual(self.failing(_job("Daily")), [])
        self.assertEqual(self.wd.failing_jobs([]), [])

    def test_reports_newest_run_time_and_line(self):
        (method, streak, when, line), = self.wd.failing_jobs([_job("Hourly", "Failed", "Failed", "Failed")])
        self.assertEqual((method, streak, when, line),
                         ("app.jobs.thing", 3, "2026-10-20 10:00:00", "ValueError: boom"))

    def test_only_failing_jobs_reported(self):
        got = self.failing(_job("Hourly", "Failed", "Failed", "Failed", method="a.bad"),
                           _job("Hourly", "Complete", method="a.good"),
                           _job("Daily", "Failed", method="b.bad"))
        self.assertEqual(got, ["a.bad", "b.bad"])

    def test_malformed_input_raises_not_healthy(self):
        for bad in ("ERR:boom", None, {"method": "x"}):
            with self.assertRaises(Exception):
                self.wd.failing_jobs(bad)
        for entry in ({"frequency": "Daily", "runs": []},                     # no method
                      {"method": "x", "frequency": "Daily", "runs": "nope"},   # runs not a list
                      {"method": "x", "frequency": "Daily", "runs": [["Failed", "t"]]},  # short row
                      {"method": "x", "frequency": "Daily", "runs": [["Scheduled", "t", ""]]}):
            with self.assertRaises(Exception, msg=str(entry)):
                self.wd.failing_jobs([entry])


class TestMaintenanceTracking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wd = _load_watchdog()

    def test_first_sighting_then_age(self):
        since = {}
        self.assertEqual(self.wd.track_maintenance(since, "a", True, 1000.0), 0.0)
        self.assertAlmostEqual(self.wd.track_maintenance(since, "a", True, 1000.0 + 3 * 3600), 3.0)

    def test_unreadable_or_deferred_keeps_first_sighting_and_age(self):
        since = {}
        self.wd.track_maintenance(since, "a", True, 1000.0)
        for unknown in (None, "ERR:x", 1):
            self.assertAlmostEqual(self.wd.track_maintenance(since, "a", unknown, 1000.0 + 3 * 3600), 3.0)
            self.assertEqual(since, {"a": 1000.0})
        self.assertAlmostEqual(self.wd.track_maintenance(since, "a", True, 1000.0 + 7200), 2.0)

    def test_unknown_without_a_sighting_is_not_maintenance(self):
        since = {}
        self.assertIsNone(self.wd.track_maintenance(since, "a", None, 1000.0))
        self.assertEqual(since, {})

    def test_only_explicit_off_clears(self):
        since = {}
        self.wd.track_maintenance(since, "a", True, 1000.0)
        self.assertIsNone(self.wd.track_maintenance(since, "a", False, 2000.0))
        self.assertEqual(since, {})
        self.assertEqual(self.wd.track_maintenance(since, "a", True, 9000.0), 0.0)  # clock restarts

    def test_sites_are_independent(self):
        since = {}
        self.wd.track_maintenance(since, "a", True, 1000.0)
        self.wd.track_maintenance(since, "b", False, 2000.0)
        self.assertEqual(since, {"a": 1000.0})


class TestDemoResetDeferral(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wd = _load_watchdog()

    CRON = "  4101   120 /bin/sh -c /opt/nexum/nexum-demo-reset.sh\n"
    BASH = "  4102   119 /bin/bash /opt/nexum/nexum-demo-reset.sh\n"

    def test_running_reset_detected(self):
        self.assertTrue(self.wd.demo_reset_in_progress(self.CRON).startswith("pid 4101"))
        self.assertTrue(self.wd.demo_reset_in_progress(self.BASH).startswith("pid 4102"))

    def test_wedged_reset_stops_deferring(self):
        self.assertIsNone(self.wd.demo_reset_in_progress(
            "  4102  %d /bin/bash /opt/nexum/nexum-demo-reset.sh\n" % (self.wd.DEMO_RESET_MAX_MIN * 60 + 1)))

    def test_editors_greps_and_other_scripts_ignored(self):
        for ln in ("  5 30 vim /opt/nexum/nexum-demo-reset.sh",
                   "  6 30 grep nexum-demo-reset.sh /var/log/syslog",
                   "  7 30 /bin/bash /opt/nexum/deploy.sh v16-prod-217",
                   "  8 30 /bin/bash /opt/nexum/nexum-demo-reset.sh.bak-20261010",
                   "garbage line", ""):
            self.assertIsNone(self.wd.demo_reset_in_progress(ln + "\n"), ln)

    PREVIOUS = (
        "SCHEDULED JOB FAILING {d}: x.y — fix it",
        "DEMO RECONCILE FAILED {d}: 'reconcile_demo_health sidebars failed' in Error Log (last 24h)",
        "PROBE FAILED {d}: watchdog could not read site health",
        "MAINTENANCE check FAILED {d}: the probe did not report maintenance_mode",
        "SITE https://{d}: HTTP Error 500",
        "B2 BACKUP {d}: newest object 30h old (limit 26h)",                 # re-derived every run
        "DEMO RESET: no successful reset within 26h (~/nexum-demo-reset.log) — {d} may be stale",
        "SCHEDULED JOB FAILING hq.nexumair.com: a.b — fix it",              # hq ran normally
    )

    def _previous(self):
        return [p.format(d=self.wd.DEMO_SITE) for p in self.PREVIOUS]

    def test_carry_forward_probe_problems_only(self):
        prev = self._previous()
        problems = [prev[0]]  # already present: no duplicate
        self.wd.carry_forward(prev, problems, self.wd.DEMO_SITE, self.wd.PROBE_PROBLEM_PREFIXES)
        self.assertEqual(sorted(problems), sorted(prev[:4]))

    def test_carry_forward_url_problems_only(self):
        prev = self._previous()
        problems = []
        self.wd.carry_forward(prev, problems, self.wd.DEMO_SITE, self.wd.URL_PROBLEM_PREFIXES)
        self.assertEqual(problems, [prev[4]])

    def test_carry_forward_keeps_alert_signature(self):
        demo = self.wd.DEMO_SITE
        last = sorted([f"SCHEDULER {demo}: disabled", "DISK /: 90% used (limit 85%)"])
        now = ["DISK /: 90% used (limit 85%)"]  # demo's probe deferred this run
        self.wd.carry_forward(last, now, demo, self.wd.PROBE_PROBLEM_PREFIXES)
        sig = lambda ps: hashlib.sha256("\n".join(sorted(ps)).encode()).hexdigest()  # noqa: E731
        self.assertEqual(sig(now), sig(last))

    def test_carry_forward_without_history(self):
        problems = []
        self.wd.carry_forward(None, problems, self.wd.DEMO_SITE, self.wd.PROBE_PROBLEM_PREFIXES)
        self.assertEqual(problems, [])


class TestProbeFindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wd = _load_watchdog()

    def healthy(self, site):
        p = {"maint": False, "jobs": []}
        if site == self.wd.DEMO_SITE:
            p["reconcile"] = []
        return p

    def test_healthy_probe_has_no_problems(self):
        for site in ("hq.nexumair.com", self.wd.DEMO_SITE):
            problems, summary = self.wd.probe_findings(site, self.healthy(site))
            self.assertEqual(problems, [], site)
            self.assertTrue(summary)

    def test_check_failed_texts_are_fixed_whatever_the_error(self):
        demo = self.wd.DEMO_SITE
        runs = []
        for err in ("ERR:(2013, 'Lost connection')", "ERR:timeout 9s", None):
            p = {"maint": err, "jobs": err, "reconcile": err}
            problems, summary = self.wd.probe_findings(demo, p)
            runs.append(sorted(problems))
            if err:
                self.assertTrue(any(err[:20] in s for s in summary), summary)  # details kept here
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        self.assertEqual(len(runs[0]), 3)  # maintenance, jobs and reconcile each report a failed check

    def test_malformed_jobs_payload_is_a_failed_check(self):
        problems, _ = self.wd.probe_findings("hq.nexumair.com", {"maint": False, "jobs": [{"method": 1}]})
        self.assertEqual(problems, ["JOB CHECK FAILED hq.nexumair.com: can't read Scheduled Job Log "
                                    "(details in the summary)"])

    def test_failing_job_problem_names_site_and_method_only(self):
        job = _job("Daily", "Failed", method="drive.api.files.auto_delete_from_trash")
        a, _ = self.wd.probe_findings("hq.nexumair.com", {"maint": False, "jobs": [job]})
        job["runs"][0][1], job["runs"][0][2] = "2026-10-21 00:00:00", "OtherError: changed"
        b, _ = self.wd.probe_findings("hq.nexumair.com", {"maint": False, "jobs": [job]})
        self.assertEqual(a, b)
        self.assertIn("drive.api.files.auto_delete_from_trash", a[0])


class _FakeRun:
    """subprocess.run stand-in for main(): every external command answers healthy except
    the per-site probes, which come from `probes` (None = no WDPROBE line)."""

    def __init__(self, wd, probes):
        self.wd, self.probes = wd, probes

    def __call__(self, args, input=None, **kw):
        out = ""
        if args[:2] == ["systemctl", "is-active"]:
            out = "active\n"
        elif args[0] == "df":
            out = "Use%\n 34%\n"
        elif args[:2] == ["docker", "ps"]:
            out = "\n".join(self.wd.CONTAINERS)
        elif "console" in args:
            probe = self.probes.get(args[args.index("--site") + 1])
            out = "WDPROBE " + json.dumps(probe) if probe is not None else "Traceback: no site"
        elif "execute" in args:
            out = "[]"
        return types.SimpleNamespace(stdout=out, stderr="", returncode=0)


class TestMainOrchestration(unittest.TestCase):
    """main() end to end with every side effect mocked (no email, no docker, no heal)."""

    HQ, SBL = "hq.nexumair.com", "sbl.nexumair.com"

    @classmethod
    def setUpClass(cls):
        cls.wd = _load_watchdog()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tsv = os.path.join(self.tmp, "tenants.tsv")
        with open(self.tsv, "w") as fh:
            for site in (self.SBL, self.wd.DEMO_SITE):
                fh.write(f"x\t{site}\towner@example.com\tbusiness\tactive\n")
        self.state_path = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def probe(self, site, **over):
        p = {"sched": True, "setup": True, "stuck": 0, "maint": False, "jobs": []}
        if site == self.HQ:
            p["billing"] = []
        if site == self.wd.DEMO_SITE:
            p["reconcile"] = []
        p.update(over)
        return p

    def run_main(self, probes=None, reset=lambda n: None, stale=(), deploy=None, state=None):
        """Run main(); `reset(n)` answers the n-th demo_reset_in_progress() call (0-based).
        Returns (problems saved in state, heal calls, demo_reset call count, state)."""
        probes = {s: self.probe(s) for s in (self.HQ, self.SBL, self.wd.DEMO_SITE)} | (probes or {})
        if state is not None:
            with open(self.state_path, "w") as fh:
                json.dump(state, fh)
        calls, heals = [], []

        def fake_reset(*a):
            calls.append(1)
            return reset(len(calls) - 1)

        resp = types.SimpleNamespace(status=200)
        wd = self.wd
        with patch.object(wd, "TSV_PATH", self.tsv), patch.object(wd, "STATE_PATH", self.state_path), \
                patch.object(wd.subprocess, "run", _FakeRun(wd, probes)), \
                patch.object(wd.urllib.request, "urlopen", lambda *a, **k: resp), \
                patch.object(wd, "log_fresh", lambda *a: (True, "ok (1h ago)")), \
                patch.object(wd, "newest_b2_age_h", lambda *a: 1.0), \
                patch.object(wd, "unit_last_run", lambda *a: ("success", "0")), \
                patch.object(wd, "asset_fresh", lambda s: s not in stale), \
                patch.object(wd, "deploy_in_progress", lambda: deploy), \
                patch.object(wd, "demo_reset_in_progress", fake_reset), \
                patch.object(wd, "heal_stale_assets", lambda: heals.append(1)), \
                patch.object(wd, "unhealed", lambda sites: []), \
                patch.object(wd, "load_config", lambda: {}), \
                patch.object(wd, "send_email", lambda *a: None), \
                patch.object(wd, "log", lambda *a: None), \
                patch.object(wd.time, "sleep", lambda *a: None):
            wd.main()
        with open(self.state_path) as fh:
            saved = json.load(fh)
        return saved["last_problems"], heals, len(calls), saved

    def test_healthy_run_is_green(self):
        problems, heals, _, _ = self.run_main()
        self.assertEqual(problems, [])
        self.assertEqual(heals, [])

    def test_reset_starting_mid_run_holds_heal_but_alerts_other_sites(self):
        # reset not running at the demo probe (call 0), running from the URL check on
        problems, heals, n, _ = self.run_main(reset=lambda n: None if n == 0 else "pid 7: bash reset",
                                              stale=(self.HQ, self.wd.DEMO_SITE))
        self.assertEqual(n, 3)  # rechecked at the demo probe, the demo URL and right before the heal
        self.assertEqual(heals, [])
        self.assertIn("STALE ASSETS (auto-heal held during the demo reset, retried next run): "
                      + self.HQ, problems)

    def test_deploy_still_skips_heal_silently(self):
        problems, heals, _, _ = self.run_main(stale=(self.HQ,), deploy="pid 9: bash deploy.sh")
        self.assertEqual(heals, [])
        self.assertFalse([p for p in problems if p.startswith("STALE")])

    def test_stale_without_reset_or_deploy_heals(self):
        _, heals, _, _ = self.run_main(stale=(self.HQ,))
        self.assertEqual(heals, [1])

    def test_maintenance_alert_survives_an_unreadable_probe(self):
        old = {"maint_since": {self.HQ: time.time() - 3 * 3600}}
        for broken in ({self.HQ: self.probe(self.HQ, maint="ERR:x")}, {self.HQ: None}):
            problems, _, _, saved = self.run_main(probes=broken, state=dict(old))
            self.assertTrue(any(p.startswith(f"MAINTENANCE MODE {self.HQ}") for p in problems), problems)
            self.assertIn(self.HQ, saved["maint_since"])
        self.assertTrue(any(p.startswith(f"MAINTENANCE check FAILED {self.HQ}") for p in
                            self.run_main(probes={self.HQ: self.probe(self.HQ, maint="ERR:x")},
                                          state=dict(old))[0]))

    def test_explicit_off_clears_maintenance(self):
        problems, _, _, saved = self.run_main(state={"maint_since": {self.HQ: time.time() - 3 * 3600}})
        self.assertFalse([p for p in problems if p.startswith("MAINTENANCE")])
        self.assertEqual(saved["maint_since"], {})

    def test_failed_check_signature_stable_across_errors(self):
        a = self.run_main(probes={self.HQ: self.probe(self.HQ, jobs="ERR:(2013, 'Lost connection')")})[0]
        b = self.run_main(probes={self.HQ: self.probe(self.HQ, jobs="ERR:read timeout")})[0]
        self.assertEqual(a, b)
        self.assertEqual(len(a), 1)

    def test_deferred_probe_carries_previous_demo_problems(self):
        demo = self.wd.DEMO_SITE
        prev = [f"SCHEDULED JOB FAILING {demo}: x.y — fix it", f"SITE https://{demo}: HTTP Error 500"]
        problems, heals, _, _ = self.run_main(reset=lambda n: "pid 7: bash reset",
                                              state={"last_problems": prev})
        self.assertEqual(sorted(problems), sorted(prev))
        self.assertEqual(heals, [])

    def test_url_only_deferral_does_not_resurrect_probe_problems(self):
        demo = self.wd.DEMO_SITE
        prev = [f"SCHEDULED JOB FAILING {demo}: x.y — fix it", f"SITE https://{demo}: HTTP Error 500"]
        problems, _, _, _ = self.run_main(reset=lambda n: None if n == 0 else "pid 7: bash reset",
                                          state={"last_problems": prev})
        self.assertEqual(problems, [prev[1]])  # demo's probe ran healthy; only its URL was deferred


class TestProbeSource(unittest.TestCase):
    def test_probe_compiles(self):
        # the probe is a string exec'd inside `bench console`; a syntax slip would only show
        # on the host as PROBE FAILED on every site
        wd = _load_watchdog()
        compile(wd.PROBE_SRC, "PROBE_SRC", "exec")
        for field in ('out["jobs"]', 'out["maint"]', 'out["reconcile"]'):
            self.assertIn(field, wd.PROBE_SRC)


if __name__ == "__main__":
    unittest.main()
